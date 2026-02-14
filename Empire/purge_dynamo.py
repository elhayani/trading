import boto3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def purge_table(table_name, keys):
    dynamodb = boto3.resource('dynamodb', region_name='eu-west-3')
    table = dynamodb.Table(table_name)
    
    logger.info(f"Purging table: {table_name}")
    
    # Scan for all items
    scan = table.scan()
    items = scan.get('Items', [])
    
    while 'LastEvaluatedKey' in scan:
        scan = table.scan(ExclusiveStartKey=scan['LastEvaluatedKey'])
        items.extend(scan.get('Items', []))
    
    if not items:
        logger.info(f"Table {table_name} is already empty.")
        return

    logger.info(f"Found {len(items)} items to delete in {table_name}.")
    
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={k: item[k] for k in keys})
            
    logger.info(f"Successfully purged {table_name}.")

if __name__ == "__main__":
    tables_to_purge = [
        ("V4TradingState", ["trader_id"]),
        ("EmpireTradesHistory", ["trader_id", "timestamp"]),
        ("EmpireSkippedTrades", ["trader_id", "timestamp"])
    ]
    
    for table_name, keys in tables_to_purge:
        try:
            purge_table(table_name, keys)
        except Exception as e:
            logger.error(f"Failed to purge {table_name}: {e}")
