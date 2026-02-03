
import json
import boto3
from decimal import Decimal
from datetime import datetime

# Initialize DynamoDB Client
dynamodb = boto3.resource('dynamodb')
table_name = "EmpireTradesHistory"
table = dynamodb.Table(table_name)

class DecimalEncoder(json.JSONEncoder):
    """Helper class to convert Decimal items to float for JSON compatibility"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def get_all_trades():
    """Scan the entire table (OK for low volume, consider Query with Index later)"""
    try:
        response = table.scan()
        data = response.get('Items', [])
        
        # Handle pagination if strictly necessary, but for valid Free Tier usage < 1MB is ok
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            data.extend(response['Items'])
            
        return data
    except Exception as e:
        print(f"Error scanning table: {e}")
        return []

def calculate_equity_curve(trades):
    """Calculate cumulative PnL over time"""
    # Sort trades by timestamp
    trades.sort(key=lambda x: x.get('Timestamp', ''))
    
    # Initialize Start Capital (Virtual Pool)
    # Crypto: 500, Forex: 300, Indices: 200 = 1000 Total
    initial_capital = 1000.0 
    current_equity = initial_capital
    
    equity_curve = []
    
    # Add initial point
    if trades:
        start_date = trades[0].get('Timestamp')
        equity_curve.append({
            'x': start_date, # Time
            'y': initial_capital # Value
        })
        
    for trade in trades:
        # Only closed trades affect PnL (assuming we log 'CLOSE' or update 'Status')
        # Simple Logic: If PnL field exists, add it.
        pnl = float(trade.get('PnL', 0.0))
        
        current_equity += pnl
        
        equity_curve.append({
            'x': trade.get('Timestamp'),
            'y': current_equity,
            'details': f"{trade.get('Pair')} ({trade.get('Type')}) PnL: {pnl}"
        })
        
    return equity_curve

def lambda_handler(event, context):
    print("📊 Dashboard API Request Received")
    
    try:
        trades = get_all_trades()
        
        # 1. Equity Curve Data
        equity_data = calculate_equity_curve(trades)
        
        # 2. Recent Trades (Reverse Chronological)
        recent_trades = sorted(trades, key=lambda x: x.get('Timestamp', ''), reverse=True)[:50]
        
        # 3. Stats Summary
        total_pnl = sum(float(t.get('PnL', 0)) for t in trades)
        win_count = sum(1 for t in trades if float(t.get('PnL', 0)) > 0)
        total_count = len(trades)
        win_rate = (win_count / total_count * 100) if total_count > 0 else 0
        
        response_body = {
            'stats': {
                'total_pnl': round(total_pnl, 2),
                'win_rate': round(win_rate, 1),
                'total_trades': total_count,
                'current_equity': round(1000 + total_pnl, 2)
            },
            'equity_curve': equity_data,
            'recent_trades': recent_trades
        }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*', # Allow frontend access
                'Access-Control-Allow-Methods': 'GET, OPTIONS'
            },
            'body': json.dumps(response_body, cls=DecimalEncoder)
        }
        
    except Exception as e:
        print(f"Server Error: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }
