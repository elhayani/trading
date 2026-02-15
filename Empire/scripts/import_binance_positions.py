
import boto3
import ccxt
import os
import time
from decimal import Decimal
from datetime import datetime, timezone
import json

# Config
REGION = 'ap-northeast-1'
TABLE_NAME = 'V4TradingState'

def import_positions():
    # 1. Connect AWS
    print(f"🔌 Connecting to AWS ({REGION})...")
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)
    secrets = boto3.client('secretsmanager', region_name=REGION)
    
    # 2. Connect Binance
    try:
        secret_value = secrets.get_secret_value(SecretId='trading/binance')['SecretString']
        keys = json.loads(secret_value)
        
        api_key = keys.get('apiKey', keys.get('api_key'))
        secret_key = keys.get('secretKey', keys.get('secret_key', keys.get('secret')))
        
        if not api_key or not secret_key:
            raise ValueError("API Keys missing in Secret")

        exchange = ccxt.binanceusdm({
            'apiKey': api_key,
            'secret': secret_key,
            'options': {'defaultType': 'future'}
        })
        print("✅ Binance Connected")
    except Exception as e:
        print(f"❌ Failed to connect Binance: {e}")
        return

    # 3. Fetch Positions
    print("🔍 Scanning Binance Positions...")
    try:
        balance = exchange.fetch_balance()
        positions = balance['info']['positions']
        
        count = 0
        for p in positions:
            amt = float(p['positionAmt'])
            if amt != 0:
                symbol = p['symbol'] # e.g. BTCUSDT
                # Convert to internal format
                base = symbol.replace('USDT', '')
                internal_symbol = f"{base}/USDT:USDT"
                
                entry_price = float(p['entryPrice'])
                leverage = int(p['leverage'])
                unrealized_pnl = float(p['unRealizedProfit'])
                
                print(f"  Found: {internal_symbol} | Open: {amt} | Entry: {entry_price}")
                
                # 4. Check DynamoDB
                response = table.scan(
                    FilterExpression=boto3.dynamodb.conditions.Attr('symbol').eq(internal_symbol) & boto3.dynamodb.conditions.Attr('status').eq('OPEN')
                )
                
                if response['Items']:
                    print(f"    ℹ️ Already in DynamoDB. Skipping.")
                else:
                    print(f"    ⚠️ MISSING in DynamoDB! Importing...")
                    
                    # Import
                    item = {
                        'trader_id': f"IMPORT_{int(time.time())}_{symbol}", 
                        'symbol': internal_symbol,
                        'status': 'OPEN',
                        'direction': 'LONG' if amt > 0 else 'SHORT',
                        'entry_price': Decimal(str(entry_price)),
                        'quantity': Decimal(str(abs(amt))),
                        'leverage': leverage,
                        'is_test': False,
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        # Set wide TP/SL to let Closer manage or Manual Close
                        # V16 Strategy: TP=2 ATR (~2%), SL=2 ATR (~2%)
                        'stop_loss': Decimal(str(entry_price * 0.98)) if amt > 0 else Decimal(str(entry_price * 1.02)), 
                        'take_profit': Decimal(str(entry_price * 1.02)) if amt > 0 else Decimal(str(entry_price * 0.98)),
                        'strategy': 'V16_RESCUE'
                    }
                    
                    try:
                        table.put_item(Item=item)
                        print(f"    ✅ Imported {internal_symbol} into DynamoDB")
                        count += 1
                    except Exception as e:
                        print(f"    ❌ Failed to import: {e}")
        
        if count == 0:
            print("✨ No orphaned positions found.")
            
    except Exception as e:
        print(f"❌ Failed to fetch/process positions: {e}")

if __name__ == "__main__":
    import_positions()
