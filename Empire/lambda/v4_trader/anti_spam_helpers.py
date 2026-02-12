"""
Anti-Spam Protection Helpers for Trading Engine
Prevents order loops and ghost trading
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, List
import logging

logger = logging.getLogger()

def is_in_cooldown(state_table, symbol: str, cooldown_seconds: int = 300) -> bool:
    """
    Check if symbol was traded recently (within cooldown period).
    Returns True if in cooldown (should skip), False if safe to trade.
    """
    try:
        safe_symbol = symbol.replace('/', '_').replace(':', '-')
        response = state_table.get_item(Key={'trader_id': f'COOLDOWN#{safe_symbol}'})
        
        if 'Item' not in response:
            return False
        
        last_trade_ts = response['Item'].get('timestamp')
        if not last_trade_ts:
            return False
        
        last_trade = datetime.fromisoformat(last_trade_ts)
        if last_trade.tzinfo is None:
            last_trade = last_trade.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_trade).total_seconds()
        
        if elapsed < cooldown_seconds:
            logger.warning(f"[COOLDOWN] {symbol} traded {int(elapsed)}s ago (< {cooldown_seconds}s)")
            return True
        
        return False
    except Exception as e:
        logger.error(f"[ERROR] Cooldown check failed: {e}")
        return False  # Fail open to avoid blocking legitimate trades


def record_trade_timestamp(state_table, symbol: str):
    """
    Record the timestamp when a trade was executed for cooldown tracking.
    """
    try:
        safe_symbol = symbol.replace('/', '_').replace(':', '-')
        state_table.put_item(Item={
            'trader_id': f'COOLDOWN#{safe_symbol}',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'symbol': symbol
        })
        logger.info(f"[COOLDOWN] Recorded trade timestamp for {symbol}")
    except Exception as e:
        logger.error(f"[ERROR] Failed to record cooldown: {e}")


def get_real_binance_positions(exchange) -> List[str]:
    """
    Fetch actual open positions from Binance (not DynamoDB).
    Returns list of symbols that have open positions.
    This is the ultimate source of truth to prevent ghost trading.
    """
    try:
        # Access the internal CCXT exchange instance
        ccxt_exchange = exchange.exchange if hasattr(exchange, 'exchange') else exchange
        
        # Use Binance Futures specific API call
        positions = ccxt_exchange.fapiPrivateV2GetPositionRisk()
        open_symbols = []
        
        for pos in positions:
            # Binance returns positionAmt as string
            position_amt = float(pos.get('positionAmt', 0))
            
            if position_amt != 0:
                symbol = pos.get('symbol', '')
                # Convert SOLUSDT to SOL/USDT:USDT format
                if symbol and not '/' in symbol:
                    # Most Binance Futures symbols are like BTCUSDT, ETHUSDT
                    if symbol.endswith('USDT'):
                        base = symbol[:-4]
                        symbol = f"{base}/USDT:USDT"
                
                if symbol:
                    open_symbols.append(symbol)
                    logger.info(f"[REAL_POSITION] Found open position: {symbol} (size={position_amt})")
        
        return open_symbols
    except Exception as e:
        logger.error(f"[ERROR] Failed to fetch real positions: {e}")
        return []  # Fail open to avoid blocking
