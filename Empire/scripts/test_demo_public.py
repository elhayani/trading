import ccxt
import boto3
import json
import os
import sys

def main():
    print("Testing PUBLIC OHLCV on Demo Host simulation...")
    
    # 1. Initialization WITHOUT keys (Public only)
    exchange = ccxt.binance({
        'options': {'defaultType': 'future'},
        'verbose': True
    })
    
    # Mirror the override to demo-fapi
    demo_host = "demo-fapi.binance.com"
    for key, url in exchange.urls['api'].items():
        if isinstance(url, str):
            new_url = url.replace("fapi.binance.com", demo_host).replace("testnet.binancefuture.com", demo_host)
            exchange.urls['api'][key] = new_url
            
    print("\n--- Executing fetch_ohlcv('BTCUSDT', '1h') ---")
    try:
        # This will use the overridden fapiPublic URL
        res = exchange.fetch_ohlcv('BTCUSDT', '1h', limit=5)
        print("\n✅ SUCCESS!")
        print(f"Data count: {len(res)}")
    except Exception as e:
        print(f"\n❌ FAILED: {e}")

if __name__ == "__main__":
    main()
