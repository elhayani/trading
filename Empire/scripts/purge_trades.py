import boto3
import os

def purge_table(table_name, region='us-east-1'):
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)
    
    print(f"Purging table: {table_name} in {region}")
    
    # Scan for all items, only requesting keys for efficiency
    projection_expression = "TradeId, #ts"
    expression_attribute_names = {"#ts": "Timestamp"}
    
    items_deleted = 0
    
    scan = table.scan(
        ProjectionExpression=projection_expression,
        ExpressionAttributeNames=expression_attribute_names
    )
    
    with table.batch_writer() as batch:
        for item in scan.get('Items', []):
            batch.delete_item(
                Key={
                    'TradeId': item['TradeId'],
                    'Timestamp': item['Timestamp']
                }
            )
            items_deleted += 1
            
        while 'LastEvaluatedKey' in scan:
            scan = table.scan(
                ProjectionExpression=projection_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExclusiveStartKey=scan['LastEvaluatedKey']
            )
            for item in scan.get('Items', []):
                batch.delete_item(
                    Key={
                        'TradeId': item['TradeId'],
                        'Timestamp': item['Timestamp']
                    }
                )
                items_deleted += 1
                
    print(f"Successfully deleted {items_deleted} items.")

if __name__ == "__main__":
    purge_table('EmpireTradesHistory')
