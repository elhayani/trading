import ccxt
import json
import boto3
import time
from datetime import datetime
import os

# Config
import sys

# Config
# Default to 2023 if not provided
YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 2023

SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
TIMEFRAME = '1h'
BUCKET_NAME = os.environ.get('TRADING_LOGS_BUCKET', 'empire-trading-data-paris')
REGION = 'eu-west-3'

s3 = boto3.client('s3', region_name=REGION)
exchange = ccxt.binance()

def fetch_year_data(symbol, year):
    start_ts = int(datetime(year, 1, 1).timestamp() * 1000)
    end_ts = int(datetime(year + 1, 1, 1).timestamp() * 1000)
    
    all_ohlcv = []
    since = start_ts
    
    print(f"📥 Fetching {symbol} for {year}...")
    
    while since < end_ts:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, since=since, limit=1000)
            if not ohlcv:
                break
            
            # Filter matches only for this year (just in case)
            # Actually fetch_ohlcv returns candles starting from `since`.
            
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 3600000 # +1 hour roughly, or just use last timestamp
             # Safer: use last timestamp + 1ms to avoid dupes? 
             # CCXT usually handles 'since' as inclusive.
             # Moving since to last_time + 1 period duration is standard.
            since = ohlcv[-1][0] + 1 
            
            print(f"   Fetched {len(ohlcv)} candles, last: {datetime.fromtimestamp(ohlcv[-1][0]/1000)}")
            
            # Sleep to avoid rate limits
            time.sleep(0.1)
            
            if ohlcv[-1][0] >= end_ts:
                break
                
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(1)
            
    # Filter strictly for the year
    filtered = [c for c in all_ohlcv if start_ts <= c[0] < end_ts]
    
    # Remove duplicates if any
    filtered_unique = []
    seen_ts = set()
    for c in filtered:
        if c[0] not in seen_ts:
            filtered_unique.append(c)
            seen_ts.add(c[0])
            
    filtered_unique.sort(key=lambda x: x[0])
    
    return filtered_unique

def upload_to_s3(symbol, data):
    formatted_symbol = symbol.replace('/', '_')
    key = f"historical/{formatted_symbol}/{YEAR}.json"
    
    print(f"📤 Uploading {key} ({len(data)} candles) to {BUCKET_NAME}...")
    
    try:
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=key,
            Body=json.dumps(data),
            ContentType='application/json'
        )
        print("✅ Upload success.")
    except Exception as e:
        print(f"❌ Upload failed: {e}")

def main():
    if not BUCKET_NAME:
        print("❌ Error: Bucket name not set.")
        return

    for symbol in SYMBOLS:
        data = fetch_year_data(symbol, YEAR)
        if data:
            upload_to_s3(symbol, data)
        else:
            print(f"⚠️ No data fetched for {symbol}")

if __name__ == "__main__":
    main()
