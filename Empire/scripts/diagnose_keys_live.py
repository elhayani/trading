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

def test_connection(name, exchange_class, config, url_override=None):
    print(f"\nTesting {name}...")
    try:
        exchange = exchange_class(config)
        
        if url_override:
            # Update URLs properly without nuking the rest
            if 'api' not in exchange.urls:
                exchange.urls['api'] = {}
            if isinstance(exchange.urls['api'], dict):
                exchange.urls['api'].update(url_override)
            else:
                # Some exchanges have str URLs, but Binance is dict
                print("Warning: Exchange URLs format unexpected.")
        
        balance = exchange.fetch_balance()
        print(f"✅ SUCCESS! Connected to {name}")
        usdt = balance.get('USDT', {}).get('free', 0)
        total = balance.get('total', {}).get('USDT', 0)
        print(f"   Balance USDT: Free={usdt}, Total={total}")
        return True
    except Exception as e:
        print(f"❌ FAILED {name}: {e}")
        return False

def main():
    secrets = get_secrets()
    if not secrets:
        return

    api_key = secrets.get('API_KEY') or secrets.get('api_key')
    secret = secrets.get('SECRET_KEY') or secrets.get('secret')
    
    if not api_key or not secret:
        print("Keys not found in secret.")
        return

    api_key = api_key.strip()
    secret = secret.strip()

    print(f"Using Key: {api_key[:6]}...{api_key[-4:]}")

    # 1. Test FUTURES LIVE
    test_connection('FUTURES LIVE', ccxt.binance, {
        'apiKey': api_key, 'secret': secret,
        'options': {'defaultType': 'future'}
    })

    # 2. Test FUTURES TESTNET (Standard)
    # Testing testnet.binancefuture.com
    test_connection('FUTURES TESTNET (Standard)', ccxt.binance, {
        'apiKey': api_key, 'secret': secret,
        'options': {'defaultType': 'future'},
        'verbose': False
    }, url_override={
        'fapi': 'https://testnet.binancefuture.com/fapi',
        'fapiPublic': 'https://testnet.binancefuture.com/fapi',
        'fapiPrivate': 'https://testnet.binancefuture.com/fapi',
    })

    # 2.5 Test FUTURES DEMO (User Provided URL)
    # Testing demo-fapi.binance.com
    test_connection('FUTURES DEMO (User URL)', ccxt.binance, {
        'apiKey': api_key, 'secret': secret,
        'options': {'defaultType': 'future'}
    }, url_override={
        'fapi': 'https://demo-fapi.binance.com/fapi',
        'fapiPublic': 'https://demo-fapi.binance.com/fapi',
        'fapiPrivate': 'https://demo-fapi.binance.com/fapi',
    })

    # 3. Test SPOT LIVE
    test_connection('SPOT LIVE', ccxt.binance, {
        'apiKey': api_key, 'secret': secret,
        'options': {'defaultType': 'spot'}
    })

if __name__ == "__main__":
    main()
