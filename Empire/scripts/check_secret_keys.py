import boto3
import json
import os

def check_secret_keys():
    session = boto3.session.Session(region_name='eu-west-3')
    client = session.client('secretsmanager')
    
    try:
        response = client.get_secret_value(SecretId='trading/binance')
        if 'SecretString' in response:
            secret = json.loads(response['SecretString'])
            print(f"Secret Keys Found: {list(secret.keys())}")
            # Do NOT print values!
        else:
            print("SecretString not found in response.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_secret_keys()
