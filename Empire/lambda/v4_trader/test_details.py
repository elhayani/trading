import json
import os
import sys
import logging

# Add the lambda directory to path
sys.path.append('/Users/zakaria/Trading/Empire/lambda/v4_trader')

from lambda2_closer import lambda_handler, get_memory_open_positions, check_and_close_position, load_binance_credentials, fetch_mark_prices_snapshot
from exchange_connector import ExchangeConnector
from config import TradingConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('test')

# Set environment variables
os.environ['STATE_TABLE'] = 'V4TradingState'
os.environ['AWS_REGION'] = 'ap-northeast-1'
os.environ['SECRET_NAME'] = 'trading/binance'
os.environ['LOG_LEVEL'] = 'INFO'

def test_details():
    creds = load_binance_credentials()
    live_mode = TradingConfig.LIVE_MODE
    exchange = ExchangeConnector(
        api_key=creds['api_key'],
        secret=creds['secret_key'],
        live_mode=live_mode
    )
    
    open_positions = get_memory_open_positions()
    print(f"DEBUG: Found {len(open_positions)} open positions in memory")
    
    mark_prices = fetch_mark_prices_snapshot(demo_mode=not live_mode)
    print(f"DEBUG: Fetched {len(mark_prices)} mark prices from WS")
    
    for symbol, position in open_positions.items():
        print(f"\n--- Checking {symbol} ---")
        print(f"Position data: Entry={position['entry_price']}, SL={position.get('stop_loss')}, TP={position.get('take_profit')}")
        
        # Check WS price
        lookup = symbol.replace(':USDT', '').replace(':BUSD', '').replace('/', '')
        ws_price = mark_prices.get(lookup)
        print(f"WS Mark Price for {lookup}: {ws_price}")
        
        # Check REST price
        try:
            ticker = exchange.fetch_ticker(symbol)
            print(f"REST Price for {symbol}: {ticker['last']}")
        except Exception as e:
            print(f"REST Price fetch FAILED for {symbol}: {e}")
            
        # Try to check position on exchange
        try:
            from lambda2_closer import _get_position_risk
            risk = _get_position_risk(exchange, symbol)
            if risk:
                print(f"Exchange Risk: Amt={risk.get('positionAmt')}, PnL={risk.get('unRealizedProfit')}, Mark={risk.get('markPrice')}")
            else:
                print("Exchange Risk: No position found or fetch failed")
        except Exception as e:
            print(f"Exchange Risk fetch FAILED: {e}")

if __name__ == "__main__":
    test_details()
