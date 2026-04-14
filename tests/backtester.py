# tests/backtester.py
# ============================================================
# OFFLINE BACKTESTER
# ============================================================
# Tests your Alpha + Beta doctrine against REAL historical data
# WITHOUT touching any real money.
#
# Usage:
#   python tests/backtester.py
#
# What it does:
#   1. Downloads historical OHLCV from Binance (free, no API key)
#   2. Walks forward bar by bar simulating the live bot
#   3. Prints a full performance report
# ============================================================

import sys
import os
import time
import logging

import pandas as pd
import numpy as np
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.alpha_filter  import AlphaFilter
from core.beta_filter   import BetaFilter
from core.risk_overlord import RiskOverlord
from config.settings    import (
    SYMBOL, STOP_LOSS_PCT, TAKE_PROFIT_PCT,
    RISK_PER_TRADE, MIN_CONFIDENCE,
    CANDLES_FOR_ALPHA, SR_PROXIMITY_PCT,
)

logging.basicConfig(level=logging.WARNING)


# ─────────────────────────────────────────────────────────────
# DATA FETCHER (no API key needed for public OHLCV)
# ─────────────────────────────────────────────────────────────
def fetch_binance_ohlcv(symbol: str, interval: str, limit: int = 1000) -> pd.DataFrame:
    """Fetches historical candles from Binance public API."""
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    raw = r.json()
    df = pd.DataFrame(raw, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "num_trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# BACKTESTER ENGINE
# ─────────────────────────────────────────────────────────────
class Backtester:

    def __init__(self, symbol: str, ltf: str = "5m", htf: str = "1h",
                 start_capital: float = 10.0):
        self.symbol        = symbol
        self.ltf           = ltf
        self.htf           = htf
        self.start_capital = start_capital
        self.capital       = start_capital
        self.trades        = []

    def run(self):
        print(f"\n{'═'*62}")
        print(f"  TradeGOD Backtester | {self.symbol} | Capital: ${self.start_capital}")
        print(f"  Timeframes: LTF={self.ltf}, HTF={self.htf}")
        print(f"{'═'*62}")
        print("  Downloading data from Binance...")

        # Download enough data for both timeframes
        ltf_df = fetch_binance_ohlcv(self.symbol, self.ltf, limit=1000)
        htf_df = fetch_binance_ohlcv(self.symbol, self.htf, limit=500)

        print(f"  LTF bars: {len(ltf_df)} | HTF bars: {len(htf_df)}")
        print(f"  Scanning for signals...\n")

        # Walk-forward simulation
        # We need at least CANDLES_FOR_ALPHA HTF bars and 50 LTF bars
        warmup = CANDLES_FOR_ALPHA
        total  = len(ltf_df)

        for i in range(warmup, total - 1):
            # Slice data up to current bar (no lookahead)
            ltf_slice = ltf_df.iloc[:i + 1].copy()
            current   = ltf_df.iloc[i]
            next_bar  = ltf_df.iloc[i + 1]

            # Match HTF bars up to current timestamp
            htf_slice = htf_df[htf_df["timestamp"] <= current["timestamp"]].copy()
            if len(htf_slice) < CANDLES_FOR_ALPHA:
                continue

            # ── ALPHA CHECK ──────────────────────────────────
            try:
                alpha     = AlphaFilter(htf_slice)
                alpha_out = alpha.verdict()
            except ValueError:
                continue

            if not alpha_out["zone_active"]:
                continue

            # ── BETA CHECK ───────────────────────────────────
            beta_slice = ltf_slice.tail(max(50, 50)).copy()
            try:
                beta     = BetaFilter(beta_slice)
                beta_out = beta.verdict(boundary=alpha_out["boundary"])
                
                # --- SPOT MODE ENFORCEMENT ---
                if beta_out["direction"] == "SELL":
                    beta_out["direction"] = "NONE"
                # -----------------------------
                
            except Exception:
                continue

            # ── RISK SIZE ────────────────────────────────────
            entry     = current["close"]
            direction = beta_out["direction"]

            if direction == "BUY":
                stop_loss   = entry * (1 - STOP_LOSS_PCT)
                take_profit = entry * (1 + TAKE_PROFIT_PCT)
            else:
                stop_loss   = entry * (1 + STOP_LOSS_PCT)
                take_profit = entry * (1 - TAKE_PROFIT_PCT)

            risk_amount   = self.capital * RISK_PER_TRADE
            risk_per_unit = abs(entry - stop_loss)
            if risk_per_unit <= 0:
                continue
            quantity = risk_amount / risk_per_unit

            # ── SIMULATE OUTCOME ─────────────────────────────
            # Check if next bar hits SL or TP first
            # (simplified: use next bar's high/low)
            hit_tp = False
            hit_sl = False

            if direction == "BUY":
                if next_bar["high"] >= take_profit:
                    hit_tp = True
                elif next_bar["low"] <= stop_loss:
                    hit_sl = True
            else:
                if next_bar["low"] <= take_profit:
                    hit_tp = True
                elif next_bar["high"] >= stop_loss:
                    hit_sl = True

            # --- PATCH 2: CONSERVATIVE INTRA-CANDLE LOGIC ---
            # If a single 5m candle is massive and hits BOTH your take-profit and stop-loss,
            # we MUST assume the stop-loss was hit first. Always assume the worst case.
            if hit_tp and hit_sl:
                hit_tp = False 
                hit_sl = True
            # ------------------------------------------------

            # Determine the raw exit price
            if not hit_tp and not hit_sl:
                exit_price = next_bar["close"]
            elif hit_tp:
                exit_price = take_profit
            else:
                exit_price = stop_loss

            raw_gross_pnl = (exit_price - entry) * quantity if direction == "BUY" else (entry - exit_price) * quantity

            # --- PATCH 3: THE TAX AND FEE DEDUCTION ---
            FEE_RATE = 0.001  # 0.1% Binance Spot Fee
            TDS_RATE = 0.01   # 1% Indian Crypto TDS (applied when selling)

            entry_fee = (entry * quantity) * FEE_RATE
            exit_fee  = (exit_price * quantity) * FEE_RATE
            
            # TDS is deducted on the SELL side.
            tds_tax = (exit_price * quantity) * TDS_RATE 

            # Calculate actual Net PNL after government and exchange take their cut
            pnl = raw_gross_pnl - entry_fee - exit_fee - tds_tax
            # ------------------------------------------

            self.capital += pnl

            self.trades.append({
                "timestamp":  current["timestamp"],
                "direction":  direction,
                "entry":      round(entry, 4),
                "exit_tp":    hit_tp,
                "exit_sl":    hit_sl,
                "pnl":        round(pnl, 6),
                "capital":    round(self.capital, 6),
                "confidence": beta_out["confidence"],
                "patterns":   "|".join(beta_out["patterns"]),
                "vector":     alpha_out["vector"],
                "boundary":   alpha_out["boundary"],
            })

        self._print_report()
        return self.trades

    # ── Report ────────────────────────────────────────────────
    def _print_report(self):
        if not self.trades:
            print("  ⚠️  No trades generated. Strategy too strict or not enough data.")
            return

        df = pd.DataFrame(self.trades)

        total_trades = len(df)
        wins         = df[df["pnl"] > 0]
        losses       = df[df["pnl"] <= 0]
        win_rate     = len(wins) / total_trades * 100

        total_pnl    = df["pnl"].sum()
        avg_win      = wins["pnl"].mean()  if len(wins)   > 0 else 0
        avg_loss     = losses["pnl"].mean() if len(losses) > 0 else 0
        best_trade   = df["pnl"].max()
        worst_trade  = df["pnl"].min()

        # Max drawdown
        capital_curve   = df["capital"].values
        peak            = np.maximum.accumulate(capital_curve)
        drawdown        = (capital_curve - peak) / peak * 100
        max_dd          = drawdown.min()

        # Profit factor
        gross_profit = wins["pnl"].sum()  if len(wins)   > 0 else 0
        gross_loss   = losses["pnl"].abs().sum() if len(losses) > 0 else 1
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else 0

        print(f"\n{'═'*62}")
        print(f"  📊 BACKTEST REPORT — {self.symbol}")
        print(f"{'═'*62}")
        print(f"  Start Capital   : ${self.start_capital:.4f}")
        print(f"  Final Capital   : ${self.capital:.4f}")
        print(f"  Net P&L         : ${total_pnl:.4f}  "
              f"({'▲' if total_pnl >= 0 else '▼'}"
              f"{total_pnl / self.start_capital * 100:.2f}%)")
        print(f"{'─'*62}")
        print(f"  Total Trades    : {total_trades}")
        print(f"  Wins / Losses   : {len(wins)} / {len(losses)}")
        print(f"  Win Rate        : {win_rate:.1f}%")
        print(f"  Avg Win         : ${avg_win:.6f}")
        print(f"  Avg Loss        : ${avg_loss:.6f}")
        print(f"  Best Trade      : ${best_trade:.6f}")
        print(f"  Worst Trade     : ${worst_trade:.6f}")
        print(f"{'─'*62}")
        print(f"  Profit Factor   : {profit_factor:.2f}  (>1.5 = good)")
        print(f"  Max Drawdown    : {max_dd:.2f}%")
        print(f"{'─'*62}")
        print(f"  Confidence avg  : {df['confidence'].mean():.1f}/100")
        print(f"{'═'*62}")

        # Pattern breakdown
        all_patterns = []
        for p in df["patterns"]:
            all_patterns.extend(p.split("|") if p else [])
        if all_patterns:
            from collections import Counter
            counts = Counter(all_patterns)
            print(f"\n  🧬 Pattern Frequency:")
            for pat, cnt in counts.most_common():
                print(f"     {pat:<30} : {cnt} times")

        print()

        # Save to CSV
        os.makedirs("docs", exist_ok=True)
        out_path = "docs/backtest_results.csv"
        df.to_csv(out_path, index=False)
        print(f"  💾 Full results saved → {out_path}\n")


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    bt = Backtester(
        symbol        = SYMBOL,
        ltf           = "5m",
        htf           = "1h",
        start_capital = float(os.getenv("CAPITAL_USDT", 10)),
    )
    bt.run()
