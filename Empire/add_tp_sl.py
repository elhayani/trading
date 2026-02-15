#!/usr/bin/env python3
"""
🔧 AJOUTER TP/SL POUR MOODENG ET KITE
Ajoute des TP/SL agressifs pour tester la fermeture automatique
"""

import boto3

# Configuration
REGION = "ap-northeast-1"
TABLE_NAME = "V4TradingState"

def add_tp_sl():
    """Ajoute TP/SL pour MOODENG et KITE"""
    dynamodb = boto3.client('dynamodb', region_name=REGION)
    
    # Positions avec TP/SL agressifs
    positions = [
        {
            "symbol": "MOODENG/USDT:USDT",
            "current_price": 0.0610883,
            "direction": "LONG",
            # TP très proche pour test
            "tp_price": 0.06105,  # Juste en dessous du prix actuel
            "sl_price": 0.06050   # SL un peu plus bas
        },
        {
            "symbol": "KITE/USDT:USDT",
            "current_price": 0.1985524,
            "direction": "LONG",
            # TP très proche pour test
            "tp_price": 0.19850,  # Juste en dessous du prix actuel
            "sl_price": 0.19700   # SL un peu plus bas
        }
    ]
    
    for pos in positions:
        symbol = pos["symbol"]
        
        try:
            response = dynamodb.update_item(
                TableName=TABLE_NAME,
                Key={
                    "trader_id": {"S": f"POSITION#{symbol}"}
                },
                UpdateExpression="SET take_profit = :tp, stop_loss = :sl, mark_price = :current",
                ExpressionAttributeValues={
                    ":tp": {"N": str(pos["tp_price"])},
                    ":sl": {"N": str(pos["sl_price"])},
                    ":current": {"N": str(pos["current_price"])}
                }
            )
            
            print(f"✅ {symbol}:")
            print(f"   TP: {pos['tp_price']:.6f}")
            print(f"   SL: {pos['sl_price']:.6f}")
            print(f"   Prix actuel: {pos['current_price']:.6f}")
            print(f"   → TP sera hit rapidement!")
            
        except Exception as e:
            print(f"❌ Erreur {symbol}: {e}")

if __name__ == "__main__":
    print("🔧 AJOUTER TP/SL POUR TEST")
    print("=" * 50)
    add_tp_sl()
    print("\n✅ TP/SL ajoutés! Les positions devraient se fermer au prochain cycle (30s)")
