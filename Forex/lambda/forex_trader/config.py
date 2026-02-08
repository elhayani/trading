# Configuration Forex V6.0 - Optimized Risk/Reward
# Période de validation : 2 ans (700 jours)
# V6.0 UPDATE: Better R/R ratio (1:3.5) + Trailing Stop activation

CONFIGURATION = {
    # Stratégie: Trend Pullback (Stable & Classique)
    'EURUSD': {
        'strategy': 'TREND_PULLBACK',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'sma_period': 200,
            'rsi_period': 14,
            'rsi_oversold': 45,  # V5.7 BOOST (was 55)
            'sl_atr_mult': 1.0,
            'tp_atr_mult': 3.5,  # V6.0: Increased from 2.5 to 3.5 for better R/R
            # V6.0 Trailing Stop Parameters
            'trailing_activation_pct': 0.5,  # Activate at +0.5%
            'trailing_distance_pct': 0.3,    # Trail 0.3% behind peak
            'breakeven_pct': 0.3             # Move SL to BE at +0.3%
        }
    },
    
    # Stratégie: Trend Pullback (Robuste sur GBP)
    'GBPUSD': {
        'strategy': 'TREND_PULLBACK',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'sma_period': 200,
            'rsi_period': 14,
            'rsi_oversold': 45, # V5.7 BOOST (was 55)
            'sl_atr_mult': 1.0,
            'tp_atr_mult': 3.5,  # V6.0: Increased from 2.5 to 3.5
            # V6.0 Trailing Stop Parameters
            'trailing_activation_pct': 0.5,
            'trailing_distance_pct': 0.3,
            'breakeven_pct': 0.3
        }
    },
    
    # Stratégie: Bollinger Breakout (La Machine à gagner sur JPY)
    'USDJPY': {
        'strategy': 'BOLLINGER_BREAKOUT',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'bb_length': 20,
            'bb_std': 2.0,
            'sl_atr_mult': 1.0,  # V6.0: Tighter SL (was 1.5)
            'tp_atr_mult': 4.0,  # V6.0: Wider TP for momentum (was 3.0)
            # V6.0 Trailing Stop Parameters
            'trailing_activation_pct': 0.8,  # Activate at +0.8% (breakout needs room)
            'trailing_distance_pct': 0.5,
            'breakeven_pct': 0.4
        }
    }
}

# Paramètres Globlaux
GLOBAL_SETTINGS = {
    'risk_per_trade': 0.02,  # V5.7 BOOST: Restored to 2% (was 1% maintenance)
    'leverage': 30,
    'max_positions_per_pair': 1,
    # V6.0 Trailing Stop Global Config
    'trailing_stop_enabled': True,
    'use_atr_trailing': True,  # Use ATR-based trailing when available
    'atr_trailing_multiplier': 1.5
}
