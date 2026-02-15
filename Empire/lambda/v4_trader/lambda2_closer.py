"""
Lambda 2: CLOSER - V16.1 Schedule Optimisé
==========================================
Fréquence: Toutes les 10 minutes (xx:00, xx:10, xx:20, xx:30, xx:40, xx:50)
Rôle: Check positions + Close si TP/SL hit + Fast Exit
NE SCAN PAS le market
N'OUVRE JAMAIS de positions
🏛️ EMPIRE V16.1: Optimisé pour réduire les frais de transaction
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
from atomic_persistence import AtomicPersistence  # Added missing import

# Configure log level based on environment
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
logging.getLogger().setLevel(getattr(logging, LOG_LEVEL))
from config import TradingConfig

# Setup logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Helper function to avoid DynamoDB code duplication
def get_persistence():
    """Get AtomicPersistence instance (avoid code duplication)"""
    table_name = os.getenv('STATE_TABLE', 'V4TradingState')
    table = dynamodb.Table(table_name)
    return AtomicPersistence(table)

# AWS Clients (lightweight)
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'ap-northeast-1'))
secretsmanager = boto3.client('secretsmanager', region_name=os.getenv('AWS_REGION', 'ap-northeast-1'))


def load_binance_credentials() -> Dict[str, str]:
    api_key = os.getenv('BINANCE_API_KEY')
    secret_key = os.getenv('BINANCE_SECRET_KEY')
    if api_key and secret_key:
        return {'api_key': api_key, 'secret_key': secret_key}

    secret_name = os.getenv('SECRET_NAME')
    if not secret_name:
        raise RuntimeError('Missing BINANCE_API_KEY/BINANCE_SECRET_KEY and SECRET_NAME')

    response = secretsmanager.get_secret_value(SecretId=secret_name)
    payload = json.loads(response['SecretString'])

    api_key = (
        payload.get('BINANCE_API_KEY')
        or payload.get('binance_api_key')
        or payload.get('api_key')
        or payload.get('API_KEY')
    )
    secret_key = (
        payload.get('BINANCE_SECRET_KEY')
        or payload.get('binance_secret_key')
        or payload.get('secret_key')
        or payload.get('SECRET_KEY')
    )

    if not api_key or not secret_key:
        raise RuntimeError(f"Secret {secret_name} missing Binance keys")

    return {'api_key': api_key, 'secret_key': secret_key}


def get_memory_open_positions() -> Dict:
    """🏛️ EMPIRE V16.3: Get open positions from DynamoDB memory (shared state)"""
    try:
        from atomic_persistence import AtomicPersistence
        table_name = os.getenv('STATE_TABLE', 'V4TradingState')
        table = dynamodb.Table(table_name)
        persistence = AtomicPersistence(table)
        
        return persistence.load_positions()
    except Exception as e:
        logger.error(f"[MEMORY_ERROR] Failed to load positions from memory: {e}")
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
        # V16: FETCH REAL PRICE FROM EXCHANGE (Ticker)
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = float(ticker['last'])
            logger.debug(f"[PRICE] {symbol} current: ${current_price:.4f}")
        except Exception as ticker_err:
            logger.error(f"[ERROR] Failed to fetch ticker for {symbol}: {ticker_err}")
            # Fallback to DynamoDB price (last known) if available
            current_price = float(position.get('mark_price', position.get('entry_price', 0)))
        
        if current_price == 0:
            logger.error(f"[ERROR] No price available for {symbol}")
            return None
        
        entry_price = float(position['entry_price'])
        direction = position['direction']
        take_profit = float(position.get('take_profit', 0))
        stop_loss = float(position.get('stop_loss', 0))
        
        # TIMEOUT: Calculer l'âge de la position
        from datetime import datetime, timezone
        ts = position.get('timestamp')
        if not ts:
            logger.warning(f"[WARN] No timestamp for {symbol}, using now as fallback")
            ts = datetime.now(timezone.utc).isoformat()
        
        entry_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        age_minutes = (datetime.now(timezone.utc) - entry_time).total_seconds() / 60
        
        # Max hold from config (V16 Momentum: 10 minutes)
        max_hold = getattr(TradingConfig, 'MAX_HOLD_CANDLES', 10)
        
        if age_minutes >= max_hold:
            logger.warning(f"⏰ TIMEOUT close for {symbol} after {age_minutes:.1f}min (max: {max_hold}min)")
            exit_reason = f'TIMEOUT_{int(age_minutes)}min'
            
            try:
                side = 'sell' if direction == 'LONG' else 'buy'
                quantity = float(position['quantity'])
                
                close_result = exchange.close_position(symbol, side, quantity)
                if close_result:
                    # Calculate PnL
                    if direction == 'LONG':
                        pnl_pct = ((current_price - entry_price) / entry_price) * 100
                    else:
                        pnl_pct = ((entry_price - current_price) / entry_price) * 100
                    
                    # Update DynamoDB
                    update_position_status(symbol, 'CLOSED', current_price, exit_reason, pnl_pct)
                    
                    # Remove from atomic risk
                    try:
                        persistence = get_persistence()
                        leverage = float(position.get('leverage', 5))
                        risk_dollars = (entry_price * quantity) / leverage
                        persistence.atomic_remove_risk(symbol, risk_dollars)
                        logger.info(f"🧹 {symbol} - Atomic risk removed: ${risk_dollars:.2f}")
                    except Exception as atomic_err:
                        logger.error(f"❌ Failed to remove atomic risk for {symbol}: {atomic_err}")
                    
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
            
            # Execute close order using exchange directly (FAST)
            try:
                # Race-condition guard: confirm position still exists on exchange
                try:
                    ccxt_symbol = exchange.resolve_symbol(symbol)
                    live_positions = exchange.fetch_positions([ccxt_symbol])
                    for p in live_positions or []:
                        if p.get('symbol') != ccxt_symbol:
                            continue
                        contracts = p.get('contracts')
                        if contracts is None:
                            contracts = p.get('contractSize')
                        try:
                            contracts = float(contracts) if contracts is not None else None
                        except Exception:
                            contracts = None
                        if contracts is not None and abs(contracts) == 0.0:
                            logger.info(f"ℹ️ {symbol} - Skip close: position already 0 on exchange")
                            return None
                except Exception as pos_err:
                    logger.warning(f"[WARN] {symbol} - Could not verify position on exchange before close: {pos_err}")

                # Direct market order execution
                if direction == 'LONG':
                    close_result = exchange.create_market_order(symbol, 'sell', position['quantity'])
                else:
                    close_result = exchange.create_market_order(symbol, 'buy', position['quantity'])
            except Exception as e:
                msg = str(e)
                if 'Position not found' in msg or 'position not found' in msg:
                    logger.info(f"ℹ️ {symbol} - Skip close: position not found on exchange")
                    return None
                logger.error(f"[ERROR] Order execution failed: {e}")
                raise
            
            if close_result and close_result.get('status') == 'closed':
                # Calculate risk to remove
                entry_price = float(position['entry_price'])
                quantity = float(position['quantity'])
                leverage = float(position.get('leverage', 5))  # Default leverage
                risk_dollars = (entry_price * quantity) / leverage
                
                # Update DynamoDB (mark as CLOSED)
                update_position_status(symbol, 'CLOSED', current_price, exit_reason, pnl_pct)
                
                # Remove from atomic risk (CRITICAL!)
                persistence = get_persistence()
                persistence.atomic_remove_risk(symbol, risk_dollars)
                logger.info(f"🧹 {symbol} - Atomic risk removed: ${risk_dollars:.2f}")
                
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
        # 🏛️ EMPIRE V16: Optimize with Query instead of Scan
        safe_symbol = symbol.replace('/', '_').replace(':', '-')
        trader_id = f'POSITION#{safe_symbol}'
        
        response = table.query(
            KeyConditionExpression='trader_id = :tid',
            FilterExpression='#status = :open',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':open': 'OPEN',
                ':tid': trader_id
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
    CLOSER LAMBDA - TP/SL/Timeout Logic
    PURE CLOSING - NO scanning, NO opening positions
    """
    
    # Identify which lambda this is (20s or 40s)
    lambda_role = 'CLOSER_30S'  # Fixed value to avoid os import issue
    
    # ⏱️ STAGGER LOGIC (Architecture 3-Lambda)
    # EventBridge Scheduler may pass delay_seconds (legacy) or offset_seconds (sub-minute loop)
    delay_seconds = event.get('delay_seconds', 0)
    if delay_seconds > 0 and not event.get('manual'):
        logger.info(f"⏱️ Scheduled execution with {delay_seconds}s delay from EventBridge")

    offset_seconds = event.get('offset_seconds')
    if isinstance(offset_seconds, int):
        offset_seconds = [offset_seconds]
    if not isinstance(offset_seconds, list):
        offset_seconds = []

    start_time = time.time()
    logger.info("=" * 60)
    logger.info(f"⚡ {lambda_role} Started")
    logger.info("=" * 60)
    
    phases = {}
    
    try:
        # Phase 1: INIT
        p1_start = time.time()
        creds = load_binance_credentials()
        live_mode = bool(getattr(TradingConfig, 'LIVE_MODE', False))

        exchange = ExchangeConnector(
            api_key=creds['api_key'],
            secret=creds['secret_key'],
            live_mode=live_mode
        )
        phases['init'] = round(time.time() - p1_start, 3)
        
        def remaining_ms() -> int:
            try:
                return int(context.get_remaining_time_in_millis())
            except Exception:
                return 0

        def run_single_pass() -> Dict:
            p2_start = time.time()
            open_positions = get_memory_open_positions()
            p2_dur = round(time.time() - p2_start, 3)

            if not open_positions:
                return {
                    'positions_checked': 0,
                    'positions_closed': 0,
                    'closed_details': [],
                    'phases': {
                        'load_positions': p2_dur,
                        'check_and_close': 0.0,
                    }
                }

            p3_start = time.time()
            logger.info(f" Checking {len(open_positions)} open positions...")
            closed_positions = []
            for symbol, position in open_positions.items():
                if remaining_ms() and remaining_ms() < 2000:
                    logger.warning("⏳ Timeout guard: stopping checks (low remaining time)")
                    break
                result = check_and_close_position(exchange, symbol, position)
                if result:
                    closed_positions.append(result)

            p3_dur = round(time.time() - p3_start, 3)
            return {
                'positions_checked': len(open_positions),
                'positions_closed': len(closed_positions),
                'closed_details': closed_positions,
                'phases': {
                    'load_positions': p2_dur,
                    'check_and_close': p3_dur,
                }
            }

        ticks_executed = []
        aggregated_closed = []
        aggregated_checked = 0

        # Manual invocations or single_pass should do a single pass (no sub-minute loop)
        if event.get('manual') or event.get('single_pass') or not offset_seconds:
            single = run_single_pass()
            phases.update(single.get('phases', {}))
            aggregated_checked = single['positions_checked']
            aggregated_closed.extend(single['closed_details'])
            ticks_executed.append({'offset_s': None, 'closed': single['positions_closed']})
        else:
            offsets_clean = set()
            for x in offset_seconds:
                try:
                    offsets_clean.add(int(float(x)))
                except Exception:
                    continue
            offsets_sorted = sorted(offsets_clean)
            for target_offset in offsets_sorted:
                if remaining_ms() and remaining_ms() < 2000:
                    logger.warning("⏳ Timeout guard: stopping tick loop (low remaining time)")
                    break

                now = datetime.now(timezone.utc)
                current_offset = now.second + (now.microsecond / 1_000_000)
                sleep_s = float(target_offset) - float(current_offset)
                if sleep_s > 0:
                    if remaining_ms() and remaining_ms() < int((sleep_s * 1000) + 2500):
                        logger.warning("⏳ Timeout guard: skipping sleep (not enough remaining time)")
                        break
                    time.sleep(sleep_s)

                if remaining_ms() and remaining_ms() < 2000:
                    logger.warning("⏳ Timeout guard: stopping before running tick (low remaining time)")
                    break

                logger.info(f"⏱️ Tick at offset {target_offset:02d}s")
                single = run_single_pass()
                aggregated_checked = max(aggregated_checked, single['positions_checked'])
                aggregated_closed.extend(single['closed_details'])
                ticks_executed.append({'offset_s': int(target_offset), 'closed': single['positions_closed']})

        duration = time.time() - start_time
        response = {
            'lambda': lambda_role,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'duration_seconds': round(duration, 2),
            'phases': phases,
            'ticks': ticks_executed,
            'positions_checked': aggregated_checked,
            'positions_closed': len(aggregated_closed),
            'closed_details': aggregated_closed
        }
        
        logger.info("=" * 60)
        logger.info(f"✅ {lambda_role} Complete: {len(aggregated_closed)} closed")
        logger.info(f"⏱️  Total Duration: {duration:.2f}s | Check: {phases.get('check_and_close', 0.0)}s")
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
