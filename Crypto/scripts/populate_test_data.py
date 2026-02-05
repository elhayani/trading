import boto3
import uuid
from datetime import datetime
from decimal import Decimal

# Helper to convert float to Decimal for DynamoDB
def create_decimal(value):
    return Decimal(str(value))

def populate_tables():
    dynamodb = boto3.resource('dynamodb', region_name='eu-west-3')
    
    timestamp = datetime.utcnow().isoformat()
    
    # 1. Crypto Test Data
    crypto_table = dynamodb.Table('EmpireCryptoV4')
    crypto_item = {
        'TradeId': f"CRYPTO-{uuid.uuid4().hex[:8]}",
        'Status': 'OPEN',
        'AssetClass': 'Crypto',
        'Pair': 'SOL/USDT',
        'Type': 'LONG',
        'EntryPrice': create_decimal(95.50),
        'Size': create_decimal(10.5), # ~1000$
        'Timestamp': timestamp,
        'Strategy': 'TEST_DATA',
        'AI_Reason': 'High conviction breakout with BTC correlation.'
    }
    crypto_table.put_item(Item=crypto_item)
    print(f"✅ Inserted Crypto Trade: {crypto_item['Pair']}")

    # 2. Forex Test Data
    forex_table = dynamodb.Table('EmpireForexHistory')
    forex_item = {
        'TradeId': f"FOREX-{uuid.uuid4().hex[:8]}",
        'Status': 'OPEN',
        'AssetClass': 'Forex',
        'Pair': 'EURUSD',
        'Type': 'SHORT',
        'EntryPrice': create_decimal(1.0850),
        'Size': create_decimal(1000), # 1000 Units
        'Timestamp': timestamp,
        'Strategy': 'TEST_DATA'
    }
    forex_table.put_item(Item=forex_item)
    print(f"✅ Inserted Forex Trade: {forex_item['Pair']}")

    # 3. Indices Test Data
    indices_table = dynamodb.Table('EmpireIndicesHistory')
    indices_item = {
        'TradeId': f"INDICES-{uuid.uuid4().hex[:8]}",
        'Status': 'OPEN',
        'AssetClass': 'Indices',
        'Pair': '^GSPC', # S&P 500
        'Type': 'LONG',
        'EntryPrice': create_decimal(4950.25),
        'Size': create_decimal(0.2), 
        'Timestamp': timestamp,
        'Strategy': 'TEST_DATA'
    }
    indices_table.put_item(Item=indices_item)
    print(f"✅ Inserted Indices Trade: {indices_item['Pair']}")
    
    # 4. Commodities Test Data
    comm_table = dynamodb.Table('EmpireCommoditiesHistory')
    comm_item = {
        'TradeId': f"COMM-{uuid.uuid4().hex[:8]}",
        'Status': 'OPEN',
        'AssetClass': 'Commodities',
        'Pair': 'GC=F', # Gold
        'Type': 'LONG',
        'EntryPrice': create_decimal(2050.00),
        'Size': create_decimal(0.5), 
        'Timestamp': timestamp,
        'Strategy': 'TEST_DATA'
    }
    comm_table.put_item(Item=comm_item)
    print(f"✅ Inserted Commodities Trade: {comm_item['Pair']}")

if __name__ == "__main__":
    try:
        populate_tables()
        print("\n🚀 All test data inserted successfully!")
    except Exception as e:
        print(f"\n❌ Error inserting data: {e}")
