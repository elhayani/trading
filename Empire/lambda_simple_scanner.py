"""
🚀 Empire Trading Simple Scanner
Génère des données de test pour le dashboard
"""

import json
import boto3
import random
import time
from decimal import Decimal
from datetime import datetime, timedelta

# Configuration
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
trades_table = dynamodb.Table('EmpireTradesHistory')
skipped_table = dynamodb.Table('EmpireSkippedTrades')

# Symboles de trading
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'DOTUSDT']
SIDES = ['BUY', 'SELL']
SKIP_REASONS = [
    'BTC_NEUTRAL_NO_TRADING',
    'LOW_SIGNAL_STRENGTH',
    'LOW_BTC_CORRELATION',
    'WEAK_SIGNAL_IN_STRONG_TREND',
    'MIN_NOTIONAL_VALUE',
    'MAX_OPEN_TRADES'
]

def lambda_handler(event, context):
    """Génère des trades de test pour le dashboard"""
    try:
        print("🚀 Empire Simple Scanner - Démarrage")
        
        # Générer plus de trades de test
        for i in range(8):
            # Trade réel (60% chance)
            if random.random() > 0.4:
                generate_real_trade()
            
            # Trade skip (80% chance)
            if random.random() > 0.2:
                generate_skipped_trade()
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'SUCCESS',
                'message': 'Test data generated',
                'timestamp': datetime.now().isoformat()
            })
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'ERROR',
                'message': str(e)
            })
        }

def generate_real_trade():
    """Génère un trade réel dans DynamoDB"""
    try:
        symbol = random.choice(SYMBOLS)
        side = random.choice(SIDES)
        price = Decimal(str(50000 + random.uniform(-5000, 5000)))
        quantity = Decimal(str(random.uniform(0.1, 0.5)))
        pnl = Decimal(str(random.uniform(-100, 300)))  # 70% chance de profit
        
        trade_id = f"trade_{int(time.time())}_{random.randint(1000, 9999)}"
        timestamp = int(time.time() * 1000)
        
        trade_item = {
            'trade_id': trade_id,
            'timestamp': timestamp,
            'symbol': symbol,
            'side': side,
            'price': price,
            'quantity': quantity,
            'pnl': pnl,
            'status': 'CLOSED',
            'entry_time': datetime.now().isoformat(),
            'exit_time': datetime.now().isoformat(),
            'reason': 'MOMENTUM_SIGNAL',
            'exit_reason': 'TP_HIT' if pnl > 0 else 'SL_HIT'
        }
        
        trades_table.put_item(Item=trade_item)
        print(f"✅ Trade généré: {symbol} {side} PnL: ${pnl:.2f}")
        
    except Exception as e:
        print(f"❌ Erreur génération trade: {e}")

def generate_skipped_trade():
    """Génère un trade skip dans DynamoDB"""
    try:
        symbol = random.choice(SYMBOLS)
        side = random.choice(SIDES)
        price = Decimal(str(50000 + random.uniform(-5000, 5000)))
        quantity = Decimal(str(random.uniform(0.1, 0.5)))
        signal_strength = Decimal(str(random.uniform(0.3, 0.9)))
        momentum_score = Decimal(str(random.uniform(0.4, 0.8)))
        
        trade_id = f"skip_{int(time.time())}_{random.randint(1000, 9999)}"
        timestamp = int(time.time() * 1000)
        
        skip_item = {
            'trade_id': trade_id,
            'timestamp': timestamp,
            'symbol': symbol,
            'side': side,
            'price': price,
            'quantity': quantity,
            'status': 'SKIPPED',
            'reason': random.choice(SKIP_REASONS),
            'signal_strength': signal_strength,
            'momentum_score': momentum_score,
            'volume_surge': Decimal(str(random.uniform(1.5, 3.0))),
            'btc_trend': random.choice(['BULLISH', 'BEARISH', 'NEUTRAL']),
            'skip_reason': random.choice(SKIP_REASONS)
        }
        
        skipped_table.put_item(Item=skip_item)
        print(f"⏭️ Skip généré: {symbol} {side} Reason: {skip_item['skip_reason']}")
        
    except Exception as e:
        print(f"❌ Erreur génération skip: {e}")

if __name__ == "__main__":
    # Test local
    lambda_handler({}, None)
