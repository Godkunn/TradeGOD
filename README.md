# TradeGOD System v1.0
> Emotionless. 24/7. Math-only. Multi-confirmation Binance Sniper Bot.

## Architecture
```
[HTF 1h Data] → ALPHA FILTER → [Zone Active?]
                                      ↓ YES
[LTF 5m Data] → BETA FILTER  → [Confidence ≥ 40?]
                                      ↓ YES
               RISK OVERLORD → [2% rule + min notional + R:R]
                                      ↓ APPROVED
                               EXECUTE ORDER (Market + OCO)
```

## Project Structure
```
TradeGOD_System/
├── config/
│   └── settings.py          ← All parameters live here
├── core/
│   ├── alpha_filter.py      ← Layer 1: Trend + ADX + SR zones (1h)
│   ├── beta_filter.py       ← Layer 2: Patterns + RSI + Volume (5m)
│   └── risk_overlord.py     ← Layer 3: Position sizing + circuit breaker
├── engines/
│   └── binance_sniper.py    ← Main bot execution loop
├── tests/
│   └── backtester.py        ← Offline walk-forward backtester
├── docs/
│   ├── The_Doctrine.txt     ← Human-readable trading rules
│   └── Trade_Logs.csv       ← Auto-generated trade history
├── logs/
│   └── tradegod.log         ← Auto-generated runtime logs
├── main.py                  ← Entry point
├── requirements.txt
├── render.yaml              ← Render.com deployment config
└── .env.example             ← Environment variables template
```

---

## Quick Start

### Step 1 — Install
```bash
git clone <your-repo>
cd TradeGOD_System
pip install -r requirements.txt
```

### Step 2 — Configure
```bash
cp .env.example .env
# Edit .env — paste your Binance Testnet API keys
```
Get free Testnet keys: https://testnet.binance.vision/

### Step 3 — Backtest first (no API key needed)
```bash
python main.py --backtest
```
This downloads real BTC historical data and simulates the full strategy. Check the report. If Profit Factor > 1.5 and Win Rate > 45%, the logic is working.

### Step 4 — Verify config
```bash
python main.py --check
```

### Step 5 — Run on Testnet
```bash
python main.py
```
Watch the logs. Let it run for 1–2 weeks on testnet before touching real money.

### Step 6 — Deploy to Render (24/7)
1. Push code to GitHub (private repo)
2. Create new **Background Worker** on render.com
3. Connect GitHub repo
4. Add environment variables from `.env` in the Render dashboard
5. Deploy → runs 24/7 even when laptop is off ✅

---

## Adjustable Parameters (config/settings.py)

| Parameter | Default | Meaning |
|---|---|---|
| `SYMBOL` | BTCUSDT | What to trade |
| `CAPITAL_USDT` | 10 | Starting capital |
| `RISK_PER_TRADE` | 0.02 | 2% max loss per trade |
| `STOP_LOSS_PCT` | 0.012 | 1.2% stop distance |
| `TAKE_PROFIT_PCT` | 0.028 | 2.8% target |
| `MIN_CONFIDENCE` | 40 | Beta score to fire trade |
| `SR_PROXIMITY_PCT` | 0.012 | How close to zone = "in zone" |

---

## What triggers a trade?

**ALL of the following must be true simultaneously:**

1. **Alpha**: SMA50 > SMA200 (or inverse for short)
2. **Alpha**: ADX > 25 (trending, not ranging)
3. **Alpha**: Price within 1.2% of recent high or low
4. **Beta**: At least one pattern (wick/engulf/false breakout) scores ≥ 40
5. **Risk**: Position notional ≥ $5.50
6. **Risk**: R:R ≥ 2.0
7. **Risk**: Daily loss < 3% circuit breaker

If any single condition fails → **no trade**.

This means the bot may sit silent for hours or days. **That is correct behavior.** Rare + accurate beats frequent + random.

---

## Telegram Alerts (Optional)
1. Create a bot via @BotFather on Telegram
2. Get your Chat ID via @userinfobot
3. Add both to `.env`

You'll get alerts on every trade execution.

---

## Indian Tax Warning ⚠️
If trading on Binance from India:
- **1% TDS** is deducted on every sell transaction
- **30% flat tax** on all crypto profits (no loss offset)
- With tight margins, fees + TDS can eat profits fast
- Minimum target per trade must clear: 0.1% fee + 1% TDS = **~1.2% just to break even**

The bot's 2.8% take-profit accounts for this, but be aware.

---

## License
Personal use only. Not financial advice.
