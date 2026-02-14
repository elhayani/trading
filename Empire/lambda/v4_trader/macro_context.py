import requests
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional
from decimal import Decimal

# Absolute imports for Lambda standalone (Critique #1 New)
import config
from config import TradingConfig

logger = logging.getLogger(__name__)

# --- CACHE SYSTEM ---
_macro_lock = threading.Lock()
_macro_cache = {
    'data': None,
    'timestamp': 0
}

YAHOO_API_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

def _fetch_yahoo_data(symbol: str, period: str = '2d') -> Optional[Dict]:
    try:
        url = f"{YAHOO_API_BASE}/{symbol}"
        params = {'interval': '1d', 'range': period}
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code != 200: return None
        data = response.json()
        result = data.get('chart', {}).get('result', [])
        if not result: return None
        
        meta = result[0].get('meta', {})
        price = float(meta.get('regularMarketPrice', 0))
        prev = float(meta.get('chartPreviousClose', price))
        return {'symbol': symbol, 'price': price, 'change_pct': (price - prev) / prev if prev > 0 else 0}
    except Exception as e:
        logger.warning(f"[INFO] Yahoo fetch failed for {symbol}: {e}")
        return None

def get_macro_context(state_table=None) -> Dict:
    """
    Récupère le contexte macro global pour filtrer les trades.
    
    IMPORTANT: Les indices traditionnels (S&P500, VIX) sont utilisés
    comme INDICATEURS DE SENTIMENT uniquement. Ils ne sont PAS tradés
    sur Binance.
    
    Usage:
    - VIX > 35 → Regime = CRASH → Réduire leverage
    - S&P500 < -3% → Risk-OFF → Skip altcoins risqués
    - DXY pump → USD strength → Bearish crypto
    
    Sources de données:
    - Yahoo Finance (^GSPC, ^VIX, UUP)
    - Lecture seule, pas de trading
    
    Get macro context with 2-level caching (Memory + DynamoDB).
    (Critique #3 New)
    """
    now_ts = time.time()
    
    # --- Level 1: Memory Cache ---
    with _macro_lock:
        if _macro_cache['data'] and (now_ts - _macro_cache['timestamp'] < TradingConfig.MACRO_CACHE_TTL_SECONDS):
            return _macro_cache['data']

    # --- Level 2: DynamoDB Cache (if table provided) ---
    if state_table:
        try:
            response = state_table.get_item(Key={'trader_id': 'CACHE#MACRO_CONTEXT'})
            item = response.get('Item', {})
            if item:
                cache_ts = float(item.get('timestamp', 0))
                if (now_ts - cache_ts) < TradingConfig.MACRO_CACHE_TTL_SECONDS:
                    logger.info("[OK] Macro context retrieved from DynamoDB cache.")
                    data = item.get('data')
                    with _macro_lock:
                        _macro_cache['data'] = data
                        _macro_cache['timestamp'] = cache_ts
                    return data
        except Exception as e:
            logger.warning(f"[WARN] DynamoDB macro cache read failed: {e}")

    # --- Fresh Fetch ---
    logger.info("[INFO] Fetching fresh macro context from Yahoo Finance...")
    dxy = _fetch_yahoo_data('UUP') # ETF proxy
    vix = _fetch_yahoo_data('^VIX')
    
    regime = "NORMAL"
    vix_val = vix['price'] if vix else 20.0
    if vix_val > 25: regime = "RISK_OFF"
    if vix_val > 35: regime = "CRASH"

    context = {
        'regime': regime,
        'can_trade': regime != "CRASH",
        'size_multiplier': 0.5 if regime == "RISK_OFF" else 1.0,
        'summary': f"Macro Regime: {regime} | VIX: {vix_val:.1f} | DXY: {dxy['price'] if dxy else 'N/A'}",
        'calendar': {'has_high_impact': False},
        'timestamp': datetime.now(timezone.utc).isoformat()
    }

    # --- Update Caches ---
    with _macro_lock:
        _macro_cache['data'] = context
        _macro_cache['timestamp'] = now_ts
        
    if state_table:
        try:
            state_table.put_item(Item={
                'trader_id': 'CACHE#MACRO_CONTEXT',
                'data': context,
                'timestamp': Decimal(str(now_ts)),
                'ttl': int(now_ts) + 7200 # 2-hour TTL for DynamoDB
            })
        except Exception as e:
            logger.warning(f"[WARN] DynamoDB macro cache write failed: {e}")
    
    return context
