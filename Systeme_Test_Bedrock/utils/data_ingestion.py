import sys
import os
import argparse
import logging
import json
import boto3
import time
from datetime import datetime, timedelta

# Dependencies
try:
    import ccxt
    import yfinance as yf
    import pandas as pd
except ImportError as e:
    print(f"Missing dependency: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BUCKET_NAME = os.environ.get('TRADING_LOGS_BUCKET', 'empire-trading-data-paris')
REGION = 'eu-west-3'

s3_client = boto3.client('s3', region_name=REGION)

def upload_to_s3(key, data):
    try:
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=key,
            Body=json.dumps(data),
            ContentType='application/json'
        )
        logger.info(f"✅ Uploaded {key} to S3")
    except Exception as e:
        logger.error(f"❌ Failed to upload {key}: {e}")

def fetch_crypto_data(symbol, days):
    logger.info(f"Fetching Crypto data for {symbol} ({days} days)")
    exchange = ccxt.binance()
    
    # Calculate start time
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=days)).isoformat())
    
    all_ohlcv = []
    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, '1h', since=since, limit=1000)
            if not ohlcv:
                break
            
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
            
            # Stop if we reached now
            if since > exchange.milliseconds():
                break
                
            time.sleep(exchange.rateLimit / 1000)
            
        except Exception as e:
            logger.error(f"Error fetching: {e}")
            break
            
    logger.info(f"Fetched {len(all_ohlcv)} candles")
    return all_ohlcv

def fetch_yfinance_data(symbol, days):
    logger.info(f"Fetching Market data for {symbol} ({days} days) via yfinance")
    
    # yfinance symbol adjustment
    yf_symbol = symbol
    if symbol == 'EURUSD': yf_symbol = 'EURUSD=X'
    if symbol == 'USDJPY': yf_symbol = 'USDJPY=X'
    # Add other mappings if needed
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    df = yf.download(yf_symbol, start=start_date, end=end_date, interval="1h", progress=False)
    
    if df.empty:
        logger.warning(f"No data for {yf_symbol}")
        return []
        
    # Convert to list of [ts, o, h, l, c, v]
    data = []
    for index, row in df.iterrows():
        ts = int(index.timestamp() * 1000)
        # Handle multi-index columns if present
        try:
            o = float(row['Open'].iloc[0]) if isinstance(row['Open'], pd.Series) else float(row['Open'])
            h = float(row['High'].iloc[0]) if isinstance(row['High'], pd.Series) else float(row['High'])
            l = float(row['Low'].iloc[0]) if isinstance(row['Low'], pd.Series) else float(row['Low'])
            c = float(row['Close'].iloc[0]) if isinstance(row['Close'], pd.Series) else float(row['Close'])
            v = float(row['Volume'].iloc[0]) if isinstance(row['Volume'], pd.Series) else float(row['Volume'])
        except:
             o = float(row['Open'])
             h = float(row['High'])
             l = float(row['Low'])
             c = float(row['Close'])
             v = float(row['Volume'])
             
        data.append([ts, o, h, l, c, v])
        
    logger.info(f"Fetched {len(data)} candles")
    return data

def fetch_news(symbol, days):
    """
    Simulate fetching historical news via yfinance.
    Note: yfinance only provides very recent news usually.
    For backfilling history, we'd need a paid API. 
    Here we do best effort: get what yfinance has.
    """
    logger.info(f"Fetching News for {symbol}")
    
    yf_symbol = symbol
    if symbol == 'EURUSD': yf_symbol = 'EURUSD=X'
    if symbol == 'USDJPY': yf_symbol = 'USDJPY=X'

    ticker = yf.Ticker(yf_symbol)
    news = ticker.news
    
    processed_news = []
    for item in news:
        # Check if it falls within the requested period?
        # yfinance news doesn't always have a clean timestamp in recent versions, checking 'providerPublishTime'
        ts = item.get('providerPublishTime')
        if ts:
             dt = datetime.fromtimestamp(ts)
             if dt > (datetime.now() - timedelta(days=days)):
                 processed_news.append({
                     'timestamp': ts * 1000,
                     'date': dt.isoformat(),
                     'title': item.get('title'),
                     'publisher': item.get('publisher'),
                     'link': item.get('link'),
                     'type': 'yfinance_news'
                 })
    
    logger.info(f"Found {len(processed_news)} recent news items")
    return processed_news

def process_ingestion(asset_class, symbol, days):
    # 1. Fetch Market Data
    if asset_class == 'Crypto':
        ohlcv = fetch_crypto_data(symbol, days)
    else:
        ohlcv = fetch_yfinance_data(symbol, days)
        
    if not ohlcv:
        logger.error("No data fetched. Aborting.")
        return

    # 2. Group by Year and Save
    safe_symbol = symbol.replace('/', '_')
    data_by_year = {}
    
    for candle in ohlcv:
        ts = candle[0]
        year = datetime.fromtimestamp(ts/1000).year
        if year not in data_by_year:
            data_by_year[year] = []
        data_by_year[year].append(candle)
        
    for year, data in data_by_year.items():
        # TODO: Should we merge with existing S3 data?
        # For now, simplistic overwrite or append logic could be complex without downloading first.
        # User said "completer the data".
        # Safe strategy: Download existing year file, merge, upload.
        
        key = f"historical/{safe_symbol}/{year}.json"
        
        # Try download existing
        existing_data = []
        try:
            resp = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
            existing_data = json.loads(resp['Body'].read().decode('utf-8'))
            logger.info(f"Downloaded existing data for {year}: {len(existing_data)} records")
        except:
            pass
            
        # Merge: Use dict to dedup by timestamp
        merged = {x[0]: x for x in existing_data}
        for candle in data:
            merged[candle[0]] = candle
            
        final_data = sorted(merged.values(), key=lambda x: x[0])
        
        upload_to_s3(key, final_data)
        
    # 3. Fetch and Save News
    news = fetch_news(symbol, days)
    if news:
        # Group by year
        news_by_year = {}
        for n in news:
            year = datetime.fromtimestamp(n['timestamp']/1000).year
            if year not in news_by_year:
                news_by_year[year] = []
            news_by_year[year].append(n)
            
        for year, data in news_by_year.items():
            key = f"news/{safe_symbol}/{year}.json"
            
            existing_news = []
            try:
                resp = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
                existing_news = json.loads(resp['Body'].read().decode('utf-8'))
            except:
                pass
                
            # Merge news (dedup by link or title)
            # using link as unique ID
            merged_news = {x.get('link'): x for x in existing_news}
            for n in data:
                merged_news[n.get('link')] = n
                
            final_news = sorted(merged_news.values(), key=lambda x: x.get('timestamp', 0))
            upload_to_s3(key, final_news)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--asset-class', required=True, choices=['Crypto', 'Forex', 'Indices', 'Commodities'])
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--days', type=int, default=30)
    
    args = parser.parse_args()
    
    process_ingestion(args.asset_class, args.symbol, args.days)
