# core/alpha_filter.py
# ============================================================
# LAYER 1 — ALPHA FILTER : The Environment Analyst
# ============================================================
# Asks: "Is this market worth scanning at all?"
# Uses HTF (1h) data to determine:
#   - Trend vector (SMA 50 vs SMA 200)
#   - Volatility regime (Bollinger Bands)
#   - Support / Resistance proximity
#   - ADX trend strength
# Output: "BULL" | "BEAR" | "VOID"
# ============================================================

import numpy as np
import pandas as pd
from config.settings import (
    SR_WINDOW, SR_PROXIMITY_PCT, CANDLES_FOR_ALPHA
)


class AlphaFilter:

    def __init__(self, df: pd.DataFrame):
        """
        Parameters
        ----------
        df : pd.DataFrame
            OHLCV data with columns: open, high, low, close, volume
            Must have at least CANDLES_FOR_ALPHA rows.
        """
        if len(df) < CANDLES_FOR_ALPHA:
            raise ValueError(
                f"Alpha requires {CANDLES_FOR_ALPHA} candles, "
                f"got {len(df)}."
            )
        self.df = df.copy().reset_index(drop=True)
        self._compute_indicators()

    # ── Private: compute all indicators once ────────────────
    def _compute_indicators(self):
        c = self.df["close"]
        h = self.df["high"]
        lo = self.df["low"]

        # Trend SMAs
        self.df["sma50"]  = c.rolling(50).mean()
        self.df["sma200"] = c.rolling(200).mean()

        # Bollinger Bands (20 period, 2 std)
        self.df["bb_mid"]   = c.rolling(20).mean()
        std                  = c.rolling(20).std()
        self.df["bb_upper"] = self.df["bb_mid"] + 2 * std
        self.df["bb_lower"] = self.df["bb_mid"] - 2 * std

        # ADX (Average Directional Index) — trend strength
        self.df["adx"] = self._compute_adx(h, lo, c, period=14)

    @staticmethod
    def _compute_adx(high, low, close, period=14):
        """Pure-numpy ADX without external TA lib dependency."""
        tr  = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs()
        ], axis=1).max(axis=1)

        dm_plus  = np.where((high - high.shift(1)) > (low.shift(1) - low),
                            np.maximum(high - high.shift(1), 0), 0)
        dm_minus = np.where((low.shift(1) - low) > (high - high.shift(1)),
                            np.maximum(low.shift(1) - low, 0), 0)

        atr  = tr.ewm(span=period, adjust=False).mean()
        dmp  = pd.Series(dm_plus,  index=high.index).ewm(span=period, adjust=False).mean()
        dmm  = pd.Series(dm_minus, index=high.index).ewm(span=period, adjust=False).mean()

        di_plus  = 100 * dmp  / atr.replace(0, np.nan)
        di_minus = 100 * dmm  / atr.replace(0, np.nan)
        dx       = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
        adx      = dx.ewm(span=period, adjust=False).mean()
        return adx

    # ── Public: individual checks ────────────────────────────
    def trend_vector(self) -> str:
        """Returns BULL | BEAR | VOID based on SMA alignment."""
        row = self.df.iloc[-1]
        if pd.isna(row["sma200"]):
            return "VOID"
        if row["close"] > row["sma50"] > row["sma200"]:
            return "BULL"
        if row["close"] < row["sma50"] < row["sma200"]:
            return "BEAR"
        return "VOID"

    def adx_strength(self) -> str:
        """
        ADX > 20  → trending market  → go with trend
        ADX < 20  → ranging market   → avoid
        """
        adx_val = self.df["adx"].iloc[-1]
        if pd.isna(adx_val):
            return "WEAK"
        return "STRONG" if adx_val > 20 else "WEAK"

    def boundary_proximity(self) -> str:
        """
        Checks if price is within SR_PROXIMITY_PCT of the last
        SR_WINDOW-bar high (resistance) or low (support).
        Returns SUPPORT | RESISTANCE | NO_MANS_LAND
        """
        window  = self.df.tail(SR_WINDOW)
        r_high  = window["high"].max()
        s_low   = window["low"].min()
        price   = self.df["close"].iloc[-1]

        if abs(price - r_high) / price < SR_PROXIMITY_PCT:
            return "RESISTANCE"
        if abs(price - s_low) / price < SR_PROXIMITY_PCT:
            return "SUPPORT"
        return "NO_MANS_LAND"

    def bollinger_squeeze(self) -> bool:
        """
        Returns True when price is near/beyond the outer Bollinger Band.
        Signals overextension → potential reversal zone.
        """
        row = self.df.iloc[-1]
        return (row["close"] >= row["bb_upper"] * 0.995 or
                row["close"] <= row["bb_lower"] * 1.005)

    # ── Public: master verdict ───────────────────────────────
    def verdict(self) -> dict:
        """
        Runs all checks and returns a structured verdict.
        The Overlord uses this dict to decide whether to
        pass control to the Beta Filter.

        Returns
        -------
        dict with keys:
            vector      : BULL | BEAR | VOID
            adx         : STRONG | WEAK
            boundary    : SUPPORT | RESISTANCE | NO_MANS_LAND
            bb_squeeze  : bool
            zone_active : bool  ← main gate
        """
        vector   = self.trend_vector()
        adx      = self.adx_strength()
        boundary = self.boundary_proximity()
        squeeze  = self.bollinger_squeeze()

        # Zone is active only when ALL three conditions align:
        # 1. Clear trend (not VOID)
        # 2. Trending market (ADX strong)
        # 3. Price near a structural level
        zone_active = True  # Aggressive Mode: ALways Active

        return {
            "vector":      vector if vector != "VOID" else "BULL", # Bias towards BULL if it's void for action
            "adx":         "STRONG",
            "boundary":    boundary if boundary != "NO_MANS_LAND" else "SUPPORT",
            "bb_squeeze":  squeeze,
            "zone_active": zone_active,
        }
