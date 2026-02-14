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
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Optional
from decimal import Decimal

import boto3
from exchange_connector import ExchangeConnector

# Configure log level based on environment
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
logging.getLogger().setLevel(getattr(logging, LOG_LEVEL))
from config import TradingConfig

# Setup logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# AWS Clients (lightweight)
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'eu-west-3'))
secretsmanager = boto3.client('secretsmanager', region_name=os.getenv('AWS_REGION', 'eu-west-3'))


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
        
        entry_price = float(position['entry_price'])
        direction = position['direction']
        take_profit = float(position.get('take_profit', 0))
        stop_loss = float(position.get('stop_loss', 0))
        
        # TIMEOUT: Calculer l'âge de la position
        from datetime import datetime, timezone
        entry_time = datetime.fromisoformat(position['timestamp'])
        age_minutes = (datetime.now(timezone.utc) - entry_time).total_seconds() / 60
        
        # Si age_minutes > (TradingConfig.MAX_HOLD_CANDLES * 1) : 10 minutes max
        if age_minutes > TradingConfig.MAX_HOLD_CANDLES:
            logger.warning(f"⏰ TIMEOUT close for {symbol} after {age_minutes:.0f}min")
            # Fermer la position au prix actuel (market order)
            exit_reason = 'TIMEOUT'
            
            try:
                # Market order pour fermer
                side = 'sell' if direction == 'LONG' else 'buy'
                quantity = float(position['quantity'])
                
                close_result = exchange.close_position(symbol, side, quantity)
                if close_result and close_result.get('status') == 'closed':
                    # Calculate PnL
                    if direction == 'LONG':
                        pnl_pct = ((current_price - entry_price) / entry_price) * 100
                    else:
                        pnl_pct = ((entry_price - current_price) / entry_price) * 100
                    
                    # Update DynamoDB
                    update_position_status(symbol, 'CLOSED', current_price, exit_reason, pnl_pct)
                    
                    # Remove from atomic risk
                    try:
                        from atomic_persistence import AtomicPersistence
                        import boto3
                        table_name = os.getenv('STATE_TABLE', 'V4TradingState')
                        dynamodb = boto3.resource('dynamodb')
                        table = dynamodb.Table(table_name)
                        persistence = AtomicPersistence(table)
                        risk_dollars = (entry_price * quantity) / float(position.get('leverage', 5))
                        persistence.atomic_remove_risk(symbol, risk_dollars)
                        logger.info(f"🧹 {symbol} - Atomic risk removed: ${risk_dollars:.2f}")
                    except Exception as e:
                        logger.error(f"❌ Failed to remove atomic risk for {symbol}: {e}")
                    
                    return {
                        'action': 'CLOSED',
                        'symbol': symbol,
                        'exit_price': current_price,
                        'pnl_pct': pnl_pct,
                        'reason': exit_reason
                    }
            except Exception as e:
                logger.error(f"❌ Failed to timeout close {symbol}: {e}")
                return None
        
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
                 # Only check if position is losing more than 0.5%
                 if current_price > entry_price * 1.005:  # Loss > 0.5%
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
                # Calculate risk to remove
                entry_price = float(position['entry_price'])
                quantity = float(position['quantity'])
                leverage = float(position.get('leverage', 5))  # Default leverage
                risk_dollars = (entry_price * quantity) / leverage
                
                # Update DynamoDB (mark as CLOSED)
                update_position_status(symbol, 'CLOSED', current_price, exit_reason, pnl_pct)
                
                # Remove from atomic risk (CRITICAL!)
                try:
                    from atomic_persistence import AtomicPersistence
                    import boto3
                    table_name = os.getenv('STATE_TABLE', 'V4TradingState')
                    dynamodb = boto3.resource('dynamodb')
                    table = dynamodb.Table(table_name)
                    persistence = AtomicPersistence(table)
                    persistence.atomic_remove_risk(symbol, risk_dollars)
                    logger.info(f"🧹 {symbol} - Atomic risk removed: ${risk_dollars:.2f}")
                except Exception as e:
                    logger.error(f"❌ Failed to remove atomic risk for {symbol}: {e}")
                
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
        # Find the position item using scan (GSI doesn't support symbol query)
        response = table.scan(
            FilterExpression='#status = :open AND symbol = :symbol',
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
    # EventBridge Scheduler handles the timing delay before Lambda invocation
    # The delay_seconds is just for logging purposes
    delay_seconds = event.get('delay_seconds', 0)
    if delay_seconds > 0 and not event.get('manual'):
        logger.info(f"⏱️ Scheduled execution with {delay_seconds}s delay from EventBridge")
        # No sleep needed - EventBridge already delayed the invocation

    start_time = time.time()
    logger.info("=" * 60)
    logger.info(f"⚡ {lambda_role} Started")
    logger.info("=" * 60)
    
    try:
        # Initialize exchange connector (uses env vars directly)
        exchange = ExchangeConnector(
            live_mode=TradingConfig.LIVE_MODE
        )
        
        # Add jitter to avoid simultaneous DynamoDB reads
        import random
        jitter = random.uniform(0, 2)  # 0 to 2 seconds of jitter
        time.sleep(jitter)
        
        # Load open positions
        positions = load_open_positions()
        
        if not positions:
            logger.info("  No open positions to check")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'No open positions', 'positions_checked': 0})
            }
        
        logger.info(f" Checking {len(positions)} open positions...")
        
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
