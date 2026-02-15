import requests
import re
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Tuple, Optional, List
from decimal import Decimal

# Absolute imports for Lambda standalone
import config
from config import TradingConfig

logger = logging.getLogger(__name__)

# --- CACHE SYSTEM ---
_macro_lock = threading.Lock()
_macro_cache = {
    'indicators': None,       # DXY, VIX
    'indicator_ts': 0,
    'calendar': None,         # List of high impact events
    'calendar_ts': 0
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

def _get_forex_factory_calendar() -> List[Dict]:
    """
    Fetch and Cache economic calendar (RSS).
    Cached for 24 hours as suggested by the user.
    """
    now = time.time()
    
    with _macro_lock:
        # Cache for 1 hour to detect "surprise" additions while staying efficient
        if _macro_cache['calendar'] and (now - _macro_cache['calendar_ts'] < 3600):
            return _macro_cache['calendar']

    try:
        logger.info("[NEWS] Fetching fresh daily economic calendar...")
        url = "https://www.forexfactory.com/ff_calendar_thisweek.xml"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return _macro_cache['calendar'] or []
            
        import xml.etree.ElementTree as ET
        root = ET.fromstring(response.content)
        events = []
        
        for item in root.findall('event'):
            impact_node = item.find('impact')
            impact = impact_node.text if impact_node is not None else ""
            if impact != 'High':
                continue
                
            title = item.find('title').text if item.find('title') is not None else "Unknown"
            date_str = item.find('date').text if item.find('date') is not None else ""
            time_str = item.find('time').text if item.find('time') is not None else ""
            
            events.append({
                'title': title,
                'impact': impact,
                'date': date_str,
                'time': time_str
            })
            
        with _macro_lock:
            _macro_cache['calendar'] = events
            _macro_cache['calendar_ts'] = now
            
        return events
    except Exception as e:
        logger.warning(f"[WARN] Failed to fetch FF calendar: {e}")
        return _macro_cache['calendar'] or []

def is_news_blackout() -> Tuple[bool, str]:
    """
    Check if we are currently in a blackout window.
    Dynamic: Checks cached calendar against current time.
    """
    events = _get_forex_factory_calendar()
    if not events:
        return False, ""
        
    now_utc = datetime.now(timezone.utc)
    
    for event in events:
        try:
            date_part = event['date']
            time_part = event['time'].lower()
            
            match = re.search(r'(\d+):(\d+)(am|pm)', time_part)
            if not match: continue
            
            h, m, period = match.groups()
            hours = int(h)
            if period == 'pm' and hours < 12: hours += 12
            if period == 'am' and hours == 12: hours = 0
            
            # Approximation EST to UTC
            event_dt_est = datetime.strptime(date_part, "%m-%d-%Y").replace(
                hour=hours, minute=int(m), tzinfo=timezone(timedelta(hours=-5))
            )
            event_dt_utc = event_dt_est.astimezone(timezone.utc)
            
            diff_mins = (now_utc - event_dt_utc).total_seconds() / 60
            
            # Rule: 5min before, 10min after
            if -TradingConfig.NEWS_PAUSE_MINUTES_BEFORE <= diff_mins <= TradingConfig.NEWS_PAUSE_MINUTES_AFTER:
                reason = f"High Impact: {event['title']} ({event['time']} EST)"
                return True, reason
                
        except:
            continue
            
    return False, ""

def get_macro_context(state_table=None) -> Dict:
    """
    Récupère le contexte macro global.
    Indicateurs (VIX, DXY) cachés 1h.
    Blackout check dynamique (chaque minute).
    """
    now_ts = time.time()
    
    # --- Level 1: Fetch Indicators (Cached 1h) ---
    with _macro_lock:
        if not _macro_cache['indicators'] or (now_ts - _macro_cache['indicator_ts'] > TradingConfig.MACRO_CACHE_TTL_SECONDS):
            logger.info("[INFO] Fetching fresh indicators (VIX/DXY)...")
            dxy = _fetch_yahoo_data('UUP')
            vix = _fetch_yahoo_data('^VIX')
            _macro_cache['indicators'] = {'dxy': dxy, 'vix': vix}
            _macro_cache['indicator_ts'] = now_ts
        
        indicators = _macro_cache['indicators']

    vix_val = indicators['vix']['price'] if indicators['vix'] else 20.0
    regime = "NORMAL"
    if vix_val > 25: regime = "RISK_OFF"
    if vix_val > 35: regime = "CRASH"

    # --- Level 2: Dynamic Blackout Check (No cache for the status, only for calendar data) ---
    is_blackout, news_reason = is_news_blackout()

    context = {
        'regime': regime,
        'can_trade': regime != "CRASH" and not is_blackout,
        'is_news_blackout': is_blackout,
        'news_reason': news_reason,
        'vix': vix_val,
        'size_multiplier': 0.5 if regime == "RISK_OFF" else 1.0,
        'summary': f"Macro: {regime} | VIX: {vix_val:.1f} | News: {'PAUSED' if is_blackout else 'OK'}",
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
        
    return context
