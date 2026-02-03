import sys
import os
import json
from unittest.mock import MagicMock, patch

# Ajouter le path pour importer le handler
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../lambda/trading_agent')))

# Mock AWS AVANT import
with patch('boto3.client') as mock_bedrock:
    from handler import lambda_handler

def test_trading_agent_decision():
    print("🚀 Démarrage Test Local Trading Agent (Cerveau)...")
    
    # 1. Scénario : Opportunité d'Achat (RSI Bas + Hammer)
    # C'est ce que data_fetcher enverrait
    market_event = {
        "detail": {
            "symbol": "BTC/USDT",
            "price": "77854.93",
            "technical": {
                "indicators": {"rsi": 25.5, "trend": "BEARISH"},
                "patterns": ["DOUBLE_BOTTOM"],
                "candles": ["HAMMER"]
            }
        }
    }
    
    # 2. Mock de la réponse de Claude (Bedrock)
    # On simule ce que Claude répondrait à ce prompt
    fake_claude_response = {
        "decision": "BUY",
        "confidence": 0.85,
        "reason": "RSI survendu (25) combiné à un Hammer et un Double Bottom indique un rebond probable malgré la tendance baissière de fond.",
        "risk_level": "MEDIUM"
    }
    
    # Configuration du Mock boto3 pour retourner ce JSON
    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps({
        "content": [{"text": json.dumps(fake_claude_response)}]
    }).encode('utf-8')
    
    mock_client.invoke_model.return_value = {'body': mock_body}
    
    # On injecte le mock dans le handler (il faut patcher bedrock_runtime qui est une variable globale dans handler.py)
    with patch('handler.bedrock_runtime', mock_client):
        response = lambda_handler(market_event, MagicMock())
        
    # 3. Validation
    if response['statusCode'] == 200:
        body = json.loads(response['body'])
        decision = body['agent_decision']
        
        print("\n✅ Réponse de l'Agent reçue !")
        print(f"Décision : {decision['decision']}")
        print(f"Confiance : {decision['confidence']}")
        print(f"Raison   : {decision['reason']}")
        
        if decision['decision'] == "BUY":
            print("\n🎉 SUCCÈS : L'agent a correctement décidé d'ACHETER sur base des signaux.")
        else:
            print("\n⚠️ Bizarre : L'agent n'a pas acheté alors que le mock disait BUY.")
    else:
        print(f"\n❌ Erreur Lambda : {response}")

if __name__ == "__main__":
    test_trading_agent_decision()
