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

    api_key = secrets.get('API_KEY') or secrets.get('api_key')
    secret = secrets.get('SECRET_KEY') or secrets.get('secret')
    
    if not api_key or not secret:
        print("Keys not found in secret.")
        return
    
    print("Testing with set_sandbox_mode(True)...")
    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret,
            'options': {'defaultType': 'future'},
            # Use verbose to see the actual URL being requested
            'verbose': True
        })

        # This method is supposedly deprecated for Futures but let's test if it works for DEMO keys
        # or if it fails on URL
        exchange.set_sandbox_mode(True)
        
        # Override URLs manually just in case set_sandbox_mode defaults to broken one
        # Because we saw set_sandbox_mode() fail earlier with "no testnet URL" error
        exchange.urls['api'] = {
            'fapi': 'https://testnet.binancefuture.com/fapi/v1',
            'fapiPublic': 'https://testnet.binancefuture.com/fapi/v1',
            'fapiPrivate': 'https://testnet.binancefuture.com/fapi/v1',
        }

        print(exchange.fetch_balance())
        print("✅ SUCCESS!")
    except Exception as e:
        print(f"❌ FAILED: {e}")

if __name__ == "__main__":
    main()
