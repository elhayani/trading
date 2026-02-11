import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    # 🛠️ Fix: RSI division by zero (Audit #V10.3)
    # If loss is 0, price only went up or stayed flat -> RSI 100
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)  # Audit Fix: Neutral (50), not overbought (100)

def calculate_sma(series, period):
    return series.rolling(window=period).mean()

def calculate_atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def analyze_market(ohlcv_data):
    """
    Analyzes market data using plain pandas/numpy (no pandas_ta/numba/llvmlite).
    """
    if not ohlcv_data or len(ohlcv_data) == 0:
        return {
            'indicators': {
                'rsi': 50.0, 'sma_50': 0.0, 'sma_200': 0.0, 'atr': 0.0, 
                'long_term_trend': 'NEUTRAL', 'signal_score': 0
            }, 
            # 'patterns': [],  # REMOVED
            'current_price': 0.0,
            'market_context': 'NO_DATA'
        }

    # Convert to DataFrame
    df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    
    # Audit Fix: Block trades on insufficient data for valid SMA_200 (250 for safety)
    if len(df) < 250:
        logger.warning(f"🚫 Insufficient data ({len(df)} candles < 250): Blocking trade.")
        return {
            'indicators': {
                'rsi': 50.0, 'sma_50': 0.0, 'sma_200': 0.0, 'atr': 0.0,
                'long_term_trend': 'NEUTRAL', 'signal_score': 0
            },
            'current_price': float(df.iloc[-1]['close']) if len(df) > 0 else 0.0,
            'market_context': 'INSUFFICIENT_DATA'
        }
    
    # Calculate Indicators
    # patterns = []  # REMOVED
    df['RSI'] = calculate_rsi(df['close'], period=14)
    df['SMA_50'] = calculate_sma(df['close'], period=50)
    df['SMA_200'] = calculate_sma(df['close'], period=200)
    df['ATR'] = calculate_atr(df['high'], df['low'], df['close'], period=14)
    
    # Latest values
    current = df.iloc[-1]
    
    indicators = {
        'rsi': 50.0,
        'sma_50': 0.0,
        'sma_200': 0.0,
        'atr': 0.0,
        'long_term_trend': 'NEUTRAL'
    }

    try:
        indicators.update({
            'rsi': float(current['RSI']) if not pd.isna(current['RSI']) else 50.0,
            'sma_50': float(current['SMA_50']) if not pd.isna(current['SMA_50']) else 0.0,
            'sma_200': float(current['SMA_200']) if not pd.isna(current['SMA_200']) else 0.0,
            'atr': float(current['ATR']) if not pd.isna(current['ATR']) else 0.0,
            'long_term_trend': 'BULLISH' if current['close'] > current['SMA_200'] and not pd.isna(current['SMA_200']) else 'BEARISH'
        })
    except Exception as e:
        logger.warning(f"⚠️ Error mapping indicators: {e}")
    
    # Signal Score Calculation (Level 2: Technical Validation)
    # 0-100 score based on RSI, Trend, and Patterns
    score = 0
    rsi_val = indicators['rsi']
    
    # RSI Component (Max 50 pts) - Bidirectional scoring (Audit Fix)
    if rsi_val < 30: score += 50      # Strong oversold (Long signal)
    elif rsi_val < 40: score += 40    # Moderate oversold
    elif rsi_val < 50: score += 20    # Mild oversold
    elif rsi_val > 80: score += 50    # Strong overbought (Short signal)
    elif rsi_val > 68: score += 40    # Moderate overbought (V10.9.1)
    
    # Trend Component (Max 30 pts)
    if indicators['long_term_trend'] == 'BULLISH':
        score += 30
    elif indicators['long_term_trend'] == 'BEARISH' and rsi_val > 68:
        score += 25  # Bearish trend + overbought = strong short
        
    indicators['signal_score'] = score
    
    # Signal Type Detection (Audit Fix V11: Bidirectional)
    signal_type = 'NEUTRAL'
    LONG_THRESHOLD = 60
    SHORT_THRESHOLD = 55
    
    if rsi_val < 40 and score >= LONG_THRESHOLD:
        signal_type = 'LONG'
    elif rsi_val > 68 and score >= SHORT_THRESHOLD:
        signal_type = 'SHORT'
    
    return {
        'indicators': indicators,
        # 'patterns': patterns, # REMOVED
        'current_price': float(current['close']),
        'market_context': f"RSI={indicators['rsi']:.1f} | Trend={indicators['long_term_trend']} | Score={score}",
        'signal_type': signal_type,
        'score': score,                 # Audit Fix: Exposed at root
        'atr': indicators['atr'],       # Audit Fix: Exposed for decision_engine
        'price': float(current['close']) # Audit Fix: Alias for compatibility
    }
