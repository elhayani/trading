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

def make_mock_get_portfolio_context(mock_dynamodb, table_name):
    def _mock(pair):
        table = mock_dynamodb.Table(table_name) 
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
    
    # Determine table name based on asset class
    table_name = 'EmpireForexHistory'
    if asset_class == 'Indices':
        table_name = 'EmpireIndicesHistory'
    elif asset_class == 'Commodities':
        table_name = 'EmpireCommoditiesHistory'

    mock_get_portfolio = make_mock_get_portfolio_context(mock_dynamodb, table_name)
    
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
            
            # Debug Portfolio State
            if mock_dynamodb:
                try:
                    table_name = 'EmpireForexHistory' if asset_class == 'Forex' else 'EmpireIndicesHistory' if asset_class == 'Indices' else 'EmpireCommoditiesHistory'
                    if asset_class != 'Crypto':
                        tbl = mock_dynamodb.Table(table_name)
                        open_pos = [i for i in tbl.items if i.get('Status') == 'OPEN']
                        if open_pos:
                            print(f"   [Portfolio] {len(open_pos)} OPEN positions at {dt}")
                except:
                    pass
            
            try:
                response = bot_module.lambda_handler(event, context)
                
                if isinstance(response, dict):
                    body = response.get('body')
                    if body:
                        # API Gateway format
                        b = json.loads(body)
                    else:
                        # Direct invocation format
                        b = response
                        
                    signals = b.get('details', [])
                    # Handle single signal object vs list
                    if isinstance(signals, str):
                         # details might be a string message like "STOP_LOSS_AT..."
                         pass 
                    elif isinstance(signals, dict):
                        signals = [signals]
                    
                    # Special handling for text-based details from manage_exits
                    details_str = b.get('details', '')
                    if isinstance(details_str, str) and ("STOP_LOSS" in details_str or "TAKE_PROFIT" in details_str or "HARD_TP" in details_str or "TRAILING" in details_str):
                         # reconstruct a signal object for the logger
                         signals = [{'action': 'EXIT', 'result': details_str}]
                        
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
                        
                        # ✅ NEW: Also log actual BUY/LONG trades from DynamoDB
                        elif log.get('Status') == 'OPEN' and log.get('Type') in ['BUY', 'LONG', 'SHORT', 'SELL']:
                            trade_type = log.get('Type')
                            if trade_type == 'LONG': trade_type = 'BUY'
                            elif trade_type == 'SHORT': trade_type = 'SELL'
                            
                            entry_price = float(log.get('EntryPrice', close_price))
                            strategy = log.get('Strategy', 'UNKNOWN')
                            ai_decision = log.get('AI_Decision', 'N/A')
                            tp_pct = log.get('TP', '0')
                            sl_pct = log.get('SL', '0')
                            reason = f"{strategy}|AI:{ai_decision}|TP:{tp_pct}%|SL:{sl_pct}%"
                            reason = reason.replace(',', ';')
                            
                            f.write(f"{symbol},{dt.strftime('%Y-%m-%d %H:%M')},{trade_type},{entry_price:.4f},0,0,0,{reason},\n")
                            print(f"📝 Logged {trade_type} at {dt} - {strategy}")
                        
                        # ✅ NEW: Log CLOSED trades with PnL
                        elif log.get('Status') == 'CLOSED':
                            exit_reason = log.get('ExitReason', 'CLOSED')
                            pnl = log.get('PnL', '0')
                            exit_price = float(log.get('ExitPrice', close_price))
                            reason = f"{exit_reason}"
                            reason = reason.replace(',', ';')
                            
                            f.write(f"{symbol},{dt.strftime('%Y-%m-%d %H:%M')},EXIT,{exit_price:.4f},0,0,0,{reason},{pnl}\n")
                            print(f"📝 Logged EXIT at {dt} - PnL: ${pnl}")

            except Exception as e:
                logger.error(f"Error at {dt}: {e}")
                
    logger.info(f"Test complete. CSV Log saved to {log_filename}")


def fetch_crypto_from_binance(symbol, days, offset_days=0):
    """
    Fetch crypto data directly from Binance API (free, no API key needed for public data)
    """
    import requests
    from datetime import timedelta
    
    # Convert symbol format: BTC/USDT -> BTCUSDT, BTC-USD -> BTCUSDT
    binance_symbol = symbol.replace('/', '').replace('-USD', 'USDT').replace('-', '')
    
    end_time = int((datetime.now() - timedelta(days=offset_days)).timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=offset_days + days)).timestamp() * 1000)
    
    logger.info(f"📊 Fetching {binance_symbol} from Binance API...")
    
    all_data = []
    current_start = start_time
    
    while current_start < end_time:
        url = f"https://api.binance.com/api/v3/klines"
        params = {
            'symbol': binance_symbol,
            'interval': '1h',
            'startTime': current_start,
            'endTime': end_time,
            'limit': 1000
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                klines = response.json()
                if not klines:
                    break
                    
                for k in klines:
                    # Format: [ts, open, high, low, close, volume]
                    all_data.append([
                        int(k[0]),      # timestamp
                        float(k[1]),    # open
                        float(k[2]),    # high
                        float(k[3]),    # low
                        float(k[4]),    # close
                        float(k[5])     # volume
                    ])
                
                # Move to next batch
                current_start = int(klines[-1][0]) + 1
            else:
                logger.error(f"Binance API error: {response.status_code}")
                break
        except Exception as e:
            logger.error(f"Binance API request failed: {e}")
            break
    
    logger.info(f"✅ Loaded {len(all_data)} candles from Binance for {binance_symbol}")
    return all_data

def fetch_market_data_with_fallback(symbol, days, offset_days=0):
    """
    Tries to fetch from S3Loader, falls back to YFinance/Binance if empty or fails.
    """
    loader = S3Loader()
    data = []
    
    # Check if this is a crypto symbol
    is_crypto = '/' in symbol or symbol in ['BTC-USD', 'ETH-USD', 'SOL-USD', 'BTCUSDT', 'ETHUSDT']
    
    # 1. Try S3
    try:
        import pandas as pd
        data = loader.fetch_historical_data(symbol, days, offset_days)
        if data:
            logger.info(f"Loaded {len(data)} candles from S3 for {symbol}")
            return data
    except Exception as e:
        logger.warning(f"S3 Load failed for {symbol}: {e}")

    # 2. For Crypto: Use Binance API (more reliable than YFinance for crypto)
    if is_crypto:
        logger.info(f"🪙 Crypto detected, using Binance API for {symbol}...")
        try:
            data = fetch_crypto_from_binance(symbol, days, offset_days)
            if data:
                return data
        except Exception as e:
            logger.warning(f"Binance fallback failed: {e}")

    # 3. Fallback to YFinance (for stocks, forex, indices)
    logger.info(f"⚠️ S3 Empty/Failed. Falling back to YFinance for {symbol}...")
    try:
        import yfinance as yf
        from datetime import timedelta
        
        end_date = datetime.now() - timedelta(days=offset_days)
        start_date = end_date - timedelta(days=days + 5) # Buffer
        
        # Smart interval selection:
        # - For indices (^GSPC, ^NDX): use 1d if days > 30 (YF 1h limit is ~7 days for indices)
        # - For forex: 1h works well
        # - For long periods: use 1d
        is_index = symbol.startswith('^')
        
        if days > 730:
            interval = "1d"
        elif is_index and days > 30:
            interval = "1d"  # Indices have limited 1h history on YF
            logger.info(f"📈 Index detected, using 1d interval for better coverage")
        else:
            interval = "1h"
        
        logger.info(f"Downloading YF data ({interval}) for {symbol}...")
        df = yf.download(symbol, start=start_date, end=end_date, interval=interval, progress=False)
        
        if df.empty and interval == "1h":
             logger.warning("YF 1h Empty, trying 1d...")
             df = yf.download(symbol, start=start_date, end=end_date, interval="1d", progress=False)

        if not df.empty:
            # Format: [ts, open, high, low, close, volume]
            formatted_data = []
            for index, row in df.iterrows():
                try:
                    ts = int(index.timestamp() * 1000)
                    op = float(row['Open'].iloc[0]) if isinstance(row['Open'], pd.Series) else float(row['Open'])
                    hi = float(row['High'].iloc[0]) if isinstance(row['High'], pd.Series) else float(row['High'])
                    lo = float(row['Low'].iloc[0]) if isinstance(row['Low'], pd.Series) else float(row['Low'])
                    cl = float(row['Close'].iloc[0]) if isinstance(row['Close'], pd.Series) else float(row['Close'])
                    vo = float(row['Volume'].iloc[0]) if isinstance(row['Volume'], pd.Series) else float(row['Volume'])
                    
                    formatted_data.append([ts, op, hi, lo, cl, vo])
                except Exception as row_err:
                     # Handle simple float (older pandas/yfinance versions)
                    ts = int(index.timestamp() * 1000)
                    op = float(row['Open'])
                    hi = float(row['High'])
                    lo = float(row['Low'])
                    cl = float(row['Close'])
                    vo = float(row['Volume'])
                    formatted_data.append([ts, op, hi, lo, cl, vo])

            logger.info(f"Loaded {len(formatted_data)} candles from YFinance for {symbol}")
            return formatted_data
            
    except Exception as e:
        logger.error(f"YFinance Fallback failed: {e}")
        
    return []

def run_test(asset_class, symbol, days, start_date=None, offset_days=0):
    logger.info(f"Starting test for {asset_class} - {symbol} over {days} days")
    
    # Use Fallback Fetcher
    market_data = fetch_market_data_with_fallback(symbol, days, offset_days)
    
    loader = S3Loader() # Still needed for news/macro
    news_data = loader.fetch_news_data(symbol, days, offset_days)
    macro_map = load_macro_data(loader, days, offset_days)
    
    if not market_data:
        logger.error("No market data found (S3 + YF). Exiting.")
        return

    logger.info(f"Loaded {len(market_data)} candles and {len(news_data)} news items.")

    mock_dynamodb = InMemoryDynamoDB()
    s3_requests = S3RequestsMock(macro_map)

    class MockCondition:
        def __init__(self, key=None, op=None, val=None, complex_val=None):
            self.key = key
            self.op = op
            self.val = val
            self.complex_val = complex_val 

        def eq(self, other):
            return MockCondition(key=self.key, op='eq', val=other)
        
        def __and__(self, other):
            return MockCondition(op='and', complex_val=[self, other])

    def mock_attr(name):
        return MockCondition(key=name)
        
    mock_conditions = MagicMock()
    mock_conditions.Attr.side_effect = mock_attr
    mock_conditions.Key.side_effect = mock_attr

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
