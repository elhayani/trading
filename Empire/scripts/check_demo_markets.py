import ccxt
import boto3
import json
import os

def get_secrets():
    client = boto3.client('secretsmanager', region_name='eu-west-3')
    try:
        response = client.get_secret_value(SecretId='trading/binance')
        return json.loads(response['SecretString'])
    except Exception as e:
        print(f"Failed to get secrets: {e}")
        return None

def main():
    secrets = get_secrets()
    if not secrets: return

    api_key = (secrets.get('API_KEY') or secrets.get('api_key')).strip()
    secret = (secrets.get('SECRET_KEY') or secrets.get('secret')).strip()

    print("Checking Demo Markets...")
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'}
    })
    
    # Apply Elite Sniper Fix (mimic exchange_connector.py)
    exchange.set_sandbox_mode(True)
    demo_domain = "demo-fapi.binance.com"
    for collection in ['test', 'api']:
        if collection in exchange.urls:
            for key in exchange.urls[collection]:
                if isinstance(exchange.urls[collection][key], str):
                    url = exchange.urls[collection][key]
                    url = url.replace("fapi.binance.com", demo_domain)
                    url = url.replace("testnet.binancefuture.com", demo_domain)
                    url = url.replace("api.binance.com", demo_domain)
                    exchange.urls[collection][key] = url

    print(f"Base URL: {exchange.urls['api']['fapiPublic']}")
    
    markets = exchange.load_markets()
    print(f"Total markets: {len(markets)}")
    
    symbols_to_check = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'PAXG/USDT', 'SPX/USDT', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'PAXGUSDT', 'SPXUSDT']
    
    print("\nSymbol Status:")
    for s in symbols_to_check:
        status = "✅ FOUND" if s in markets else "❌ MISSING"
        print(f"  {s:10} : {status}")

    # Check for anything containing SOL and USDT
    print("\nPartial matches for 'SOL' and 'USDT':")
    matches = [s for s in markets.keys() if 'SOL' in s and 'USDT' in s]
    for m in matches:
        print(f"  - {m}")

if __name__ == "__main__":
    main()
