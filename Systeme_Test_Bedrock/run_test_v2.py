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

# Fake DateTime class for mocking
class FakeDateTime(datetime):
    _current_time = datetime(2020, 1, 1)

    @classmethod
    def utcnow(cls):
        return cls._current_time

    @classmethod
    def now(cls, tz=None):
        return cls._current_time

    @classmethod
    def set_time(cls, new_time):
        cls._current_time = new_time

def make_mock_get_portfolio_context(mock_dynamodb):
    def _mock(pair):
        table = mock_dynamodb.Table('EmpireIndicesHistory') 
        all_items = table.items
        
        open_trades = [item for item in all_items if item.get('Pair') == pair and item.get('Status') == 'OPEN']
        
        pair_trades = [item for item in all_items if item.get('Pair') == pair and item.get('Type') in ['BUY', 'SELL', 'LONG', 'SHORT']]
        pair_trades.sort(key=lambda x: x.get('Timestamp', ''), reverse=True)
        last_trade = pair_trades[0] if pair_trades else None
        
        return {
            'exposure': len(open_trades),
            'last_trade': last_trade,
            'open_trades': open_trades
        }
    return _mock

def run_test_crypto(bot_module, symbol, market_data, news_data, mock_dynamodb, s3_requests):
    # Prepare Mocks
    mock_exchange_conn = S3ExchangeConnector(exchange_id='binance', historical_data={symbol: market_data})
    mock_news_fetcher = S3NewsFetcher(news_data)

    module_name = bot_module.__name__
    
    with patch(f'{module_name}.ExchangeConnector') as MockExchangeClass, \
         patch(f'{module_name}.get_news_context', side_effect=mock_news_fetcher.get_news_context), \
         patch(f'{module_name}.requests.get', side_effect=s3_requests.get), \
         patch(f'{module_name}.datetime', FakeDateTime):
        
        MockExchangeClass.return_value = mock_exchange_conn
        
        run_loop(bot_module, 'Crypto', symbol, market_data, mock_exchange_conn, mock_news_fetcher, s3_requests, mock_dynamodb)

def run_test_forex_indices_commodities(bot_module, asset_class, symbol, market_data, news_data, mock_dynamodb, s3_requests):
    mock_loader = S3DataLoader({symbol: market_data})
    mock_news_fetcher = S3NewsFetcher(news_data)

    module_name = bot_module.__name__
    
    import requests
    strategies_module = sys.modules.get('strategies')
    
    # Patch CONFIGURATION
    original_config = getattr(bot_module, 'CONFIGURATION', {})
    if symbol in original_config:
        patched_config = {symbol: original_config[symbol]}
    else:
        patched_config = original_config
    
    mock_get_portfolio = make_mock_get_portfolio_context(mock_dynamodb)
    
    # Mock Bedrock to avoid hanging/cost and ensure deterministic test
    mock_ask_bedrock = MagicMock(return_value={'decision': 'CONFIRM', 'reason': 'Test Mock: Strategy Valid'})

    with patch(f'{module_name}.DataLoader') as MockDataLoaderPatch, \
         patch(f'{module_name}.news_fetcher', mock_news_fetcher), \
         patch(f'{module_name}.ask_bedrock', mock_ask_bedrock), \
         patch('requests.get', side_effect=s3_requests.get), \
         patch(f'{module_name}.datetime', FakeDateTime), \
         patch(f'{module_name}.CONFIGURATION', patched_config), \
         patch(f'{module_name}.get_portfolio_context', side_effect=mock_get_portfolio), \
         patch.object(strategies_module, 'is_within_golden_window', return_value=True) if strategies_module else patch('strategies.is_within_golden_window', return_value=True), \
         patch.object(strategies_module, 'get_session_phase', return_value={'is_tradeable': True, 'aggressiveness': 'HIGH'}) if strategies_module else patch('strategies.get_session_phase', return_value={'is_tradeable': True, 'aggressiveness': 'HIGH'}), \
         patch.object(strategies_module, 'check_volume_veto', return_value={'veto': False, 'reason': 'TEST'}) if strategies_module else patch('strategies.check_volume_veto', return_value={'veto': False}):


        MockDataLoaderPatch.get_latest_data.side_effect = mock_loader.get_latest_data
        
        run_loop(bot_module, asset_class, symbol, market_data, mock_loader, mock_news_fetcher, s3_requests, mock_dynamodb)

def run_loop(bot_module, asset_class, symbol, market_data, mock_data_provider, mock_news_provider, s3_requests, mock_dynamodb=None):
    # Create CSV log file
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"backtest_{asset_class}_{symbol.replace('/', '_')}_{timestamp_str}.log"
    
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
            
            # Update mocks
            mock_data_provider.set_timestamp(timestamp)
            mock_news_provider.set_timestamp(timestamp)
            s3_requests.set_timestamp(timestamp)
            FakeDateTime.set_time(dt)
            
            event = {
                'symbol': symbol,
                'asset_class': asset_class,
                'is_test': True,
                'timestamp': dt.isoformat()
            }
            context = TestContext()
            
            try:
                response = bot_module.lambda_handler(event, context)
                
                if isinstance(response, dict):
                    body = response.get('body')
                    if body:
                        b = json.loads(body)
                        signals = b.get('details', [])
                        
                        for signal in signals:
                            if signal.get('action') == 'EXIT':
                                reason = signal.get('result', 'EXIT')
                                profit = "0.0" 
                                # Parse profit from reason if possible: CLOSED_X_TRADES_PNL_$10.00
                                if "PNL_" in reason:
                                    try:
                                        profit = reason.split("PNL_")[1]
                                    except: pass
                                    
                                f.write(f"{symbol},{dt.strftime('%Y-%m-%d %H:%M')},SELL,{close_price:.4f},0,0,0,{reason},{profit}\n")
                                print(f"📝 Logged SELL at {dt}")

                            elif signal.get('signal') in ['BUY', 'LONG', 'SHORT', 'SELL']:
                                rsi = signal.get('rsi', 0)
                                atr = signal.get('atr', 0)
                                reason = f"RSI{int(rsi)}+CONFIRM"
                                direction = signal.get('signal')
                                if direction == 'LONG': direction = 'BUY'
                                elif direction == 'SHORT': direction = 'SELL'
                                
                                f.write(f"{symbol},{dt.strftime('%Y-%m-%d %H:%M')},{direction},{close_price:.4f},{rsi:.1f},0,{atr:.4f},{reason},\n")
                                print(f"📝 Logged {direction} at {dt}")
                
                if mock_dynamodb:
                    logs = mock_dynamodb.get_trades_at(dt.isoformat())
                    for log in logs:
                        if log.get('Status') == 'SKIPPED':
                            reason = log.get('ExitReason', 'NO_SIGNAL')
                            reason = reason.replace(',', ';') 
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
    
    loader = S3Loader()
    market_data = loader.fetch_historical_data(symbol, days, offset_days)
    news_data = loader.fetch_news_data(symbol, days, offset_days)
    macro_map = load_macro_data(loader, days, offset_days)
    
    if not market_data:
        logger.error("No market data found. Exiting.")
        return

    logger.info(f"Loaded {len(market_data)} candles and {len(news_data)} news items.")

    mock_dynamodb = InMemoryDynamoDB()
    s3_requests = S3RequestsMock(macro_map)

    class MockCondition:
        def __init__(self, value='MOCK'):
            self.value = value
        def eq(self, other):
            return MockCondition(f"{self.value} == {other}")
        def __and__(self, other):
            return MockCondition(f"{self.value} & {other.value}")
            
    mock_condition_builder = MagicMock()
    mock_condition_builder.eq.side_effect = lambda val: MockCondition(f"EQ({val})")
    mock_conditions = MagicMock()
    mock_conditions.Attr.return_value = mock_condition_builder
    mock_conditions.Key.return_value = mock_condition_builder

    with patch('boto3.resource') as mock_resource, \
         patch('boto3.dynamodb.conditions', mock_conditions, create=True):
        
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
