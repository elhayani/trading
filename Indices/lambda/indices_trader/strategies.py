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

# 🛡️ V5.1 Predictability Index - Détection des actifs erratiques
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
        V5 UPDATE: Included Momentum Filter & Reversal Trigger
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
        
        # --- 🏛️ V5 GOLDEN WINDOW FILTER ---
        # Vérifie si on est dans la session optimale pour cet actif
        # Pour les Indices: Session US uniquement (15h-22h Paris)
        if TRADING_WINDOWS_AVAILABLE:
            if not is_within_golden_window(pair):
                # Hors session optimale - on SKIP
                return None
        
        # --- 🕐 V5.1 SESSION PHASE (Horloge Biologique) ---
        session_phase = None
        aggressiveness = "MEDIUM"
        if SESSION_PHASE_AVAILABLE:
            session_phase = get_session_phase(pair)
            aggressiveness = session_phase.get('aggressiveness', 'MEDIUM')
            if not session_phase.get('is_tradeable', True):
                return None  # Marché fermé ou hors heures
        
        # --- 🎯 V5.1 MICRO-CORRIDOR ADAPTATIF ---
        corridor_info = None
        tp_multiplier = 1.0
        sl_multiplier = 1.0
        risk_multiplier = 1.0
        scalping_mode = False
        corridor_name = "Default"
        current_regime = "STANDARD"
        min_volume_ratio = 1.0
        
        if MICRO_CORRIDORS_AVAILABLE:
            corridor_info = get_corridor_params(pair)
            corridor_params = corridor_info.get('params', {})
            tp_multiplier = corridor_params.get('tp_multiplier', 1.0)
            sl_multiplier = corridor_params.get('sl_multiplier', 1.0)
            risk_multiplier = corridor_params.get('risk_multiplier', 1.0)
            scalping_mode = corridor_params.get('scalping_mode', False)
            corridor_name = corridor_info.get('name', 'Default')
            current_regime = corridor_info.get('regime', 'STANDARD')
            min_volume_ratio = corridor_params.get('min_volume_ratio', 1.0)
            
            # RSI adaptatif selon le corridor
            adaptive_rsi = get_rsi_threshold_adaptive(pair, params.get('rsi_oversold', 40))
            params = params.copy()
            params['rsi_oversold'] = adaptive_rsi
            
            # --- 🛑 V5.1 VETO DE VOLUME (Point 3) ---
            if 'volume' in df.columns:
                current_volume = float(current.get('volume', 0))
                avg_volume = float(df['volume'].tail(20).mean()) if len(df) >= 20 else 0
                
                if avg_volume > 0 and current_volume > 0:
                    volume_veto = check_volume_veto(pair, current_volume, avg_volume)
                    if volume_veto.get('veto', False):
                        return None

        # --- 🛡️ V5.1 PREDICTABILITY INDEX (Anti-Erratic Filter) ---
        predictability_score = None
        predictability_grade = None
        predictability_adjustment = {}
        
        if PREDICTABILITY_INDEX_AVAILABLE and len(df) >= 50:
            try:
                pred_result = calculate_predictability_score(df)
                predictability_score = pred_result.get('score', 50)
                predictability_grade = pred_result.get('grade', 'MODERATE')
                
                # 🚫 QUARANTINE: Asset trop erratique
                if pred_result.get('is_erratic', False):
                    # Score < 30 = erratique, on vérifie avec notre threshold
                    if predictability_score < 25:
                        # Asset ERRATIC = SKIP complet
                        return None
                
                # Récupérer les ajustements
                predictability_adjustment = get_predictability_adjustment(df)
                
                # Appliquer les ajustements au volume_multiplier
                if predictability_adjustment.get('should_trade', True):
                    pred_volume_mult = predictability_adjustment.get('volume_multiplier', 1.0)
                    min_volume_ratio *= pred_volume_mult
                    
                    # Ajuster TP/SL selon la prédictibilité
                    pred_tp_mult = predictability_adjustment.get('tp_multiplier', 1.0)
                    pred_sl_mult = predictability_adjustment.get('sl_multiplier', 1.0)
                    tp_multiplier *= pred_tp_mult
                    sl_multiplier *= pred_sl_mult
                    
                    # Ajuster le risk_multiplier
                    pred_risk_mult = predictability_adjustment.get('position_multiplier', 1.0)
                    risk_multiplier *= pred_risk_mult
                else:
                    # Asset en quarantine
                    return None
                    
            except Exception:
                # En cas d'erreur, on continue avec les paramètres par défaut
                pass
        
        # --- STRATÉGIE 1: TREND PULLBACK ---
        if strategy == 'TREND_PULLBACK':
            if 'SMA_200' not in df.columns or pd.isna(current['SMA_200']):
                return None
            
            is_bull_trend = (current['close'] > current['SMA_200']) and (current['EMA_50'] > current['SMA_200'])
            
            if is_bull_trend:
                if current['RSI'] < params['rsi_oversold']:
                    if atr > 0.0005:
                        if ForexStrategies.check_reversal(current, 'LONG'):
                            signal = 'LONG'
                            sl_dist = atr * params['sl_atr_mult'] * sl_multiplier
                            tp_dist = atr * params['tp_atr_mult'] * tp_multiplier
                            stop_loss = entry_price - sl_dist
                            take_profit = entry_price + tp_dist

        # --- STRATÉGIE 2: BOLLINGER BREAKOUT ---
        elif strategy == 'BOLLINGER_BREAKOUT':
            if 'BBU' not in df.columns or pd.isna(current['BBU']):
                return None
                
            if current['close'] > current['BBU'] and prev['close'] <= prev['BBU']:
                if current['close'] > current['EMA_50']:
                    if ForexStrategies.check_reversal(current, 'LONG'):
                        signal = 'LONG'
                        sl_dist = atr * params['sl_atr_mult'] * sl_multiplier
                        tp_dist = atr * params['tp_atr_mult'] * tp_multiplier
                        stop_loss = entry_price - sl_dist
                        take_profit = entry_price + tp_dist
                
            elif current['close'] < current['BBL'] and prev['close'] >= prev['BBL']:
                if current['close'] < current['EMA_50']:
                    if ForexStrategies.check_reversal(current, 'SHORT'):
                        signal = 'SHORT'
                        sl_dist = atr * params['sl_atr_mult'] * sl_multiplier
                        tp_dist = atr * params['tp_atr_mult'] * tp_multiplier
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
                # V5.1 Predictability Index
                'predictability_score': predictability_score,
                'predictability_grade': predictability_grade,
            }
            
        return None
