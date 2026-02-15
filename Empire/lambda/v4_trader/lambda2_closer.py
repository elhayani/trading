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
import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional
from decimal import Decimal

import boto3
from exchange_connector import ExchangeConnector
from atomic_persistence import AtomicPersistence  # Added missing import
from websocket_manager import BinanceWebSocketManager
import requests
import hmac
import hashlib

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


def _to_binance_symbol(symbol: str) -> str:
    # CCXT futures symbols often look like BTC/USDT:USDT
    s = symbol.replace(':USDT', '').replace(':BUSD', '')
    s = s.replace('/', '')
    return s


async def _fetch_mark_prices_snapshot(demo_mode: bool, timeout_s: float = 1.25) -> Dict[str, float]:
    try:
        import websockets
    except Exception as e:
        logger.warning(f"[WS] websockets import failed: {e}")
        return {}

    base_ws = "wss://stream.binancefuture.com/ws" if demo_mode else "wss://fstream.binance.com/ws"
    url = f"{base_ws}/!markPrice@arr@1s"

    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
            msg = json.loads(raw)

            data = msg.get('data') if isinstance(msg, dict) else None
            if data is None and isinstance(msg, list):
                data = msg
            if not isinstance(data, list):
                return {}

            prices = {}
            for item in data:
                try:
                    sym = item.get('s')
                    price = float(item.get('p'))
                    if sym and price:
                        prices[sym] = price
                except Exception:
                    continue
            return prices
    except Exception as e:
        logger.warning(f"[WS] markPrice snapshot failed: {e}")
        return {}


def _get_live_position_amt(exchange: ExchangeConnector, symbol: str) -> Optional[float]:
    try:
        ccxt_symbol = exchange.resolve_symbol(symbol)
        live_positions = exchange.fetch_positions([ccxt_symbol])
        for p in live_positions or []:
            if p.get('symbol') != ccxt_symbol:
                continue
            info = p.get('info') or {}

            # Binance futures: info.positionAmt is signed (LONG > 0, SHORT < 0)
            position_amt = info.get('positionAmt')
            if position_amt is not None:
                return float(position_amt)

            # CCXT normalized fields may be unsigned; use only as fallback
            contracts = p.get('contracts')
            if contracts is not None:
                try:
                    contracts_f = float(contracts)
                    side = (p.get('side') or info.get('positionSide') or '').upper()
                    if side == 'SHORT':
                        return -abs(contracts_f)
                    if side == 'LONG':
                        return abs(contracts_f)
                    return contracts_f
                except Exception:
                    pass
    except Exception:
        return None


def _signed_binance_get(exchange: ExchangeConnector, path: str, params: Dict[str, str]) -> Dict:
    from urllib.parse import urlencode
    base_url = "https://fapi.binance.com" if exchange.live_mode else "https://demo-fapi.binance.com"
    ts = str(int(time.time() * 1000))
    qp = {**params, 'timestamp': ts}
    
    # Sort keys for consistency and encode
    query_string = urlencode(sorted(qp.items()))
    signature = hmac.new(exchange.exchange.secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    
    url = f"{base_url}{path}?{query_string}&signature={signature}"
    headers = {'X-MBX-APIKEY': exchange.exchange.apiKey}
    resp = requests.get(url, headers=headers, timeout=5)
    if resp.status_code != 200:
        raise RuntimeError(f"Binance GET failed ({resp.status_code}): {resp.text}")
    return resp.json()


def _get_position_risk(exchange: ExchangeConnector, symbol: str) -> Optional[Dict]:
    try:
        clean_symbol = symbol.replace('/', '').replace(':USDT', '')
        data = _signed_binance_get(exchange, '/fapi/v2/positionRisk', {'symbol': clean_symbol})
        # Response can be list
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning(f"[RISK] Failed to fetch positionRisk for {symbol}: {e}")
        return None
    return None


def _get_live_position_side(exchange: ExchangeConnector, symbol: str) -> Optional[str]:
    try:
        ccxt_symbol = exchange.resolve_symbol(symbol)
        live_positions = exchange.fetch_positions([ccxt_symbol])
        for p in live_positions or []:
            if p.get('symbol') != ccxt_symbol:
                continue
            info = p.get('info') or {}
            ps = info.get('positionSide')
            if ps:
                ps = str(ps).upper()
                if ps in ('LONG', 'SHORT'):
                    return ps
    except Exception:
        return None
    return None


def cleanup_ghost_position(symbol: str, position: Dict) -> bool:
    try:
        safe_symbol = symbol.replace('/', '_').replace(':', '-')
        trader_id = f'POSITION#{safe_symbol}'

        table_name = os.getenv('STATE_TABLE', 'V4TradingState')
        table = dynamodb.Table(table_name)

        try:
            table.delete_item(Key={'trader_id': trader_id})
        except Exception as e:
            logger.error(f"❌ Failed to delete ghost position item for {symbol}: {e}")

        try:
            entry_price = float(position.get('entry_price', 0))
            quantity = float(position.get('quantity', 0))
            leverage = float(position.get('leverage', 5))
            risk_dollars = 0.0
            if entry_price and quantity and leverage:
                risk_dollars = (entry_price * quantity) / leverage
            if risk_dollars > 0:
                persistence = get_persistence()
                persistence.atomic_remove_risk(symbol, risk_dollars)
        except Exception as e:
            logger.error(f"❌ Failed to cleanup atomic risk for ghost {symbol}: {e}")

        logger.info(f"🧹 {symbol} - Ghost cleaned (Dynamo + risk)")
        return True
    except Exception as e:
        logger.error(f"❌ Ghost cleanup failed for {symbol}: {e}")
        return False
    return None


async def _fetch_user_positions_snapshot(
    demo_mode: bool,
    listen_key: str,
    timeout_s: float = 0.75,
) -> Dict[str, float]:
    try:
        import websockets
    except Exception as e:
        logger.warning(f"[WS] websockets import failed: {e}")
        return {}

    base_ws = "wss://stream.binancefuture.com/ws" if demo_mode else "wss://fstream.binance.com/ws"
    url = f"{base_ws}/{listen_key}"

    positions = {}
    start = time.time()
    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            while time.time() - start < timeout_s:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=0.25)
                except asyncio.TimeoutError:
                    continue

                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    continue

                if msg.get('e') != 'ACCOUNT_UPDATE':
                    continue

                update = msg.get('a', {})
                pos_list = update.get('P', [])
                for p in pos_list:
                    try:
                        sym = p.get('s')
                        amt = float(p.get('pa', 0))
                        if sym is not None:
                            positions[sym] = amt
                    except Exception:
                        continue

    except Exception as e:
        logger.warning(f"[WS] user data snapshot failed: {e}")
        return {}

    return positions


def fetch_user_positions_snapshot(demo_mode: bool, listen_key: str) -> Dict[str, float]:
    try:
        return asyncio.run(_fetch_user_positions_snapshot(demo_mode=demo_mode, listen_key=listen_key))
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(_fetch_user_positions_snapshot(demo_mode=demo_mode, listen_key=listen_key))
        except Exception:
            return {}


def fetch_mark_prices_snapshot(demo_mode: bool) -> Dict[str, float]:
    try:
        return asyncio.run(_fetch_mark_prices_snapshot(demo_mode=demo_mode))
    except RuntimeError:
        # In case an event loop already exists (rare in Lambda sync handler)
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(_fetch_mark_prices_snapshot(demo_mode=demo_mode))
        except Exception:
            return {}


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
    position: Dict,
    current_price_override: Optional[float] = None,
    user_position_amt_override: Optional[float] = None,
) -> Optional[Dict]:
    """
    Check if TP or SL is hit, close if yes
    Returns: Dict with action info or None
    """
    try:
        # V16: Prefer WebSocket mark price snapshot, fallback to REST ticker
        if current_price_override is not None:
            current_price = float(current_price_override)
        else:
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

        # Race-condition guard (strong): if user data says positionAmt is 0, skip immediately
        if user_position_amt_override is not None:
            try:
                if abs(float(user_position_amt_override)) == 0.0:
                    logger.info(f"ℹ️ {symbol} - Skip close: user stream says positionAmt=0")
                    return None
            except Exception:
                pass
        
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
                risk = _get_position_risk(exchange, symbol)
                if risk is not None:
                    live_amt = float(risk.get('positionAmt', 0))
                    position_side = str(risk.get('positionSide', '')).upper() or None
                else:
                    live_amt = _get_live_position_amt(exchange, symbol)
                    position_side = _get_live_position_side(exchange, symbol) if live_amt is not None else None

                if live_amt is not None and abs(live_amt) == 0.0:
                    logger.info(f"ℹ️ {symbol} - Skip timeout close: live position amount is 0")
                    cleanup_ghost_position(symbol, position)
                    return None

                if live_amt is not None:
                    side = 'sell' if live_amt > 0 else 'buy'
                    quantity = abs(float(live_amt))
                else:
                    side = 'sell' if direction == 'LONG' else 'buy'
                    quantity = float(position['quantity'])
                    position_side = None
                
                try:
                    close_result = exchange.close_position(symbol, side, quantity, position_side=position_side)
                except Exception as e:
                    msg = str(e)
                    if "ReduceOnly" in msg or "reduceOnly" in msg:
                        logger.info(f"ℹ️ {symbol} - Skip timeout close: reduceOnly rejected")
                        # Re-check: if now zero, ghost cleanup
                        risk2 = _get_position_risk(exchange, symbol)
                        if risk2 is not None and abs(float(risk2.get('positionAmt', 0))) == 0.0:
                            cleanup_ghost_position(symbol, position)
                        return None
                    raise
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
            
        # 🏛️ EMPIRE V16.7: Hard Leveraged Targets
        # Close if Leveraged PnL >= 1.0% (Profit target)
        # Close if Leveraged PnL <= -2.5% (Max loss target)
        leverage = float(position.get('leverage', 5))
        leveraged_pnl = pnl_pct * leverage
        
        target_hit = False
        if leveraged_pnl >= 1.75:
            logger.info(f"💰 {symbol} - TARGET PnL HIT: {leveraged_pnl:.2f}% (Limit: 1.75%)")
            target_hit = True
        elif leveraged_pnl <= -2.25:
            logger.warning(f"🚨 {symbol} - MAX LOSS HIT: {leveraged_pnl:.2f}% (Limit: -2.25%)")
            target_hit = True

        # Check TP hit (Standard ATR/Static)
        tp_hit = False
        if not target_hit:
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
        if tp_hit or sl_hit or anti_trend_hit or target_hit:
            exit_reason = 'TARGET_EXIT' if target_hit else ('TP_HIT' if tp_hit else ('SL_HIT' if sl_hit else 'ANTI_TREND_BLOCK'))
            
            logger.info(f"🎯 {symbol} - {exit_reason} at ${current_price:.4f} ({pnl_pct:+.2f}%)")
            
            # 🏛️ EMPIRE V16.7.2: Cancel pending TP/SL orders FIRST to avoid ReduceOnly conflicts
            try:
                exchange.cancel_all_orders(symbol)
                logger.info(f"🧹 {symbol} - Pending orders cancelled before market close")
            except Exception as e:
                logger.warning(f"⚠️ {symbol} - Failed to cancel orders: {e}")

            # Execute close order using exchange directly (FAST)
            try:
                risk = _get_position_risk(exchange, symbol)
                if risk is not None:
                    live_amt = float(risk.get('positionAmt', 0))
                    position_side = str(risk.get('positionSide', '')).upper() or None
                else:
                    live_amt = _get_live_position_amt(exchange, symbol)
                    position_side = _get_live_position_side(exchange, symbol) if live_amt is not None else None

                if live_amt is not None and abs(live_amt) == 0.0:
                    logger.info(f"ℹ️ {symbol} - Skip close: position already 0 on exchange")
                    cleanup_ghost_position(symbol, position)
                    return None

                # Direct market order execution
                if live_amt is not None:
                    close_side = 'sell' if live_amt > 0 else 'buy'
                    close_qty = abs(float(live_amt))
                else:
                    close_side = 'sell' if direction == 'LONG' else 'buy'
                    close_qty = float(position['quantity'])

                close_result = exchange.close_position(symbol, close_side, close_qty, position_side=position_side)
            except Exception as e:
                msg = str(e)
                if "ReduceOnly" in msg or "reduceOnly" in msg:
                    logger.info(f"ℹ️ {symbol} - Skip close: reduceOnly rejected (likely already closed / wrong state)")
                    risk2 = _get_position_risk(exchange, symbol)
                    if risk2 is not None and abs(float(risk2.get('positionAmt', 0))) == 0.0:
                        cleanup_ghost_position(symbol, position)
                    return None
                if 'Position not found' in msg or 'position not found' in msg:
                    logger.info(f"ℹ️ {symbol} - Skip close: position not found on exchange")
                    cleanup_ghost_position(symbol, position) # Cleanup as it's not on exchange
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

def sync_binance_orphans(exchange: ExchangeConnector, memory_positions: Dict) -> Dict:
    """
    🏛️ EMPIRE V16.4: Anti-Orphan Management
    Compare Binance Real positions vs DynamoDB Memory positions.
    Register orphans in DynamoDB so they get managed by Closer.
    """
    results = {'orphans_found': 0, 'errors': 0}
    try:
        # 1. Fetch ALL active positions from Binance
        # Use CCXT for robustness or direct API for speed
        live_positions = exchange.exchange.fapiPrivateV2GetPositionRisk()
        
        # 2. Extract active ones (amt != 0)
        active_on_exchange = {}
        for p in live_positions:
            amt = float(p.get('positionAmt', 0))
            if abs(amt) > 0:
                # Map back to CCXT format for consistency
                # Symbol is e.g. 'USELESSUSDT'
                raw_sym = p['symbol']
                # Try to find the CCXT symbol (e.g. USELESS/USDT:USDT)
                ccxt_sym = None
                if exchange.markets:
                    for s, m in exchange.markets.items():
                        if m.get('id') == raw_sym:
                            ccxt_sym = s
                            break
                
                
                if not ccxt_sym:
                    # Fallback mapping if not in cache (common for Chinese/new tokens)
                    if raw_sym.endswith('USDT'):
                        base = raw_sym[:-4]
                        ccxt_sym = f"{base}/USDT:USDT"
                    else:
                        ccxt_sym = raw_sym

                active_on_exchange[ccxt_sym] = {
                    'quantity': abs(amt),
                    'direction': 'LONG' if amt > 0 else 'SHORT',
                    'entry_price': float(p.get('entryPrice', 0)),
                    'leverage': int(p.get('leverage', 5)),
                    'mark_price': float(p.get('markPrice', 0))
                }

        # 3. Identify orphans (On Exchange but NOT in Memory)
        for sym, data in active_on_exchange.items():
            if sym not in memory_positions:
                logger.warning(f"🚨 ORPHAN DETECTED: {sym} on Binance but missing in DynamoDB. Registering...")
                
                # Create mock position data
                # SL/TP based on entry price (emergency defaults)
                entry = data['entry_price']
                if data['direction'] == 'LONG':
                    tp = entry * (1 + TradingConfig.MIN_TP_PCT)
                    sl = entry * (1 - (TradingConfig.SL_MULTIPLIER * 0.005)) # ~0.5% default SL
                else:
                    tp = entry * (1 - TradingConfig.MIN_TP_PCT)
                    sl = entry * (1 + (TradingConfig.SL_MULTIPLIER * 0.005))

                pos_data = {
                    'trade_id': f"ORPHAN-{int(time.time())}",
                    'symbol': sym,
                    'status': 'OPEN',
                    'entry_price': entry,
                    'quantity': data['quantity'],
                    'direction': data['direction'],
                    'take_profit': tp,
                    'stop_loss': sl,
                    'leverage': data['leverage'],
                    'asset_class': 'Crypto',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'entry_time': datetime.now(timezone.utc).isoformat(),
                    'risk_dollars': (entry * data['quantity']) / data['leverage'],
                    'notes': 'Automatically Registered Orphan'
                }
                
                # Save to DynamoDB
                try:
                    persistence = get_persistence()
                    persistence.save_position(sym, pos_data)
                    # Register risk atomically to avoid portfolio imbalance
                    persistence.atomic_check_and_add_risk(sym, pos_data['risk_dollars'], 999999) # Safe limit
                    results['orphans_found'] += 1
                except Exception as e:
                    logger.error(f"❌ Failed to register orphan {sym}: {e}")
                    results['errors'] += 1

    except Exception as e:
        logger.error(f"❌ Orphan Sync failed: {e}")
        results['errors'] += 1
        
    return results

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
        safe_symbol = symbol.replace('/', '_').replace(':', '-')
        trader_id = f'POSITION#{safe_symbol}'

        response = table.get_item(Key={'trader_id': trader_id})
        item = response.get('Item')
        if item and item.get('status') == 'OPEN':
            table.update_item(
                Key={'trader_id': trader_id},
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
    EMPIRE V16.7.6: Persistent Closer Loop
    Runs for 13 minutes, executing a check every 7 seconds.
    """
    lambda_role = 'CLOSER_PERSISTENT'
    start_time = time.time()
    logger.info("=" * 60)
    logger.info(f"🚀 {lambda_role} Starting 13-minute session")
    logger.info("=" * 60)
    
    try:
        # Phase 1: INIT - Common for all cycles
        p1_start = time.time()
        creds = load_binance_credentials()
        live_mode = bool(getattr(TradingConfig, 'LIVE_MODE', False))
        demo_mode = not live_mode

        exchange = ExchangeConnector(
            api_key=creds['api_key'],
            secret=creds['secret_key'],
            live_mode=live_mode
        )
        
        def remaining_ms() -> int:
            try:
                return int(context.get_remaining_time_in_millis())
            except Exception:
                return 0

        persistent_duration_min = 13
        tick_interval_seconds = 7
        session_start = time.time()
        
        total_closed = 0
        cycle_count = 0
        consecutive_errors = 0  # 🏛️ V16.7.8 FIX: Track consecutive failures
        MAX_CONSECUTIVE_ERRORS = 3  # Fail fast after 3 consecutive errors
        
        while True:
            cycle_start = time.time()
            cycle_count += 1
            
            # 🏛️ EMPIRE V16.7.7: Vigilance "Zombie Loop" & Time Tracking
            rem = remaining_ms()
            elapsed_total = cycle_start - session_start
            
            # Security: Log remainig time frequently
            if cycle_count % 5 == 1:
                logger.info(f"🌀 CYCLE {cycle_count} STARTING (Remaining: {rem/1000:.1f}s, Elapsed Session: {elapsed_total:.1f}s)")
            
            # Check if we should stop (Safety: 15s margin)
            if elapsed_total > (persistent_duration_min * 60) - 15:
                logger.info(f"🏁 Session time limit reached ({elapsed_total:.1f}s). Finishing.")
                break
                
            if rem < 12000: # 12s safety
                logger.warning(f"⚠️ Low visibility on Lambda time ({rem}ms). Closing session to avoid hard timeout.")
                break

            # ⚙️ Execute logic
            try:
                # 1. Source of Truth: Binance
                live_positions = exchange.exchange.fapiPrivateV2GetPositionRisk()
                active_on_exchange = {}
                for p in live_positions:
                    amt = float(p.get('positionAmt', 0))
                    if abs(amt) > 0:
                        symbol = p['symbol']
                        if symbol.endswith('USDT'):
                            ccxt_symbol = f"{symbol[:-4]}/USDT:USDT"
                        else:
                            ccxt_symbol = symbol
                        active_on_exchange[ccxt_symbol] = p
                
                persistence = get_persistence()
                memory_positions = persistence.load_positions()
                
                # Sync & Cleanup
                final_positions = {}
                for sym, binance_data in active_on_exchange.items():
                    if sym in memory_positions:
                        pos = memory_positions[sym]
                        pos['quantity'] = abs(float(binance_data['positionAmt']))
                        pos['entry_price'] = float(binance_data['entryPrice'])
                        final_positions[sym] = pos
                    else:
                        # Orphan
                        logger.warning(f"🚨 ORPHAN SYNC: {sym} found on Binance. Mocking SL/TP...")
                        entry = float(binance_data['entryPrice'])
                        side = 'LONG' if float(binance_data['positionAmt']) > 0 else 'SHORT'
                        tp = entry * (1 + TradingConfig.MIN_TP_PCT) if side == 'LONG' else entry * (1 - TradingConfig.MIN_TP_PCT)
                        sl = entry * (1 - 0.004) if side == 'LONG' else entry * (1 + 0.004)
                        orphan_pos = {
                            'trade_id': f"ORPHAN-{int(time.time())}",
                            'symbol': sym, 'status': 'OPEN', 'entry_price': entry,
                            'quantity': abs(float(binance_data['positionAmt'])), 'direction': side,
                            'take_profit': tp, 'stop_loss': sl, 'leverage': int(binance_data.get('leverage', 5)),
                            'timestamp': datetime.now(timezone.utc).isoformat()
                        }
                        persistence.save_position(sym, orphan_pos)
                        final_positions[sym] = orphan_pos

                for sym in memory_positions:
                    if sym not in active_on_exchange:
                        persistence.delete_position(sym)

                # 2. Check each position
                if final_positions:
                    # 🏛️ EMPIRE V16.7.7: Global News Blackout Protection
                    import macro_context
                    macro = macro_context.get_macro_context()
                    is_blackout = macro.get('is_news_blackout', False)
                    
                    mark_prices = fetch_mark_prices_snapshot(demo_mode=demo_mode)
                    for symbol, position in final_positions.items():
                        # Safety: skip if time is critical
                        if remaining_ms() < 3000:
                            break
                            
                        current_price_override = None
                        if mark_prices:
                            lookup = symbol.replace('/USDT:USDT', 'USDT').replace('/', '')
                            current_price_override = mark_prices.get(lookup)
                        # 1. News Blackout Protection
                        if is_blackout:
                            logger.warning(f"🛑 NEWS BLACKOUT EXIT: Closing {symbol} - {macro.get('news_reason', 'Major Event')}")
                            try:
                                close_side = 'sell' if position.get('direction') == 'LONG' else 'buy'
                                exchange.close_position(symbol, close_side, position['quantity'])
                                persistence.delete_position(symbol)
                                total_closed += 1
                                continue
                            except Exception as e:
                                logger.error(f"❌ Failed to close {symbol} during blackout: {e}")

                        # 🧭 2. BTC COMPASS PROTECTION (Audit Fix #2)
                        from btc_compass import btc_compass
                        # Basic BTC Data Fetching within the closer session
                        # (Ideally we'd use the mark_prices from Phase 1)
                        btc_price = mark_prices.get('BTCUSDT') if mark_prices else None
                        if btc_price:
                            # Feed the compass (approximate volume as it's not critical for trend here)
                            btc_compass.analyze_btc_trend(btc_price=btc_price, btc_volume=0)
                            
                            # Exit if Trend Lock is violated
                            if getattr(TradingConfig, 'BTC_DIRECTION_LOCK', False):
                                current_btc_trend = btc_compass.btc_trend
                                position_side = position.get('direction')
                                
                                if current_btc_trend == 'BEARISH' and position_side == 'LONG':
                                    logger.warning(f"🧭 [COMPASS_EXIT] BTC BEARISH reversal! Closing LONG {symbol}")
                                    exchange.close_position(symbol, position['direction'] == 'LONG' and 'sell' or 'buy', position['quantity'])
                                    persistence.delete_position(symbol)
                                    total_closed += 1
                                    continue
                                elif current_btc_trend == 'BULLISH' and position_side == 'SHORT':
                                    logger.warning(f"🧭 [COMPASS_EXIT] BTC BULLISH reversal! Closing SHORT {symbol}")
                                    exchange.close_position(symbol, position['direction'] == 'LONG' and 'sell' or 'buy', position['quantity'])
                                    persistence.delete_position(symbol)
                                    total_closed += 1
                                    continue

                        result = check_and_close_position(exchange, symbol, position, current_price_override=current_price_override)
                        if result and result.get('action') == 'CLOSED':
                            total_closed += 1
                            logger.info(f"✅ Closed: {symbol} ({result.get('reason')})")
                
                # ✅ V16.7.8 FIX: Reset consecutive errors on successful cycle
                consecutive_errors = 0

            except Exception as e:
                # Global cycle try/except for recovery
                consecutive_errors += 1
                logger.error(f"⚠️ CYCLE {cycle_count} RECOVERED FROM ERROR ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}", exc_info=True)
                
                # 🚨 V16.7.8 FIX: Fail fast if too many consecutive errors
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.critical(f"🚨 CRITICAL: {MAX_CONSECUTIVE_ERRORS} consecutive cycle failures! Aborting session to trigger CloudWatch alarms.")
                    raise RuntimeError(f"Too many consecutive failures ({consecutive_errors}). Last error: {e}")

            # Sleep
            elapsed_cycle = time.time() - cycle_start
            wait_time = max(0.1, tick_interval_seconds - elapsed_cycle)
            time.sleep(wait_time)

        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'SESSION_COMPLETE', 'cycles': cycle_count, 'closed': total_closed})
        }
        
    except Exception as e:
        logger.error(f"❌ FATAL: {e}", exc_info=True)
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
