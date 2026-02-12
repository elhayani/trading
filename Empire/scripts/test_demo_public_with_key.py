import ccxt
import boto3
import json
import os
import sys

def main():
    print("Testing PUBLIC OHLCV WITH API KEY on Demo Host simulation...")
    
    # 1. Fetch credentials
    client = boto3.client('secretsmanager', region_name='eu-west-3')
    resp = client.get_secret_value(SecretId='trading/binance')
    creds = json.loads(resp['SecretString'])
    api_key = creds['api_key'].strip()
    secret = creds['secret'].strip()

    # 2. Initialization WITH keys
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'},
        'verbose': True
    })
    
    # 3. GLOBAL REPLACE
    demo_host = "demo-fapi.binance.com"
    for key, url in exchange.urls['api'].items():
        if isinstance(url, str):
            new_url = url.replace("fapi.binance.com", demo_host).replace("testnet.binancefuture.com", demo_host)
            exchange.urls['api'][key] = new_url
            
    print("\n--- Executing fetch_ohlcv('BTCUSDT', '1h') ---")
    try:
        # CCXT will likely include X-MBX-APIKEY header because apiKey is set
        res = exchange.fetch_ohlcv('BTCUSDT', '1h', limit=5)
        print("\n✅ SUCCESS!")
    except Exception as e:
        print(f"\n❌ FAILED: {e}")

if __name__ == "__main__":
    main()
