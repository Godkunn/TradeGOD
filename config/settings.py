# config/settings.py
# ============================================================
# TradeGOD System — Central Configuration Loader
# All runtime parameters live here. Touch this, not the engines.
# ============================================================

import os
from dotenv import load_dotenv

load_dotenv()

# ── EXCHANGE ────────────────────────────────────────────────
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")
BINANCE_TESTNET    = os.getenv("BINANCE_MODE", "testnet").lower() == "testnet"

# ── MARKET ──────────────────────────────────────────────────
SYMBOLS     = [s.strip() for s in os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT").split(",") if s.strip()]
SYMBOL      = SYMBOLS[0] if SYMBOLS else "BTCUSDT" # For backwards compatibility (backtester)
TIMEFRAME   = "5m"          # Primary chart (Beta sniper)
HTF         = "1h"          # Higher timeframe (Alpha context)

# ── CAPITAL ─────────────────────────────────────────────────
CAPITAL_USDT    = float(os.getenv("CAPITAL_USDT", 10))
RISK_PER_TRADE  = float(os.getenv("RISK_PER_TRADE", 0.02))   # 2%
MIN_RR_RATIO    = 2.0        # Minimum reward-to-risk required
MIN_NOTIONAL    = 5.5        # Binance rejects orders below ~$5
STOP_LOSS_PCT   = 0.012      # 1.2% stop distance
TAKE_PROFIT_PCT = 0.028      # 2.8% target  (RR ≈ 2.3x)

# ── FILTERS ─────────────────────────────────────────────────
CANDLES_FOR_ALPHA = 200      # Candles needed to compute SMAs
CANDLES_FOR_BETA  = 50       # Candles needed for pattern scan
SR_WINDOW         = 50       # Bars to determine support/resistance
SR_PROXIMITY_PCT  = 0.012    # Within 1.2% of a boundary = "zone"
REJECTION_WICK_RATIO = 0.62  # Wick must be 62% of total candle range
MIN_CONFIDENCE = 40       # Minimum confidence score (0-100) to trigger Beta sniper
SPOT_MODE_ONLY = True   # If True, only take signals that apply to spot trading (no shorts)

# ── TIMING ──────────────────────────────────────────────────
LOOP_SLEEP_VOID    = 300     # Sleep (s) when Alpha says VOID
LOOP_SLEEP_STALK   = 120     # Sleep (s) when stalking but no trigger
COOLDOWN_AFTER_TRADE = 900   # 15-min buffer after any executed trade

# ── TELEGRAM ────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── PATHS ───────────────────────────────────────────────────
LOG_FILE   = "logs/tradegod.log"
TRADE_FILE = "docs/Trade_Logs.csv"
