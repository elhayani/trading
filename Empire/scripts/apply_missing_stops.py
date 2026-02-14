import sys
import os
import json
import boto3
import ccxt
import time

def get_secrets():
    secret_name = "EmpireBotSecrets"
    region_name = "eu-west-3"
    
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
        print(f"Error fetching secrets: {e}")
        return None, None

def main():
    print("APPLYING MISSING STOP LOSSES FOR TOSHI AND Q...")
    api_key, secret = get_secrets()
    if not api_key:
        print("CRITICAL: API Key missing.")
        sys.exit(1)

    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret,
        'options': {'defaultType': 'future'}
    })

    try:
        positions = exchange.fetch_positions()
        open_orders = exchange.fetch_open_orders()
    except Exception as e:
        print(f"Error fetching data: {e}")
        sys.exit(1)

    # Map existing STOP orders by symbol
    active_stops = {}
    for order in open_orders:
        if order['type'] == 'STOP_MARKET':
            active_stops[order['symbol']] = True

    targets = ['TOSHI', 'Q']
    
    for pos in positions:
        # Handle CCXT position structure
        symbol = pos['symbol']
        amt = float(pos['contracts']) if 'contracts' in pos else float(pos['info']['positionAmt'])
        entry = float(pos['entryPrice'])
        
        # Determine side
        # Note: positionAmt is signed in raw info, but contracts is usually absolute in ccxt structure depending on version.
        # Let's rely on 'side' or raw 'positionAmt'
        raw_amt = float(pos['info']['positionAmt'])
        if raw_amt == 0:
            continue

        is_target = False
        for t in targets:
            if t in symbol:
                is_target = True
                break
        
        if not is_target:
            continue
            
        print(f"Found Target Position: {symbol} | Size: {raw_amt} | Entry: {entry}")
        
        if active_stops.get(symbol):
            print(f" -> Stop Loss already exists for {symbol}. Skipping.")
            continue

        # Calculate SL
        sl_pct = 0.0025 # 0.25%
        side = 'long' if raw_amt > 0 else 'short'
        
        if side == 'long':
            stop_price = entry * (1 - sl_pct)
            order_side = 'sell'
        else:
            stop_price = entry * (1 + sl_pct)
            order_side = 'buy'
            
        print(f" -> APPLYING STOP LOSS: {order_side.upper()} {abs(raw_amt)} @ {stop_price:.5f}")
        
        try:
            # Create STOP_MARKET order
            # Binance Futures requires stopPrice and Close Position behavior or reduceOnly
            params = {
                'stopPrice': stop_price,
                'reduceOnly': True
            }
            order = exchange.create_order(symbol, 'STOP_MARKET', order_side, abs(raw_amt), params=params)
            print(f" -> SUCCESS: SL Placed. Order ID: {order['id']}")
        except Exception as e:
            print(f" -> FAILED to place SL: {e}")

if __name__ == "__main__":
    main()
