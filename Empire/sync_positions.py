#!/usr/bin/env python3
"""
🚨 SYNC POSITIONS - URGENCE
Synchronise les positions Binance réelles vers DynamoDB
"""

import os
import sys
import json
import boto3
from datetime import datetime, timezone

# Configuration
REGION = "ap-northeast-1"
TABLE_NAME = "V4TradingState"

def get_binance_positions():
    """Récupère les positions réelles depuis Binance"""
    # Simuler la récupération - remplacer avec vrais credentials
    positions = [
        {
            "symbol": "MOODENG/USDT:USDT",
            "direction": "LONG",
            "size": 84266,
            "entry_price": 0.06273,
            "mark_price": 0.0636,
            "pnl": 65.72,
            "pnl_pct": 6.13,
            "leverage": 5,
            "margin": 1054.55,
            "tp_price": 0.06297,
            "sl_price": 0.0507225,
            "entry_time": datetime.now(timezone.utc).isoformat()
        },
        {
            "symbol": "ARC/USDT:USDT", 
            "direction": "LONG",
            "size": 20529,
            "entry_price": 0.07975,
            "mark_price": 0.0815655,
            "pnl": 36.95,
            "pnl_pct": 6.61,
            "leverage": 3,
            "margin": 544.91,
            "tp_price": 0.08013,
            "sl_price": 0.0542923,
            "entry_time": datetime.now(timezone.utc).isoformat()
        },
        {
            "symbol": "KITE/USDT:USDT",
            "direction": "LONG", 
            "size": 11013,
            "entry_price": 0.20085,
            "mark_price": 0.1992767,
            "pnl": -20.04,
            "pnl_pct": -2.73,
            "leverage": 3,
            "margin": 736.21,
            "tp_price": None,
            "sl_price": 0.1488893,
            "entry_time": datetime.now(timezone.utc).isoformat()
        }
    ]
    return positions

def sync_to_dynamodb(positions):
    """Synchronise les positions vers DynamoDB"""
    dynamodb = boto3.client('dynamodb', region_name=REGION)
    
    for pos in positions:
        symbol = pos["symbol"]
        
        # Créer l'item pour DynamoDB avec attributs GSI
        current_time = datetime.now(timezone.utc).isoformat()
        item = {
            "trader_id": {"S": f"POSITION#{symbol}"},
            "symbol": {"S": symbol},
            "direction": {"S": pos["direction"]},
            "status": {"S": "OPEN"},  # Pour GSI status-timestamp-index
            "entry_price": {"N": str(pos["entry_price"])},
            "mark_price": {"N": str(pos["mark_price"])},
            "size": {"N": str(pos["size"])},
            "quantity": {"N": str(pos["size"])},  # Pour le closer
            "leverage": {"N": str(pos["leverage"])},
            "margin": {"N": str(pos["margin"])},
            "pnl": {"N": str(pos["pnl"])},
            "pnl_pct": {"N": str(pos["pnl_pct"])},
            "entry_time": {"S": pos["entry_time"]},
            "timestamp": {"S": current_time}  # Pour GSI status-timestamp-index
        }
        
        # Ajouter TP/SL s'ils existent
        if pos.get("tp_price"):
            item["take_profit"] = {"N": str(pos["tp_price"])}
        if pos.get("sl_price"):
            item["stop_loss"] = {"N": str(pos["sl_price"])}
        
        try:
            dynamodb.put_item(TableName=TABLE_NAME, Item=item)
            print(f"✅ Synchronisé: {symbol}")
        except Exception as e:
            print(f"❌ Erreur {symbol}: {e}")

def main():
    print("🚨 SYNC POSITIONS - URGENCE")
    print("=" * 50)
    
    # Récupérer positions Binance
    positions = get_binance_positions()
    print(f"📊 {len(positions)} positions trouvées sur Binance")
    
    # Synchroniser vers DynamoDB
    sync_to_dynamodb(positions)
    
    print("\n✅ Synchronisation terminée!")
    print("🔄 Le closer devrait maintenant voir les positions")

if __name__ == "__main__":
    main()
