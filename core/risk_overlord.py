# core/risk_overlord.py
# ============================================================
# LAYER 3 — RISK OVERLORD : The Final Gatekeeper
# ============================================================
# Asks: "Even if the signal is valid, should we ACTUALLY trade?"
# Enforces:
#   - 2% absolute risk rule per trade
#   - Minimum notional value check (Binance $5 floor)
#   - Minimum reward-to-risk validation
#   - Daily max loss circuit breaker (3% of capital)
#   - Position sizing in correct decimal precision
# ============================================================

import math
import logging
from datetime import date
from config.settings import (
    RISK_PER_TRADE, MIN_NOTIONAL, MIN_RR_RATIO,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT
)

logger = logging.getLogger("TradeGOD.RiskOverlord")


class RiskOverlord:

    # Daily loss circuit breaker: stop trading if we lose >3% in one day
    DAILY_MAX_LOSS_PCT = 0.03

    def __init__(self, capital_usdt: float):
        self.capital         = capital_usdt
        self._daily_loss     = 0.0
        self._daily_reset_dt = date.today()

    # ── Private helpers ──────────────────────────────────────
    def _reset_daily_if_needed(self):
        if date.today() != self._daily_reset_dt:
            logger.info("New trading day — resetting daily loss tracker.")
            self._daily_loss     = 0.0
            self._daily_reset_dt = date.today()

    def _round_step(self, quantity: float, step_size: float) -> float:
        """Rounds quantity down to the nearest Binance step size compliance."""
        if step_size <= 0:
            return round(quantity, 6)
        import math
        precision = int(round(-math.log10(step_size), 0))
        # Floor then round to clean up floating point artifacts
        floored = math.floor(quantity / step_size) * step_size
        return round(floored, precision)

    # ── Public ───────────────────────────────────────────────
    def update_capital(self, new_balance: float):
        """Call after each trade to keep capital current."""
        self.capital = new_balance

    def record_loss(self, loss_amount: float):
        """Log a realised loss so the circuit breaker can track it."""
        self._reset_daily_if_needed()
        self._daily_loss += abs(loss_amount)
        logger.info(f"Daily loss so far: ${self._daily_loss:.4f}")

    def circuit_breaker_tripped(self) -> bool:
        """
        Returns True if daily losses exceed DAILY_MAX_LOSS_PCT.
        When True, the bot must NOT trade until the next UTC day.
        """
        self._reset_daily_if_needed()
        threshold = self.capital * self.DAILY_MAX_LOSS_PCT
        tripped   = self._daily_loss >= threshold
        if tripped:
            logger.warning(
                f"🛑 CIRCUIT BREAKER: daily loss ${self._daily_loss:.2f} "
                f">= ${threshold:.2f} limit. No more trades today."
            )
        return tripped

    def compute_trade_levels(self, entry: float, direction: str) -> dict:
        """
        Computes stop-loss and take-profit levels from entry price.

        Parameters
        ----------
        entry     : float   current market price
        direction : str     "BUY" | "SELL"

        Returns
        -------
        dict with stop_loss, take_profit, rr_ratio
        """
        if direction == "BUY":
            stop_loss   = entry * (1 - STOP_LOSS_PCT)
            take_profit = entry * (1 + TAKE_PROFIT_PCT)
        else:
            stop_loss   = entry * (1 + STOP_LOSS_PCT)
            take_profit = entry * (1 - TAKE_PROFIT_PCT)

        risk   = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        rr     = reward / risk if risk > 0 else 0

        return {
            "stop_loss":   round(stop_loss,   2),
            "take_profit": round(take_profit, 2),
            "rr_ratio":    round(rr, 2),
        }

    def validate_and_size(
        self,
        entry:     float,
        direction: str,
        step_size: float = 0.00001
    ) -> dict:
        """
        Master method: validates all risk rules and returns final
        position size (in base asset units) or a rejection reason.

        Parameters
        ----------
        entry     : float   market entry price
        direction : str     "BUY" | "SELL"
        step_size : float   Binance lot step size for this symbol

        Returns
        -------
        dict:
            approved  : bool
            reason    : str (empty if approved)
            quantity  : float (0 if rejected)
            stop_loss : float
            take_profit : float
            risk_usdt : float
            rr_ratio  : float
        """
        result = {
            "approved":    False,
            "reason":      "",
            "quantity":    0.0,
            "stop_loss":   0.0,
            "take_profit": 0.0,
            "risk_usdt":   0.0,
            "rr_ratio":    0.0,
        }

        # 1. Circuit breaker
        if self.circuit_breaker_tripped():
            result["reason"] = "Daily loss limit reached. No trades today."
            return result

        # 2. Compute levels
        levels = self.compute_trade_levels(entry, direction)
        result["stop_loss"]   = levels["stop_loss"]
        result["take_profit"] = levels["take_profit"]
        result["rr_ratio"]    = levels["rr_ratio"]

        # 3. Minimum R:R check
        if levels["rr_ratio"] < MIN_RR_RATIO:
            result["reason"] = (
                f"R:R {levels['rr_ratio']:.2f} below minimum {MIN_RR_RATIO}."
            )
            return result

        # 4. Compute position size using 2% risk rule
        risk_usdt = self.capital * RISK_PER_TRADE
        risk_per_unit = abs(entry - levels["stop_loss"])

        if risk_per_unit <= 0:
            result["reason"] = "Risk per unit is zero — cannot size position."
            return result

        raw_qty = risk_usdt / risk_per_unit
        quantity = self._round_step(raw_qty, step_size)

        # 5. Minimum notional check (Binance $5 floor)
        notional = quantity * entry
        if notional < MIN_NOTIONAL:
            result["reason"] = (
                f"Notional ${notional:.2f} below Binance minimum ${MIN_NOTIONAL}. "
                f"Increase capital or reduce risk pct."
            )
            return result

        # 6. Sanity: do we have enough balance?
        if notional > self.capital:
            result["reason"] = (
                f"Notional ${notional:.2f} exceeds capital ${self.capital:.2f}."
            )
            return result

        # All checks passed
        result["approved"]  = True
        result["quantity"]  = quantity
        result["risk_usdt"] = round(risk_usdt, 4)

        logger.info(
            f"✅ Risk approved | Dir={direction} | "
            f"Qty={quantity} | Entry={entry} | "
            f"SL={levels['stop_loss']} | TP={levels['take_profit']} | "
            f"R:R={levels['rr_ratio']} | Risk=${risk_usdt:.4f}"
        )
        return result
