import json
import os
import sys
import logging

# Add the lambda directory to path
sys.path.append('/Users/zakaria/Trading/Empire/lambda/v4_trader')

from lambda2_closer import lambda_handler

# Mock event with ONLY USELESS
event = {
    'manual': True,
    'single_pass': True,
    'symbols': 'USELESS/USDT:USDT'
}

# Set environment variables
os.environ['STATE_TABLE'] = 'V4TradingState'
os.environ['AWS_REGION'] = 'ap-northeast-1'
os.environ['SECRET_NAME'] = 'trading/binance'
os.environ['LOG_LEVEL'] = 'INFO'

# Run handler
result = lambda_handler(event, None)
print(json.dumps(result, indent=2))
