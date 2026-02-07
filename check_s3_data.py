import boto3
import json
import os

s3 = boto3.client('s3', region_name='eu-west-3')
bucket = 'empire-trading-data-paris'
symbol = 'EUR_USD'
years = [2024, 2025, 2026]

print(f"Checking data for {symbol} in {bucket}")

for y in years:
    key = f"historical/{symbol}/{y}.json"
    try:
        resp = s3.get_object(Bucket=bucket, Key=key)
        data = json.loads(resp['Body'].read().decode('utf-8'))
        print(f"{key}: Found {len(data)} candles")
        if len(data) > 0:
            print(f"  First: {data[0]}")
            print(f"  Last : {data[-1]}")
    except Exception as e:
        print(f"{key}: Failed - {e}")
