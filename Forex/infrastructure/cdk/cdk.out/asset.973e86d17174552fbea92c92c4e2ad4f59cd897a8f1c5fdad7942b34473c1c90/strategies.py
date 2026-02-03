import pandas as pd
import numpy as np

class ForexStrategies:
    @staticmethod
    def calculate_indicators(df, strategy_type):
        """
        Calcule les indicateurs nécessaires (Pure Pandas implementation)
        """
        df = df.copy()
        
        # --- Helpers ---
        def calculate_rsi(series, period=14):
            # EMA Smoothing (Wilder's Smoothing equivalent-ish)
            delta = series.diff()
            up = delta.clip(lower=0)
            down = -1 * delta.clip(upper=0)
            ema_up = up.ewm(com=period-1, adjust=False).mean()
            ema_down = down.ewm(com=period-1, adjust=False).mean()
            rs = ema_up / ema_down
            return 100 - (100 / (1 + rs))
            
        def calculate_atr(high, low, close, period=14):
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            return tr.rolling(window=period).mean()
            
        # --- ATR (Toujours nécessaire) ---
        df['ATR'] = calculate_atr(df['high'], df['low'], df['close'], 14)
        
        # --- Strategy Specifics ---
        if strategy_type == 'TREND_PULLBACK':
            df['SMA_200'] = df['close'].rolling(window=200).mean()
            df['RSI'] = calculate_rsi(df['close'], 14)
            
        elif strategy_type == 'BOLLINGER_BREAKOUT':
            # BB 20, 2.0
            sma20 = df['close'].rolling(window=20).mean()
            std20 = df['close'].rolling(window=20).std()
            df['BBU'] = sma20 + (std20 * 2.0)
            df['BBL'] = sma20 - (std20 * 2.0)
            
        return df

    @staticmethod
    def check_signal(pair, df, config):
        """
        Analyse la dernière bougie pour générer un signal
        """
        # Ensure we have enough data (200 + buffer)
        if len(df) < 201:
            return None
            
        current = df.iloc[-1]
        prev = df.iloc[-2]
        params = config['params']
        strategy = config['strategy']
        
        signal = None
        entry_price = float(current['close'])
        stop_loss = 0.0
        take_profit = 0.0
        
        # Handle NaN ATR
        if pd.isna(current['ATR']):
            return None
        
        atr = float(current['ATR'])
        
        # --- ROLLOVER FILTER (22:00-00:00 UTC) ---
        # Spreads widen significantly, avoid trading
        try:
            # Assuming current.name is timestamp or string convertible to timestamp
            # yfinance index is usually tz-aware datetime
            ts = pd.to_datetime(current.name)
            if ts.hour == 23 or ts.hour == 0: 
                # Block 23:00-01:00 roughly
                return None
        except:
            pass # Ignore if timestamp parsing fails
        
        # --- STRATÉGIE 1: TREND PULLBACK (EURUSD, GBPUSD) ---
        if strategy == 'TREND_PULLBACK':
            if 'SMA_200' not in df.columns or pd.isna(current['SMA_200']):
                return None
            
            # Condition 1: Tendance Haussière (Prix > SMA 200)
            if current['close'] > current['SMA_200']:
                # Condition 2: Signal Pullback (RSI < Seuil)
                if current['RSI'] < params['rsi_oversold']:
                    if atr > 0.0005: 
                        signal = 'LONG'
                        sl_dist = atr * params['sl_atr_mult']
                        tp_dist = atr * params['tp_atr_mult']
                        stop_loss = entry_price - sl_dist
                        take_profit = entry_price + tp_dist

        # --- STRATÉGIE 2: BOLLINGER BREAKOUT (USDJPY) ---
        elif strategy == 'BOLLINGER_BREAKOUT':
            if 'BBU' not in df.columns or pd.isna(current['BBU']):
                return None
                
            # Breakout HAUSSIER
            if current['close'] > current['BBU'] and prev['close'] <= prev['BBU']:
                signal = 'LONG'
                sl_dist = atr * params['sl_atr_mult']
                tp_dist = atr * params['tp_atr_mult']
                stop_loss = entry_price - sl_dist
                take_profit = entry_price + tp_dist
                
            # Breakout BAISSIER
            elif current['close'] < current['BBL'] and prev['close'] >= prev['BBL']:
                signal = 'SHORT'
                sl_dist = atr * params['sl_atr_mult']
                tp_dist = atr * params['tp_atr_mult']
                stop_loss = entry_price + sl_dist
                take_profit = entry_price - tp_dist
        
        if signal:
            return {
                'pair': pair,
                'signal': signal,
                'strategy': strategy,
                'entry': entry_price,
                'sl': stop_loss,
                'tp': take_profit,
                'atr': atr,
                'timestamp': str(current.name)
            }
            
        return None
