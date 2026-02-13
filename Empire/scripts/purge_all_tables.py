import boto3
import os

def get_table_keys(table):
    """Dynamically find the partition and sort keys of a table."""
    key_schema = table.key_schema
    keys = [k['AttributeName'] for k in key_schema]
    return keys

def purge_table(table_name, region='eu-west-3'):
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)
    
    print(f"\n🚀 Purging table: {table_name} in {region}...")
    
    try:
        keys = get_table_keys(table)
        print(f"  → Detected keys: {', '.join(keys)}")
        
        # Projection for keys only
        projection = ", ".join([f"#{k}" for k in keys])
        names = {f"#{k}": k for k in keys}
        
        items_deleted = 0
        scan = table.scan(ProjectionExpression=projection, ExpressionAttributeNames=names)
        
        def delete_batch(items):
            count = 0
            with table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(Key={k: item[k] for k in keys})
                    count += 1
            return count

        items_deleted += delete_batch(scan.get('Items', []))
        
        while 'LastEvaluatedKey' in scan:
            scan = table.scan(
                ProjectionExpression=projection,
                ExpressionAttributeNames=names,
                ExclusiveStartKey=scan['LastEvaluatedKey']
            )
            items_deleted += delete_batch(scan.get('Items', []))
            
        print(f"  ✅ Successfully deleted {items_deleted} items.")
    except Exception as e:
        print(f"  ❌ Error purging {table_name}: {e}")

if __name__ == "__main__":
    tables = [
        'EmpireTradesHistory',
        'EmpireSkippedTrades',
        'V4TradingState'
    ]
    
    region = os.getenv('AWS_REGION', 'eu-west-3')
    
    print("="*50)
    print(f"🧹 EMPIRE DYNAMODB PURGE (Region: {region})")
    print("="*50)
    
    for table in tables:
        purge_table(table, region)
    
    print("\n✨ All tables purged. Ready for a fresh start!")
