
import boto3
import ccxt
import os
import json
import logging
from decimal import Decimal

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def get_secrets():
    secret_name = "EmpireBotSecrets"
    region_name = "us-east-1"
    
    # Try env vars first
    api_key = os.getenv('BINANCE_API_KEY')
    secret_key = os.getenv('BINANCE_SECRET_KEY')
    if api_key and secret_key:
        return api_key, secret_key

    try:
        session = boto3.session.Session()
        client = session.client(service_name='secretsmanager', region_name=region_name)
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        secret = get_secret_value_response['SecretString']
        secret_dict = json.loads(secret)
        return secret_dict.get('api_key'), secret_dict.get('secret')
    except Exception as e:
        logger.error(f"Error fetching secrets: {e}")
        return None, None

def to_decimal(obj):
    if isinstance(obj, float): return Decimal(str(obj))
    if isinstance(obj, dict): return {k: to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list): return [to_decimal(v) for v in obj]
    return obj

def from_decimal(obj):
    if isinstance(obj, Decimal): return float(obj)
    if isinstance(obj, dict): return {k: from_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list): return [from_decimal(v) for v in obj]
    return obj

def inspect_position():
    api_key, secret = get_secrets()
    if not api_key:
        logger.error("API Key missing")
        return

    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'}
    })

    dynamodb = boto3.resource('dynamodb', region_name='eu-west-3') # User is in eu-west-3 based on logs
    if os.getenv('AWS_REGION'):
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION'))
    
    state_table = dynamodb.Table('V4TradingState')

    # 1. Scan DynamoDB for Q positions
    try:
        response = state_table.scan(
            FilterExpression='begins_with(trader_id, :prefix)',
            ExpressionAttributeValues={':prefix': 'POSITION#'}
        )
        items = response.get('Items', [])
        logger.info(f"Found {len(items)} positions in DynamoDB")
        
        q_pos_db = None
        for item in items:
            if 'Q' in item['trader_id'] or '1000Q' in item['trader_id']:
                logger.info(f"DynamoDB Position Found: {item['trader_id']}")
                logger.info(json.dumps(from_decimal(item), indent=2))
                q_pos_db = item
    except Exception as e:
        logger.error(f"DynamoDB Scan failed: {e}")

    # 2. Check Binance Position
    try:
        positions = exchange.fetch_positions()
        q_pos_binance = None
        for pos in positions:
            if float(pos['contracts']) > 0:
                if 'Q' in pos['symbol']:
                    logger.info(f"Binance Position Found: {pos['symbol']}")
                    # logger.info(json.dumps(pos, indent=2)) # Too verbose
                    logger.info(f"Side: {pos['side']}")
                    logger.info(f"Contracts: {pos['contracts']}")
                    logger.info(f"Entry Price: {pos['entryPrice']}")
                    logger.info(f"Mark Price: {pos['markPrice']}")
                    logger.info(f"Unrealized PnL: {pos['unrealizedPnl']}")
                    if 'info' in pos:
                         logger.info(f"Raw Entry Price (info): {pos['info'].get('entryPrice')}")
                         logger.info(f"Raw Position Amt (info): {pos['info'].get('positionAmt')}")
                    q_pos_binance = pos
    except Exception as e:
        logger.error(f"Binance fetch_positions failed: {e}")

    # 3. Check Open Orders
    if q_pos_binance:
        symbol = q_pos_binance['symbol']
        try:
            orders = exchange.fetch_open_orders(symbol)
            logger.info(f"Open Orders for {symbol}: {len(orders)}")
            for order in orders:
                logger.info(f"Order: {order['type']} {order['side']} @ {order.get('stopPrice')} (Trigger)")
                logger.info(f"Status: {order['status']}")
                logger.info(json.dumps(order['info'], indent=2))
        except Exception as e:
            logger.error(f"Binance fetch_open_orders failed: {e}")

if __name__ == "__main__":
    inspect_position()
