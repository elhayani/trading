import json
import boto3
import time
import os

def lambda_handler(event, context):
    start = time.time()
    try:
        print("INIT HANDLER")
        dynamodb = boto3.resource('dynamodb', region_name='eu-west-3')
        table_name = os.environ.get('TABLE_NAME', 'EmpireTradesHistory')
        table = dynamodb.Table(table_name)
        
        print(f"SCANNING {table_name}")
        resp = table.scan(Limit=10)
        items = resp.get('Items', [])
        
        duration = time.time() - start
        print(f"DONE in {duration}s")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json', 
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Debug Scan Success',
                'duration': duration,
                'items_count': len(items),
                'table_name': table_name
            }, default=str)
        }
    except Exception as e:
        print(f"ERROR: {e}")
        return {
            'statusCode': 200, # Return 200 to see the error
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
