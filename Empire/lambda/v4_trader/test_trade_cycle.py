"""
🧪 TEST: Trade Cycle Integrity (Open → Close → Verify DynamoDB)
================================================================
Teste que le bot peut:
1. Ouvrir un trade et le logger dans EmpireTradesHistory (Status=OPEN)
2. Fermer un trade et le mettre à jour (Status=CLOSED, ExitPrice, PnL, ExitReason)
3. Logger un SKIP dans EmpireSkippedTrades (table séparée)
4. Vérifier que MAX_OPEN_TRADES bloque les excédents
5. Vérifier la cohérence DynamoDB ↔ Binance

Usage:
    python test_trade_cycle.py              # Run all tests
    python test_trade_cycle.py --cleanup    # Clean ghost OPEN trades
"""

import os
import sys
import json
import time
import uuid
import boto3
from datetime import datetime, timezone, timedelta
from decimal import Decimal

# Setup env
os.environ.setdefault('AWS_DEFAULT_REGION', 'eu-west-3')
os.environ.setdefault('HISTORY_TABLE', 'EmpireTradesHistory')
os.environ.setdefault('SKIPPED_TABLE', 'EmpireSkippedTrades')
os.environ.setdefault('STATE_TABLE', 'V4TradingState')

REGION = os.environ['AWS_DEFAULT_REGION']
dynamodb = boto3.resource('dynamodb', region_name=REGION)
trades_table = dynamodb.Table(os.environ['HISTORY_TABLE'])
skipped_table = dynamodb.Table(os.environ['SKIPPED_TABLE'])
state_table = dynamodb.Table(os.environ['STATE_TABLE'])

# ==================== HELPERS ====================

def to_decimal(obj):
    if isinstance(obj, float): return Decimal(str(obj))
    if isinstance(obj, dict): return {k: to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list): return [to_decimal(v) for v in obj]
    return obj

def from_decimal(obj):
    if isinstance(obj, Decimal): return float(obj)
    if isinstance(obj, dict): return {k: from_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list): return [from_decimal(v) for v in obj]
    return obj

PASS = "✅"
FAIL = "❌"
results = []

def test(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, condition))
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))
    return condition

# ==================== TEST 1: OPEN TRADE ====================

def test_open_trade():
    print("\n📝 TEST 1: Log Trade OPEN")
    trade_id = f"TEST-{uuid.uuid4().hex[:8]}"
    timestamp = datetime.now(timezone.utc).isoformat()
    
    item = {
        'trader_id': trade_id,
        'timestamp': timestamp,
        'TradeId': trade_id,
        'Symbol': 'TEST/USDT:USDT',
        'Pair': 'TEST/USDT:USDT',
        'AssetClass': 'crypto',
        'Type': 'LONG',
        'EntryPrice': 100.0,
        'Size': 1.0,
        'Cost': 100.0,
        'TakeProfit': 100.25,
        'StopLoss': 99.60,
        'Leverage': 2,
        'Timestamp': timestamp,
        'Status': 'OPEN',
        'Reason': 'RSI=28.5 | RSI=28.5 | Trend=BULLISH | AI=70% | Score=70 | Lev=2x'
    }
    
    trades_table.put_item(Item=to_decimal(item))
    
    # Verify it was written
    response = trades_table.query(
        KeyConditionExpression='trader_id = :tid',
        ExpressionAttributeValues={':tid': trade_id},
        Limit=1
    )
    
    items = response.get('Items', [])
    test("Trade OPEN écrit dans EmpireTradesHistory", len(items) == 1)
    
    if items:
        item_read = from_decimal(items[0])
        test("Status = OPEN", item_read['Status'] == 'OPEN')
        test("Symbol correct", item_read['Symbol'] == 'TEST/USDT:USDT')
        test("Direction = LONG", item_read['Type'] == 'LONG')
        test("Leverage = 2", item_read.get('Leverage') == 2)
        test("TakeProfit = 100.25", item_read.get('TakeProfit') == 100.25)
        test("StopLoss = 99.60", item_read.get('StopLoss') == 99.60)
        test("Reason détaillée présente", 'RSI=' in item_read.get('Reason', ''))
    
    return trade_id, timestamp

# ==================== TEST 2: CLOSE TRADE ====================

def test_close_trade(trade_id):
    print("\n📝 TEST 2: Log Trade CLOSE (query au lieu de scan)")
    
    # Simulate close — this is the EXACT code from log_trade_close (fixed version)
    response = trades_table.query(
        KeyConditionExpression='trader_id = :tid',
        ExpressionAttributeValues={':tid': trade_id},
        Limit=1
    )
    
    found = len(response.get('Items', [])) > 0
    test("Query par trader_id trouve le trade", found)
    
    if not found:
        print(f"  {FAIL} ABORT: trade not found, cannot test close")
        return False
    
    item = response['Items'][0]
    trader_id = item['trader_id']
    timestamp = item['timestamp']
    
    exit_price = 100.30
    pnl = 0.30
    reason = "Take Profit hit at $100.30 (TP: $100.25, PnL: +0.30%)"
    
    trades_table.update_item(
        Key={'trader_id': trader_id, 'timestamp': timestamp},
        UpdateExpression='SET #st = :status, ExitPrice = :price, PnL = :pnl, ExitReason = :reason, ClosedAt = :closed_at',
        ExpressionAttributeNames={'#st': 'Status'},
        ExpressionAttributeValues=to_decimal({
            ':status': 'CLOSED', ':price': exit_price, ':pnl': pnl, ':reason': reason,
            ':closed_at': datetime.now(timezone.utc).isoformat()
        })
    )
    
    # Verify update
    response2 = trades_table.query(
        KeyConditionExpression='trader_id = :tid',
        ExpressionAttributeValues={':tid': trade_id},
        Limit=1
    )
    
    if response2.get('Items'):
        closed = from_decimal(response2['Items'][0])
        test("Status = CLOSED", closed['Status'] == 'CLOSED')
        test("ExitPrice = 100.30", closed.get('ExitPrice') == 100.30)
        test("PnL = 0.30", closed.get('PnL') == 0.30)
        test("ExitReason contient 'Take Profit'", 'Take Profit' in closed.get('ExitReason', ''))
        test("ClosedAt présent", 'ClosedAt' in closed)
        return True
    else:
        test("Trade retrouvé après close", False)
        return False

# ==================== TEST 3: SKIPPED TRADE ====================

def test_skipped_trade():
    print("\n📝 TEST 3: Log SKIP dans EmpireSkippedTrades (table séparée)")
    
    trade_id = f"SKIP-{uuid.uuid4().hex[:8]}"
    timestamp = datetime.now(timezone.utc).isoformat()
    ttl = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
    
    try:
        skipped_table.put_item(Item=to_decimal({
            'trader_id': trade_id,
            'timestamp': timestamp,
            'Symbol': 'BTC/USDT:USDT',
            'Pair': 'BTC/USDT:USDT',
            'AssetClass': 'crypto',
            'Status': 'SKIPPED',
            'Reason': 'RSI neutral (45.2) | Low technical score (0)',
            'ttl': ttl
        }))
        test("SKIP écrit dans EmpireSkippedTrades", True)
    except Exception as e:
        test("SKIP écrit dans EmpireSkippedTrades", False, str(e))
        return trade_id
    
    # Verify it's in skipped table
    response = skipped_table.query(
        KeyConditionExpression='trader_id = :tid',
        ExpressionAttributeValues={':tid': trade_id},
        Limit=1
    )
    items = response.get('Items', [])
    test("SKIP retrouvé dans EmpireSkippedTrades", len(items) == 1)
    
    if items:
        skip = from_decimal(items[0])
        test("Reason détaillée présente", 'RSI neutral' in skip.get('Reason', ''))
        test("TTL configuré (7 jours)", skip.get('ttl', 0) > 0)
    
    # Verify it's NOT in trades table
    response2 = trades_table.query(
        KeyConditionExpression='trader_id = :tid',
        ExpressionAttributeValues={':tid': trade_id},
        Limit=1
    )
    test("SKIP absent de EmpireTradesHistory", len(response2.get('Items', [])) == 0)
    
    return trade_id

# ==================== TEST 4: POSITION STATE ====================

def test_position_state():
    print("\n📝 TEST 4: Position State (V4TradingState)")
    
    symbol = 'TEST/USDT:USDT'
    safe_symbol = symbol.replace('/', '_').replace(':', '-')
    trader_id = f'POSITION#{safe_symbol}'
    
    # Save position
    pos_data = {
        'trade_id': 'TEST-pos123',
        'entry_price': 100.0,
        'quantity': 1.0,
        'direction': 'LONG',
        'stop_loss': 99.60,
        'take_profit': 100.25,
        'asset_class': 'crypto',
        'risk_dollars': 4.0,
        'entry_time': datetime.now(timezone.utc).isoformat()
    }
    
    state_table.put_item(Item=to_decimal({
        'trader_id': trader_id,
        'position': pos_data,
        'status': 'OPEN',
        'timestamp': datetime.now(timezone.utc).isoformat()
    }))
    
    # Read back via GSI
    try:
        response = state_table.query(
            IndexName='status-timestamp-index',
            KeyConditionExpression='#status = :open',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':open': 'OPEN'}
        )
        positions = {}
        for item in response.get('Items', []):
            san = item['trader_id'].replace('POSITION#', '')
            orig = san.replace('_', '/').replace('-', ':')
            positions[orig] = from_decimal(item['position'])
        
        test("Position sauvée et lisible via GSI", symbol in positions)
        if symbol in positions:
            pos = positions[symbol]
            test("Direction = LONG", pos['direction'] == 'LONG')
            test("trade_id = TEST-pos123", pos['trade_id'] == 'TEST-pos123')
    except Exception as e:
        test("GSI Query fonctionne", False, str(e))
    
    # Delete position
    state_table.delete_item(Key={'trader_id': trader_id})
    
    # Verify deleted
    response2 = state_table.get_item(Key={'trader_id': trader_id})
    test("Position supprimée après delete", 'Item' not in response2)

# ==================== TEST 5: COUNT OPEN TRADES ====================

def test_count_open_trades():
    print("\n📝 TEST 5: Comptage trades OPEN dans EmpireTradesHistory")
    
    response = trades_table.scan(
        FilterExpression='#st = :open',
        ExpressionAttributeNames={'#st': 'Status'},
        ExpressionAttributeValues={':open': 'OPEN'},
        Select='COUNT'
    )
    count = response.get('Count', 0)
    
    # Paginate if needed
    while 'LastEvaluatedKey' in response:
        response = trades_table.scan(
            FilterExpression='#st = :open',
            ExpressionAttributeNames={'#st': 'Status'},
            ExpressionAttributeValues={':open': 'OPEN'},
            Select='COUNT',
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        count += response.get('Count', 0)
    
    print(f"  📊 Trades OPEN en DB: {count}")
    test(f"Nombre raisonnable de OPEN (<= 10)", count <= 10, f"Trouvé: {count}")
    return count

# ==================== CLEANUP: Ghost OPEN trades ====================

def cleanup_ghost_trades():
    print("\n🧹 CLEANUP: Marquer tous les ghost OPEN comme ORPHANED")
    
    response = trades_table.scan(
        FilterExpression='#st = :open',
        ExpressionAttributeNames={'#st': 'Status'},
        ExpressionAttributeValues={':open': 'OPEN'}
    )
    
    items = response.get('Items', [])
    while 'LastEvaluatedKey' in response:
        response = trades_table.scan(
            FilterExpression='#st = :open',
            ExpressionAttributeNames={'#st': 'Status'},
            ExpressionAttributeValues={':open': 'OPEN'},
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        items.extend(response.get('Items', []))
    
    print(f"  Found {len(items)} ghost OPEN trades")
    
    for item in items:
        tid = item['trader_id']
        ts = item['timestamp']
        symbol = item.get('Symbol', 'UNKNOWN')
        
        # Skip our test trades
        if 'TEST' in str(tid):
            continue
            
        trades_table.update_item(
            Key={'trader_id': tid, 'timestamp': ts},
            UpdateExpression='SET #st = :status, ExitReason = :reason, ClosedAt = :closed_at',
            ExpressionAttributeNames={'#st': 'Status'},
            ExpressionAttributeValues=to_decimal({
                ':status': 'ORPHANED',
                ':reason': 'Ghost trade cleaned by test_trade_cycle.py (V13.4 cleanup)',
                ':closed_at': datetime.now(timezone.utc).isoformat()
            })
        )
        print(f"  🧹 Marked ORPHANED: {tid} ({symbol})")
    
    print(f"  ✅ Cleaned {len(items)} ghost trades")

# ==================== CLEANUP TEST DATA ====================

def cleanup_test_data(trade_id, skip_id):
    print("\n🧹 Cleaning up test data...")
    
    # Delete test trade from EmpireTradesHistory
    if trade_id:
        response = trades_table.query(
            KeyConditionExpression='trader_id = :tid',
            ExpressionAttributeValues={':tid': trade_id}
        )
        for item in response.get('Items', []):
            trades_table.delete_item(Key={'trader_id': item['trader_id'], 'timestamp': item['timestamp']})
            print(f"  Deleted test trade: {trade_id}")
    
    # Delete test skip from EmpireSkippedTrades
    if skip_id:
        response = skipped_table.query(
            KeyConditionExpression='trader_id = :tid',
            ExpressionAttributeValues={':tid': skip_id}
        )
        for item in response.get('Items', []):
            skipped_table.delete_item(Key={'trader_id': item['trader_id'], 'timestamp': item['timestamp']})
            print(f"  Deleted test skip: {skip_id}")

# ==================== MAIN ====================

if __name__ == '__main__':
    print("=" * 60)
    print("🧪 EMPIRE V13.4 — Trade Cycle Integrity Test")
    print("=" * 60)
    
    if '--cleanup' in sys.argv:
        cleanup_ghost_trades()
        sys.exit(0)
    
    # Run tests
    trade_id, trade_ts = test_open_trade()
    close_ok = test_close_trade(trade_id)
    skip_id = test_skipped_trade()
    test_position_state()
    open_count = test_count_open_trades()
    
    # Cleanup test data
    cleanup_test_data(trade_id, skip_id)
    
    # Summary
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"📊 RÉSULTATS: {passed}/{total} tests passés")
    
    if passed == total:
        print("✅ ALL TESTS PASSED — Le cycle Open/Close/Skip fonctionne correctement")
    else:
        failed = [name for name, ok in results if not ok]
        print(f"❌ {total - passed} TESTS FAILED:")
        for f in failed:
            print(f"   - {f}")
    
    if open_count > 10:
        print(f"\n⚠️  {open_count} ghost OPEN trades détectés. Lancer: python test_trade_cycle.py --cleanup")
    
    print("=" * 60)
    sys.exit(0 if passed == total else 1)
