#!/usr/bin/env python3
"""
Script pour convertir les CSVs locaux au format S3 attendu par le backtest
et les uploader.
"""
import os
import json
import boto3
import pandas as pd
from datetime import datetime

# Config
LOCAL_DATA_DIR = "/Users/zakaria/Trading/tests/data"
S3_BUCKET = "empire-trading-data-paris"
S3_REGION = "eu-west-3"

# Mapping nom fichier -> symbole ccxt
FILE_TO_SYMBOL = {
    'BTCUSD': 'BTC_USDT',
    'ETHUSD': 'ETH_USDT',
    'SOLUSD': 'SOL_USDT',
    'EURUSD': 'EUR_USD',
    'GBPUSD': 'GBP_USD',
    'USDJPY': 'USD_JPY'
}

s3 = boto3.client('s3', region_name=S3_REGION)

def convert_csv_to_ohlcv_json(csv_path):
    """
    Convert CSV to OHLCV JSON format: [[timestamp_ms, open, high, low, close, volume], ...]
    """
    df = pd.read_csv(csv_path)
    
    # Parse timestamp
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Convert to OHLCV format (ccxt-like)
    ohlcv = []
    for _, row in df.iterrows():
        ts_ms = int(row['timestamp'].timestamp() * 1000)
        ohlcv.append([
            ts_ms,
            float(row['open']),
            float(row['high']),
            float(row['low']),
            float(row['close']),
            float(row['volume']) if pd.notna(row['volume']) else 0
        ])
    
    return ohlcv

def upload_to_s3(symbol, year, data):
    """Upload JSON data to S3"""
    key = f"historical/{symbol}/{year}.json"
    body = json.dumps(data)
    
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=body,
        ContentType='application/json'
    )
    print(f"✅ Uploaded: s3://{S3_BUCKET}/{key} ({len(data)} candles)")

def main():
    print(f"📥 Converting and uploading data to S3: {S3_BUCKET}")
    print("-" * 60)
    
    files = [f for f in os.listdir(LOCAL_DATA_DIR) if f.endswith('.csv')]
    
    for filename in sorted(files):
        filepath = os.path.join(LOCAL_DATA_DIR, filename)
        
        # Parse filename (e.g., BTCUSD_180d.csv)
        base_name = filename.split('_')[0]  # BTCUSD
        
        if base_name not in FILE_TO_SYMBOL:
            print(f"⚠️ Skipping unknown: {filename}")
            continue
            
        symbol = FILE_TO_SYMBOL[base_name]
        
        # Convert
        ohlcv = convert_csv_to_ohlcv_json(filepath)
        
        if not ohlcv:
            print(f"⚠️ No data in: {filename}")
            continue
        
        # Group by year
        by_year = {}
        for candle in ohlcv:
            ts = candle[0] / 1000
            year = datetime.fromtimestamp(ts).year
            if year not in by_year:
                by_year[year] = []
            by_year[year].append(candle)
        
        # Upload each year
        for year, year_data in by_year.items():
            upload_to_s3(symbol, year, year_data)
    
    print("-" * 60)
    print("✅ Done!")

if __name__ == "__main__":
    main()
