import sys
import os
import argparse
import logging
from datetime import datetime
import json
from unittest.mock import patch, MagicMock
import time

# Add utils to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
# Add utils to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
from s3_loader import S3Loader
from s3_adapters import S3ExchangeConnector, S3NewsFetcher, InMemoryDynamoDB, TestContext, S3DataLoader, S3RequestsMock

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths for bots
BOT_PATHS = {
    'Crypto': '/Users/zakaria/Trading/Crypto/lambda/v4_trader',
    'Forex': '/Users/zakaria/Trading/Forex/lambda/forex_trader',
    'Indices': '/Users/zakaria/Trading/Indices/lambda/indices_trader', 
    'Commodities': '/Users/zakaria/Trading/Commodities/lambda/commodities_trader'
}

def load_bot_module(asset_class):
    path = BOT_PATHS.get(asset_class)
    if not path:
        raise ValueError(f"Unknown asset class: {asset_class}")
    
    sys.path.append(path)
    
    # Import based on file name conventions
    if asset_class == 'Crypto':
        import v4_hybrid_lambda as bot_module  # Use STANDARD version for testing
    elif asset_class == 'Forex':
        import lambda_function as bot_module 
    elif asset_class == 'Indices':
        import lambda_function as bot_module
    elif asset_class == 'Commodities':
        import lambda_function as bot_module
        
    return bot_module

def load_macro_data(loader, days, offset_days=0):
    # Try to load Macro symbols if available in S3
    macro_map = {}
    macro_symbols = ['^VIX', 'DX-Y.NYB', '^TNX'] # VIX, DXY, US10Y
    
    for sym in macro_symbols:
        data = loader.fetch_historical_data(sym, days, offset_days)
        if data:
            macro_map[sym] = data
            logger.info(f"Loaded Macro data for {sym}: {len(data)} candles")
            
    return macro_map

def run_test_crypto(bot_module, symbol, market_data, news_data, mock_dynamodb, s3_requests):
    # Prepare Mocks
    mock_exchange_conn = S3ExchangeConnector(exchange_id='binance', historical_data={symbol: market_data})
    mock_news_fetcher = S3NewsFetcher(news_data)

    module_name = bot_module.__name__
    
    # Crypto bot imports:
    # - from exchange_connector import ExchangeConnector
    # - from news_fetcher import get_news_context (function, not class!)
    # - requests (for macro data)
    
    # We need to patch:
    # 1. ExchangeConnector class
    # 2. get_news_context function
    # 3. requests.get for macro data
    
    with patch(f'{module_name}.ExchangeConnector') as MockExchangeClass, \
         patch(f'{module_name}.get_news_context', side_effect=mock_news_fetcher.get_news_context), \
         patch(f'{module_name}.requests.get', side_effect=s3_requests.get):
        
        MockExchangeClass.return_value = mock_exchange_conn
        
        run_loop(bot_module, 'Crypto', symbol, market_data, mock_exchange_conn, mock_news_fetcher, s3_requests, mock_dynamodb)

def run_test_forex_indices_commodities(bot_module, asset_class, symbol, market_data, news_data, mock_dynamodb, s3_requests):
    # Forex/Indices/Commodities use static DataLoader and global news_fetcher instance
    
    mock_loader = S3DataLoader({symbol: market_data})
    mock_news_fetcher = S3NewsFetcher(news_data)

    module_name = bot_module.__name__
    
    import requests
    
    with patch(f'{module_name}.DataLoader') as MockDataLoaderPatch, \
         patch(f'{module_name}.news_fetcher', mock_news_fetcher), \
         patch('requests.get', side_effect=s3_requests.get): # Global patch for requests

        # DataLoader is static
        MockDataLoaderPatch.get_latest_data.side_effect = mock_loader.get_latest_data
        
        run_loop(bot_module, asset_class, symbol, market_data, mock_loader, mock_news_fetcher, s3_requests, mock_dynamodb)

def run_loop(bot_module, asset_class, symbol, market_data, mock_data_provider, mock_news_provider, s3_requests, mock_dynamodb=None):
    # Create CSV log file
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"backtest_{asset_class}_{symbol.replace('/', '_')}_{timestamp_str}.log"
    
    # Skip first 200 candles for warm-up
    start_idx = min(200, len(market_data)-1)
    logger.info(f"Starting loop from candle {start_idx} to {len(market_data)}")
    
    with open(log_filename, 'w') as f:
        # Write Header
        f.write("SYMBOL,TIMESTAMP,TYPE,PRICE,RSI,SMA200,ATR,REASON,PROFIT\n")
        
        for i in range(start_idx, len(market_data)):
            candle = market_data[i]
            timestamp = candle[0]
            dt = datetime.fromtimestamp(timestamp/1000)
            close_price = candle[4]
            
            # Update mocks with current time
            mock_data_provider.set_timestamp(timestamp)
            mock_news_provider.set_timestamp(timestamp)
            s3_requests.set_timestamp(timestamp)
            
            # Create Event
            event = {
                'symbol': symbol,
                'asset_class': asset_class,
                'is_test': True,
                'timestamp': dt.isoformat()
            }
            context = TestContext()
            
            # Call Handler
            try:
                # Capture logs to check for trade executions
                with patch('logging.Logger.info') as mock_info, \
                     patch('logging.Logger.warning') as mock_warn:
                    
                    response = bot_module.lambda_handler(event, context)
                    
                    # 1. Check Response for Executed Trades (Standard Path)
                    if isinstance(response, dict):
                        body = response.get('body')
                        if body:
                            b = json.loads(body)
                            signals = b.get('details', [])
                            
                            for signal in signals:
                                # ENTRY SIGNAL
                                if signal.get('action') == 'EXIT':
                                    reason = signal.get('result', 'EXIT')
                                    profit = "0.0" 
                                    f.write(f"{symbol},{dt.strftime('%Y-%m-%d %H:%M')},SELL,{close_price:.4f},0,0,0,{reason},{profit}\n")
                                    print(f"📝 Logged SELL at {dt}")

                                elif signal.get('signal') in ['BUY', 'LONG', 'SHORT', 'SELL']:
                                    # Entry
                                    rsi = signal.get('rsi', 0)
                                    atr = signal.get('atr', 0)
                                    reason = f"RSI{int(rsi)}+CONFIRM"
                                    
                                    # Determine direction
                                    direction = signal.get('signal')
                                    if direction == 'LONG': direction = 'BUY'
                                    elif direction == 'SHORT': direction = 'SELL'
                                    
                                    f.write(f"{symbol},{dt.strftime('%Y-%m-%d %H:%M')},{direction},{close_price:.4f},{rsi:.1f},0,{atr:.4f},{reason},\n")
                                    print(f"📝 Logged {direction} at {dt}")
                    
                    # 2. Check DynamoDB for SKIPPED logs (No Signal Reason)
                    if mock_dynamodb:
                        logs = mock_dynamodb.get_trades_at(dt.isoformat())
                        for log in logs:
                            if log.get('Status') == 'SKIPPED':
                                reason = log.get('ExitReason', 'NO_SIGNAL')
                                # Clean up reason for CSV
                                reason = reason.replace(',', ';') 
                                
                                # Extract RSI from reason if present (e.g., "NO_SIGNAL: RSI=50.0 | ...")
                                rsi_val = 0
                                if 'RSI=' in reason:
                                    try:
                                        rsi_str = reason.split('RSI=')[1].split('|')[0].strip()
                                        rsi_val = float(rsi_str)
                                    except: pass
                                
                                f.write(f"{symbol},{dt.strftime('%Y-%m-%d %H:%M')},WAIT,{close_price:.4f},{rsi_val:.1f},0,0,{reason},\n")

            except Exception as e:
                logger.error(f"Error at {dt}: {e}")
                
    logger.info(f"Test complete. CSV Log saved to {log_filename}")


def run_test(asset_class, symbol, days, start_date=None, offset_days=0):
    logger.info(f"Starting test for {asset_class} - {symbol} over {days} days")
    
    # 1. Load Data from S3
    loader = S3Loader()
    market_data = loader.fetch_historical_data(symbol, days, offset_days)
    news_data = loader.fetch_news_data(symbol, days, offset_days)
    
    # Load Macro data
    macro_map = load_macro_data(loader, days, offset_days)
    
    if not market_data:
        logger.error("No market data found. Exiting.")
        return

    logger.info(f"Loaded {len(market_data)} candles and {len(news_data)} news items.")

    mock_dynamodb = InMemoryDynamoDB()
    s3_requests = S3RequestsMock(macro_map)

    # 2. Setup Patches & Import Bot
    
    # Mock boto3.dynamodb.conditions.Attr
    class MockCondition:
        def __init__(self, value='MOCK'):
            self.value = value
        def eq(self, other):
            return MockCondition(f"{self.value} == {other}")
        def __and__(self, other):
            return MockCondition(f"{self.value} & {other.value}")
            
    mock_attr = MagicMock()
    mock_attr.eq.side_effect = lambda val: MockCondition(f"EQ({val})")
    
    # We need Attr to return an object that has .eq method which returns a MockCondition
    # Actually, Attr('Status') returns an object that has .eq('OPEN')
    # .eq('OPEN') returns a Condition object that has .__and__
    
    mock_condition_builder = MagicMock()
    mock_condition_builder.eq.side_effect = lambda val: MockCondition(f"EQ({val})")
    
    mock_conditions = MagicMock()
    mock_conditions.Attr.return_value = mock_condition_builder
    mock_conditions.Key.return_value = mock_condition_builder

    # Apply patches
    with patch('boto3.resource') as mock_resource, \
         patch('boto3.dynamodb.conditions', mock_conditions, create=True):  # Create mock if not exists
        
        mock_resource.return_value = mock_dynamodb
        
        try:
            bot_module = load_bot_module(asset_class)
        except ImportError as e:
            logger.error(f"Failed to import bot module: {e}")
            return
            
        if asset_class == 'Crypto':
            run_test_crypto(bot_module, symbol, market_data, news_data, mock_dynamodb, s3_requests)
        else:
            run_test_forex_indices_commodities(bot_module, asset_class, symbol, market_data, news_data, mock_dynamodb, s3_requests)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--asset-class', required=True, choices=['Crypto', 'Forex', 'Indices', 'Commodities'])
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--offset-days', type=int, default=0, help="Days to shift back from today (default 0)")
    
    args = parser.parse_args()
    
    run_test(args.asset_class, args.symbol, args.days, offset_days=args.offset_days)
