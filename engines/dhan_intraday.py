# engines/dhan_intraday.py
import time
import logging
import os
from dhanhq import dhanhq
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("TradeGOD.DhanEngine")

class DhanIntradayEngine:
    def __init__(self):
        logger.info("═" * 60)
        logger.info("  TradeGOD System — DHAN INTRADAY STARTING UP")
        logger.info("═" * 60)
        
        self.client_id = os.getenv("DHAN_CLIENT_ID")
        self.access_token = os.getenv("DHAN_ACCESS_TOKEN")
        
        # --- THE CREDENTIALS FAILSAFE ---
        if not self.client_id or not self.access_token:
            logger.warning("⚠️ Dhan credentials missing in .env. Engine set to INACTIVE.")
            self.active = False
            return
        # --------------------------------
        
        self.active = True
        self.dhan = dhanhq(self.client_id, self.access_token)
        
    def _is_market_open(self):
        """Checks if current IST time is between 9:15 AM and 3:30 PM, Mon-Fri"""
        now = datetime.now() # Make sure your server time is set to IST
        
        # 0 = Monday, 4 = Friday. If it's the weekend (5 or 6), market is closed.
        if now.weekday() > 4: 
            return False
            
        market_start = now.replace(hour=9, minute=15, second=0)
        market_end = now.replace(hour=15, minute=30, second=0)
        
        return market_start <= now <= market_end

    def run(self):
        # Check if the Failsafe disabled the bot
        if getattr(self, 'active', False) == False:
            logger.error("🛑 Dhan Engine is INACTIVE. Shutting down this thread.")
            return # This cleanly kills the Dhan process without touching Binance

        logger.info("🔭 Dhan Overlord Patrolling...")
        
        while True:
            # Check if Market is Open
            if not self._is_market_open():
                logger.info("💤 NSE Market Closed. Dhan Engine sleeping for 5 minutes...")
                time.sleep(300) # Sleeps for 5 minutes, then checks the clock again
                continue
                
            try:
                self._patrol_cycle() # Your Alpha/Beta logic runs here
            except Exception as e:
                logger.error(f"Dhan Error: {e}")
                time.sleep(60)

    def _patrol_cycle(self):
        # 1. Fetch Data using self.dhan.get_historical_minute_charts()
        # 2. Pass data to AlphaFilter / BetaFilter
        # 3. If Valid -> place order using self.dhan.place_order()
        pass
