import sys
import os
import json
from unittest.mock import MagicMock, patch

# Ajouter le dossier lambda/data_fetcher au path pour les imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../lambda/data_fetcher')))

# Mock des services AWS AVANT d'importer le handler
with patch('boto3.resource') as mock_dynamodb:
    from handler import lambda_handler

def run_lambda_test(event, context, scenario_name):
    print(f"\n🔹 SCÉNARIO : {scenario_name}")
    try:
        response = lambda_handler(event, context)
        
        if response['statusCode'] != 200:
            print(f"❌ Erreur: {response}")
            return

        body = json.loads(response['body'])
        print(f"✅ {body['symbol']} : {body['price']}")
        print(f"   Source: {body.get('source', 'N/A')}")
        print(f"   Signal: {body.get('signal')}")
        patterns = body['analysis'].get('patterns')
        print(f"   Patterns: {patterns if patterns else 'Aucun'}")
        
    except Exception as e:
        print(f"❌ Crash Test : {e}")
        import traceback
        traceback.print_exc()

def test_lambda_execution():
    print("🚀 Démarrage du Test Multi-Asset...")
    
    context = MagicMock()
    context.function_name = "test-multi-asset"

    # Scenario 1: Crypto (Default)
    event_crypto = {"symbol": "BTC/USDT", "asset_type": "CRYPTO"} 
    run_lambda_test(event_crypto, context, "CRYPTO (Binance Real)")

    # Scenario 2: Forex (Mock)
    event_forex = {"symbol": "EUR/USD", "asset_type": "FOREX"}
    run_lambda_test(event_forex, context, "FOREX (Mock Oanda)")

if __name__ == "__main__":
    test_lambda_execution()
