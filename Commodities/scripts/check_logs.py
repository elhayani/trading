import boto3
import time
from datetime import datetime, timedelta

logs = boto3.client('logs', region_name='eu-west-3')  # Assuming region from previous context
log_group_name = '/aws/lambda/CommoditiesLiveTrader'

try:
    print(f"Checking logs for {log_group_name}...")
    response = logs.filter_log_events(
        logGroupName=log_group_name,
        startTime=int((datetime.utcnow() - timedelta(hours=2)).timestamp() * 1000),
        limit=20
    )
    
    events = response.get('events', [])
    if not events:
        print("No log events found in the last 2 hours.")
    else:
        for event in events:
            print(f"{datetime.fromtimestamp(event['timestamp']/1000)}: {event['message'].strip()}")

except Exception as e:
    print(f"Error reading logs: {e}")
