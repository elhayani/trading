import ccxt
import boto3
import json
import os
import sys

def main():
    print("Testing Method Deletion simulation...")
    
    # 1. Fetch credentials
    client = boto3.client('secretsmanager', region_name='eu-west-3')
    resp = client.get_secret_value(SecretId='trading/binance')
    creds = json.loads(resp['SecretString'])
    api_key = creds['api_key'].strip()
    secret = creds['secret'].strip()
    
    # Initialize
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'},
        'verbose': True
    })
    
    # THE ULTIMATE BRUTE FORCE
    # We remove the method that calls SAPI
    exchange.fetch_config = None
    exchange.fetch_configs = None
    
    # Apply Elite Sniper Fix
    if 'api' in exchange.urls:
        # Force sandbox mode first
        exchange.set_sandbox_mode(True)
        
        demo_domain = "demo-fapi.binance.com"
        for key, url in exchange.urls['api'].items():
            if isinstance(url, str):
                new_url = url
                # Replace only problematic domains, preserve exact paths
                new_url = new_url.replace("fapi.binance.com", demo_domain)
                new_url = new_url.replace("dapi.binance.com", demo_domain)
                new_url = new_url.replace("api.binance.com", demo_domain)
                # Clean double prefixes
                new_url = new_url.replace("demo-fdemo-fapi.binance.com", demo_domain)
                exchange.urls['api'][key] = new_url
    
    # Also fix test URLs
    if 'test' in exchange.urls:
        for key, url in exchange.urls['test'].items():
            if isinstance(url, str):
                new_url = url
                new_url = new_url.replace("fapi.binance.com", demo_domain)
                new_url = new_url.replace("testnet.binancefuture.com", demo_domain)
                new_url = new_url.replace("api.binance.com", demo_domain)
                new_url = new_url.replace("demo-fdemo-fapi.binance.com", demo_domain)
                exchange.urls['test'][key] = new_url
    
    # Disable SAPI config check
    exchange.options['fetchConfig'] = False

    print("\n--- TEST: load_markets ---")
    try:
        exchange.load_markets()
        print("\n✅ SUCCESS!")
    except Exception as e:
        print(f"\n❌ FAILED: {e}")

if __name__ == "__main__":
    main()
