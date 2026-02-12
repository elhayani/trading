import ccxt
import boto3
import json
import os
import sys

def main():
    print("Testing CCXT 'test' URL map override simulation...")
    
    # 1. Fetch credentials
    client = boto3.client('secretsmanager', region_name='eu-west-3')
    resp = client.get_secret_value(SecretId='trading/binance')
    creds = json.loads(resp['SecretString'])
    api_key = creds['api_key'].strip()
    secret = creds['secret'].strip()

    # 2. Initialization
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'},
        'verbose': True
    })
    
    # 3. Aggressive Override (Version Elite)
    exchange.set_sandbox_mode(True)
    
    # On ne remplace que le domaine, en préservant les chemins exacts
    demo_domain = "demo-fapi.binance.com"
    
    # On écrase tout proprement en préservant la structure des chemins
    for collection in ['test', 'api']:
        if collection in exchange.urls:
            for key in exchange.urls[collection]:
                if isinstance(exchange.urls[collection][key], str):
                    url = exchange.urls[collection][key]
                    # Remplacer uniquement les domaines problématiques
                    url = url.replace("fapi.binance.com", demo_domain)
                    url = url.replace("testnet.binancefuture.com", demo_domain)
                    url = url.replace("api.binance.com", demo_domain)
                    # Nettoyer les doubles préfixes
                    url = url.replace("demo-fdemo-fapi.binance.com", demo_domain)
                    exchange.urls[collection][key] = url

    # Désactiver le check SAPI qui pollue
    exchange.options['fetchConfig'] = False
            
    try:
        print("\n--- TEST 1: fetch_ohlcv (Public) ---")
        res = exchange.fetch_ohlcv('BTCUSDT', '1h', limit=1)
        print("✅ SUCCESS (OHLCV)")
        
        print("\n--- TEST 2: Balance (Private) ---")
        # Use the fapiPrivateV2GetAccount we know works
        res_bal = exchange.fapiPrivateV2GetAccount()
        print("✅ SUCCESS (Balance)")
        if isinstance(res_bal, dict):
            print(f"Total Wallet Balance: {res_bal.get('totalWalletBalance', 'N/A')}")
        else:
            print(f"Response type: {type(res_bal)}, Content: {res_bal}")
        
    except Exception as e:
        print(f"\n❌ FAILED: {e}")

if __name__ == "__main__":
    main()
