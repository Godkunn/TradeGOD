#!/usr/bin/env python3
# main.py
# ============================================================
# TradeGOD System — Overlord Entry Point
# ============================================================
# Usage:
#   python main.py             → Run live/testnet bot
#   python main.py --backtest  → Run backtester only
#   python main.py --check     → Verify config & connectivity
# ============================================================

import sys
import os
import time


def banner():
    print("""
+----------------------------------------------------------+
|                                                          |
|        T R A D E G O D    S Y S T E M    v 2 . 0        |
|                                                          |
|        Alpha x Beta x Risk Overlord Pipeline             |
+----------------------------------------------------------+
""")


def check_env():
    """Verifies .env file and connectivity before starting."""
    print("🔍 Running pre-flight checks...\n")

    # Check .env
    if not os.path.exists(".env"):
        print("❌  .env file not found!")
        print("    → Copy .env.example to .env and fill in your API keys.\n")
        return False

    from config.settings import (
        BINANCE_API_KEY, BINANCE_SECRET_KEY,
        BINANCE_TESTNET, SYMBOLS, CAPITAL_USDT
    )

    if not BINANCE_API_KEY or BINANCE_API_KEY == "your_testnet_api_key_here":
        print("❌  BINANCE_API_KEY is not set in .env")
        return False

    print(f"  ✅ API Key        : {'*' * 8}{BINANCE_API_KEY[-4:]}")
    print(f"  ✅ Mode           : {'TESTNET ⚠️' if BINANCE_TESTNET else 'LIVE 🔴'}")
    print(f"  ✅ Symbols        : {', '.join(SYMBOLS)}")
    print(f"  ✅ Capital        : ${CAPITAL_USDT} USDT")

    # Test connection
    try:
        from binance.client import Client
        client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY, testnet=BINANCE_TESTNET)
        server_time = client.get_server_time()
        print(f"  ✅ Exchange ping  : OK (server time synced)")
        
        for sym in SYMBOLS:
            price = client.get_symbol_ticker(symbol=sym)
            print(f"  ✅ {sym} price  : ${float(price['price']):,.2f}")

        # Check balance
        usdt = client.get_asset_balance(asset="USDT")
        print(f"  ✅ USDT balance   : ${float(usdt['free']):.4f}")
        print()
        print("🟢 All checks passed. System is ready.\n")
        return True
    except Exception as e:
        print(f"\n❌  Connection failed: {e}")
        print("    → Check your API keys and internet connection.\n")
        return False


def run_bot():
    from engines.binance_sniper import BinanceSniper
    bot = BinanceSniper()
    bot.run()


def run_backtest():
    from tests.backtester import Backtester
    from config.settings import SYMBOL, CAPITAL_USDT
    bt = Backtester(symbol=SYMBOL, start_capital=CAPITAL_USDT)
    bt.run()


from keep_alive import keep_alive

# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    banner()
    
    # Start the keep-alive server (for Render 24/7 pings)
    keep_alive()

    mode = sys.argv[1] if len(sys.argv) > 1 else "--binance" # Default to binance

    if mode == "--backtest":
        print("📊 Mode: BACKTEST (no real orders)\n")
        run_backtest()

    elif mode == "--check":
        check_env()
        
    elif mode == "--binance":
        print("🤖 Mode: LIVE BINANCE SNIPER\n")
        from engines.binance_sniper import BinanceSniper
        bot = BinanceSniper()
        bot.run()
        
    elif mode == "--dhan":
        print("🇮🇳 Mode: LIVE DHAN INTRADAY\n")
        from engines.dhan_intraday import DhanIntradayEngine
        bot = DhanIntradayEngine()
        bot.run()
