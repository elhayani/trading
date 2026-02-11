import boto3
import os
import logging
from botocore.exceptions import ClientError

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_v4_trading_state():
    """
    Migration script to add 'status' attribute to existing positions.
    Required for the 'status-timestamp-index' GSI (Audit #V11.5).
    """
    region = os.getenv('AWS_REGION', 'eu-west-3')
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table_name = os.getenv('STATE_TABLE', 'V4TradingState')
    table = dynamodb.Table(table_name)

    # ✅ Table existence validation
    try:
        table.table_status
        logger.info(f"✅ Table {table_name} found in {region}")
    except Exception as e:
        logger.error(f"❌ Table {table_name} not found or inaccessible in {region}: {e}")
        return

    logger.info(f"🚀 Starting migration for table: {table_name}")

    try:
        # Scan for all items starting with POSITION#
        response = table.scan(
            FilterExpression='begins_with(trader_id, :prefix)',
            ExpressionAttributeValues={':prefix': 'POSITION#'}
        )
        items = response.get('Items', [])
        
        updated_count = 0
        for item in items:
            trader_id = item['trader_id']
            
            # Check if status already exists
            if 'status' not in item:
                logger.info(f"  → Migrating {trader_id}...")
                table.update_item(
                    Key={'trader_id': trader_id},
                    UpdateExpression="SET #s = :status",
                    ExpressionAttributeNames={'#s': 'status'},
                    ExpressionAttributeValues={':status': 'OPEN'}
                )
                updated_count += 1
            else:
                logger.info(f"  [SKIP] {trader_id} already has status.")

        logger.info(f"✅ Migration complete. {updated_count} items updated.")

    except ClientError as e:
        logger.error(f"❌ Migration failed: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    migrate_v4_trading_state()
