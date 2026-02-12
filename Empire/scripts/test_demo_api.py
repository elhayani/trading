import ccxt
import boto3
import json
import os
import sys

def get_secrets():
    print("Retrieving secrets from AWS...")
    client = boto3.client('secretsmanager', region_name='eu-west-3')
    try:
        response = client.get_secret_value(SecretId='trading/binance')
        return json.loads(response['SecretString'])
    except Exception as e:
        print(f"Failed to get secrets: {e}")
        return None

def main():
    secrets = get_secrets()
    if not secrets:
        print("No secrets found.")
        return

    api_key = secrets.get('api_key') or secrets.get('API_KEY')
    secret = secrets.get('secret') or secrets.get('SECRET_KEY')
    
    api_key = api_key.strip()
    secret = secret.strip()

    print(f"Testing with Demo URL Global Override")
    
    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret,
            'options': {
                'defaultType': 'future',
            },
            'verbose': True
        })

        # Apply Elite Sniper Fix
        exchange.set_sandbox_mode(True)
        
        demo_domain = "demo-fapi.binance.com"
        for collection in ['test', 'api']:
            if collection in exchange.urls:
                for key in exchange.urls[collection]:
                    if isinstance(exchange.urls[collection][key], str):
                        url = exchange.urls[collection][key]
                        # Replace only problematic domains, preserve exact paths
                        url = url.replace("fapi.binance.com", demo_domain)
                        url = url.replace("testnet.binancefuture.com", demo_domain)
                        url = url.replace("api.binance.com", demo_domain)
                        # Clean double prefixes
                        url = url.replace("demo-fdemo-fapi.binance.com", demo_domain)
                        exchange.urls[collection][key] = url
        
        # Disable SAPI config check
        exchange.options['fetchConfig'] = False

        print("\n--- Testing fapiPrivateV2GetAccount ---")
        res = exchange.fapiPrivateV2GetAccount()
        
        print("\n✅ SUCCESS!")
        print(f"Total Wallet Balance: {res.get('totalWalletBalance', 'N/A')}")
        
    except Exception as e:
        print(f"\n❌ FAILED: {e}")

if __name__ == "__main__":
    main()
