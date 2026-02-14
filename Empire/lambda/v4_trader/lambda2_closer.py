"""
Lambda 2 & 3: QUICK CLOSER
===========================
Fréquence: 20s et 40s (2 lambdas avec le même code)
Rôle: Check positions + Close si TP/SL hit
NE SCAN PAS le market
N'OUVRE JAMAIS de positions
"""

import json
import os
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from decimal import Decimal

import boto3

# Imports from existing modules
from exchange_connector import ExchangeConnector
from config import TradingConfig

# Setup logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# AWS Clients (lightweight)
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'eu-west-3'))
secretsmanager = boto3.client('secretsmanager', region_name=os.getenv('AWS_REGION', 'eu-west-3'))

def get_binance_credentials():
    """Fetch credentials from Secrets Manager (cached)"""
    if not hasattr(get_binance_credentials, 'cache'):
        secret_name = os.getenv('SECRET_NAME', 'trading/binance')
        try:
            response = secretsmanager.get_secret_value(SecretId=secret_name)
            secret = json.loads(response['SecretString'])
            get_binance_credentials.cache = {
                'api_key': secret.get('api_key') or secret.get('apiKey'),
                'api_secret': secret.get('api_secret') or secret.get('secret') or secret.get('apiSecret')
            }
        except Exception as e:
            logger.error(f"Failed to fetch secrets: {e}")
            raise
    return get_binance_credentials.cache

def load_open_positions() -> Dict:
    """
    Load OPEN positions from DynamoDB (optimized query)
    Uses GSI status-timestamp-index for fast retrieval
    """
    table_name = os.getenv('STATE_TABLE', 'V4TradingState')
    table = dynamodb.Table(table_name)
    
    try:
        response = table.query(
            IndexName='status-timestamp-index',
            KeyConditionExpression='#status = :open',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':open': 'OPEN'},
            ScanIndexForward=False,  # Most recent first
            Limit=20  # Max 20 concurrent positions
        )
        
        positions = {}
        for item in response.get('Items', []):
            symbol = item.get('symbol')
            if symbol:
                positions[symbol] = {
                    'symbol': symbol,
                    'direction': item.get('direction'),
                    'entry_price': float(item.get('entry_price', 0)),
                    'quantity': float(item.get('quantity', 0)),
                    'stop_loss': float(item.get('stop_loss', 0)),
                    'take_profit': float(item.get('take_profit', 0)),
                    'timestamp': item.get('timestamp'),
                    'leverage': int(item.get('leverage', 3))
                }
        
        return positions
        
    except Exception as e:
        logger.error(f"Failed to load positions: {e}")
        return {}

def check_and_close_position(
    exchange: ExchangeConnector,
    symbol: str,
    position: Dict
) -> Optional[Dict]:
    """
    Check if TP or SL is hit, close if yes
    Returns: Dict with action info or None
    """
    try:
        # Fetch current price (ultra-fast ticker request)
        ticker = exchange.fetch_ticker(symbol)
        current_price = float(ticker['last'])
        
        entry_price = position['entry_price']
        direction = position['direction']
        take_profit = position.get('take_profit', 0)
        stop_loss = position.get('stop_loss', 0)
        
        # Calculate PnL %
        if direction == 'LONG':
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:  # SHORT
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
        
        # Check TP hit
        tp_hit = False
        if direction == 'LONG' and current_price >= take_profit:
            tp_hit = True
        elif direction == 'SHORT' and current_price <= take_profit:
            tp_hit = True
        
        # Check SL hit
        sl_hit = False
        if direction == 'LONG' and current_price <= stop_loss:
            sl_hit = True
        elif direction == 'SHORT' and current_price >= stop_loss:
            sl_hit = True
        
        # 🏛️ EMPIRE V15.3: Emergency Counter-Trend Check
        # Close shorts in strong uptrends regardless of TP/SL (Rescue logic)
        anti_trend_hit = False
        if not (tp_hit or sl_hit) and direction == 'SHORT':
             try:
                 # Only check if position is losing or price is stretching
                 if current_price > entry_price:
                     from market_analysis import calculate_adx
                     ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=30)
                     import pandas as pd
                     df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                     adx, di_p, di_m = calculate_adx(df['h'], df['l'], df['c'])
                     
                     current_adx = adx.iloc[-1]
                     if current_adx > 40 and di_p.iloc[-1] > di_m.iloc[-1]:
                         logger.warning(f"⚠️ {symbol} - EMERGENCY COUNTER-TREND EXIT: SHORT in ADX={current_adx:.1f} uptrend")
                         anti_trend_hit = True
             except Exception as e:
                 logger.error(f"[ERROR] Emergency check failed: {e}")

        # Close if either hit
        if tp_hit or sl_hit or anti_trend_hit:
            exit_reason = 'TP_HIT' if tp_hit else ('SL_HIT' if sl_hit else 'ANTI_TREND_BLOCK')
            
            logger.info(f"🎯 {symbol} - {exit_reason} at ${current_price:.4f} ({pnl_pct:+.2f}%)")
            
            # Execute close order
            close_result = exchange.close_position(
                symbol=symbol,
                side='sell' if direction == 'LONG' else 'buy',
                quantity=position['quantity']
            )
            
            if close_result and close_result.get('status') == 'closed':
                # Update DynamoDB (mark as CLOSED)
                update_position_status(symbol, 'CLOSED', current_price, exit_reason, pnl_pct)
                
                return {
                    'action': 'CLOSED',
                    'symbol': symbol,
                    'exit_price': current_price,
                    'pnl_pct': pnl_pct,
                    'reason': exit_reason
                }
        
        # Position still open
        return None
        
    except Exception as e:
        logger.error(f"Error checking {symbol}: {e}")
        return None

def update_position_status(
    symbol: str,
    status: str,
    exit_price: float,
    reason: str,
    pnl_pct: float
):
    """Update position status in DynamoDB"""
    table_name = os.getenv('STATE_TABLE', 'V4TradingState')
    table = dynamodb.Table(table_name)
    
    try:
        # Find the position item
        response = table.query(
            IndexName='status-timestamp-index',
            KeyConditionExpression='#status = :open AND symbol = :symbol',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':open': 'OPEN',
                ':symbol': symbol
            },
            Limit=1
        )
        
        if response['Items']:
            item = response['Items'][0]
            trader_id = item['trader_id']
            timestamp = item['timestamp']
            
            # Update status
            table.update_item(
                Key={
                    'trader_id': trader_id,
                    'timestamp': timestamp
                },
                UpdateExpression='SET #status = :closed, exit_price = :price, exit_reason = :reason, pnl_pct = :pnl, closed_at = :now',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':closed': 'CLOSED',
                    ':price': Decimal(str(exit_price)),
                    ':reason': reason,
                    ':pnl': Decimal(str(pnl_pct)),
                    ':now': datetime.now(timezone.utc).isoformat()
                }
            )
            
            logger.info(f"✅ {symbol} - DynamoDB updated to CLOSED")
            
    except Exception as e:
        logger.error(f"Failed to update {symbol} status: {e}")

def lambda_handler(event, context):
    """
    Lambda 2/3 Handler: Quick Closer
    
    Workflow:
    1. Load open positions from DynamoDB (GSI query)
    2. For each position:
       - Fetch current price (ticker only)
       - Check if TP or SL hit
       - Close if hit
    3. Return summary
    
    NO scanning, NO opening positions
    """
    
    # Identify which lambda this is (20s or 40s)
    lambda_role = os.getenv('LAMBDA_ROLE', 'CLOSER_UNKNOWN')
    
    # ⏱️ STAGGER LOGIC (Architecture 3-Lambda)
    if not event.get('manual'):
        if '20S' in lambda_role:
            logger.info("⏱️ Waiting 20 seconds...")
            time.sleep(20)
        elif '40S' in lambda_role:
            logger.info("⏱️ Waiting 40 seconds...")
            time.sleep(40)

    start_time = time.time()
    logger.info("=" * 60)
    logger.info(f"⚡ {lambda_role} Started")
    logger.info("=" * 60)
    
    try:
        # Initialize exchange connector (Updated to match Architecture 3-Lambda)
        creds = get_binance_credentials()
        exchange = ExchangeConnector(
            api_key=creds['api_key'],
            secret=creds['api_secret'],
            live_mode=TradingConfig.LIVE_MODE
        )
        
        # Load open positions
        positions = load_open_positions()
        
        if not positions:
            logger.info("ℹ️  No open positions to check")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'lambda': lambda_role,
                    'positions_checked': 0,
                    'positions_closed': 0,
                    'duration_seconds': round(time.time() - start_time, 2)
                })
            }
        
        logger.info(f"📊 Checking {len(positions)} open positions...")
        
        # Check each position
        closed_positions = []
        
        for symbol, position in positions.items():
            result = check_and_close_position(exchange, symbol, position)
            
            if result:
                closed_positions.append(result)
        
        # Response
        duration = time.time() - start_time
        
        response = {
            'lambda': lambda_role,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'duration_seconds': round(duration, 2),
            'positions_checked': len(positions),
            'positions_closed': len(closed_positions),
            'closed_details': closed_positions
        }
        
        logger.info("=" * 60)
        logger.info(f"✅ {lambda_role} Complete: {len(closed_positions)} closed")
        logger.info(f"⏱️  Duration: {duration:.2f}s")
        logger.info("=" * 60)
        
        return {
            'statusCode': 200,
            'body': json.dumps(response)
        }
        
    except Exception as e:
        logger.error(f"❌ {lambda_role} FATAL ERROR: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'lambda': lambda_role
            })
        }
