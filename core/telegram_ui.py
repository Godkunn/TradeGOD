# core/telegram_ui.py
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import logging
import time
import requests
from telebot.apihelper import ApiTelegramException

from config.settings import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, SYMBOLS, CAPITAL_USDT

logger = logging.getLogger("TradeGOD.TelegramUI")

class TelegramUI:
    def __init__(self, sniper_engine):
        self.sniper = sniper_engine
        self.active = False
        
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            logger.warning("Telegram credentials missing. UI Disabled.")
            return

        self.bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode='HTML')
        self.chat_id = TELEGRAM_CHAT_ID
        self.active = True

        self._setup_handlers()
        self._start_polling()

    def _start_polling(self):
        """Starts a background supervisor thread to manage bot polling."""
        thread = threading.Thread(target=self._start_polling_supervisor, daemon=True)
        thread.start()
        self.send_alert("🟢 <b>TradeGOD Command Center Online</b>\nType /start to access the terminal.")

    def _start_polling_supervisor(self):
        """Infinite loop that restarts polling if it crashes due to network/timeout errors."""
        while self.active:
            try:
                logger.info("📡 Telegram Polling Supervisor: Starting engine...")
                # Increase timeouts for higher resilience on weak connections
                self.bot.infinity_polling(timeout=60, long_polling_timeout=60)
            except Exception as e:
                logger.error(f"⚠️ Telegram Polling Failure: {e}")
                logger.info("⏳ Supervisor: Retrying in 10 seconds...")
                time.sleep(10)

    def _safe_send_message(self, chat_id, text, **kwargs):
        """Production wrapper for send_message to handle network/API errors without crashing."""
        if not self.active: return None
        
        for attempt in range(3): # Retry up to 3 times
            try:
                return self.bot.send_message(chat_id, text, **kwargs)
            except (ApiTelegramException, requests.exceptions.RequestException) as e:
                logger.warning(f"⚠️ Send failed (Attempt {attempt+1}/3): {e}")
                if attempt == 2: # Last attempt
                    logger.error("🛑 Failed to send message after 3 attempts.")
                time.sleep(2)
        return None

    def _setup_handlers(self):
        @self.bot.message_handler(commands=['start', 'menu'])
        def send_welcome(message):
            if str(message.chat.id) != str(self.chat_id): return
            text = (
                "╔═════════════════════════╗\n"
                "║ ⚡ <b>GODKUN TERMINAL v2.0</b> ║\n"
                "╚═════════════════════════╝\n\n"
                "<i>System is patrolling the markets...</i>"
            )
            self._safe_send_message(message.chat.id, text, reply_markup=self._main_menu())

        # Added /profile as an alias for /portfolio
        @self.bot.message_handler(commands=['portfolio', 'profile'])
        def command_portfolio(message):
            if str(message.chat.id) != str(self.chat_id): return
            self._send_portfolio()

        @self.bot.callback_query_handler(func=lambda call: True)
        def handle_query(call):
            if call.data == "btn_portfolio":
                self._send_portfolio()
            elif call.data == "btn_status":
                self._send_status()
            elif call.data == "btn_toggle_pause":
                self._toggle_pause(call.message)
            elif call.data == "btn_close_trade":
                self._emergency_close(call.message)
            self.bot.answer_callback_query(call.id)

    def _main_menu(self):
        markup = InlineKeyboardMarkup(row_width=2)
        btn1 = InlineKeyboardButton("📊 View Portfolio", callback_data="btn_portfolio")
        btn2 = InlineKeyboardButton("⚙️ System Stats", callback_data="btn_status")
        btn3 = InlineKeyboardButton("⏸️ Play/Pause", callback_data="btn_toggle_pause")
        btn4 = InlineKeyboardButton("🚨 KILL SWITCH", callback_data="btn_close_trade")
        markup.add(btn1, btn2)
        markup.add(btn3)
        markup.add(btn4)
        return markup

    def _send_status(self):
        """Reports the overall bot trading performance and current settings"""
        mode = "TESTNET" if self.sniper.client.TESTNET else "LIVE"
        state = "⏸️ PAUSED" if getattr(self.sniper, "paused", False) else "🟢 PATROLLING"
        
        win_rate = 0
        if self.sniper.total_trades > 0:
            win_rate = (self.sniper.wins / self.sniper.total_trades) * 100
            
        msg = (
            "<b><pre>⚙️ SYSTEM STATUS</pre></b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Status :</b> <code>{state}</code>\n"
            f"<b>Mode   :</b> <code>{mode}</code>\n"
            f"<b>Pairs  :</b> <code>{len(SYMBOLS)} active</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Total Trades :</b> <code>{self.sniper.total_trades}</code>\n"
            f"<b>Wins/Losses  :</b> <code>{self.sniper.wins} / {self.sniper.losses}</code>\n"
            f"<b>Win Rate     :</b> <code>{win_rate:.1f}%</code>\n"
            f"<b>Gross Net PNL:</b> <code>${self.sniper.pnl:.2f}</code>\n"
        )
        self._safe_send_message(self.chat_id, msg, reply_markup=self._main_menu())

    def _toggle_pause(self, message):
        """Toggles the execution loop without terminating the program"""
        is_paused = getattr(self.sniper, "paused", False)
        self.sniper.paused = not is_paused
        
        if self.sniper.paused:
            self._safe_send_message(self.chat_id, "⏸️ <b>BOT PAUSED</b>\nThe system will continue fetching data but will NOT execute trades.", reply_markup=self._main_menu())
        else:
            self._safe_send_message(self.chat_id, "▶️ <b>BOT RESUMED</b>\nThe system is now actively hunting for executing conditions.", reply_markup=self._main_menu())

    def _send_portfolio(self):
        """Fetches live data and calculates real-time PNL of the active trade"""
        try:
            usdt_bal = self.sniper._get_balance()
            
            active_asset = None
            active_bal = 0.0
            active_price = 0.0
            active_val = 0.0
            
            for sym in SYMBOLS:
                b_asset = sym.replace("USDT", "")
                try:
                    b_bal = self.sniper._get_base_asset_balance(sym)
                    c_price = self.sniper._get_price(sym)
                    val = b_bal * c_price
                    if val > 5.0:
                        active_asset = b_asset
                        active_bal = b_bal
                        active_price = c_price
                        active_val = val
                        break
                except Exception:
                    pass
            
            total_equity = usdt_bal + active_val
            net_pnl = total_equity - self.sniper.risk.capital
            
            # Real-time trade tracking
            if active_asset:
                entry_price = self.sniper._get_average_entry_price(active_asset + "USDT")
                trade_pnl = (active_price - entry_price) * active_bal if entry_price > 0 else 0.0
                trade_pnl_str = f"+${trade_pnl:.2f}" if trade_pnl >= 0 else f"-${abs(trade_pnl):.2f}"
                
                if entry_price > 0:
                    px_lines = (
                        f"   Buy Px   : <code>${entry_price:.2f}</code>\n"
                        f"   Curr Px  : <code>${active_price:.2f}</code>\n"
                        f"   Pos Val  : <code>${active_val:.2f}</code>\n"
                        f"   Trade PNL: <b><code>{trade_pnl_str}</code></b>"
                    )
                else:
                    px_lines = (
                        f"   Curr Val : <code>${active_val:.2f}</code>\n"
                        f"   Price    : <code>${active_price:.2f}</code>"
                    )

                pos_status = (
                    f"<b>ACTIVE LONG:</b> <code>{active_asset}</code>\n"
                    f"   Holdings : <code>{active_bal:.4f}</code>\n"
                    f"{px_lines}"
                )
            else:
                pos_status = "<code>NO ACTIVE TRADES (Patrolling)</code>"

            msg = (
                "<b><pre>🏦 GODKUN PORTFOLIO</pre></b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Liquid USDT :</b> <code>${usdt_bal:.2f}</code>\n"
                f"💰 <b>Total Equity:</b> <code>${total_equity:.2f}</code>\n"
                f"📈 <b>Session PNL :</b> <code>${net_pnl:.2f}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🎯 <b>CURRENT POSITION:</b>\n"
                f"{pos_status}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            self._safe_send_message(self.chat_id, msg, reply_markup=self._main_menu())
        except Exception as e:
            self._safe_send_message(self.chat_id, f"⚠️ Error: {e}")

    def _emergency_close(self, message):
        """Panic Button: Cancels all open orders and market sells the asset"""
        self._safe_send_message(self.chat_id, "⚠️ <b>EXECUTING EMERGENCY KILL SWITCH...</b>")
        try:
            sold_any = False
            for sym in SYMBOLS:
                # 1. Cancel all open Stop Loss / Take Profit orders
                try:
                    self.sniper.client.cancel_open_orders(symbol=sym)
                except Exception:
                    pass
                
                # 2. Check if we actually hold the coin
                base_asset = sym.replace("USDT", "")
                try:
                    base_bal = self.sniper._get_base_asset_balance(sym)
                except Exception:
                    continue
                
                # 3. Market Sell
                if base_bal > 0:
                    qty = self.sniper.risk._round_step(base_bal, self.sniper._step_sizes.get(sym, 0.00001))
                    if qty > 0:
                        try:
                            self.sniper._place_market_order(sym, "SELL", qty)
                            self._safe_send_message(self.chat_id, f"✅ <b>SUCCESS:</b> Sold {qty} {base_asset} at Market Price. Orders cleared.")
                            sold_any = True
                        except Exception as e:
                            self._safe_send_message(self.chat_id, f"❌ <b>FAILED to sell {sym}:</b> {e}")
            
            if not sold_any:
                self._safe_send_message(self.chat_id, "ℹ️ No active position to sell. All open orders cleared.")
        except Exception as e:
            self._safe_send_message(self.chat_id, f"❌ <b>KILL SWITCH FATAL ERROR:</b> {e}")

    def send_alert(self, text):
        if self.active:
            self._safe_send_message(self.chat_id, text)