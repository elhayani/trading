import pandas as pd
import numpy as np
import logging
from typing import Tuple, Dict, List

# Absolute imports (Critique #1 New)
import config
from config import TradingConfig
import models
from models import AssetClass

logger = logging.getLogger(__name__)

def classify_asset(symbol: str) -> AssetClass:
    s = symbol.upper().replace('/', '')
    # Elite Tech Stocks: TSLA, NVDA (treated as indices for volatility profile)
    if any(k in s for k in ['TSLA', 'NVDA', 'SPX', 'NDX', 'US30', 'GSPC', 'IXIC', 'GER40', 'FTSE', 'DAX', 'VIX']): 
        return AssetClass.INDICES
    # Commodities & Energy: PAXG (Gold), WTI (Oil), etc.
    if any(k in s for k in ['PAXG', 'XAG', 'XAU', 'OIL', 'WTI', 'USOIL', 'GOLD', 'SILVER', 'BRENT', 'XPT', 'XPD']): 
        return AssetClass.COMMODITIES
    forex_chars = ['EUR', 'GBP', 'AUD', 'JPY', 'CHF', 'CAD', 'SGD', 'NZD']
    if any(k in s for k in forex_chars) and 'USDT' not in s:
        return AssetClass.FOREX
    return AssetClass.CRYPTO

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)

def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calculate_vwap(df: pd.DataFrame, window: int = 24) -> pd.Series:
    """
    Rolling VWAP over the last `window` candles (default 24 = 1 day on 1H TF).

    The original cumsum() accumulated from candle #1 (up to 500 candles / 20 days).
    For tokens that pumped at listing this produced dist_vwap of ±30-90% — far beyond
    the ±20% filter thresholds, making every trade impossible. A 24h rolling window
    reflects the actual intraday supply/demand balance traders use.
    """
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    tp_vol = typical_price * df['volume']
    rolling_tp_vol = tp_vol.rolling(window=window, min_periods=1).sum()
    rolling_vol    = df['volume'].rolling(window=window, min_periods=1).sum()
    vwap = rolling_tp_vol / rolling_vol.replace(0, np.nan)
    return vwap.fillna(typical_price)

def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    ADX (Average Directional Index) + DI+ / DI-
    Returns: (ADX, DI+, DI-)
    """
    # True Range
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Directional Movement
    up_move = high - high.shift()
    down_move = low.shift() - low
    
    plus_dm = pd.Series(0.0, index=high.index)
    minus_dm = pd.Series(0.0, index=high.index)
    
    # +DM et -DM
    # where condition: if up_move > down_move and up_move > 0 -> up_move, else 0
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    # Convert numpy result back to Series for rolling ops
    plus_dm = pd.Series(plus_dm, index=high.index)
    minus_dm = pd.Series(minus_dm, index=high.index)
    
    # ATR (pour normalisation)
    atr = tr.rolling(window=period).mean()
    
    # DI+ et DI-
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    
    # DX (Directional Index)
    # Avoid division by zero
    sum_di = plus_di + minus_di
    dx = 100 * (plus_di - minus_di).abs() / sum_di
    dx = dx.replace([np.inf, -np.inf], 0).fillna(0)
    
    # ADX (moyenne lissée du DX)
    adx = dx.rolling(window=period).mean()
    
    return adx.fillna(0), plus_di.fillna(0), minus_di.fillna(0)

def detect_volatility_spike(ohlcv: List, atr_current: float, atr_avg: float, asset_class: AssetClass = AssetClass.CRYPTO) -> Tuple[bool, str]:
    if len(ohlcv) < 10: return False, "OK"
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['close'] = df['close'].astype(float)

    # Fix C: Use the LAST COMPLETED candle (iloc[-2] vs iloc[-3]).
    # iloc[-1] is the live in-progress candle — a single large trade at candle open
    # makes it look like a spike that will fully settle by close. This caused false
    # positives: BANK 3.25%, PIPPIN -5.74%, TAKE 5.36% were blocked below the 8% threshold
    # because the live candle open-to-now move was measured instead of the true 1h move.
    if len(df) >= 3:
        last_change_1h = (df.iloc[-2]['close'] - df.iloc[-3]['close']) / df.iloc[-3]['close']
    else:
        last_change_1h = (df.iloc[-1]['close'] - df.iloc[-2]['close']) / df.iloc[-2]['close']

    atr_ratio = atr_current / atr_avg if atr_avg > 0 else 1.0

    thresholds = {
        AssetClass.CRYPTO:      {'1h': 0.08, 'atr': 4.0},
        AssetClass.FOREX:       {'1h': 0.015, 'atr': 3.0},
        AssetClass.INDICES:     {'1h': 0.030, 'atr': 3.5},
        AssetClass.COMMODITIES: {'1h': 0.040, 'atr': 3.5}
    }
    cfg = thresholds.get(asset_class, thresholds[AssetClass.CRYPTO])
    if abs(last_change_1h) > cfg['1h']: return True, f"PRICE_SPIKE_1H_{last_change_1h:.2%}"
    if atr_ratio > cfg['atr']: return True, f"ATR_SPIKE_{atr_ratio:.1f}x"
    return False, "OK"

def analyze_market(ohlcv: List, symbol: str = "TEST", asset_class: AssetClass = AssetClass.CRYPTO, scanner_score: int = 0, volume_24h_usdt: float = 0) -> Dict:
    if not ohlcv or len(ohlcv) < TradingConfig.MIN_REQUIRED_CANDLES:
        logger.error(f"[ERROR] INSUFFICIENT DATA for {symbol}")
        raise ValueError(f"Need {TradingConfig.MIN_REQUIRED_CANDLES} candles.")

    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Conversions numériques
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # ========== CALCUL DES INDICATEURS ==========
    df['RSI'] = calculate_rsi(df['close'])
    df['SMA_50'] = calculate_sma(df['close'], 50)
    df['SMA_200'] = calculate_sma(df['close'], 200)
    df['ATR'] = calculate_atr(df['high'], df['low'], df['close'])
    
    # 🆕 VWAP
    df['VWAP'] = calculate_vwap(df)
    
    # 🆕 ADX + DI
    df['ADX'], df['DI_PLUS'], df['DI_MINUS'] = calculate_adx(df['high'], df['low'], df['close'])
    
    # 🆕 Volume Ratio (volume actuel vs moyenne 20 périodes)
    df['Volume_SMA'] = df['volume'].rolling(20).mean()
    
    current = df.iloc[-1]
    current_atr = float(current['ATR']) if not pd.isna(current['ATR']) else 0.0
    avg_atr = float(df.iloc[-30:]['ATR'].mean()) if len(df) >= 30 else current_atr
    
    # 🆕 ATR en pourcentage du prix
    atr_perc = (current_atr / current['close']) * 100 if current['close'] > 0 else 0.0
    
    # 🆕 Distance au VWAP
    vwap_val = float(current['VWAP']) if not pd.isna(current['VWAP']) else float(current['close'])
    dist_vwap = ((current['close'] - vwap_val) / vwap_val) * 100 if vwap_val > 0 else 0.0
    
    # 🆕 ADX & DI
    adx_val = float(current['ADX']) if not pd.isna(current['ADX']) else 0.0
    di_plus = float(current['DI_PLUS']) if not pd.isna(current['DI_PLUS']) else 0.0
    di_minus = float(current['DI_MINUS']) if not pd.isna(current['DI_MINUS']) else 0.0
    
    # 🏛️ EMPIRE V15.8: Volume Ratio (Disabled - too volatile for scalping)
    # Using absolute 24h volume instead from scanner
    vol_ratio = 1.0
    
    # Volatility Spike Detection
    is_spike, spike_reason = detect_volatility_spike(ohlcv, current_atr, avg_atr, asset_class)
    if is_spike:
        return {
            'indicators': {'atr': current_atr, 'atr_perc': atr_perc, 'adx': adx_val, 'vwap': vwap_val},
            'current_price': float(current['close']),
            'market_context': f'VOLATILITY_SPIKE: {spike_reason}',
            'signal_type': 'NEUTRAL', 'score': 0, 
            'atr': current_atr, 'atr_perc': atr_perc,
            'dist_vwap': dist_vwap,
            'price': float(current['close'])
        }

    rsi_val = float(current['RSI'])
    trend = 'BULLISH' if current['close'] > current['SMA_200'] else 'BEARISH'
    
    # ========== SCORING AMÉLIORÉ ==========
    base_config = {
        AssetClass.CRYPTO:      {'buy': 32, 'sell': 65, 'min_score': TradingConfig.MIN_TECHNICAL_SCORE_CRYPTO},
        AssetClass.FOREX:       {'buy': 35, 'sell': 62, 'min_score': TradingConfig.MIN_TECHNICAL_SCORE_FOREX},
        AssetClass.INDICES:     {'buy': 35, 'sell': 60, 'min_score': TradingConfig.MIN_TECHNICAL_SCORE_INDICES},
        AssetClass.COMMODITIES: {'buy': 35, 'sell': 68, 'min_score': TradingConfig.MIN_TECHNICAL_SCORE_COMMODITIES}
    }
    cfg = base_config.get(asset_class, base_config[AssetClass.CRYPTO])
    
    score = 0
    signal_type = 'NEUTRAL'
    _paths_active = 0   # counts independent signal paths that fired

    # =========================================================
    # SCORING V2 — Multi-path signal architecture
    #
    # Three independent paths can establish a direction. Each that
    # fires increments _paths_active for the convergence bonus.
    # This allows scanner-sourced micro-caps (Vol 0.3-1.1x) to pass
    # the min_score bar when 2+ independent signals agree, without
    # lowering quality for large-cap setups.
    # =========================================================

    # --- PATH 1: RSI (primary gate, highest conviction) ---
    if rsi_val <= cfg['buy']:
        score += 40; signal_type = 'LONG';  _paths_active += 1
    elif rsi_val >= cfg['sell']:
        score += 40; signal_type = 'SHORT'; _paths_active += 1
    elif rsi_val < 45:
        score += 12; signal_type = 'LONG'   # mild bearish-to-neutral tilt
    elif rsi_val > 55:
        score += 12; signal_type = 'SHORT'  # mild bullish-to-neutral tilt

    # --- PATH 2: ADX trend strength ---
    if adx_val > 25:
        score += 20; _paths_active += 1
        if signal_type == 'NEUTRAL':
            signal_type = 'LONG' if di_plus > di_minus else 'SHORT'
        if   signal_type == 'LONG'  and di_plus  > di_minus: score += 10
        elif signal_type == 'SHORT' and di_minus  > di_plus:  score += 10
    elif adx_val > 20:
        score += 10
        if signal_type == 'NEUTRAL':
            signal_type = 'LONG' if di_plus > di_minus else 'SHORT'

    # --- PATH 3: VWAP momentum (price breaking away from session VWAP) ---
    if dist_vwap > 1.5 and signal_type != 'SHORT':
        score += 10; _paths_active += 1
        if signal_type == 'NEUTRAL': signal_type = 'LONG'
    elif dist_vwap < -1.5 and signal_type != 'LONG':
        score += 10; _paths_active += 1
        if signal_type == 'NEUTRAL': signal_type = 'SHORT'

    # --- VWAP alignment bonus ---
    if   signal_type == 'LONG'  and dist_vwap > 0:  score += 10
    elif signal_type == 'SHORT' and dist_vwap < 0:   score += 10

    # --- VWAP counter-directional penalty (threshold -3% not -2% to avoid over-blocking dips) ---
    if   signal_type == 'LONG'  and dist_vwap < -3:  score -= 10
    elif signal_type == 'SHORT' and dist_vwap > 2.0:  score -= 10 # Tightened to 2.0% (User req)

    # 🏛️ EMPIRE V15.9: TIGHTENED BLOCKS (Anti-Rocket Protection)
    if signal_type == 'SHORT' and dist_vwap > 3.0:
        logger.warning(f"🚫 [BLOCKED_VWAP] {symbol} - SHORT with price {dist_vwap:+.1f}% above VWAP | Vol={vol_ratio:.1f}x")
        return {
            'signal_type': 'NEUTRAL', 'score': 0, 'price': float(current['close']),
            'market_context': f'BLOCKED_VWAP: Price {dist_vwap:+.1f}% above VWAP',
            'vol_ratio': vol_ratio
        }
    if signal_type == 'LONG' and dist_vwap < -3.0:
        logger.warning(f"🚫 [BLOCKED_VWAP] {symbol} - LONG with price {dist_vwap:+.1f}% below VWAP | Vol={vol_ratio:.1f}x")
        return {
            'signal_type': 'NEUTRAL', 'score': 0, 'price': float(current['close']),
            'market_context': f'BLOCKED_VWAP: Price {dist_vwap:+.1f}% below VWAP',
            'vol_ratio': vol_ratio
        }

    if signal_type == 'SHORT':
         if adx_val > 45 and di_plus > di_minus:
             logger.warning(f"🚫 [BLOCKED_ADX] {symbol} - SHORT vs ADX={adx_val:.1f} ROCKET_UPTREND | Vol={vol_ratio:.1f}x")
             return {
                 'signal_type': 'NEUTRAL', 'score': 0, 'price': float(current['close']),
                 'market_context': f'BLOCKED_ROCKET_TREND: ADX={adx_val:.1f} > 50',
                 'vol_ratio': vol_ratio
             }
         elif adx_val > 25 and di_plus > di_minus:
             penalty = 30 if adx_val > 40 else 15
             score -= penalty
             logger.info(f"⚠️ [PENALTY_ADX] {symbol} - SHORT vs ADX={adx_val:.1f} uptrend: -{penalty} pts")
             
    elif signal_type == 'LONG':
         if adx_val > 45 and di_minus > di_plus:
             logger.warning(f"🚫 [BLOCKED_ADX] {symbol} - LONG vs ADX={adx_val:.1f} CRASH_DOWNTREND | Vol={vol_ratio:.1f}x")
             return {
                 'signal_type': 'NEUTRAL', 'score': 0, 'price': float(current['close']),
                 'market_context': f'BLOCKED_ROCKET_TREND: ADX={adx_val:.1f} > 50',
                 'vol_ratio': vol_ratio
             }
         elif adx_val > 25 and di_minus > di_plus:
             penalty = 30 if adx_val > 40 else 15
             score -= penalty
             logger.info(f"⚠️ [PENALTY_ADX] {symbol} - LONG vs ADX={adx_val:.1f} downtrend: -{penalty} pts")

    # --- Volume surge bonus ---
    if   vol_ratio > 1.5:  score += 15
    elif vol_ratio > 1.2:  score += 10

    # --- RSI extreme conviction bonus ---
    if rsi_val < 25 or rsi_val > 75:
        score += 12

    # --- Multi-path convergence bonus ---
    # When 2+ independent TA paths agree (e.g. RSI oversold + ADX bullish trend),
    # add +12 as confirmation premium. The scanner's 7-metric pre-filter already
    # validates setup quality; this rewards genuine signal convergence.
    if _paths_active >= 2:
        score += 12

    # --- Scanner pre-score bonus (raised 8→15) ---
    # V15 scanner runs orderbook, delta, taker_buy, momentum, whale, volatility,
    # and POC analysis. A score ≥60 there represents strong multi-metric consensus.
    # Weight raised from 8 to 15 to properly reflect that pre-qualification.
    if scanner_score >= 60:
        score += 15

    score = min(score, 100)  # hard cap

    # --- Validation finale ---
    if score < cfg['min_score']:
        signal_type = 'NEUTRAL'
    return {
        'indicators': {
            'rsi': rsi_val,
            'atr': current_atr,
            'atr_perc': atr_perc,
            'adx': adx_val,
            'di_plus': di_plus,
            'di_minus': di_minus,
            'vwap': vwap_val,
            'dist_vwap': dist_vwap,
            'vol_ratio': vol_ratio
        },
        'current_price': float(current['close']),
        'market_context': f"RSI={rsi_val:.1f} | ADX={adx_val:.1f} | VWAP{dist_vwap:+.1f}% | Vol={vol_ratio:.1f}x | Trend={trend}",
        'signal_type': signal_type,
        'score': score,
        'vol_ratio': vol_ratio,
        'volume_24h_usdt': volume_24h_usdt,
        'atr': current_atr,
        'atr_perc': atr_perc,
        'dist_vwap': dist_vwap,
        'rsi': rsi_val,
        'adx': adx_val,
        'price': float(current['close'])
    }

def mobility_score(ohlcv_1min: List) -> tuple[int, str]:
    """
    Pre-filter: évalue si l'actif EST EN MOUVEMENT maintenant.
    Retourne (score, raison_skip)
    Score 0 = skip, 100 = candidat parfait
    """
    if len(ohlcv_1min) < 25:
        return 0, 'INSUFFICIENT_DATA'
    
    import pandas as pd
    from config import TradingConfig
    
    df = pd.DataFrame(ohlcv_1min, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Conversions numériques
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    score = 0
    
    # 1. ATR récent (volatilité)
    atr_10 = calculate_atr(df['high'], df['low'], df['close'], period=10).iloc[-1]
    atr_pct = (atr_10 / df['close'].iloc[-1]) * 100
    
    if atr_pct >= 0.50:
        score += 40  # Très volatile ✅
    elif atr_pct >= 0.25:
        score += 20  # Acceptable
    else:
        return 0, 'FLAT'  # Skip immédiat
    
    # 2. Volume surge (accélération volume)
    vol_recent = df['volume'].iloc[-3:].mean()
    vol_avg = df['volume'].iloc[-23:-3].mean()
    vol_ratio = vol_recent / vol_avg if vol_avg > 0 else 0
    
    if vol_ratio >= 2.0:
        score += 35  # Explosion de volume ✅
    elif vol_ratio >= 1.3:
        score += 15  # Volume correct
    else:
        return 0, 'NO_VOLUME'  # Skip immédiat
    
    # 3. Price thrust (amplitude mouvement)
    thrust = abs(df['close'].iloc[-1] - df['close'].iloc[-6]) / df['close'].iloc[-6] * 100
    
    if thrust >= 0.50:
        score += 25  # Mouvement fort ✅
    elif thrust >= 0.20:
        score += 10  # Mouvement présent
    else:
        return 0, 'NO_THRUST'  # Skip immédiat
    
    return score, 'OK'

def analyze_momentum(ohlcv_1min: List, symbol: str = "TEST") -> Dict:
    """
    Momentum scanner sur bougies 1 minute.
    Signal LONG  : EMA5 croise au-dessus EMA13 + volume surge + prix en hausse
    Signal SHORT : EMA5 croise en-dessous EMA13 + volume surge + prix en baisse
    """
    import pandas as pd
    from config import TradingConfig
    
    # 1. Charger les ohlcv_1min dans un DataFrame
    if len(ohlcv_1min) < 30:
        return {
            'signal_type': 'NEUTRAL',
            'score': 0,
            'price': 0,
            'atr': 0,
            'atr_pct': 0,
            'tp_price': 0,
            'sl_price': 0,
            'tp_pct': 0,
            'sl_pct': 0,
            'volume_ratio': 0,
            'ema_fast': 0,
            'ema_slow': 0,
            'price_change_3': 0,
            'blocked': False
        }
    
    df = pd.DataFrame(ohlcv_1min, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Conversions numériques
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 2. Calculer EMA_FAST (5) et EMA_SLOW (13)
    df['ema_fast'] = df['close'].ewm(span=TradingConfig.EMA_FAST).mean()
    df['ema_slow'] = df['close'].ewm(span=TradingConfig.EMA_SLOW).mean()
    
    # 3. Calculer ATR sur 14 périodes
    atr_values = calculate_atr(df['high'], df['low'], df['close'], period=14)
    df['atr'] = atr_values
    
    # 4. Calculer volume_ratio
    volume_avg_20 = df['volume'].rolling(20).mean().iloc[-1]
    volume_current = df['volume'].iloc[-1]
    volume_ratio = volume_current / volume_avg_20 if volume_avg_20 > 0 else 1.0
    
    # 5. Détecter le croisement EMA
    ema_fast_current = df['ema_fast'].iloc[-1]
    ema_fast_prev = df['ema_fast'].iloc[-2]
    ema_slow_current = df['ema_slow'].iloc[-1]
    ema_slow_prev = df['ema_slow'].iloc[-2]
    
    crossover_up = ema_fast_current > ema_slow_current and ema_fast_prev <= ema_slow_prev
    crossover_down = ema_fast_current < ema_slow_current and ema_fast_prev >= ema_slow_prev
    
    # 6. Calculer le score (0-100)
    score = 0
    signal = 'NEUTRAL'
    
    if crossover_up:
        signal = 'LONG'
        score += 40
    elif crossover_down:
        signal = 'SHORT'
        score += 40
    else:
        # Pas de croisement = pas de signal
        return {
            'signal_type': 'NEUTRAL',
            'score': 0,
            'price': float(df['close'].iloc[-1]),
            'atr': float(df['atr'].iloc[-1]),
            'atr_pct': 0,
            'tp_price': 0,
            'sl_price': 0,
            'tp_pct': 0,
            'sl_pct': 0,
            'volume_ratio': volume_ratio,
            'ema_fast': float(ema_fast_current),
            'ema_slow': float(ema_slow_current),
            'price_change_3': 0,
            'blocked': False
        }
    
    # Confirmation momentum prix
    price_change_3 = (df['close'].iloc[-1] - df['close'].iloc[-4]) / df['close'].iloc[-4] * 100
    if signal == 'LONG' and price_change_3 > 0:
        score += 20
    elif signal == 'SHORT' and price_change_3 < 0:
        score += 20
    
    # Volume confirmation (obligatoire)
    if volume_ratio >= 1.5:
        score += 25
    elif volume_ratio >= 1.2:
        score += 15
    elif volume_ratio < 1.0:
        score -= 20  # volume faible = faux signal probable
    
    # ATR minimum (le marché doit bouger assez pour couvrir les frais)
    atr_current = df['atr'].iloc[-1]
    close_current = df['close'].iloc[-1]
    atr_pct = atr_current / close_current * 100
    
    if atr_pct >= 0.15:
        score += 15
    elif atr_pct < 0.10:
        # trop plat, frais > gain
        return {
            'signal_type': 'NEUTRAL',
            'score': 0,
            'price': float(close_current),
            'atr': float(atr_current),
            'atr_pct': atr_pct,
            'tp_price': 0,
            'sl_price': 0,
            'tp_pct': 0,
            'sl_pct': 0,
            'volume_ratio': volume_ratio,
            'ema_fast': float(ema_fast_current),
            'ema_slow': float(ema_slow_current),
            'price_change_3': price_change_3,
            'blocked': False
        }
    
    # 7. Calculer TP et SL
    if signal == 'LONG':
        tp_price = close_current * (1 + atr_pct/100 * TradingConfig.TP_MULTIPLIER)
        sl_price = close_current * (1 - atr_pct/100 * TradingConfig.SL_MULTIPLIER)
    else:  # SHORT
        tp_price = close_current * (1 - atr_pct/100 * TradingConfig.TP_MULTIPLIER)
        sl_price = close_current * (1 + atr_pct/100 * TradingConfig.SL_MULTIPLIER)
    
    # 8. Retourner le résultat
    return {
        'signal_type': signal,
        'score': score,
        'price': float(close_current),
        'atr': float(atr_current),
        'atr_pct': atr_pct,
        'tp_price': float(tp_price),
        'sl_price': float(sl_price),
        'tp_pct': atr_pct * TradingConfig.TP_MULTIPLIER,
        'sl_pct': atr_pct * TradingConfig.SL_MULTIPLIER,
        'volume_ratio': volume_ratio,
        'ema_fast': float(ema_fast_current),
        'ema_slow': float(ema_slow_current),
        'price_change_3': price_change_3,
        'volume_24h_usdt': 0,  # Sera rempli par trading_engine.py
        'blocked': False
    }
