import sys
import os
import argparse
import logging
from datetime import datetime
import json
from unittest.mock import patch, MagicMock

# Add utils to path
sys.path.append(os.path.dirname(__file__))
from utils.s3_loader import S3Loader
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
        import v4_hybrid_lambda as bot_module
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
    
    # Patch S3 components + Requests (for VIX/Macro)
    # Note: requests is imported in v4_hybrid_lambda AND macro_context
    # We patch it where it is used.
    
    with patch(f'{module_name}.ExchangeConnector') as MockExchangeClass, \
         patch(f'{module_name}.NewsFetcher') as MockNewsClass, \
         patch(f'{module_name}.requests.get', side_effect=s3_requests.get): # Patch requests inside module
        
        MockExchangeClass.return_value = mock_exchange_conn
        MockNewsClass.return_value = mock_news_fetcher
        
        run_loop(bot_module, 'Crypto', symbol, market_data, mock_exchange_conn, mock_news_fetcher, s3_requests)

def run_test_forex_indices_commodities(bot_module, asset_class, symbol, market_data, news_data, mock_dynamodb, s3_requests):
    # Forex/Indices/Commodities use static DataLoader and global news_fetcher instance
    
    mock_loader = S3DataLoader({symbol: market_data})
    mock_news_fetcher = S3NewsFetcher(news_data)

    module_name = bot_module.__name__
    
    # Patch requests in macro_context if imported?
    # Forex bot imports macro_context.
    # macro_context imports requests.
    # So we need to patch `macro_context.requests.get`? 
    # Or generically patch requests.get globally for the duration?
    # Since we can't easily predict all imports, global patch is risky but effective if scoped.
    # But patching 'bot_module.macro_context.requests.get' might work.
    
    # We can patch `requests.get` globally in `run_loop` context?
    # However, `patch` works on *where it is looked up*.
    
    # Let's try patching `requests.get` on the `requests` module itself before calling handler.
    # But we need to import requests here to patch it?
    import requests
    
    with patch(f'{module_name}.DataLoader') as MockDataLoaderPatch, \
         patch(f'{module_name}.news_fetcher', mock_news_fetcher), \
         patch('requests.get', side_effect=s3_requests.get): # Global patch for requests

        # DataLoader is static
        MockDataLoaderPatch.get_latest_data.side_effect = mock_loader.get_latest_data
        
        run_loop(bot_module, asset_class, symbol, market_data, mock_loader, mock_news_fetcher, s3_requests)

def run_loop(bot_module, asset_class, symbol, market_data, mock_data_provider, mock_news_provider, s3_requests):
    results = []
    
    # Skip first 200 candles for warm-up
    start_idx = min(200, len(market_data)-1)
    
    logger.info(f"Starting loop from candle {start_idx} to {len(market_data)}")
    
    for i in range(start_idx, len(market_data)):
        candle = market_data[i]
        timestamp = candle[0]
        dt = datetime.fromtimestamp(timestamp/1000)
        
        # Update mocks with current time
        mock_data_provider.set_timestamp(timestamp)
        mock_news_provider.set_timestamp(timestamp)
        s3_requests.set_timestamp(timestamp)
        
        # Create Event
        event = {
            'symbol': symbol,
            'asset_class': asset_class,
            'is_test': True
        }
        context = TestContext()
        
        # Call Handler
        try:
            response = bot_module.lambda_handler(event, context)
            
            # Extract status
            status = "UNKNOWN"
            if isinstance(response, dict):
                body = response.get('body')
                if body:
                    try:
                        b = json.loads(body)
                        signals = b.get('signals_found', 0)
                        status = f"SIGNALS: {signals}"
                        if signals > 0:
                            logger.info(f"✅ {dt} - Signal Found: {b.get('details')}")
                    except:
                        pass
                else:
                    status = response.get('status', 'OK')
                
                # Check for skipped reasons
                if 'SKIPPED' in str(status) or 'BLOCKED' in str(status):
                     pass
                     # logger.info(f"Refused: {status}")

            results.append({
                'timestamp': dt.isoformat(),
                'status': status,
                'response': response
            })
        except Exception as e:
            logger.error(f"Error at {dt}: {e}")
    
    # Save results
    output_file = f"test_results_{asset_class}_{symbol.replace('/','_')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2) #, default=str)
    
    logger.info(f"Test complete. Results saved to {output_file}")


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
    with patch('boto3.resource') as mock_resource:
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
