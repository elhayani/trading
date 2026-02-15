import os
import sys
import json
import logging

# Set up logging to see the output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add the lambda directory to sys.path
lambda_dir = os.path.join(os.getcwd(), 'lambda/v4_trader')
sys.path.append(lambda_dir)

from lambda1_scanner import lambda_handler

if __name__ == "__main__":
    print("🚀 Starting manual scan...")
    result = lambda_handler(None, None)
    print("\n📊 Scan Result:")
    print(json.dumps(json.loads(result['body']), indent=4))
