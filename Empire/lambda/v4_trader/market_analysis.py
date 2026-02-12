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
    if any(k in s for k in ['SPX', 'NDX', 'US30', 'GSPC', 'IXIC', 'GER40', 'FTSE', 'DAX', 'VIX']): 
        return AssetClass.INDICES
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

def detect_volatility_spike(ohlcv: List, atr_current: float, atr_avg: float, asset_class: AssetClass = AssetClass.CRYPTO) -> Tuple[bool, str]:
    if len(ohlcv) < 10: return False, "OK"
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['close'] = df['close'].astype(float)
    last_change_1h = (df.iloc[-1]['close'] - df.iloc[-2]['close']) / df.iloc[-2]['close']
    atr_ratio = atr_current / atr_avg if atr_avg > 0 else 1.0
    
    thresholds = {
        AssetClass.CRYPTO:      {'1h': 0.025, 'atr': 2.5},
        AssetClass.FOREX:       {'1h': 0.005, 'atr': 2.0},
        AssetClass.INDICES:     {'1h': 0.010, 'atr': 2.2},
        AssetClass.COMMODITIES: {'1h': 0.015, 'atr': 2.3}
    }
    cfg = thresholds.get(asset_class, thresholds[AssetClass.CRYPTO])
    if abs(last_change_1h) > cfg['1h']: return True, f"PRICE_SPIKE_1H_{last_change_1h:.2%}"
    if atr_ratio > cfg['atr']: return True, f"ATR_SPIKE_{atr_ratio:.1f}x"
    return False, "OK"

def analyze_market(ohlcv: List, symbol: str = "TEST", asset_class: AssetClass = AssetClass.CRYPTO) -> Dict:
    if not ohlcv or len(ohlcv) < TradingConfig.MIN_REQUIRED_CANDLES:
        logger.error(f"[ERROR] INSUFFICIENT DATA for {symbol}")
        raise ValueError(f"Need {TradingConfig.MIN_REQUIRED_CANDLES} candles.")

    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    
    df['RSI'] = calculate_rsi(df['close'])
    df['SMA_50'] = calculate_sma(df['close'], 50)
    df['SMA_200'] = calculate_sma(df['close'], 200)
    df['ATR'] = calculate_atr(df['high'], df['low'], df['close'])
    
    current = df.iloc[-1]
    current_atr = float(current['ATR']) if not pd.isna(current['ATR']) else 0.0
    avg_atr = float(df.iloc[-30:]['ATR'].mean()) if len(df) >= 30 else current_atr
    
    is_spike, spike_reason = detect_volatility_spike(ohlcv, current_atr, avg_atr, asset_class)
    if is_spike:
        return {
            'indicators': {'atr': current_atr},
            'current_price': float(current['close']),
            'market_context': f'VOLATILITY_SPIKE: {spike_reason}',
            'signal_type': 'NEUTRAL', 'score': 0, 'atr': current_atr, 'price': float(current['close'])
        }

    rsi_val = float(current['RSI'])
    trend = 'BULLISH' if current['close'] > current['SMA_200'] else 'BEARISH'
    
    base_config = {
        AssetClass.CRYPTO:      {'buy': 32, 'sell': 65, 'min_score': TradingConfig.MIN_TECHNICAL_SCORE_CRYPTO},
        AssetClass.FOREX:       {'buy': 35, 'sell': 62, 'min_score': TradingConfig.MIN_TECHNICAL_SCORE_FOREX},
        AssetClass.INDICES:     {'buy': 35, 'sell': 60, 'min_score': TradingConfig.MIN_TECHNICAL_SCORE_INDICES},
        AssetClass.COMMODITIES: {'buy': 35, 'sell': 68, 'min_score': TradingConfig.MIN_TECHNICAL_SCORE_COMMODITIES}
    }
    cfg = base_config.get(asset_class, base_config[AssetClass.CRYPTO])
    # Simplified score logic
    score = 0
    if rsi_val <= cfg['buy']: score = 70
    elif rsi_val >= cfg['sell']: score = 70
    
    signal_type = 'NEUTRAL'
    if rsi_val <= cfg['buy'] and score >= cfg['min_score']: signal_type = 'LONG'
    elif rsi_val >= cfg['sell'] and score >= (cfg['min_score'] - 5): signal_type = 'SHORT'
    
    return {
        'indicators': {'rsi': rsi_val, 'atr': current_atr},
        'current_price': float(current['close']),
        'market_context': f"RSI={rsi_val:.1f} | Trend={trend}",
        'signal_type': signal_type, 'score': score, 'atr': current_atr, 'price': float(current['close']),
        'rsi': rsi_val  # Add to root for easy access in logging
    }
