import sys
import os
import json
import boto3
import ccxt
import time

def get_secrets():
    secret_name = "EmpireBotSecrets"
    region_name = "us-east-1" 

    # Try env vars first
    api_key = os.getenv('BINANCE_API_KEY')
    secret_key = os.getenv('BINANCE_SECRET_KEY')
    if api_key and secret_key:
        print("Using API keys from environment variables.")
        return api_key, secret_key

    print(f"Attempting to fetch secret '{secret_name}' from AWS Secrets Manager...")
    try:
        session = boto3.session.Session()
        client = session.client(service_name='secretsmanager', region_name=region_name)
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        secret = get_secret_value_response['SecretString']
        secret_dict = json.loads(secret)
        
        api_key = secret_dict.get('api_key') or secret_dict.get('apiKey') or secret_dict.get('API_KEY')
        secret_key = secret_dict.get('secret') or secret_dict.get('secretKey') or secret_dict.get('SECRET_KEY') or secret_dict.get('api_secret')
        
        if api_key and secret_key:
            return api_key, secret_key
        else:
            raise ValueError("Keys not found in secret.")
            
    except Exception as e:
        print(f"Error fetching secrets: {e}")
        return None, None

def main():
    print("EMERGENCY CLOSE SCRIPT - CLOSING TOSHI AND Q POSITIONS")
    
    api_key, secret = get_secrets()
    if not api_key:
        print("CRITICAL: Could not find API keys. Set BINANCE_API_KEY and BINANCE_SECRET_KEY env vars or ensure AWS credentials are valid.")
        sys.exit(1)

    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': secret,
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True,
        },
        'enableRateLimit': True
    })

    print("Connecting to Binance Futures...")
    try:
        exchange.load_markets()
    except Exception as e:
        print(f"Error connecting to exchange: {e}")
        sys.exit(1)

    print("Fetching open positions...")
    try:
        balance = exchange.fetch_balance()
        positions = balance['info']['positions']
    except Exception as e:
         # Fallback to fetchPositions if fetchBalance doesn't return info as expected in some ccxt versions
        print(f"fetch_balance failed ({e}), trying fetch_positions...")
        positions = exchange.fetch_positions()
        # CCXT fetch_positions returns a list of dictionaries with standardized fields usually, but raw info is in 'info'
        # Let's handle both raw list or CCXT formatted list
        
    open_positions = []
    # If using raw positions from balance['info']['positions']
    if isinstance(positions, list):
         for pos in positions:
            # Check if it's raw binance dict or ccxt dict
            if 'positionAmt' in pos: # Raw Binance
                amt = float(pos['positionAmt'])
                symbol = pos['symbol']
                entry = float(pos['entryPrice'])
                pnl = float(pos['unRealizedProfit'])
            else: # CCXT structure
                amt = float(pos.get('contracts', pos.get('amount', 0))) * (1 if pos.get('side') == 'long' else -1)
                symbol = pos.get('id') or pos.get('symbol') # id is usually raw symbol
                entry = float(pos.get('entryPrice', 0))
                pnl = float(pos.get('unrealizedPnl', 0))

            if amt != 0:
                print(f"FOUND OPEN POSITION: {symbol} Size: {amt} Entry: {entry} PnL: {pnl}")
                # Store raw pos for simplicity if available, or construct simple dict
                open_positions.append({
                    'symbol': symbol, # RAW SYMBOL
                    'amount': amt,
                    'type': 'raw' if 'positionAmt' in pos else 'ccxt'
                })

    # Target symbols
    targets = ['TOSHI', 'Q'] 
    
    to_close = []
    for pos in open_positions:
        symbol = pos['symbol']
        for t in targets:
            if t in symbol:
                to_close.append(pos)
                break
    
    if not to_close:
        print("No matching positions found for TOSHI or Q.")
        return

    print(f"Identified {len(to_close)} positions to CLOSE IMMEDIATELY:")
    for p in to_close:
        print(f" - {p['symbol']} (Amt: {p['amount']})")

    # EXECUTE CLOSE
    for p in to_close:
        market_id = p['symbol']
        amt = p['amount']
        side = 'sell' if amt > 0 else 'buy'
        quantity = abs(amt)
        
        # Find CCXT symbol
        ccxt_symbol = None
        for m in exchange.markets.values():
            if m['id'] == market_id:
                ccxt_symbol = m['symbol']
                break
        
        if not ccxt_symbol:
            ccxt_symbol = market_id # Try raw
            print(f"Warning: Could not map {market_id} to CCXT symbol. Using raw ID.")

        print(f"Executing MARKET CLOSE for {ccxt_symbol} (Size: {quantity})...")
        try:
            # reduceOnly=True ensures we don't open opposite position
            order = exchange.create_market_order(ccxt_symbol, side, quantity, {'reduceOnly': True})
            print(f"SUCCESS: Closed {ccxt_symbol}. OrderID: {order['id']}")
        except Exception as e:
            print(f"FAILED to close {ccxt_symbol}: {e}")
