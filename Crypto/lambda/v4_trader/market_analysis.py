import pandas_ta as ta
import pandas as pd
import numpy as np

def analyze_market(ohlcv_data):
    """
    Analyzes market data and returns indicators and patterns.
    Expects ohlcv_data as list of [timestamp, open, high, low, close, volume]
    """
    if not ohlcv_data:
        return {'indicators': {}, 'patterns': [], 'market_context': 'NO_DATA'}

    # Convert to DataFrame
    df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    
    # Calculate Indicators
    # RSI
    df['RSI'] = ta.rsi(df['close'], length=14)
    
    # SMA
    df['SMA_50'] = ta.sma(df['close'], length=50)
    df['SMA_200'] = ta.sma(df['close'], length=200)
    
    # ATR
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    # Latest values
    current = df.iloc[-1]
    
    indicators = {
        'rsi': float(current['RSI']) if not pd.isna(current['RSI']) else 50.0,
        'sma_50': float(current['SMA_50']) if not pd.isna(current['SMA_50']) else 0.0,
        'sma_200': float(current['SMA_200']) if not pd.isna(current['SMA_200']) else 0.0,
        'atr': float(current['ATR']) if not pd.isna(current['ATR']) else 0.0,
        'long_term_trend': 'BULLISH' if current['close'] > current['SMA_200'] else 'BEARISH'
    }
    
    # Simple Pattern Detection (Placeholder for more complex logic)
    patterns = []
    if current['close'] > current['SMA_50'] and df.iloc[-2]['close'] <= df.iloc[-2]['SMA_50']:
        patterns.append('GOLDEN_CROSS_SMA50_PRICE')
        
    return {
        'indicators': indicators,
        'patterns': patterns,
        'current_price': float(current['close']),
        'market_context': f"RSI={indicators['rsi']:.1f} | Trend={indicators['long_term_trend']}"
    }
