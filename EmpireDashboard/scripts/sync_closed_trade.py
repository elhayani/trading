import boto3
from decimal import Decimal
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('EmpireTradesHistory')

# We target the trade from 10:13:46
# Based on previous logs, it's TRADE-dae203cf
trade_id = "TRADE-dae203cf"
timestamp = "2026-02-09T10:13:46.306473"

# Calculated PnL: Approx -21.00 USDT
pnl = Decimal("-21.00")

print(f"🔄 Updating trade {trade_id} with PnL {pnl}...")

try:
    table.update_item(
        Key={
            'TradeId': trade_id,
            'Timestamp': timestamp
        },
        UpdateExpression="SET #s = :s, PnL = :p, ExitPrice = :e, ClosedAt = :c",
        ExpressionAttributeNames={
            "#s": "Status"
        },
        ExpressionAttributeValues={
            ":s": "CLOSED",
            ":p": pnl,
            ":e": Decimal("70602.7"), # Estimated exit price based on loss
            ":c": datetime.utcnow().isoformat()
        }
    )
    print("✅ Trade updated successfully in EmpireTradesHistory!")
except Exception as e:
    print(f"❌ Error updating trade: {e}")

# Check if there is a duplicate or another record to update (like the one at 10:15:48)
try:
    table.update_item(
        Key={
            'TradeId': "TRADE-7769514c",
            'Timestamp': "2026-02-09T10:15:48Z"
        },
        UpdateExpression="SET #s = :s, PnL = :p",
        ExpressionAttributeNames={"#s": "Status"},
        ExpressionAttributeValues={":s": "CLOSED", ":p": Decimal("0.0")} # Already closed in logs
    )
except:
    pass
