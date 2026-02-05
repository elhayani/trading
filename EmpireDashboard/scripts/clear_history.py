
import boto3
from botocore.exceptions import ClientError

# Configuration
TABLE_NAME = "EmpireTradesHistory"
REGION = "eu-west-3"

# Client
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

def clear_table():
    print(f"🧹 Clearing all data from {TABLE_NAME}...")
    
    try:
        # Scan to get all items (expensive but necessary for wipe without deleting table)
        scan = table.scan()
        items = scan.get('Items', [])
        
        while 'LastEvaluatedKey' in scan:
            scan = table.scan(ExclusiveStartKey=scan['LastEvaluatedKey'])
            items.extend(scan['Items'])
            
        print(f"Found {len(items)} items to delete.")
        
        if not items:
            print("Table is already empty.")
            return

        with table.batch_writer() as batch:
            for item in items:
                # Need both keys for deletion
                batch.delete_item(
                    Key={
                        'TradeId': item['TradeId'],
                        'Timestamp': item['Timestamp']
                    }
                )
                
        print("✅ Table cleared successfully. Ready for Real Trading data.")
        
    except Exception as e:
        print(f"❌ Error clearing table: {e}")

if __name__ == "__main__":
    confirm = input("⚠️  WARNING: This will delete ALL trade history. Type 'DELETE' to confirm: ")
    if confirm == "DELETE":
        clear_table()
    else:
        print("Operation cancelled.")
