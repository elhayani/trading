"""
Lambda 1: SCANNER / OPENER
==========================
Fréquence: 1 minute
Rôle: Scan market + Open positions UNIQUEMENT
Ne touche PAS aux positions ouvertes (géré par Lambda 2 et 3)
"""

import json
import os
import logging
import time
from datetime import datetime, timezone
from typing import List, Dict

import boto3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure log level based on environment
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
logging.getLogger().setLevel(getattr(logging, LOG_LEVEL))
logger = logging.getLogger(__name__)

# Imports from existing modules
from trading_engine import (
    AWSClients,
    TradingEngine
)
from config import TradingConfig

# Session optimization imports
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

lambda_client = boto3.client('lambda')

# ================================================================
# BINANCE REST API - FILTRES SERVER-SIDE
from config import TradingConfig

def get_binance_base_url():
    """Get correct base URL based on TradingConfig.LIVE_MODE"""
    if getattr(TradingConfig, 'LIVE_MODE', False):
        return "https://fapi.binance.com"
    else:
        # Binance Futures Demo REST API - Correct endpoint
        return "https://demo-fapi.binance.com"

BASE_URL = get_binance_base_url()

def fetch_filtered_symbols_server_side(
    min_volume_24h: float = 5_000_000,
    min_price_change_pct: float = 0.3,
    max_symbols: int = 150
) -> List[Dict]:
    """
    Utilise l'endpoint /fapi/v1/ticker/24hr avec filtres
    
    ULTRA-FAST: 1 seul appel API au lieu de 415
    Latency: 200-500ms (vs 3-5s)
    Gain: -4s
    
    Returns: Liste de symboles déjà pré-filtrés par Binance
    """
    try:
        # Endpoint qui retourne TOUS les tickers 24h en 1 call
        response = requests.get(
            f"{BASE_URL}/fapi/v1/ticker/24hr",
            timeout=5
        )
        response.raise_for_status()
        all_tickers = response.json()
        
        # Filtrer localement (ultra-rapide car déjà en mémoire)
        filtered = []
        
        for ticker in all_tickers:
            symbol = ticker['symbol']
            
            # Skip non-USDT/FDUSD
            if not (symbol.endswith('USDT') or symbol.endswith('FDUSD')):
                continue
            
            # Filtres server-side data
            volume_24h = float(ticker.get('quoteVolume', 0))
            price_change_pct = abs(float(ticker.get('priceChangePercent', 0)))
            
            # Apply filters
            if volume_24h >= min_volume_24h and price_change_pct >= min_price_change_pct:
                # Normaliser au format CCXT
                quote = 'FDUSD' if symbol.endswith('FDUSD') else 'USDT'
                base = symbol.replace(quote, '')
                normalized_symbol = f"{base}/{quote}:{quote}"
                
                filtered.append({
                    'symbol': normalized_symbol,
                    'volume_24h': volume_24h,
                    'quoteVolume': volume_24h,             # Pour compatibilité check_technical_health
                    'price_change_pct': price_change_pct,
                    'last_price': float(ticker.get('lastPrice', 0)),
                    'lastPrice': float(ticker.get('lastPrice', 0)), # Pour compatibilité
                    'bidPrice': float(ticker.get('bidPrice', 0)),   # Pour spread check
                    'askPrice': float(ticker.get('askPrice', 0)),   # Pour spread check
                    'count': int(ticker.get('count', 0))
                })
        
        # Trier par volume (top mobilité)
        filtered.sort(key=lambda x: x['volume_24h'], reverse=True)
        
        return filtered[:max_symbols]
        
    except Exception as e:
        logger.error(f"Server-side filter failed: {e}")
        return []


def fetch_batch_klines_fast(symbols: List[str], limit: int = 60) -> Dict[str, List[list]]:
    """
    ULTRA-LOW LATENCY BATCH FETCH (V16 Optimized).
    - Utilise ThreadPoolExecutor optimisé (60 workers)
    - Session reuse (Keep-Alive TCP + SSL handshake)
    - Limit strict = 60 (minimal data needed)
    """
    
    def _fetch_single(sess, s, lim):
        try:
            # Binance symbol conversion clean & fast
            pair = s.split(':')[0] if ':' in s else s
            base, quote = pair.split('/')
            bin_sym = f"{base}{quote}"
            
            # Fast get with session reuse
            resp = sess.get(
                f"{BASE_URL}/fapi/v1/klines",
                params={'symbol': bin_sym, 'interval': '1m', 'limit': lim},
                timeout=2.0  # Fail fast
            )
            
            if resp.status_code == 200:
                data = resp.json()
                # Parse minimaliste pour CPU save: [timestamp, open, high, low, close, volume]
                ohlcv = [
                    [d[0], float(d[1]), float(d[2]), float(d[3]), float(d[4]), float(d[5])]
                    for d in data
                ]
                return s, ohlcv
            return s, None
        except Exception:
            return s, None

    # INIT SESSION POOL
    session = requests.Session()
    # Retry strategy for resilience
    retries = Retry(total=2, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
    # Pool size = Max workers pour éviter le blocage de connection
    adapter = HTTPAdapter(max_retries=retries, pool_connections=60, pool_maxsize=60)
    session.mount('https://', adapter)
    # Force keep-alive headers
    session.headers.update({'Connection': 'keep-alive', 'Accept-Encoding': 'gzip, deflate'})
    
    results = {}
    MAX_WORKERS = 60 # V16: Lambda 1536MB allow heavy IO concurrency without OOM
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        futures = [executor.submit(_fetch_single, session, s, limit) for s in symbols]
        
        for future in as_completed(futures):
            res_sym, res_ohlcv = future.result()
            if res_ohlcv:
                results[res_sym] = res_ohlcv
    
    session.close() # Clean exit
    return results


def unified_mobility_check(ohlcv_60: List, hour_utc: int, btc_atr_pct: float = 0.25) -> tuple[int, str]:
    """
    SINGLE SOURCE OF TRUTH pour la mobilité
    Utilisé UNIQUEMENT dans le scanner
    
    Returns: (mobility_score: 0-100, reason: str)
    """
    
    if len(ohlcv_60) < 60:
        return 0, "INSUFFICIENT_DATA"
    
    closes = [c[4] for c in ohlcv_60]
    volumes = [c[5] for c in ohlcv_60]
    
    # ========================================
    # CRITÈRE 1: Movement récent (10min)
    # ========================================
    last_10_closes = closes[-10:]
    recent_move_pct = abs((last_10_closes[-1] - last_10_closes[0]) / last_10_closes[0]) * 100
    
    # Seuil adaptatif selon volatilité BTC
    if btc_atr_pct < 0.10:
        min_move = 0.10  # Marché mort → accepter moins
    elif btc_atr_pct > 0.30:
        min_move = 0.25  # Marché chaud → être sélectif
    else:
        min_move = 0.15  # Normal
    
    movement_ok = recent_move_pct >= min_move
    
    # ========================================
    # CRITÈRE 2: Volume SESSION (1h = 60 bougies)
    # ========================================
    last_60_volumes = volumes[-60:] if len(volumes) >= 60 else volumes
    last_60_closes = closes[-len(last_60_volumes):]
    
    # Volume en USDT (volume × prix)
    session_vol_usdt = sum(v * c for v, c in zip(last_60_volumes, last_60_closes))
    
    # Seuil adaptatif selon session
    # Nuit (0-7h) : $100K/h acceptable
    # Jour (7-22h) : $150K/h minimum
    if 0 <= hour_utc < 7:
        min_session_vol = 100_000
    else:
        min_session_vol = 150_000
    
    volume_session_ok = session_vol_usdt >= min_session_vol
    
    # ========================================
    # CRITÈRE 3: Volume SURGE (pas de chute)
    # ========================================
    last_10_volumes = volumes[-10:]
    recent_vol_avg = sum(last_10_volumes) / len(last_10_volumes)
    
    vol_avg_20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else recent_vol_avg
    vol_ratio = recent_vol_avg / vol_avg_20 if vol_avg_20 > 0 else 1.0
    
    # Pas de chute de volume (minimum 80% de la moyenne)
    volume_surge_ok = vol_ratio >= 0.8
    
    # ========================================
    # SCORING
    # ========================================
    
    reasons = []
    
    # Tous les critères OK → Score selon intensité
    if movement_ok and volume_session_ok and volume_surge_ok:
        if recent_move_pct >= 0.5:
            mobility_score = 95
            reasons.append(f'STRONG({recent_move_pct:.2f}%)')
        elif recent_move_pct >= 0.3:
            mobility_score = 75
            reasons.append(f'MODERATE({recent_move_pct:.2f}%)')
        else:
            mobility_score = 50
            reasons.append(f'WEAK({recent_move_pct:.2f}%)')
        
        # Bonus volume surge
        if vol_ratio >= 1.5:
            mobility_score = min(mobility_score + 20, 100)
            reasons.append(f'VOL_SURGE({vol_ratio:.1f}x)')
        else:
            reasons.append(f'VOL_NORMAL({vol_ratio:.1f}x)')
        
        reason_str = '|'.join(reasons)
        return mobility_score, reason_str
    
    # Un critère échoue → Rejet avec raison précise
    else:
        if not movement_ok:
            reasons.append(f'FLAT({recent_move_pct:.2f}%<{min_move:.2f}%)')
        if not volume_session_ok:
            reasons.append(f'LOW_SESSION_VOL(${session_vol_usdt/1000:.0f}K<${min_session_vol/1000:.0f}K)')
        if not volume_surge_ok:
            reasons.append(f'VOL_DROP({vol_ratio:.1f}x<0.8x)')
        
        reason_str = '|'.join(reasons)
        return 0, reason_str


def get_btc_atr_pct(klines_map: Dict) -> float:
    """Récupère l'ATR de BTC pour adaptation"""
    btc_symbol = 'BTC/USDT:USDT'
    if btc_symbol in klines_map:
        btc_ohlcv = klines_map[btc_symbol]
        btc_closes = [c[4] for c in btc_ohlcv[-20:]]  # Dernières 20 bougies
        
        if len(btc_closes) >= 20:
            btc_highs = [c[2] for c in btc_ohlcv[-20:]]
            btc_lows = [c[3] for c in btc_ohlcv[-20:]]
            
            # Calcul ATR BTC
            true_ranges = []
            for i in range(-20, 0):
                tr = max(
                    btc_highs[i] - btc_lows[i],
                    abs(btc_highs[i] - btc_closes[i-1]) if i > -20 else 0,
                    abs(btc_lows[i] - btc_closes[i-1]) if i > -20 else 0
                )
                true_ranges.append(tr)
            
            btc_atr = sum(true_ranges) / len(true_ranges)
            btc_atr_pct = (btc_atr / btc_closes[-1]) * 100
            return btc_atr_pct
    
    return 0.25  # Default normal



def check_technical_health(ticker_data: Dict) -> tuple:
    """Check basic technical health for scalping viability."""
    try:
        bid = float(ticker_data.get('bidPrice', 0))
        ask = float(ticker_data.get('askPrice', 0))
        last = float(ticker_data.get('lastPrice', 0))
        
        if bid > 0 and ask > 0 and last > 0:
            spread = (ask - bid) / last * 100
            if spread > 0.35:  # RELACHE: 0.35% max spread (micro-cap OK)
                return False, f"SPREAD_TOO_HIGH({spread:.2f}%)"
                
        q_vol = float(ticker_data.get('quoteVolume', 0))
        if q_vol < 2_000_000:  # RELACHE: $2M min absolute safeline
            return False, f"VOLUME_TOO_LOW(${q_vol/1000000:.1f}M)"
            
        return True, "OK"
    except: return True, "CHECK_ERROR"

def calculate_rsi(closes, period=14):
    """Calcul rapide du RSI pour le dashboard AI"""
    if len(closes) < period + 1:
        return 50.0
    delta = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gain = [d if d > 0 else 0 for d in delta]
    loss = [abs(d) if d < 0 else 0 for d in delta]
    avg_gain = sum(gain[-period:]) / period
    avg_loss = sum(loss[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_elite_score_light(
    symbol: str,
    ohlcv_60: List[list],
    ticker_data: Dict,
    hour_utc: int,
    mobility_score: int,
    mobility_reason: str
) -> Dict:
    # 🆕 TECHNICAL HEALTH CHECK
    health_ok, health_reason = check_technical_health(ticker_data)
    if not health_ok:
        return {'elite_score': 0, 'is_elite': False, 'reason': f"TECH_FAIL: {health_reason}", 'rejection_reason': health_reason}

    """
    SINGLE SOURCE OF TRUTH pour la mobilité.
    Le trading_engine lui fera 100% confiance.
    """
    
    if len(ohlcv_60) < 60:
        return {'elite_score': 0, 'is_elite': False, 'reason': 'INSUFFICIENT_DATA'}
    
    closes = [c[4] for c in ohlcv_60]
    highs = [c[2] for c in ohlcv_60]
    lows = [c[3] for c in ohlcv_60]
    volumes = [c[5] for c in ohlcv_60]
    
    components = {}
    signals = []
    
    # RSI for Dashboard
    rsi = calculate_rsi(closes)
    
    # 1. MOMENTUM (25%)
    ema_5 = sum(closes[-5:]) / 5
    ema_13 = sum(closes[-13:]) / 13
    ema_diff_pct = ((ema_5 - ema_13) / ema_13) * 100
    move_5min = ((closes[-1] - closes[-6]) / closes[-6]) * 100
    
    momentum_score = 0
    if abs(ema_diff_pct) >= 0.30:
        momentum_score += 40
        signals.append('STRONG_MOMENTUM')
    elif abs(ema_diff_pct) >= 0.15:
        momentum_score += 25
    
    if abs(move_5min) >= 0.50:
        momentum_score += 35
    elif abs(move_5min) >= 0.30:
        momentum_score += 20
    
    direction = 'LONG' if ema_5 > ema_13 else 'SHORT'
    components['momentum'] = min(momentum_score, 100)
    
    # Store RSI and history for Haiku
    history_closes = [round(c, 5) for c in closes[-5:]]
    
    # 2. VOLATILITY (25%)
    true_ranges = []
    for i in range(-20, 0):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]) if i > -20 else 0,
            abs(lows[i] - closes[i-1]) if i > -20 else 0
        )
        true_ranges.append(tr)
    
    atr = sum(true_ranges) / len(true_ranges)
    atr_pct = (atr / closes[-1]) * 100
    
    volatility_score = 0
    if atr_pct >= 0.50:
        volatility_score = 90
    elif atr_pct >= 0.35:
        volatility_score = 70
    elif atr_pct >= 0.25:
        volatility_score = 50
    else:
        volatility_score = 20
    
    components['volatility'] = volatility_score
    
    # 3. LIQUIDITY (20%)
    vol_current = volumes[-1]
    vol_avg_20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else vol_current
    vol_ratio = vol_current / vol_avg_20 if vol_avg_20 > 0 else 1.0
    
    liquidity_score = 0
    if vol_ratio >= 3.0:
        liquidity_score = 100
        signals.append('EXTREME_VOLUME')
    elif vol_ratio >= 2.0:
        liquidity_score = 80
        signals.append('VOLUME_SURGE')
    elif vol_ratio >= 1.5:
        liquidity_score = 60
    else:
        liquidity_score = 30
    
    if ticker_data['volume_24h'] >= 20_000_000:
        liquidity_score = min(liquidity_score + 20, 100)
    
    components['liquidity'] = liquidity_score
    
    # 4. 🆕 MOBILITY (15%) - DÉJÀ CALCULÉ
    components['mobility'] = mobility_score
    
    # 5. SESSION (10%)
    ASIA = {'BNB','TRX','ADA','DOT','ATOM','FIL','JASMY','ONE','ZIL','VET','IOTA','NEAR'}
    EU = {'BTC','ETH','LTC','XRP','LINK','UNI','AAVE','MKR','SNX','ZEC','XMR'}
    US = {'SOL','AVAX','DOGE','SHIB','PEPE','ARB','OP','INJ','TIA','SEI','SUI'}
    
    base = symbol.split('/')[0]
    
    if 0 <= hour_utc < 8:
        session_score = 90 if base in ASIA else (30 if base in US else 60)
    elif 7 <= hour_utc < 16:
        session_score = 85 if base in EU else 65
    elif 13 <= hour_utc < 22:
        session_score = 90 if base in US else (75 if base in EU else 65)
    else:
        session_score = 55
    
    components['session'] = session_score
    
    # 6. RISK/QUALITY (5%)
    tp_target = atr * 2.0
    sl_distance = atr * 1.0
    risk_reward = tp_target / sl_distance if sl_distance > 0 else 2.0
    
    risk_score = 100 if risk_reward >= 2.5 else (80 if risk_reward >= 2.0 else 60)
    components['risk_quality'] = risk_score
    
    # ============================================================
    # FINAL SCORE
    # ============================================================
    
    elite_score = (
        components['momentum'] * 0.25 +
        components['volatility'] * 0.25 +
        components['liquidity'] * 0.20 +
        components['mobility'] * 0.15 +
        components['session'] * 0.10 +
        components['risk_quality'] * 0.05
    )
    
    # ============================================================
    # CONDITIONS ÉLITE (STRICTES - mobility_score > 0 obligatoire)
    # ============================================================
    
    is_elite = (
        elite_score >= 60 and
        atr_pct >= 0.25 and
        mobility_score > 0 and
        direction in getattr(TradingConfig, 'ALLOWED_DIRECTIONS', ['LONG', 'SHORT'])
    )
    
    # Si pas élite à cause de mobility, logger la raison précise
    if not is_elite and mobility_score == 0:
        rejection_reason = f"MOBILITY_FAILED: {mobility_reason}"
    else:
        rejection_reason = None
    
    return {
        'symbol': symbol,
        'elite_score': round(elite_score, 2),
        'is_elite': is_elite,
        'components': components,
        'signals': signals,
        'rejection_reason': rejection_reason,
        'rsi': rsi,
        'history': history_closes,
        'vol_surge': vol_ratio,
        'metadata': {
            'direction': direction,
            'atr_pct': atr_pct,
            'vol_ratio': vol_ratio,
            'move_5min': move_5min,
            'mobility_reason': mobility_reason
        }
    }


def sync_ghost_trades_fast(engine) -> int:
    """Nettoyage rapide des ghost trades"""
    try:
        dynamo_positions = engine.persistence.load_positions()
        binance_positions = engine._get_real_binance_positions()
        
        ghost_cleaned = 0
        for symbol, pos_data in dynamo_positions.items():
            if symbol not in binance_positions:
                logger.warning(f"👻 GHOST TRADE DETECTED: {symbol} in DynamoDB but not on Binance")
                
                # Calculate risk to remove
                entry_price = float(pos_data.get('entry_price', 0))
                quantity = float(pos_data.get('quantity', 0))
                leverage = float(pos_data.get('leverage', 1))
                risk_dollars = (entry_price * quantity) / leverage
                
                # Log the trade as closed with GHOST_CLEANUP reason
                engine.persistence.log_trade_close(
                    trade_id=symbol,
                    exit_price=0.0,
                    pnl=0.0,
                    reason="GHOST_CLEANUP"
                )
                
                # Remove from risk manager
                engine.risk_manager.close_trade(symbol, entry_price)
                
                # Risk manager cleanup already done above
                # No more atomic_persistence needed in V16
                
                ghost_cleaned += 1
                logger.info(f"🧹 Ghost {symbol} cleaned - Risk removed: ${risk_dollars:.2f}")
        
        # Sauvegarder l'état après nettoyage
        if ghost_cleaned > 0:
            engine.persistence.save_risk_state(engine.risk_manager.get_state())
            logger.info(f"💾 State saved after cleaning {ghost_cleaned} ghosts")
        
        return ghost_cleaned
        
    except Exception as e:
        logger.error(f"❌ Ghost sync failed: {e}")
        return 0

def get_session_boost(symbol: str, hour_utc: int) -> float:
    """
    Multiplie le score de mobilité selon la session active.
    Retourne un coefficient 0.5 (pénalité) à 2.0 (boost).
    """
    s = symbol.replace('USDT', '')

    # Session Asie (00H-08H UTC) - Heure Paris = 01H-09H
    ASIA_TOKENS = ['BNB','TRX','ADA','DOT','ATOM','FIL',
                   'JASMY','ONE','ZIL','VET','IOTA','NEAR']
    # Session Europe (07H-16H UTC) - Heure Paris = 08H-17H  
    EU_TOKENS   = ['BTC','ETH','LTC','XRP','LINK','UNI',
                   'AAVE','MKR','SNX','ZEC','XMR']
    # Session US (13H-22H UTC) - Heure Paris = 14H-23H
    US_TOKENS   = ['SOL','AVAX','DOGE','SHIB','PEPE','ARB',
                   'OP','INJ','TIA','SEI','SUI']

    if 0 <= hour_utc < 8:    # Nuit Europe = Asie active
        if s in ASIA_TOKENS: return 2.0
        if s in US_TOKENS:   return 0.7
        return 1.0

    elif 7 <= hour_utc < 16:  # Journée Europe
        if s in EU_TOKENS:   return 1.8
        return 1.0

    elif 13 <= hour_utc < 22: # US actif
        if s in US_TOKENS:   return 2.0
        if s in EU_TOKENS:   return 1.5
        return 1.0

    else:                     # Transition
        return 1.0

def get_min_atr(hour_utc: int, btc_atr_pct: float) -> float:
    """
    ATR minimum adaptatif.
    Si BTC lui-même est peu volatile → tout le marché l'est → baisser le seuil.
    """
    # Base selon l'heure
    if 0 <= hour_utc < 7:    # Nuit profonde
        base = 0.20
    elif 13 <= hour_utc < 22: # Full US session
        base = 0.40
    else:
        base = 0.30

    # Ajustement selon volatilité BTC en temps réel
    # Si BTC ATR < 0.10% → marché mort → baisser encore
    if btc_atr_pct < 0.10:
        return base * 0.6
    elif btc_atr_pct > 0.30:
        return base * 1.3  # Marché chaud → être plus sélectif

    return base

def check_session_volume(ohlcv_1min: list, hour_utc: int) -> bool:
    """
    Vérifie que le volume RÉCENT est suffisant,
    pas le volume 24H qui dilue les pics sessionels.
    """
    if len(ohlcv_1min) < 60:
        return False

    # Volume des 60 dernières bougies 1min = 1 heure
    vol_1h = sum(c[5] * c[4] for c in ohlcv_1min[-60:])  # volume × close = USDT

    # Seuil horaire = volume 24H / 24 avec bonus session
    # Si on est dans la session principale de l'actif → seuil plus bas
    MIN_VOL_1H_USDT = 150_000   # $150K/heure = $3.6M/jour équivalent

    return vol_1h >= MIN_VOL_1H_USDT

def detect_night_pump(ohlcv_1min: list) -> tuple[bool, str]:
    """
    Détecte les mouvements anormaux qui signalent une opportunité nocturne.
    """
    if len(ohlcv_1min) < 20:
        return False, ""

    closes = [c[4] for c in ohlcv_1min]
    volumes = [c[5] for c in ohlcv_1min]

    # Mouvement des 5 dernières minutes vs les 15 précédentes
    move_5min = abs(closes[-1] - closes[-6])  / closes[-6]  * 100
    move_15min = abs(closes[-6] - closes[-21]) / closes[-21] * 100

    # Volume des 5 dernières minutes vs moyenne
    vol_5min = sum(volumes[-5:]) / 5
    vol_avg = sum(volumes[-20:-5]) / 15
    vol_ratio = vol_5min / vol_avg if vol_avg > 0 else 0

    # Pump détecté si mouvement récent > 3× le mouvement de fond + volume ×3
    if move_5min > 0.50 and move_5min > move_15min * 2 and vol_ratio > 3.0:
        direction = 'LONG' if closes[-1] > closes[-6] else 'SHORT'
        return True, direction

    return False, ""

def lambda_handler(event, context):
    """
    EMPIRE V16.7.6: Persistent Scanner Loop
    Runs for 13 minutes, executing a scan every 60 seconds.
    """
    logger.info("🚀 EMPIRE V16.7.6: Starting 13-minute persistent session")
    
    # Cycles: 13 minutes (to match EventBridge and stay under 15m timeout)
    max_cycles = 13
    
    for cycle in range(max_cycles):
        cycle_start = time.time()
        
        # 🏛️ EMPIRE V16.7.7: Vigilance "Zombie Loop" & Time Tracking
        remaining_ms = context.get_remaining_time_in_millis() if hasattr(context, 'get_remaining_time_in_millis') else 0
        logger.info(f"🌀 CYCLE {cycle+1}/{max_cycles} STARTING (Remaining: {remaining_ms/1000:.1f}s)")
        
        try:
            # Perform the actual scan
            perform_single_scan(event, context)
        except Exception as e:
            # Global try/except to survive network spikes or transient errors
            logger.error(f"⚠️ CYCLE {cycle+1} RECOVERED FROM ERROR: {e}", exc_info=True)
            
        elapsed = time.time() - cycle_start
        wait_time = max(0.1, 60 - elapsed)
        
        if cycle < max_cycles - 1:
            # Safety check: if less than 65s left, don't risk another cycle
            if remaining_ms > 0 and remaining_ms < 65000:
                logger.warning(f"🛑 Stopping at cycle {cycle+1} - only {remaining_ms/1000:.1f}s left (need >65s)")
                break
            
            logger.info(f"😴 Cycle {cycle+1} complete. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            
    logger.info(f"🏁 13-minute session finished. Cycles: {cycle+1}")
    return {'statusCode': 200, 'body': json.dumps({'status': 'SESSION_COMPLETE', 'cycles': cycle+1})}

def perform_single_scan(event, context):
    """
    ULTRA-FAST Scanner < 15 seconds
    
    Timeline:
    0-1s:   Init + Ghost sync
    1-2s:   Server-side filter (415 → 150)
    2-6s:   Fetch 60 klines parallel (150 symbols)
    6-8s:   Calculate scores (150 → 50 elites)
    8-14s:  Process top 50 (open trades)
    14-15s: Save state
    """
    
    start_time = time.time()
    logger.info("� LAMBDA 1 - ULTRA-FAST < 15s")
    
    try:
        closer_function_name = os.getenv('CLOSER_FUNCTION_NAME')
        if closer_function_name and not event.get('manual'):
            try:
                lambda_client.invoke(
                    FunctionName=closer_function_name,
                    InvocationType='Event',
                    Payload=json.dumps({'source': 'scanner_pre', 'manual': False, 'single_pass': True})
                )
            except Exception as invoke_err:
                logger.warning(f"[WARN] Failed to invoke closer pre-scan: {invoke_err}")

        # ========== PHASE 1: INIT (0-1s) ==========
        engine = TradingEngine()
        engine.risk_manager.load_state(engine.persistence.load_risk_state())
        
        # Récupérer le capital réel depuis Binance
        capital = engine.exchange.get_balance_usdt()
        
        ghost_count = sync_ghost_trades_fast(engine)
        existing_count = len(engine.persistence.load_positions())
        
        logger.info(f"💰 Capital (Binance Real): ${capital:.2f} | Open: {existing_count}/{TradingConfig.MAX_OPEN_TRADES}")
        
        if existing_count >= TradingConfig.MAX_OPEN_TRADES:
            logger.info("� Max trades reached")
            return {'statusCode': 200, 'body': json.dumps({'reason': 'MAX_TRADES'})}
        
        phase1_time = time.time() - start_time
        
        # ========== PHASE 2: SERVER-SIDE FILTER (1-2s) ==========
        filter_start = time.time()
        
        filtered_tickers = fetch_filtered_symbols_server_side(
            min_volume_24h=5_000_000,      # $5M
            min_price_change_pct=0.25,     # 0.25% mouvement min 24h
            max_symbols=150                # Top 150 seulement
        )
        
        if not filtered_tickers:
            raise Exception("No symbols passed server filter")
        
        symbols_to_scan = [t['symbol'] for t in filtered_tickers]
        ticker_map = {t['symbol']: t for t in filtered_tickers}
        
        phase2_time = time.time() - filter_start
        logger.info(f"⚡ Server filter: {len(symbols_to_scan)} symbols in {phase2_time:.1f}s")
        
        # ========== PHASE 3: FETCH KLINES (2-6s) ==========
        klines_start = time.time()
        hour_utc = datetime.utcnow().hour
        
        klines_map = fetch_batch_klines_fast(symbols_to_scan, limit=60)
        
        phase3_time = time.time() - klines_start
        logger.info(f"📊 Fetched {len(klines_map)} klines in {phase3_time:.1f}s")
        
        # ========== PHASE 4: UNIFIED MOBILITY + SCORES (6-8s) ==========
        score_start = time.time()
        
        # Récupérer BTC ATR pour adaptation
        btc_atr_pct = get_btc_atr_pct(klines_map)
        logger.info(f"📊 BTC ATR: {btc_atr_pct:.2f}% (adaptation)")
        
        elite_candidates = []
        rejected_count = 0
        
        for symbol in symbols_to_scan:
            if symbol not in klines_map:
                continue
            
            ohlcv = klines_map[symbol]
            ticker_data = ticker_map[symbol]
            
            # 1. UNIFIED MOBILITY CHECK (SEUL FILTRE)
            mobility_score, mobility_reason = unified_mobility_check(
                ohlcv_60=ohlcv,
                hour_utc=hour_utc,
                btc_atr_pct=btc_atr_pct
            )
            
            # 2. Si mobility = 0 → Skip immédiatement
            if mobility_score == 0:
                logger.debug(f"⏭️ {symbol} rejected: {mobility_reason}")
                rejected_count += 1
                continue
            
            # 3. Calculer le reste du score seulement si mobile
            result = calculate_elite_score_light(
                symbol=symbol,
                ohlcv_60=ohlcv,
                ticker_data=ticker_data,
                hour_utc=hour_utc,
                mobility_score=mobility_score,
                mobility_reason=mobility_reason
            )
            
            if result['is_elite']:
                # ELITE CANDIDATE: store full data for AI selection
                elite_candidates.append({
                    'symbol': symbol,
                    'score': result['elite_score'],
                    'direction': result['metadata']['direction'],
                    'rsi': result['rsi'],
                    'vol_surge': result['vol_surge'],
                    'history': result['history']
                })
        
        # Sort by score
        elite_candidates.sort(key=lambda x: x['score'], reverse=True)
        
        # 🏛️ EMPIRE V16.7.8: ENSEMBLE SELECTION
        # Haiku chooses the best trades to fill available slots
        all_positions = engine.persistence.load_positions()
        current_open_count = len(all_positions)
        empty_slots = max(0, TradingConfig.MAX_OPEN_TRADES - current_open_count)
        final_picks = []
        if elite_candidates and empty_slots > 0:
            logger.info(f"🧠 Asking Haiku to pick {empty_slots} trades among {len(elite_candidates[:12])} elites...")
            haiku_result = engine.claude.pick_best_trades(elite_candidates[:12], empty_slots)
            final_picks = haiku_result.get('picks', [])
            logger.info(f"🏆 Haiku Logic: {haiku_result.get('reasons')}")
        
        # Filter the candidates to process only those picked by Haiku
        to_process = [c for c in elite_candidates if c['symbol'] in final_picks]
        
        phase4_time = time.time() - score_start
        logger.info(f"🏆 Score Phase: {len(symbols_to_scan)} symbols in {phase4_time:.1f}s")
        logger.info(f"   ✅ {len(elite_candidates)} technical elites | 🧠 {len(final_picks)} AI final picks")
        
        # ========== PHASE 5: EXECUTION (8-14s) ==========
        process_start = time.time()
        opened_count = 0
        
        logger.info(f"📊 Executing {len(to_process)} AI picks. Slots: {empty_slots}")

        for cand in to_process:
            symbol = cand['symbol']
            score = cand['score']
            direction = cand['direction']
            if current_open_count >= TradingConfig.MAX_OPEN_TRADES:
                logger.info("🛑 Max trades reached (Local Counter)")
                break
            
            try:
                # Préparer les données du scanner pour le trading_engine
                # Récupérer les vraies données du scanner
                ohlcv = klines_map[symbol]
                closes = [c[4] for c in ohlcv]
                current_price = closes[-1]
                
                # Calculer ATR pour TP/SL
                highs = [c[2] for c in ohlcv[-20:]]
                lows = [c[3] for c in ohlcv[-20:]]
                true_ranges = []
                for i in range(-20, 0):
                    tr = max(
                        highs[i] - lows[i],
                        abs(highs[i] - closes[i-1]) if i > -20 else 0,
                        abs(lows[i] - closes[i-1]) if i > -20 else 0
                    )
                    true_ranges.append(tr)
                atr = sum(true_ranges) / len(true_ranges)
                
                # TP/SL basés sur ATR (V16) + MIN_TP_PCT floor
                tp_dist = max(atr * TradingConfig.TP_MULTIPLIER, current_price * TradingConfig.MIN_TP_PCT)
                
                if direction == 'LONG':
                    tp_price = current_price + tp_dist
                    sl_price = current_price - (atr * TradingConfig.SL_MULTIPLIER)
                else:
                    tp_price = current_price - tp_dist
                    sl_price = current_price + (atr * TradingConfig.SL_MULTIPLIER)
                
                # Volume ratio
                volumes = [c[5] for c in ohlcv]
                vol_current = volumes[-1]
                vol_avg_20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else vol_current
                vol_ratio = vol_current / vol_avg_20 if vol_avg_20 > 0 else 1.0
                
                scanner_data = {
                    'direction': direction,
                    'elite_score': score,
                    'current_price': current_price,
                    'atr': atr,
                    'tp_price': tp_price,
                    'sl_price': sl_price,
                    'vol_ratio': vol_ratio
                }
                
                result = engine.run_cycle(symbol, scanner_data, positions=all_positions)
                status = result.get('status', '')
                
                if 'OPEN' in status:
                    opened_count += 1
                    current_open_count += 1
                    logger.info(f"✅ OPENED {symbol} (score: {score:.0f}, {direction})")
                else:
                    skipped_count += 1
                    
            except Exception as e:
                logger.error(f"❌ {symbol}: {e}")
                skipped_count += 1
        
        phase5_time = time.time() - process_start

        if closer_function_name and not event.get('manual') and opened_count > 0:
            try:
                lambda_client.invoke(
                    FunctionName=closer_function_name,
                    InvocationType='Event',
                    Payload=json.dumps({'source': 'scanner_post_open', 'manual': False, 'single_pass': True})
                )
            except Exception as invoke_err:
                logger.warning(f"[WARN] Failed to invoke closer post-open: {invoke_err}")
        
        # ========== PHASE 6: SAVE STATE (14-15s) ==========
        engine.persistence.save_risk_state(engine.risk_manager.get_state())
        
        total_duration = time.time() - start_time
        
        # ========== RESPONSE ==========
        response = {
            'lambda': 'ULTRA_FAST_SCANNER',
            'duration_seconds': round(total_duration, 2),
            'phases': {
                'init': round(phase1_time, 2),
                'server_filter': round(phase2_time, 2),
                'fetch_klines': round(phase3_time, 2),
                'calculate_scores': round(phase4_time, 2),
                'process_elites': round(phase5_time, 2)
            },
            'total_filtered': len(symbols_to_scan),
            'elites_found': len(elite_candidates),
            'top_50_processed': len(top_50),
            'positions_opened': opened_count,
            'positions_skipped': skipped_count,
            'total_open': existing_count + opened_count,
            'top_5': [s for s, _, _ in top_50[:5]],
            'target_met': total_duration < 15.0
        }
        
        logger.info("=" * 80)
        logger.info(f"✅ COMPLETE in {total_duration:.1f}s (target: <15s) {'✓' if total_duration < 15 else '✗'}")
        logger.info(f"   Filter: {phase2_time:.1f}s | Klines: {phase3_time:.1f}s | Score: {phase4_time:.1f}s | Process: {phase5_time:.1f}s")
        logger.info(f"   {opened_count} opened, {skipped_count} skipped")
        logger.info("=" * 80)
        
        return {'statusCode': 200, 'body': json.dumps(response)}
        
    except Exception as e:
        logger.error(f"❌ LAMBDA 1 FATAL ERROR: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'lambda': 'SCANNER'
            })
        }
