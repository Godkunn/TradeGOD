# ⚡ TradeGOD System v2.0 ⚡
> **The Quantitative Overlord.** Multi-Coin Scanner. Emotionless Execution. 24/7 Production Deployment.

![TradeGOD Banner](assets/tradegod_banner.png)

## 🏆 The Vision
TradeGOD is not just a script; it is a **Quantitative Fund Management Engine**. Built for professional retail traders who demand institutional-grade execution on a decentralized scale. 

Version 2.0 introduces the **Multi-Market Scanner**, allowing the bot to simultaneously track, evaluate, and prioritize the best trade setups across a customized basket of crypto assets (BTC, ETH, SOL, BNB, etc.) while maintaining a strict "One Position" risk-first doctrine.

---

## 🚀 Key Features (v2.0)

### 🧺 Multi-Coin "Best-of-Breed" Scanner
- **Parallel Scanning**: Monitors multiple symbols from your `.env` simultaneously.
- **Smart Prioritization**: If multiple coins hit a valid setup at the same time, the bot automatically selects the one with the highest **Statistical Confidence Score**.
- **Single-Exposure Doctrine**: Enforces a strict one-position-at-a-time limit to protect your capital.

### 📱 God-Mode Telegram Terminal
- **Supervisor Loop**: Self-healing connection logic. If Telegram’s API lags or your network drops, the bot automatically reconnects in seconds.
- **Safe-Send Messaging**: Robust retries for all alerts. No trade alert is ever lost to a "Timeout Error."
- **Live Portfolio Tracking**: Real-time entry prices, buy prices, and PnL breakdown directly from your phone.
- **Emergency Kill Switch**: Instant, one-tap liquidation of all active positions and cancellation of all open OCO orders.

### 🛡️ 3-Layer Quantitative Filter
1.  **ALPHA (HTF)**: Trend enforcement using 1h SMA/ADX and Macro Support/Resistance zones.
2.  **BETA (LTF)**: Execution trigger based on 5m rejection wicks, engulfing patterns, and false-breakout traps.
3.  **RISK OVERLORD**: Final gatekeeper ensuring 2% max risk per trade, Binance-compliant lot sizing, and a 3% daily loss circuit breaker.

---

## 📂 Project Structure
```
TradeGOD_System/
├── config/
│   └── settings.py          ← System parameters & symbol logic
├── core/
│   ├── alpha_filter.py      ← Layer 1: Macro Overlord
│   ├── beta_filter.py       ← Layer 2: Pattern Trigger
│   ├── risk_overlord.py     ← Layer 3: Risk Compliance
│   └── telegram_ui.py       ← Production-grade Command Center
├── engines/
│   ├── binance_sniper.py    ← Multi-coin scanner execution engine
│   └── dhan_intraday.py     ← (Optional) Indian Equities Engine
├── tests/
│   └── backtester.py        ← Offline walk-forward strategy tester
├── main.py                  ← Entry point (Routing & Keep-Alive)
├── keep_alive.py            ← Heartbeat server for 24/7 Render uptime
├── requirements.txt         ← Dependency Manifest
└── render.yaml              ← Cloud deployment template
```

---

## 🛠️ Deployment (Production Level)

### 1. Verification
Before going live, always run the pre-flight check:
```bash
python main.py --check
```

### 2. Live Execution
Run the live scan for Binance:
```bash
python main.py --binance
```

### 3. Cloud Deployment
1.  **Push to GitHub**: Keep your repo private.
2.  **Create Web Service**: Connect your GitHub repo
3.  **Build Command**: `pip install -r requirements.txt`
4.  **Start Command**: `python main.py --binance`

---

## ⚠️ Risk Disclaimer
Trading cryptocurrencies involves high risk. This software is provided "as is" for educational purposes. Always trade on **Testnet** for at least 30 days before moving to a live production environment. 

---
**Build by GodKun. Powered by TradeGOD.**
