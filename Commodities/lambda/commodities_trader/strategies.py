import pandas as pd
import numpy as np

# 🏛️ V5 Golden Windows - Import du module de couloirs horaires
try:
    from trading_windows import is_within_golden_window, get_session_info
    TRADING_WINDOWS_AVAILABLE = True
except ImportError:
    TRADING_WINDOWS_AVAILABLE = False

# 🎯 V5.1 Micro-Corridors - Stratégies adaptatives par tranche horaire
try:
    from micro_corridors import (
        get_corridor_params, 
        get_current_regime, 
        calculate_adaptive_tp_sl,
        should_increase_position_size,
        is_scalping_enabled,
        get_rsi_threshold_adaptive,
        get_max_trades_in_corridor,
        get_adaptive_params,
        check_volume_veto,
        MarketRegime
    )
    MICRO_CORRIDORS_AVAILABLE = True
except ImportError:
    MICRO_CORRIDORS_AVAILABLE = False

# 🕐 V5.1 Session Phase - Horloge biologique centralisée
try:
    from trading_windows import get_session_phase
    SESSION_PHASE_AVAILABLE = True
except ImportError:
    SESSION_PHASE_AVAILABLE = False

# 🛡️ V5.1 Predictability Index - Détection des actifs erratiques (CRUCIAL pour OIL!)
try:
    from predictability_index import (
        calculate_predictability_score,
        is_asset_erratic,
        get_predictability_adjustment,
        calculate_symbol_health
    )
    PREDICTABILITY_INDEX_AVAILABLE = True
except ImportError:
    PREDICTABILITY_INDEX_AVAILABLE = False


class ForexStrategies:
    @staticmethod
    def calculate_indicators(df, strategy_type):
        """
        Calcule les indicateurs nécessaires (Pure Pandas implementation)
        V5 UPDATE: Added EMA 50 for Momentum Filter
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
        
        # --- V5 COMMON INDICATORS ---
        # EMA 50 for Momentum Filter (V5 Fortress)
        df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
        # SMA 50 for Stricter Trend Filter (Commodities V5.1)
        df['SMA_50'] = df['close'].rolling(window=50).mean()
        
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
    def check_reversal(current, direction):
        """
        V5 Reversal Trigger: Confirm candle color matches direction
        Prevents catching falling knives.
        """
        open_p = float(current['open'])
        close_p = float(current['close'])
        
        if direction == 'LONG':
            return close_p >= open_p # Green Candle
        if direction == 'SHORT':
            return close_p <= open_p # Red Candle
        return False

    @staticmethod
    def check_signal(pair, df, config):
        """
        Analyse la dernière bougie pour générer un signal
        🔙 V4 LEGACY LOGIC: Simple Technicals, No V5.1 Complexity
        """
        # Ensure we have enough data
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
        
        # --- 🏛️ TRAIDING WINDOWS (Gardé car essentiel pour éviter la nuit) ---
        if TRADING_WINDOWS_AVAILABLE:
            if not is_within_golden_window(pair):
                return None
        
        # --- 🔙 V4 PARAMETERS (FIXED) ---
        # On ignore les micro-corridors dynamiques V5.1
        tp_multiplier = 1.0
        sl_multiplier = 1.0
        risk_multiplier = 1.0
        corridor_name = "V4_LEGACY"
        current_regime = "STANDARD"
        scalping_mode = False
        
        # Par défaut RSI Oversold
        rsi_buy_threshold = params.get('rsi_oversold', 30)
        rsi_sell_threshold = params.get('rsi_overbought', 70)

        # --- 🛡️ V5.1 PREDICTABILITY INDEX (Anti-Erratic Filter) ---
        # CRUCIAL pour Oil (CL=F) qui est très erratique!
        predictability_score = None
        predictability_grade = None
        
        if PREDICTABILITY_INDEX_AVAILABLE and len(df) >= 50:
            try:
                pred_result = calculate_predictability_score(df)
                predictability_score = pred_result.get('score', 50)
                predictability_grade = pred_result.get('grade', 'MODERATE')
                
                # 🚫 QUARANTINE: Asset trop erratique (seuil plus strict pour commodities)
                # Oil est souvent erratique, on applique un seuil de 30
                erratic_threshold = 30 if 'CL=F' in pair else 25
                if pred_result.get('is_erratic', False) and predictability_score < erratic_threshold:
                    return None
                
                # Appliquer les ajustements si asset POOR ou pire
                if predictability_grade in ['POOR', 'ERRATIC']:
                    pred_adj = get_predictability_adjustment(df)
                    if not pred_adj.get('should_trade', True):
                        return None
                    # Réduire le risque pour commodities érratiques
                    risk_multiplier *= pred_adj.get('position_multiplier', 1.0)
                    tp_multiplier *= pred_adj.get('tp_multiplier', 1.0)
                    sl_multiplier *= pred_adj.get('sl_multiplier', 1.0)
                    
            except Exception:
                pass
        
        # --- STRATÉGIE 1: TREND PULLBACK (Gold V4) ---
        if strategy == 'TREND_PULLBACK':
            if 'SMA_200' not in df.columns or pd.isna(current['SMA_200']):
                return None
            
            # Simple Trend Filter
            is_bull_trend = (current['close'] > current['SMA_200'])
            
            if is_bull_trend:
                # Buy Dip: RSI < 30/40
                if current['RSI'] < rsi_buy_threshold:
                    if atr > 0.0005: # Min volatility check
                        signal = 'LONG'
                        sl_dist = atr * params['sl_atr_mult']
                        tp_dist = atr * params['tp_atr_mult']
                        stop_loss = entry_price - sl_dist
                        take_profit = entry_price + tp_dist

        # --- STRATÉGIE 2: BOLLINGER BREAKOUT (Oil V4) ---
        # Simple Breakout sans filtre SMA50 strict
        elif strategy == 'BOLLINGER_BREAKOUT':
            if 'BBU' not in df.columns or pd.isna(current['BBU']):
                return None
            
            # LONG Breakout
            if current['close'] > current['BBU'] and prev['close'] <= prev['BBU']:
                signal = 'LONG'
                sl_dist = atr * params['sl_atr_mult']
                tp_dist = atr * params['tp_atr_mult']
                stop_loss = entry_price - sl_dist
                take_profit = entry_price + tp_dist
            
            # SHORT Breakout
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
                'timestamp': str(current.name),
                'corridor': corridor_name,
                'regime': current_regime,
                'scalping_mode': scalping_mode,
                'risk_multiplier': risk_multiplier,
                'tp_multiplier': tp_multiplier,
                'sl_multiplier': sl_multiplier,
                # 🛡️ V5.1: Predictability Index
                'predictability_score': predictability_score,
                'predictability_grade': predictability_grade,
            }
            
        return None
