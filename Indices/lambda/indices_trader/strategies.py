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
        V5.8 Reversal Trigger: Relaxed for Indices
        1. Green Candle (Standard)
        2. Doji (Small Body/Indecision) -> Allowed
        3. RSI Crossing Up (Signal Line) -> Allowed even if red (if RSI < 40)
        4. Deep Oversold Exception (<30)
        """
        open_p = float(current['open'])
        close_p = float(current['close'])
        high_p = float(current['high'])
        low_p = float(current['low'])
        
        body_size = abs(close_p - open_p)
        total_range = high_p - low_p if high_p != low_p else 1.0
        is_doji = (body_size / total_range) < 0.15 # Body is less than 15% of range
        
        if direction == 'LONG':
            rsi = current.get('RSI', 50)
            
            # 1. Deep Oversold (Knife Catch)
            if rsi < 35: # Relaxed form 30 to 35
                print(f"DEBUG: Falling Knife Bypass (RSI {rsi:.1f} < 35)")
                return True
                
            # 2. Green Candle or Doji
            if close_p >= open_p or is_doji:
                print(f"DEBUG: Reversal Valid (Green={close_p>=open_p}, Doji={is_doji})")
                return True
                
            # 3. RSI Hook (If candle red but RSI turning up strongly - simplified as > previous RSI)
            # This requires 'prev' which relies on caller context, assuming basic candle check here.
            # We stick to candle logic in this static method for now.
            
            return False
        
        if direction == 'SHORT':
             # 1. Deep Overbought
            if 'RSI' in current and current['RSI'] > 65: # Relaxed from 70
                print(f"DEBUG: Spiking Knife Bypass (RSI {current['RSI']:.1f} > 65)")
                return True
                
            # 2. Red Candle or Doji
            if close_p <= open_p or is_doji:
                return True
                
            return False
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
            is_valid = is_within_golden_window(pair)
            if not is_valid:
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
            
            # RSI adaptatif selon le corridor (DISABLED FOR V5.8 INDICES FIX)
            # adaptive_rsi = get_rsi_threshold_adaptive(pair, params.get('rsi_oversold', 40))
            # params = params.copy()
            # params['rsi_oversold'] = adaptive_rsi
            
            # --- 🛑 V5.1 VETO DE VOLUME (Point 3) ---
            if 'volume' in df.columns:
                current_volume = float(current.get('volume', 0))
                # V5.8: Volume check using config parameter (default 0.9x relaxed)
                min_vol_mult = params.get('min_volume_mult', 1.1)
                
                # Check for Volume Veto (if available)
                if check_volume_veto: # Check if imported function exists
                    volume_veto = check_volume_veto(pair, df, min_vol_mult)
                    if volume_veto.get('veto', False):
                        print(f"DEBUG: 🔇 Volume Veto (Vol < {min_vol_mult}x Avg)")
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
        
        # --- STRATÉGIE 1: TREND PULLBACK (V5.8 OPTIMIZED) ---
        if strategy == 'TREND_PULLBACK':
            
            if 'SMA_200' not in df.columns or pd.isna(current['SMA_200']):
                return None
            
            # 1. Trend Condition
            sma200 = float(current['SMA_200'])
            close_p = float(current['close'])
            deviation_pct = ((close_p - sma200) / sma200) * 100
            
            # V5.8: Allow dip up to 4.0% below SMA200 (Very generous)
            is_bull_trend = (deviation_pct > -4.0)
            
            # 2. RSI Condition
            try:
                rsi_val = float(current.get('RSI', 100))
                # prev_rsi = float(prev.get('RSI', 100)) # Not strictly needed if relying on current
                trigger_rsi = float(params.get('rsi_oversold', 58))
            except Exception:
                return None
            
            # Deep Value Bypass
            if rsi_val < 35:
                is_bull_trend = True
            
            # Check Signal (RSI Oversold)
            # Simplified: Only current RSI matters for clean entry (prev RSI can trigger late)
            is_rsi_oversold = (rsi_val < trigger_rsi)
            
            if is_rsi_oversold and is_bull_trend:
                
                if atr > 0.0001: # Basic volatility check
                     # Reversal Check
                     reversal = ForexStrategies.check_reversal(current, 'LONG')
                     
                     if reversal:
                        signal = 'LONG'
                        sl_dist = atr * params['sl_atr_mult'] * sl_multiplier
                        tp_dist = atr * params['tp_atr_mult'] * tp_multiplier
                        stop_loss = entry_price - sl_dist
                        take_profit = entry_price + tp_dist

        # --- STRATÉGIE 2: BOLLINGER BREAKOUT ---
        elif strategy == 'BOLLINGER_BREAKOUT':
            if 'BBU' not in df.columns or pd.isna(current['BBU']):
                return None
                
            print(f"DEBUG: BB Analysis - Close={current['close']:.2f} BBU={current['BBU']:.2f} EMA50={current.get('EMA_50', 'N/A')}")
            
            if current['close'] > current['BBU'] and prev['close'] <= prev['BBU']:
                print(f"DEBUG: BB Upside Breakout Detected ({prev['close']:.2f} -> {current['close']:.2f} > {current['BBU']:.2f})")
                if current['close'] > current['EMA_50']:
                    reversal = ForexStrategies.check_reversal(current, 'LONG')
                    print(f"DEBUG: BB Trend OK + Reversal Check -> {reversal}")
                    if reversal:
                        signal = 'LONG'
                        sl_dist = atr * params['sl_atr_mult'] * sl_multiplier
                        tp_dist = atr * params['tp_atr_mult'] * tp_multiplier
                        stop_loss = entry_price - sl_dist
                        take_profit = entry_price + tp_dist
                else:
                     print(f"DEBUG: BB Breakout but Below EMA50 ({current['close']:.2f} < {current['EMA_50']:.2f})")
                
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
