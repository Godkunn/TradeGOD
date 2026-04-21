# engines/binance_sniper.py
# ============================================================
# ENGINE — BINANCE SNIPER
# ============================================================
# Connects to Binance (Testnet or Live), fetches data,
# feeds it to Alpha → Beta → Risk Overlord pipeline,
# then executes orders and logs every outcome.
# ============================================================

import time
import logging
import csv
import os
import requests
from datetime import datetime
from core.telegram_ui import TelegramUI
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException

from config.settings import (
    BINANCE_API_KEY, BINANCE_SECRET_KEY, BINANCE_TESTNET,
    SYMBOLS, TIMEFRAME, ITF, HTF, SPOT_MODE_ONLY,
    CAPITAL_USDT,
    CANDLES_FOR_ALPHA, CANDLES_FOR_BETA,
    LOOP_SLEEP_VOID, LOOP_SLEEP_STALK, COOLDOWN_AFTER_TRADE,
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    LOG_FILE, TRADE_FILE,
)
from core.alpha_filter  import AlphaFilter
from core.beta_filter   import BetaFilter
from core.risk_overlord import RiskOverlord

# ── Logging setup ────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
os.makedirs("docs", exist_ok=True)

import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("TradeGOD.BinanceSniper")

# Minimum Beta confidence score to execute a trade (out of 100)
MIN_CONFIDENCE = 40


# ─────────────────────────────────────────────────────────────
class BinanceSniper:

    def __init__(self):
        logger.info("═" * 60)
        logger.info("  TradeGOD System — Binance Sniper STARTING UP")
        logger.info(f"  Mode     : {'TESTNET ⚠️' if BINANCE_TESTNET else 'LIVE 🔴'}")
        logger.info(f"  Symbols  : {', '.join(SYMBOLS)}")
        logger.info(f"  Capital  : ${CAPITAL_USDT}")
        logger.info("═" * 60)

        self.client = Client(
            BINANCE_API_KEY,
            BINANCE_SECRET_KEY,
            testnet=BINANCE_TESTNET,
        )

        self.risk = RiskOverlord(capital_usdt=CAPITAL_USDT)
        self._active_order = None   # track open position

        # 🔥 PERFORMANCE TRACKING (ADD THIS)
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.pnl = 0.0

        # Cache symbol info
        self._step_sizes = {}
        for sym in SYMBOLS:
            self._step_sizes[sym] = self._fetch_step_size(sym)
        
        # --- NEW TELEGRAM UI INITIALIZATION ---
        self.tg_ui = TelegramUI(self)
        # --------------------------------------

        self._notify(f"🤖 TradeGOD online | {len(SYMBOLS)} Pairs | "
                     f"{'TESTNET' if BINANCE_TESTNET else 'LIVE'}")

    # ── Exchange helpers ──────────────────────────────────────
    def _fetch_step_size(self, symbol: str) -> float:
        try:
            info = self.client.get_symbol_info(symbol)
            for f in info["filters"]:
                if f["filterType"] == "LOT_SIZE":
                    return float(f["stepSize"])
        except Exception:
            pass
        return 0.00001

    def _get_klines(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        raw = self.client.get_klines(
            symbol=symbol, interval=interval, limit=limit
        )
        df = pd.DataFrame(raw, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "num_trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df

    def _get_balance(self) -> float:
        """Returns free USDT balance."""
        try:
            bal = self.client.get_asset_balance(asset="USDT")
            return float(bal["free"])
        except Exception:
            return self.risk.capital

    def _get_price(self, symbol: str) -> float:
        ticker = self.client.get_symbol_ticker(symbol=symbol)
        return float(ticker["price"])

    def _get_base_asset_balance(self, symbol: str) -> float:
        """Returns free balance of base asset (e.g. BTC for BTCUSDT)."""
        base = symbol.replace("USDT", "")
        try:
            bal = self.client.get_asset_balance(asset=base)
            return float(bal["free"])
        except Exception:
            return 0.0

    def _get_average_entry_price(self, symbol: str) -> float:
        """Returns the approximate entry price using the last buy order on the symbol."""
        try:
            trades = self.client.get_my_trades(symbol=symbol, limit=10)
            for t in reversed(trades):
                if t["isBuyer"]:
                    return float(t["price"])
        except Exception:
            pass
        return 0.0

    # ── Telegram alerts ──────────────────────────────────────
    def _notify(self, message: str):
        logger.info(f"📢 {message}")
        if hasattr(self, 'tg_ui') and self.tg_ui.active:
            self.tg_ui.send_alert(message)

    # ── Trade logging ─────────────────────────────────────────
    def _log_trade(self, record: dict):
        write_header = not os.path.exists(TRADE_FILE)
        with open(TRADE_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=record.keys())
            if write_header:
                writer.writeheader()
            writer.writerow(record)

    # ── Order execution ───────────────────────────────────────
    def _place_market_order(self, symbol: str, direction: str, quantity: float) -> dict | None:
        qty_str = f"{quantity:.8f}".rstrip('0').rstrip('.')
        try:
            if direction == "BUY":
                order = self.client.order_market_buy(
                    symbol=symbol, quantity=qty_str
                )
            else:
                order = self.client.order_market_sell(
                    symbol=symbol, quantity=qty_str
                )
            return order
        except BinanceAPIException as e:
            logger.error(f"Order failed: {e}")
            return None

    def _place_oco_order(
        self,
        symbol: str,
        direction: str,
        quantity:  float,
        stop_loss: float,
        take_profit: float,
    ) -> dict | None:
        """
        Places an OCO (One-Cancels-Other) order for automatic
        stop-loss + take-profit management.
        For a BUY entry, we place SELL OCO.
        For a SELL entry, we place BUY OCO (futures only; for spot we just set SL).
        """
        qty_str = f"{quantity:.8f}".rstrip('0').rstrip('.')
        try:
            if direction == "BUY":
                order = self.client.order_oco_sell(
                    symbol       = symbol,
                    quantity     = qty_str,
                    price        = str(round(take_profit, 2)),
                    stopPrice    = str(round(stop_loss, 2)),
                    stopLimitPrice=str(round(stop_loss * 0.999, 2)),
                    stopLimitTimeInForce="GTC",
                )
                return order
        except BinanceAPIException as e:
            logger.warning(f"OCO order failed (may need manual SL): {e}")
        return None

    # ─────────────────────────────────────────────────────────
    # MAIN PATROL LOOP
    # ─────────────────────────────────────────────────────────
    def run(self):
        logger.info("🔭 Overlord Patrolling — press Ctrl+C to stop")

        while True:
            try:
                self._patrol_cycle()
            except KeyboardInterrupt:
                logger.info("🛑 Manual shutdown. Goodbye.")
                self._notify("🛑 TradeGOD manually stopped.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in patrol: {e}", exc_info=True)
                time.sleep(60)

    def _patrol_cycle(self):
        ts = datetime.utcnow().strftime("%H:%M:%S UTC")

        # ── Sync capital ──────────────────────────────────────
        balance = self._get_balance()
        self.risk.update_capital(balance)

        # --- PATCH 5: POSITION TRACKING (BLOCK OVERLAPPING TRADES) ---
        # If we currently hold more than $5 of the base asset of ANY symbol, skip scanning.
        active_position = False
        for sym in SYMBOLS:
            base_asset = sym.replace("USDT", "")
            try:
                base_bal = float(self.client.get_asset_balance(asset=base_asset)["free"])
                current_price = self._get_price(sym)
                # FIX: Binance testnet gives default 1 BTC, so we only block if total_trades > 0
                if self.total_trades > 0 and (base_bal * current_price) > 5.0:
                    logger.info(f"[{ts}] ⏳ Position Active ({base_bal:.4f} {base_asset}). Waiting for SL/TP exit...")
                    active_position = True
                    break
            except Exception:
                pass
        
        if active_position:
            time.sleep(LOOP_SLEEP_STALK)
            return

        # ── MULTI-MARKET SCAN ─────────────────────────────────
        valid_setups = []
        for sym in SYMBOLS:
            # Render Free Tier / GitHub Action API Safeguard
            time.sleep(1.5)
            
            # ── LAYER 1 : ALPHA FILTER (HTF 1H) ─────────────
            try:
                htf_df     = self._get_klines(sym, HTF, CANDLES_FOR_ALPHA)
                alpha      = AlphaFilter(htf_df)
                alpha_out  = alpha.verdict()
            except Exception as e:
                logger.warning(f"[{sym}] Alpha init error: {e}")
                continue

            if not alpha_out["zone_active"]:
                continue

            # ── LAYER 1.5 : INTERMEDIATE MOMENTUM (ITF 15m) ─────────────
            try:
                itf_df   = self._get_klines(sym, ITF, 50)
                beta_itf = BetaFilter(itf_df)
                itf_rsi  = beta_itf.rsi_zone()
            except Exception as e:
                itf_rsi = "NEUTRAL"

            # ── LAYER 2 : BETA FILTER (TIMEFRAME 5m) ──────────────
            try:
                ltf_df   = self._get_klines(sym, TIMEFRAME, max(CANDLES_FOR_BETA, 50))
                beta     = BetaFilter(ltf_df)
                beta_out = beta.verdict(boundary=alpha_out["boundary"], alpha_vector=alpha_out["vector"])
            except Exception as e:
                logger.warning(f"[{sym}] Beta error: {e}")
                continue

            # TREND AND SPOT ENFORCEMENT
            if alpha_out["vector"] == "BULL" and beta_out["direction"] == "SELL":
                beta_out["direction"] = "NONE"
            if alpha_out["vector"] == "BEAR" and beta_out["direction"] == "BUY":
                beta_out["direction"] = "NONE"
                
            # Block SELL if we are explicitly running in Spot Only Mode
            if SPOT_MODE_ONLY and beta_out["direction"] == "SELL":
                beta_out["direction"] = "NONE"

            if beta_out["direction"] != "NONE" and beta_out["confidence"] >= MIN_CONFIDENCE:
                setup = {
                    "symbol": sym,
                    "alpha_out": alpha_out,
                    "beta_out": beta_out
                }
                valid_setups.append(setup)
                logger.info(f"[{ts}] ✨ Valid setup on {sym}: Dir={beta_out['direction']} Conf={beta_out['confidence']}")

        if not valid_setups:
            logger.info(f"[{ts}] No active setups across {len(SYMBOLS)} pairs. Stalking...")
            time.sleep(LOOP_SLEEP_STALK)
            return

        # Choose the best setup based on confidence
        best_setup = max(valid_setups, key=lambda s: s["beta_out"]["confidence"])
        
        target_sym = best_setup["symbol"]
        alpha_out = best_setup["alpha_out"]
        beta_out = best_setup["beta_out"]

        logger.info(f"[{ts}] 🎯 Targeting {target_sym} with CONF={beta_out['confidence']}")

        # ── LAYER 3 : RISK OVERLORD ───────────────────────────
        try:
            entry = self._get_price(target_sym)
        except Exception as e:
            logger.error(f"Failed to get price for {target_sym}: {e}")
            time.sleep(LOOP_SLEEP_STALK)
            return

        risk_out  = self.risk.validate_and_size(
            entry     = entry,
            direction = beta_out["direction"],
            step_size = self._step_sizes.get(target_sym, 0.00001),
        )

        if not risk_out["approved"]:
            logger.warning(f"[{ts}] RISK for {target_sym}: Rejected — {risk_out['reason']}")
            time.sleep(LOOP_SLEEP_STALK)
            return

        # ── EXECUTE ───────────────────────────────────────────
        direction   = beta_out["direction"]
        quantity    = risk_out["quantity"]
        stop_loss   = risk_out["stop_loss"]
        take_profit = risk_out["take_profit"]

        logger.info(
            f"[{ts}] 🔥 EXECUTING {direction} on {target_sym} | "
            f"Qty={quantity} @ {entry} | "
            f"SL={stop_loss} | TP={take_profit} | "
            f"R:R={risk_out['rr_ratio']} | Risk=${risk_out['risk_usdt']}"
        )
        
        vector_emoji = "🐂 BULL" if alpha_out['vector'] == "BULL" else "🐻 BEAR"
        strategy_name = beta_out['patterns'][-1].replace("_", " ") if beta_out['patterns'] else "Reversal Zone"
        
        self._notify(
            f"🔥 <b>TRADE DIRECTIVE: {target_sym} (RECALIBRATED)</b>\n\n"
            f"<b>1. Market Status - Vector Alignment</b>\n"
            f"• Current State: Price is in a {vector_emoji} macro-vector.\n"
            f"• Technical Zone: Established <b>{alpha_out['boundary']}</b> matrix nearby.\n\n"
            
            f"<b>2. Momentum & Strength (Multi-TF)</b>\n"
            f"• 15m Momentum (ITF): <code>{itf_rsi}</code>\n"
            f"• Confluence: {beta_out['confidence']}% Beta Signature Match\n\n"
            
            f"<b>3. The Strategy (Target Lock)</b>\n"
            f"• Execution Math: The <b>{strategy_name}</b> sequence is active.\n"
            f"• Reward/Risk Matrix: {risk_out['rr_ratio']}x Output Potential\n\n"
            
            f"<b>4. ACTION PLAN</b>\n"
            f"• Position Cost: <code>${quantity * entry:,.2f}</code>\n"
            f"• <b>ENTRY POINT:</b> <code>{entry}</code>\n"
            f"• <b>STOP LOSS:</b> <code>{stop_loss}</code>\n"
            f"• <b>TAKE PROFIT:</b> <code>{take_profit}</code>\n"
            f"• <b>TRIGGER:</b> Wait for platform order-fill completion.\n"
            f"• <b>ACTION:</b> <b>{direction}</b>"
        )

        order = self._place_market_order(target_sym, direction, quantity)
        if not order:
            logger.error(f"Market order failed for {target_sym}. Skipping OCO.")
            time.sleep(LOOP_SLEEP_STALK)
            return

        fill_price = float(order["fills"][0]["price"])
        self.total_trades += 1
        logger.info(f"✅ Filled @ {fill_price}")

        # Place OCO for automatic SL + TP
        if direction == "BUY":
            self._place_oco_order(target_sym, direction, quantity, stop_loss, take_profit)

        # Log trade to CSV
        self._log_trade({
            "datetime":    datetime.utcnow().isoformat(),
            "symbol":      target_sym,
            "direction":   direction,
            "entry":       fill_price,
            "stop_loss":   stop_loss,
            "take_profit": take_profit,
            "quantity":    quantity,
            "risk_usdt":   risk_out["risk_usdt"],
            "rr_ratio":    risk_out["rr_ratio"],
            "confidence":  beta_out["confidence"],
            "patterns":    "|".join(beta_out["patterns"]),
            "vector":      alpha_out["vector"],
            "boundary":    alpha_out["boundary"],
            "rsi":         beta_out["rsi"],
        })

        # Post-trade cooldown (15 min)
        logger.info(f"🧘 Cooldown {COOLDOWN_AFTER_TRADE}s after trade.")
        time.sleep(COOLDOWN_AFTER_TRADE)

        try:
            current_price = self._get_price(target_sym)
        except Exception:
            current_price = fill_price

        if direction == "BUY":
            trade_pnl = (current_price - fill_price) * quantity
        else:
            trade_pnl = (fill_price - current_price) * quantity

        self.pnl += trade_pnl

        if trade_pnl > 0:
            self.wins += 1
        else:
            self.losses += 1

        logger.info(
            f"📊 STATS | Trades={self.total_trades} | Wins={self.wins} | "
            f"Losses={self.losses} | PnL={round(self.pnl, 4)} USDT"
        )