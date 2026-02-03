import json
import boto3
import os
import traceback
from decimal import Decimal
from datetime import datetime

# Initialize DynamoDB Client
dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('TABLE_NAME', 'EmpireTradesHistory')
config_table_name = os.environ.get('CONFIG_TABLE', 'EmpireConfig')

table = dynamodb.Table(table_name)
config_table = dynamodb.Table(config_table_name)

class DecimalEncoder(json.JSONEncoder):
    """Helper class to convert Decimal items to float for JSON compatibility"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def get_all_trades():
    try:
        response = table.scan()
        data = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            data.extend(response['Items'])
        return data
    except Exception as e:
        print(f"Error scanning table: {e}")
        return []

def calculate_equity_curve(trades):
    if not trades:
        return []
    
    # Sort trades by timestamp
    sorted_trades = sorted(trades, key=lambda x: x.get('Timestamp', ''))
    
    initial_capital = 1000.0 
    current_equity = initial_capital
    equity_curve = []
    
    # Start point
    start_date = sorted_trades[0].get('Timestamp')
    equity_curve.append({'x': start_date, 'y': initial_capital})
        
    for trade in sorted_trades:
        pnl = float(trade.get('PnL', 0.0))
        current_equity += pnl
        equity_curve.append({
            'x': trade.get('Timestamp'),
            'y': current_equity,
            'details': f"{trade.get('Pair')} ({trade.get('Type')}) PnL: {pnl}"
        })
    return equity_curve

def lambda_handler(event, context):
    print(f"📊 Dashboard API Request: {json.dumps(event)}")
    
    # Standard CORS Headers for all responses
    cors_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token'
    }

    try:
        # Determine Route
        # In HTTP API, path is event['rawPath'] or event['requestContext']['http']['path']
        path = event.get('rawPath') or event.get('path', '/')
        method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        
        # --- PANIC SWITCH STATUS (/status) ---
        if '/status' in path:
            if method == 'GET':
                statuses = {}
                for sys in ['Crypto', 'Forex', 'Indices']:
                    try:
                        res = config_table.get_item(Key={'ConfigKey': f'PANIC_{sys.upper()}'})
                        statuses[sys] = res.get('Item', {}).get('Value', 'ACTIVE')
                    except:
                        statuses[sys] = 'ACTIVE'
                return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps(statuses)
                }
            
            elif method == 'POST':
                try:
                    body = json.loads(event.get('body', '{}'))
                    system = body.get('system')
                    new_status = body.get('status')
                    if system in ['Crypto', 'Forex', 'Indices'] and new_status in ['ACTIVE', 'PANIC']:
                        config_table.put_item(Item={
                            'ConfigKey': f'PANIC_{system.upper()}',
                            'Value': new_status,
                            'UpdatedAt': datetime.utcnow().isoformat()
                        })
                        return {
                            'statusCode': 200,
                            'headers': cors_headers,
                            'body': json.dumps({'message': f'{system} set to {new_status}'})
                        }
                except:
                    pass
                return {'statusCode': 400, 'headers': cors_headers, 'body': json.dumps({'error': 'Invalid request'})}

        # --- STATS LOGIC (/stats or default) ---
        query_params = event.get('queryStringParameters') or {}
        year_filter = query_params.get('year')

        all_trades = get_all_trades()
        
        if year_filter and year_filter != 'ALL':
            trades = [t for t in all_trades if t.get('Timestamp', '').startswith(year_filter)]
            
            # Start Balance (Cumulative from before the year)
            trades_before = [t for t in all_trades if t.get('Timestamp', '') < f"{year_filter}-01-01"]
            pnl_before = sum(float(t.get('PnL', 0.0)) for t in trades_before)
            start_equity = 1000.0 + pnl_before
            
            # Curve for target year
            trades.sort(key=lambda x: x.get('Timestamp', ''))
            run_equity = start_equity
            equity_data = [{'x': f"{year_filter}-01-01T00:00:00Z", 'y': start_equity}]
            
            for trade in trades:
                pnl = float(trade.get('PnL', 0.0))
                run_equity += pnl
                equity_data.append({
                    'x': trade.get('Timestamp'),
                    'y': run_equity,
                    'details': f"{trade.get('Pair')} ({trade.get('Type')}) PnL: {pnl}"
                })
            current_display_equity = run_equity
        else:
            trades = all_trades
            equity_data = calculate_equity_curve(trades)
            current_display_equity = 1000.0 + sum(float(t.get('PnL', 0.0)) for t in trades)

        # Recent Trades & Key Stats
        recent_trades = sorted(trades, key=lambda x: x.get('Timestamp', ''), reverse=True)[:50]
        total_pnl = sum(float(t.get('PnL', 0.0)) for t in trades)
        win_count = sum(1 for t in trades if float(t.get('PnL', 0.0)) > 0)
        total_count = len(trades)
        win_rate = (win_count / total_count * 100) if total_count > 0 else 0
        
        # Allocation Breakdown (End of year state)
        if year_filter and year_filter != 'ALL':
            cutoff = f"{int(year_filter)+1}-01-01"
            cum_trades = [t for t in all_trades if t.get('Timestamp', '') < cutoff]
        else:
            cum_trades = all_trades

        allocations = {
            'Crypto': {'current': 500.0, 'pnl': 0.0, 'total': 0, 'open': 0, 'closed': 0},
            'Forex': {'current': 300.0, 'pnl': 0.0, 'total': 0, 'open': 0, 'closed': 0},
            'Indices': {'current': 200.0, 'pnl': 0.0, 'total': 0, 'open': 0, 'closed': 0}
        }
        for t in cum_trades:
            asset = t.get('AssetClass')
            if asset in allocations:
                pnl = float(t.get('PnL', 0.0))
                status = t.get('Status', 'OPEN').upper()
                allocations[asset]['pnl'] += pnl
                allocations[asset]['current'] += pnl
                allocations[asset]['total'] += 1
                if status == 'OPEN':
                    allocations[asset]['open'] += 1
                else:
                    allocations[asset]['closed'] += 1

        response_body = {
            'stats': {
                'total_pnl': round(total_pnl, 2),
                'win_rate': round(win_rate, 1),
                'total_trades': total_count,
                'current_equity': round(current_display_equity, 2)
            },
            'allocations': allocations,
            'equity_curve': equity_data,
            'recent_trades': recent_trades,
            'year': year_filter or 'ALL'
        }
        
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(response_body, cls=DecimalEncoder)
        }
        
    except Exception as e:
        print(f"🔥 Lambda Error: {e}")
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e), 'trace': traceback.format_exc()})
        }
