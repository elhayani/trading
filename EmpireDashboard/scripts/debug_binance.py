import boto3
import ccxt
import os

REGION = 'eu-west-3'
CONFIG_TABLE = 'EmpireConfig'

def test_api():
    print("🔍 Récupération des clés...")
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(CONFIG_TABLE)
    resp = table.get_item(Key={'ConfigKey': 'BINANCE_CREDENTIALS'})
    creds = resp['Item']
    api_key = creds.get('ApiKey')
    api_secret = creds.get('ApiSecret')

    print(f"🔑 Clé: {api_key[:5]}...")

    print("\n--- TEST LIVE FUTURES ---")
    try:
        exchange = ccxt.binance({
            'apiKey': api_key, 'secret': api_secret,
            'enableRateLimit': True, 'options': {'defaultType': 'future'}
        })
        balance = exchange.fetch_balance()
        print(f"✅ LIVE OK ! Solde USDT: {balance.get('USDT', {}).get('total', 0)}")
    except Exception as e:
        print(f"❌ LIVE FAIL: {e}")

    print("\n--- TEST NEW DEMO TRADING MODE ---")
    try:
        exchange = ccxt.binance({
            'apiKey': api_key, 'secret': api_secret,
            'enableRateLimit': True, 'options': {'defaultType': 'future'}
        })
        if hasattr(exchange, 'enable_demo_trading'):
            exchange.enable_demo_trading(True)
            
        balance = exchange.fetch_balance()
        print(f"✅ DEMO OK ! Solde USDT: {balance.get('USDT', {}).get('total', 0)}")
    except Exception as e:
        print(f"❌ DEMO FAIL: {e}")





if __name__ == "__main__":
    test_api()
