# core/beta_filter.py
# ============================================================
# LAYER 2 — BETA FILTER : The Execution Trigger
# ============================================================
# Asks: "Has the crowd been trapped? Is the exact moment NOW?"
# Scans 5m candles for:
#   - Rejection Wicks (Pin Bars / Hammer / Shooting Star)
#   - Engulfing Candles (Bullish / Bearish)
#   - False Breakout Traps
#   - RSI divergence confirmation
#   - Volume spike confirmation
# Output: signal dict with direction (BUY | SELL | NONE)
#         and confidence score 0–100
# ============================================================

import numpy as np
import pandas as pd
from config.settings import (
    CANDLES_FOR_BETA, REJECTION_WICK_RATIO
)


class BetaFilter:

    def __init__(self, df: pd.DataFrame):
        """
        Parameters
        ----------
        df : pd.DataFrame
            5-min OHLCV data (open, high, low, close, volume)
            Minimum CANDLES_FOR_BETA rows recommended.
        """
        self.df = df.copy().reset_index(drop=True)
        self._compute_candle_geometry()
        self._compute_rsi()
        self._compute_volume_metrics()

    # ── Private: geometry ────────────────────────────────────
    def _compute_candle_geometry(self):
        o, h, lo, c = (self.df["open"], self.df["high"],
                       self.df["low"],  self.df["close"])
        self.df["body"]        = (c - o).abs()
        self.df["total_range"] = (h - lo).clip(lower=0.000001)
        self.df["upper_wick"]  = h - pd.concat([o, c], axis=1).max(axis=1)
        self.df["lower_wick"]  = pd.concat([o, c], axis=1).min(axis=1) - lo
        self.df["is_bull"]     = c > o
        self.df["body_ratio"]  = self.df["body"] / self.df["total_range"]

    # ── Private: RSI(14) ─────────────────────────────────────
    def _compute_rsi(self, period=14):
        delta = self.df["close"].diff()
        gain  = delta.clip(lower=0)
        loss  = (-delta).clip(lower=0)
        avg_g = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_l = loss.ewm(com=period - 1, min_periods=period).mean()
        rs    = avg_g / avg_l.replace(0, np.nan)
        self.df["rsi"] = 100 - (100 / (1 + rs))

    # ── Private: volume ──────────────────────────────────────
    def _compute_volume_metrics(self, period=20):
        vol = self.df["volume"].astype(float)
        self.df["vol_ma"]    = vol.rolling(period).mean()
        self.df["vol_ratio"] = vol / self.df["vol_ma"].replace(0, np.nan)

    # ─────────────────────────────────────────────────────────
    # PATTERN DETECTORS  (return 1=bullish, -1=bearish, 0=none)
    # ─────────────────────────────────────────────────────────

    def detect_rejection_wick(self) -> int:
        """
        Pin Bar / Hammer / Shooting Star.
        A wick that is >= REJECTION_WICK_RATIO of total range
        with a small body → price violently rejected that level.
        """
        row = self.df.iloc[-1]
        rng = row["total_range"]
        if rng == 0:
            return 0

        # Bullish rejection (long lower wick → buyers overwhelmed sellers)
        if (row["lower_wick"] / rng >= REJECTION_WICK_RATIO and
                row["upper_wick"] < row["body"]):
            return 1

        # Bearish rejection (long upper wick → sellers overwhelmed buyers)
        if (row["upper_wick"] / rng >= REJECTION_WICK_RATIO and
                row["lower_wick"] < row["body"]):
            return -1

        return 0

    def detect_engulfing(self) -> int:
        """
        Classic Engulfing: current body FULLY swallows previous body
        AND direction flips. High-probability reversal signal.
        """
        if len(self.df) < 2:
            return 0
        c1 = self.df.iloc[-2]
        c2 = self.df.iloc[-1]

        # Bullish engulfing
        if (not c1["is_bull"] and c2["is_bull"] and
                c2["open"] <= c1["close"] and c2["close"] >= c1["open"]):
            return 1

        # Bearish engulfing
        if (c1["is_bull"] and not c2["is_bull"] and
                c2["open"] >= c1["close"] and c2["close"] <= c1["open"]):
            return -1

        return 0

    def detect_false_breakout(self, boundary: str) -> int:
        """
        False Breakout Trap:
        Price briefly breaks through a key level (wick through it)
        then snaps back inside → retail traders get trapped on the
        wrong side.

        Parameters
        ----------
        boundary : str  "SUPPORT" | "RESISTANCE"
        """
        if len(self.df) < 3:
            return 0

        window  = self.df.tail(50)
        r_high  = window["high"].max()
        s_low   = window["low"].min()
        c2      = self.df.iloc[-1]  # Current
        c1      = self.df.iloc[-2]  # Previous (the breakout candle)

        if boundary == "RESISTANCE":
            # Wick punched above resistance but closed back below
            if c1["high"] > r_high and c1["close"] < r_high:
                return -1  # Bearish trap

        if boundary == "SUPPORT":
            # Wick punched below support but closed back above
            if c1["low"] < s_low and c1["close"] > s_low:
                return 1   # Bullish trap

        return 0

    def detect_doji(self) -> bool:
        """
        Doji: body < 10% of total range → indecision.
        Can precede a big move. Used as a secondary flag, not primary.
        """
        row = self.df.iloc[-1]
        return row["body_ratio"] < 0.10

    # ─────────────────────────────────────────────────────────
    # CONFIRMATION CHECKS
    # ─────────────────────────────────────────────────────────

    def rsi_zone(self) -> str:
        """
        OVERSOLD  (<35) → bias BUY
        OVERBOUGHT(>65) → bias SELL
        NEUTRAL   (35-65) → no edge
        """
        val = self.df["rsi"].iloc[-1]
        if pd.isna(val):
            return "NEUTRAL"
        if val < 35:
            return "OVERSOLD"
        if val > 65:
            return "OVERBOUGHT"
        return "NEUTRAL"

    def volume_spike(self, min_ratio: float = 1.5) -> bool:
        """
        Returns True if current bar volume is >= min_ratio × 20-bar MA.
        Without volume, a pattern is a rumour. With volume, it's a fact.
        """
        row = self.df.iloc[-1]
        return bool(row["vol_ratio"] >= min_ratio)

    # ─────────────────────────────────────────────────────────
    # MASTER VERDICT
    # ─────────────────────────────────────────────────────────

    def verdict(self, boundary: str, alpha_vector: str) -> dict:
        """
        Runs all pattern + confirmation checks and returns
        a structured execution signal with a confidence score.

        Confidence scoring:
          +25 pts : rejection wick
          +25 pts : engulfing
          +20 pts : false breakout trap
          +15 pts : RSI alignment
          +15 pts : volume spike

        Threshold to fire a trade: confidence >= 40 pts
        (minimum: pattern + one confirmation)

        Parameters
        ----------
        boundary : str  "SUPPORT" | "RESISTANCE"  (from Alpha verdict)
        """
        wick        = self.detect_rejection_wick()
        engulf      = self.detect_engulfing()
        false_break = self.detect_false_breakout(boundary)
        rsi         = self.rsi_zone()
        vol_spike   = self.volume_spike()

        # ── Direction bias from patterns ────────────────────
        # Collect all pattern votes
        pattern_votes = [v for v in [wick, engulf, false_break] if v != 0]
        if not pattern_votes:
            return {"direction": "NONE", "confidence": 0,
                    "patterns": [], "rsi": rsi, "volume_spike": vol_spike}

        # Majority direction (most patterns agree)
        direction_sum = sum(pattern_votes)
        direction = "BUY" if direction_sum > 0 else "SELL"

        # Ensure direction is consistent with boundary
        if boundary == "SUPPORT"    and direction == "SELL": direction = "NONE"
        if boundary == "RESISTANCE" and direction == "BUY":  direction = "NONE"

        # 🔥 NEW: Enforce Alpha Trend Alignment (Doctrine Rule A1)
        if alpha_vector == "BULL" and direction == "SELL":
            direction = "NONE"
        if alpha_vector == "BEAR" and direction == "BUY":
            direction = "NONE"
        if direction == "NONE":
            return {"direction": "NONE", "confidence": 0,
                    "patterns": [], "rsi": rsi, "volume_spike": vol_spike}

        # ── Confidence score ────────────────────────────────
        score = 0
        active_patterns = []

        if wick != 0 and wick == (1 if direction == "BUY" else -1):
            score += 25
            active_patterns.append("REJECTION_WICK")

        if engulf != 0 and engulf == (1 if direction == "BUY" else -1):
            score += 25
            active_patterns.append("ENGULFING")

        if false_break != 0 and false_break == (1 if direction == "BUY" else -1):
            score += 20
            active_patterns.append("FALSE_BREAKOUT_TRAP")

        # RSI alignment bonus
        rsi_aligned = (direction == "BUY"  and rsi == "OVERSOLD") or \
                      (direction == "SELL" and rsi == "OVERBOUGHT")
        if rsi_aligned:
            score += 15

        # Volume bonus
        if vol_spike:
            score += 15

        return {
            "direction":    direction,
            "confidence":   score,
            "patterns":     active_patterns,
            "rsi":          rsi,
            "volume_spike": vol_spike,
        }
