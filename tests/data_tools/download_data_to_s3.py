#!/usr/bin/env python3
"""
Télécharge les données historiques (Crypto/Forex) et les stocke sur S3.
Sert de 'Data Lake' pour le backtest historique sur les 6 dernières années.
"""
import ccxt
import yfinance as yf
import pandas as pd
import boto3
import json
import os
import sys
from datetime import datetime, timedelta
import math

# Configuration S3
BUCKET_NAME = os.environ.get('TRADING_LOGS_BUCKET')
if not BUCKET_NAME:
    # On essaie de le trouver via CloudFormation/CDK output si possible, ou on demande à l'user
    print("⚠️  TRADING_LOGS_BUCKET non défini. Usage: export TRADING_LOGS_BUCKET=my-bucket-name")
    # Placeholder pour test si l'user a oublié, à remplacer par le vrai nom
    # sys.exit(1)

s3 = boto3.client('s3')

def upload_to_s3(data, symbol, year):
    if not BUCKET_NAME:
        print(f"❌ Pas de bucket défini, skip upload {symbol} {year}")
        return

    safe_symbol = symbol.replace('/', '_')
    key = f"historical/{safe_symbol}/{year}.json"
    
    try:
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=key,
            Body=json.dumps(data),
            ContentType='application/json'
        )
        print(f"✅ Uploadé s3://{BUCKET_NAME}/{key} ({len(data)} bougies)")
    except Exception as e:
        print(f"❌ Erreur Upload S3: {e}")

def fetch_crypto_history(symbol, years=6):
    exchange = ccxt.binance()
    now = datetime.now()
    all_ohlcv = []
    
    start_date = now - timedelta(days=365*years)
    since = int(start_date.timestamp() * 1000)
    
    print(f"\n📥 [CRYPTO] {symbol} depuis {start_date.year}...")
    
    while True:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, '1h', since=since, limit=1000)
            if not ohlcv: break
            
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
            
            if ohlcv[-1][0] >= int(now.timestamp() * 1000):
                break
        except:
             break
             
    # Split par année et upload
    grouped = {}
    for candle in all_ohlcv:
        ts = candle[0] # ms
        dt = datetime.fromtimestamp(ts/1000)
        y = dt.year
        if y not in grouped: grouped[y] = []
        grouped[y].append(candle)
        
    for y, candles in grouped.items():
        if len(candles) > 100:
             upload_to_s3(candles, symbol, y)

def fetch_forex_history(pair, years=6):
    print(f"\n📥 [FOREX] {pair} (via Yahoo)...")
    ticker = f"{pair}=X"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*years)
    
    try:
        df = yf.download(ticker, start=start_date, end=end_date, interval='1h', progress=False)
        if df.empty: return

        # Formatage standard
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        df = df.reset_index()
        
        col_map = {'Datetime': 'ts', 'Date': 'ts', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'vol'}
        df = df.rename(columns={c: col_map.get(c, c) for c in df.columns})
        df.columns = [c.lower() for c in df.columns]

        # Conversion
        grouped = {}
        for _, row in df.iterrows():
            ts_val = row.get('timestamp') or row.get('datetime') or row.get('ts')
            if not ts_val: continue
            
            dt = pd.to_datetime(ts_val)
            ts = int(dt.timestamp() * 1000)
            y = dt.year
            
            candle = [
                ts, 
                float(row['open']), float(row['high']), float(row['low']), float(row['close']), 
                int(row['volume']) if 'volume' in row else 0
            ]
            
            if y not in grouped: grouped[y] = []
            grouped[y].append(candle)
            
        for y, candles in grouped.items():
            if len(candles) > 100:
                 upload_to_s3(candles, pair, y)

    except Exception as e:
        print(f"❌ Erreur Forex {pair}: {e}")

if __name__ == "__main__":
    # Liste des actifs à historiser (Crypto uniquement)
    CRYPTOS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    
    if not BUCKET_NAME:
        print("⚠️  S3 Upload désactivé (pas de bucket). Exécution DRY RUN.")
        
    for c in CRYPTOS:
        fetch_crypto_history(c)

