import boto3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clear_table(table_name, partition_key, sort_key=None):
    dynamodb = boto3.resource('dynamodb', region_name='eu-west-3')
    table = dynamodb.Table(table_name)
    
    logger.info(f"Scanning table {table_name}...")
    scan = table.scan()
    items = scan.get('Items', [])
    
    count = 0
    with table.batch_writer() as batch:
        for item in items:
            key = {partition_key: item[partition_key]}
            if sort_key:
                key[sort_key] = item[sort_key]
            batch.delete_item(Key=key)
            count += 1
            
    logger.info(f"Successfully deleted {count} items from {table_name}.")

if __name__ == "__main__":
    tables_to_clear = [
        {"name": "EmpireTradesHistory", "pk": "trader_id", "sk": "timestamp"},
        {"name": "EmpireSkippedTrades", "pk": "trader_id", "sk": "timestamp"}
    ]
    
    for table_info in tables_to_clear:
        try:
            clear_table(table_info["name"], table_info["pk"], table_info["sk"])
        except Exception as e:
            logger.error(f"Failed to clear {table_info['name']}: {e}")
