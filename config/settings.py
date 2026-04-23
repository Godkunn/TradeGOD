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
ITF         = "15m"         # Intermediate timeframe (Momentum check)
HTF         = "1h"          # Higher timeframe (Alpha context)

# ── CAPITAL ─────────────────────────────────────────────────
CAPITAL_USDT    = float(os.getenv("CAPITAL_USDT", 10))
# To take massive trades with small capital, RISK_PER_TRADE must be <= STOP_LOSS_PCT to keep notional <= capital
RISK_PER_TRADE  = float(os.getenv("RISK_PER_TRADE", 0.95))   # 95% risk! (Aggressive)
MIN_RR_RATIO    = 0.5        # Dropped from 2.0 to take more trades
MIN_NOTIONAL    = 5.5        # Binance rejects orders below ~$5
STOP_LOSS_PCT   = 0.95       # 95% stop distance (allows using almost 100% capital)
TAKE_PROFIT_PCT = 0.95       # 95% target

# ── FILTERS ─────────────────────────────────────────────────
CANDLES_FOR_ALPHA = 200      # Candles needed to compute SMAs
CANDLES_FOR_BETA  = 50       # Candles needed for pattern scan
SR_WINDOW         = 50       # Bars to determine support/resistance
SR_PROXIMITY_PCT  = 1.0      # VERY high proximity -> almost always in a zone
REJECTION_WICK_RATIO = 0.1   # Tiny wick triggers execution
MIN_CONFIDENCE = 0        # Execute even with low confidence
SPOT_MODE_ONLY = False   # Set to False to allow SHORTS (DOWN trades). Required for full doctrine.

# ── TIMING ──────────────────────────────────────────────────
LOOP_SLEEP_VOID    = 2       # Sleep (s) when Alpha says VOID (Aggressive stalk)
LOOP_SLEEP_STALK   = 2       # Sleep (s) when stalking but no trigger (Aggressive)
COOLDOWN_AFTER_TRADE = 10    # 10-sec buffer after any executed trade

# ── TELEGRAM ────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── PATHS ───────────────────────────────────────────────────
LOG_FILE   = "logs/tradegod.log"
TRADE_FILE = "docs/Trade_Logs.csv"
