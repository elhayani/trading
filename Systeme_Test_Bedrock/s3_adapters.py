import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class S3ExchangeConnector:
    def __init__(self, exchange_id, historical_data):
        self.exchange_id = exchange_id
        # format: { 'BTC/USDT': [[ts, o, h, l, c, v], ...], ... }
        self.historical_data = historical_data 
        self.current_timestamp = None # Set by the test runner

    def set_timestamp(self, ts):
        self.current_timestamp = ts

    def fetch_ohlcv(self, symbol, timeframe='1h', limit=100):
        if not self.current_timestamp:
            raise ValueError("Timestamp not set in S3ExchangeConnector")
            
        data = self.historical_data.get(symbol, [])
        if not data:
            logger.warning(f"No historical data for {symbol}")
            return []

        # Filter data up to current_timestamp
        cutoff_index = len(data)
        for i, candle in enumerate(data):
            if candle[0] > self.current_timestamp:
                cutoff_index = i
                break
        
        start_index = max(0, cutoff_index - limit)
        return data[start_index:cutoff_index]

    def fetch_ticker(self, symbol):
        if not self.current_timestamp:
            raise ValueError("Timestamp not set in S3ExchangeConnector")

        data = self.historical_data.get(symbol, [])
        if not data:
            return {'last': 0.0}

        latest_candle = None
        for candle in reversed(data):
            if candle[0] <= self.current_timestamp:
                latest_candle = candle
                break
        
        if latest_candle:
            return {'last': latest_candle[4]} # Close price
        return {'last': 0.0}

class S3NewsFetcher:
    def __init__(self, news_data):
        self.news_data = news_data # List of news items
        self.current_timestamp = None

    def set_timestamp(self, ts):
        self.current_timestamp = ts

    def get_latest_news(self, symbol, hours=24, max_news=5):
        if not self.current_timestamp:
            raise ValueError("Timestamp not set in S3NewsFetcher")
            
        relevant_news = []
        limit_ts = self.current_timestamp - (hours * 3600 * 1000)

        for news in self.news_data:
            ts = news.get('timestamp')
            if not ts and news.get('date'):
                try:
                    dt = datetime.fromisoformat(news['date'].replace('Z', '+00:00'))
                    ts = int(dt.timestamp() * 1000)
                except:
                    continue
            
            if ts and limit_ts <= ts <= self.current_timestamp:
                relevant_news.append(news)
        
        relevant_news.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return relevant_news[:max_news]
        
    def get_news_context(self, symbol):
        news_items = self.get_latest_news(symbol)
        formatted = ""
        if news_items:
            formatted += "ASSET NEWS:\n"
            for item in news_items:
                title = item.get('title', 'No Title')
                formatted += f"- {title}\n"
        else:
            formatted += "ASSET NEWS: None found.\n"
        return formatted

class InMemoryDynamoDB:
    def __init__(self):
        self.tables = {}
        
    def Table(self, name):
        if name not in self.tables:
            self.tables[name] = InMemoryTable(name)
        return self.tables[name]

    def get_trades_at(self, timestamp_str):
        all_trades = []
        for table in self.tables.values():
            all_trades.extend(table.get_trades_at(timestamp_str))
        return all_trades

class InMemoryTable:
    def __init__(self, name):
        self.name = name
        self.items = []
        
    def put_item(self, Item):
        self.items.append(Item)
        logger.info(f"DynamoDB Put: {Item}")
        
    def scan(self, FilterExpression=None):
        return {'Items': self.items}

    def get_trades_at(self, timestamp_str):
        trades = []
        for item in self.items:
            # Check for trades executed at this exact timestamp (V5.1 backtest accuracy)
            if item.get('Timestamp') and item.get('Timestamp').startswith(timestamp_str):
                trades.append(item)
        return trades

    def update_item(self, Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues):
        logger.info(f"DynamoDB Update: {Key} {UpdateExpression}")
        
        # Find the item
        target_item = None
        key_name = list(Key.keys())[0]
        key_val = list(Key.values())[0]
        
        for item in self.items:
            if item.get(key_name) == key_val:
                target_item = item
                break
        
        if not target_item:
            logger.warning(f"UpdateItem: Item not found {Key}")
            return {}
            
        # Parse SET expression (simple implementation for test)
        # "set #st = :s, PnL = :p..."
        clean_expr = UpdateExpression.strip()
        if clean_expr.lower().startswith('set '):
            updates = clean_expr[4:].split(',')
            for upd in updates:
                parts = upd.split('=')
                if len(parts) == 2:
                    k = parts[0].strip()
                    v = parts[1].strip()
                    
                    # Resolve Names
                    if ExpressionAttributeNames and k in ExpressionAttributeNames:
                        k = ExpressionAttributeNames[k]
                    
                    # Resolve Values
                    if ExpressionAttributeValues and v in ExpressionAttributeValues:
                        val = ExpressionAttributeValues[v]
                        target_item[k] = val
                        
        return {}

class S3DataLoader:
    def __init__(self, historical_data):
        self.historical_data = historical_data # {symbol: [[ts, o, h, l, c, v], ...]}
        self.current_timestamp = None
        
    def set_timestamp(self, ts):
        self.current_timestamp = ts
        
    def get_latest_data(self, pair, period=None, interval=None):
        import pandas as pd
        if not self.current_timestamp:
            logger.warning("S3DataLoader: Timestamp not set")
            return None
            
        # Standardize pair name lookup
        key = pair
        if key not in self.historical_data:
            if '=' in pair:
                 key = pair.split('=')[0]
            elif '/' in pair:
                 key = pair # Keep as is
            # Try appending =X if missing
            else:
                 key = f"{pair}=X"
                 
        data = self.historical_data.get(key, [])
        if not data:
             # Fallback: check if we have it under any key matching partial?
             # Also try standard forex format (ABC/DEF -> ABCDEF)
             for k in self.historical_data.keys():
                 try:
                     if pair in k or k in pair:
                         data = self.historical_data[k]
                         break
                     # Try matching with/without slash
                     normalized_k = k.replace('/', '').replace('=', '').replace('X', '')
                     normalized_pair = pair.replace('/', '').replace('=', '').replace('X', '')
                     if normalized_k == normalized_pair:
                         data = self.historical_data[k]
                         break
                 except:
                     continue

        if not data:
            return None
            
        cutoff_index = len(data)
        found = False
        for i, candle in enumerate(data):
            if candle[0] > self.current_timestamp:
                cutoff_index = i
                found = True
                break
        
        if not found and data[-1][0] < self.current_timestamp:
            # Current time is after last data point, use all data?
            pass

        # Take enough history
        start_index = max(0, cutoff_index - 300)
        subset = data[start_index:cutoff_index]
        
        if not subset:
            return None
            
        df = pd.DataFrame(subset, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df

class MockResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json_data = json_data
        
    def json(self):
        return self._json_data

class S3RequestsMock:
    """
    Mocks requests.get calls for Macro Data (Yahoo)
    """
    def __init__(self, macro_data_map):
        self.macro_data_map = macro_data_map # {'^VIX': [...], 'DX-Y.NYB': [...]}
        self.current_timestamp = None

    def set_timestamp(self, ts):
        self.current_timestamp = ts

    def get(self, url, params=None, **kwargs):
        if not self.current_timestamp:
            raise ValueError("Timestamp not set in S3RequestsMock")

        # Parsing logic for Yahoo Chart API
        symbol = None
        if 'query1.finance.yahoo.com/v8/finance/chart/' in url:
            parts = url.split('/v8/finance/chart/')
            if len(parts) > 1:
                raw_symbol = parts[1].split('?')[0] # Remove query params
                symbol = raw_symbol.replace('%5E', '^') # Decode ^

        if symbol and symbol in self.macro_data_map:
            data = self.macro_data_map[symbol]
            current_price = 0.0
            prev_close = 0.0
            
            # Find index
            idx = -1
            for i, candle in enumerate(data):
                if candle[0] > self.current_timestamp:
                    break
                idx = i
            
            if idx >= 0:
                current_price = float(data[idx][4])
                if idx > 0:
                    prev_close = float(data[idx-1][4])
                else:
                    prev_close = current_price
            
            # Return Mock
            return MockResponse(200, {
                'chart': {
                    'result': [{
                        'meta': {
                            'regularMarketPrice': current_price,
                            'chartPreviousClose': prev_close,
                            'currency': 'USD',
                            'symbol': symbol
                        },
                        'timestamp': [int(self.current_timestamp/1000)],
                        'indicators': {
                            'quote': [{
                                'close': [current_price]
                            }]
                        }
                    }],
                    'error': None
                }
            })
            
        # Fallback for unknown URLs: return 404 or empty
        # logger.info(f"S3RequestsMock: URL not mocked {url}")
        return MockResponse(404, {'error': 'Not found in S3 mock'})

class TestContext:
    def __init__(self, request_id="test-req-id"):
        self.aws_request_id = request_id
        self.log_stream_name = "test-log-stream"
