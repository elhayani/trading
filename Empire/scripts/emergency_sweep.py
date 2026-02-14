
import boto3
import json
import logging
from datetime import datetime, timezone
import ccxt
import time
import os

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("EmergencySweep")

# --- API KEYS ---
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

# --- CONFIG ---
MAX_LOSS_PCT = 0.0035  # 0.35% (slightly higher than 0.30% to be safe)
LEVERAGE = 1 # Assume 1x for safety calculation if unknown, but better to use price delta

def get_exchange():
    return ccxt.binance({
        'apiKey': API_KEY,
        'secret': SECRET_KEY,
        'options': {'defaultType': 'future'}
    })

def emergency_sweep():
    exchange = get_exchange()
    logger.info("Connecting to Binance...")
    
    try:
        # 1. Fetch all open positions
        positions = exchange.fetch_positions()
        active_positions = [p for p in positions if float(p['contracts']) > 0]
        
        logger.info(f"Found {len(active_positions)} active positions on Binance.")
        
        for pos in active_positions:
            symbol = pos['symbol']
            side = pos['side'].upper() # LONG / SHORT
            entry_price = float(pos['entryPrice'])
            current_price = float(pos['lastPrice']) if pos['lastPrice'] else float(pos['markPrice'])
            qty = float(pos['contracts'])
            unrealized_pnl = float(pos['unrealizedPnl'] or 0)
            initial_margin = float(pos['initialMargin'])
            leverage = int(pos['leverage'])
            
            # PnL Percentage Calculation
            # For SHORT: (Entry - Current) / Entry
            # For LONG: (Current - Entry) / Entry
            
            if side == 'LONG':
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price
                
            logger.info(f"[CHECK] {symbol} {side} x{leverage} | Entry: {entry_price} | Curr: {current_price} | PnL: {pnl_pct*100:.2f}% (${unrealized_pnl:.2f})")
            
            # --- EMERGENCY LOGIC ---
            # If PnL < -0.35% (MAX LOSS), CLOSE IT
            if pnl_pct < -0.0030: # Strict 0.30% threshold
                logger.warning(f"🚨 [EMERGENCY] {symbol} is below Stop Loss ({pnl_pct*100:.2f}% < -0.30%). CLOSING NOW.")
                
                close_side = 'sell' if side == 'LONG' else 'buy'
                try:
                    exchange.create_market_order(symbol, close_side, qty, params={'reduceOnly': True})
                    logger.info(f"✅ [CLOSED] {symbol} closed successfully.")
                    exchange.cancel_all_orders(symbol)
                except Exception as e:
                    logger.error(f"❌ [FAIL] Could not close {symbol}: {e}")
            else:
                logger.info(f"SAFE: {symbol} inside limits.")

    except Exception as e:
        logger.error(f"Sweep failed: {e}")

if __name__ == "__main__":
    if not API_KEY or not SECRET_KEY:
        logger.error("Missing API Keys in env")
    else:
        emergency_sweep()
