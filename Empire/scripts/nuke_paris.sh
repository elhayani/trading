
#!/bin/bash
REGION="eu-west-3"
echo "☢️  NUKING REGION: $REGION"

# 1. DynamoDB Tables
TABLES=$(aws dynamodb list-tables --region $REGION --query "TableNames[]" --output text)
for table in $TABLES; do
    echo "Deleting DynamoDB Table: $table..."
    aws dynamodb delete-table --table-name $table --region $REGION
done

# 2. S3 Buckets (Force Delete)
BUCKETS=$(aws s3api list-buckets --query "Buckets[?contains(Name, 'empire') || contains(Name, 'dashboard')].Name" --output text)
for bucket in $BUCKETS; do
    echo "Deleting S3 Bucket: $bucket..."
    aws s3 rb s3://$bucket --force --region $REGION
done

# 3. Log Groups (Optional)
LOGS=$(aws logs describe-log-groups --region $REGION --query "logGroups[?contains(logGroupName, 'Empire') || contains(logGroupName, 'V4')].logGroupName" --output text)
for log in $LOGS; do
    echo "Deleting Log Group: $log..."
    aws logs delete-log-group --logGroupName "$log" --region $REGION
done

echo "✅ PARIS CLEANED."
