
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
        # Get Year Filter from Query Params
        query_params = event.get('queryStringParameters') or {}
        year_filter = query_params.get('year') # e.g., '2025' or None for ALL
        
        all_trades = get_all_trades()
        
        # Filter by Year if requested
        if year_filter and year_filter != 'ALL':
            trades = [t for t in all_trades if t.get('Timestamp', '').startswith(year_filter)]
            
            # --- Equity Curve for SPECIFIC YEAR ---
            # Should we start from 1000 or from the balance at start of that year?
            # For simplicity in this user request ("donnees de l'annee en complet"), 
            # we will show performance WITHIN that year (starting 0 PnL for chart or absolute equity?)
            # Let's show Absolute Equity but filtered points.
            
            # Better: Filter trades for the curve calculation BUT include previous history for initial balance?
            # Or just show PnL evolution during that year.
            # Let's keep it simple: Show trades of that year. 
            # Recalculate curve ONLY for that year starting from actual balance at year start?
            
            # 1. Calculate Balance at Start of Year
            trades_before = [t for t in all_trades if t.get('Timestamp', '') < f"{year_filter}-01-01"]
            pnl_before = sum(float(t.get('PnL', 0)) for t in trades_before)
            start_equity = 1000.0 + pnl_before
            
            # 2. Calculate Curve for Target Year
            # Sort Target Trades
            trades.sort(key=lambda x: x.get('Timestamp', ''))
            
            current_equity = start_equity
            equity_curve = []
            
            # Add Start Point (Jan 1st)
            equity_curve.append({
                'x': f"{year_filter}-01-01T00:00:00",
                'y': start_equity
            })
            
            for trade in trades:
                pnl = float(trade.get('PnL', 0.0))
                current_equity += pnl
                equity_curve.append({
                    'x': trade.get('Timestamp'),
                    'y': current_equity,
                    'details': f"{trade.get('Pair')} ({trade.get('Type')}) PnL: {pnl}"
                })
                
            equity_data = equity_curve

        else:
            # ALL TIME logic
            trades = all_trades
            equity_data = calculate_equity_curve(trades)

        # 2. Recent Trades (Stats based on filtered list)
        recent_trades = sorted(trades, key=lambda x: x.get('Timestamp', ''), reverse=True)[:50]
        
        # 3. Stats Summary (For the filtered period)
        total_pnl = sum(float(t.get('PnL', 0)) for t in trades)
        win_count = sum(1 for t in trades if float(t.get('PnL', 0)) > 0)
        total_count = len(trades)
        win_rate = (win_count / total_count * 100) if total_count > 0 else 0
        
        # Current Equity is always Global End Equity for the display at top? 
        # Or End Equity of the year? 
        # User requested "donnees de l'annee en complet". 
        # If I select 2025, I expect to see 2025 performance.
        
        if year_filter and year_filter != 'ALL':
             end_equity = start_equity + total_pnl
        else:
             end_equity = 1000.0 + total_pnl

        # 4. Asset Allocation Breakdown (End of Period)
        # Determine relevant trades for cumulative PnL calculation
        if year_filter and year_filter != 'ALL':
            next_year = int(year_filter) + 1
            cutoff_date = f"{next_year}-01-01"
            cumulative_trades = [t for t in all_trades if t.get('Timestamp', '') < cutoff_date]
        else:
            cumulative_trades = all_trades

        # Initial Allocations
        allocations = {
            'Crypto': {'initial': 500.0, 'current': 500.0, 'pnl': 0.0},
            'Forex': {'initial': 300.0, 'current': 300.0, 'pnl': 0.0},
            'Indices': {'initial': 200.0, 'current': 200.0, 'pnl': 0.0}
        }

        for t in cumulative_trades:
            asset = t.get('AssetClass') # 'Crypto', 'Forex', 'Indices'
            if asset in allocations:
                pnl = float(t.get('PnL', 0.0))
                allocations[asset]['pnl'] += pnl
                allocations[asset]['current'] += pnl

        response_body = {
            'stats': {
                'total_pnl': round(total_pnl, 2),
                'win_rate': round(win_rate, 1),
                'total_trades': total_count,
                'current_equity': round(end_equity, 2)
            },
            'allocations': allocations,
            'equity_curve': equity_data,
            'recent_trades': recent_trades,
            'year': year_filter or 'ALL'
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
