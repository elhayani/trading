#!/usr/bin/env python3
"""
DEEP HISTORY FETCHER & S3 UPLOADER
==================================
Télécharge l'historique long terme (Daily) pour Forex, Indices, Commodities
depuis Yahoo Finance et l'upload sur S3 pour backtests profonds.

Période : 2010-01-01 -> 2023-12-31 (Avant la période 'récente' 1H)
Intervalle : 1d (Daily) car 1h non disponible si loin.
Bucket S3 : empire-trading-data-paris
"""

import yfinance as yf
import pandas as pd
import boto3
import os
from io import StringIO

# CONFIGURATION
BUCKET_NAME = "empire-trading-data-paris"
START_DATE = "2010-01-01"
END_DATE = "2023-12-31"

ASSETS = {
    'FOREX': ['EURUSD=X', 'GBPUSD=X', 'JPY=X'],
    'INDICES': ['^GSPC', '^IXIC', '^DJI'],
    'COMMODITIES': ['GC=F', 'CL=F'],
    'CRYPTO': ['BTC-USD', 'ETH-USD']
}

def upload_to_s3(df, s3_key):
    """Upload DataFrame to S3 as CSV"""
    csv_buffer = StringIO()
    df.to_csv(csv_buffer)
    
    s3 = boto3.client('s3')
    try:
        s3.put_object(Bucket=BUCKET_NAME, Key=s3_key, Body=csv_buffer.getvalue())
        print(f"✅ Uploaded to s3://{BUCKET_NAME}/{s3_key}")
        return True
    except Exception as e:
        print(f"❌ S3 Upload Failed: {e}")
        return False

def fetch_and_store():
    print(f"🌍 STARTING DEEP HISTORY FETCH ({START_DATE} -> {END_DATE})")
    print(f"   Resolution: 1d (Daily)")
    print("------------------------------------------------")
    
    for category, symbols in ASSETS.items():
        print(f"\n📂 Processing {category}...")
        
        for symbol in symbols:
            print(f"   ⬇️ Downloading {symbol}...")
            try:
                # Download Daily Data
                df = yf.download(symbol, start=START_DATE, end=END_DATE, interval="1d", progress=False)
                
                if df.empty:
                    print(f"      ⚠️ No data found for {symbol}")
                    continue
                
                # Cleanup MultiIndex if present
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                # Standardize columns
                df.columns = [c.lower() for c in df.columns]
                
                # S3 Path: historical/{category}/{symbol}_1d_2010_2023.csv
                # Clean symbol for filename (remove =X, ^, etc)
                clean_sym = symbol.replace('=X', '').replace('^', '').replace('=F', '')
                s3_key = f"historical/{category.lower()}/{clean_sym}_1d_2010_2023.csv"
                
                # Upload
                upload_to_s3(df, s3_key)
                print(f"      📊 Rows: {len(df)}")
                
            except Exception as e:
                print(f"      ❌ Error: {e}")

if __name__ == "__main__":
    fetch_and_store()
