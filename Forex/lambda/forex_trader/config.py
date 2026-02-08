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
            'rsi_oversold': 42,  # V6.1: Slightly tighter (was 45) for quality
            'sl_atr_mult': 1.0,
            'tp_atr_mult': 4.0,  # V6.1: Increased from 3.5 to 4.0 (R/R 1:4)
            # V6.0 Trailing Stop Parameters
            'trailing_activation_pct': 0.4,  # V6.1: Activate earlier (was 0.5)
            'trailing_distance_pct': 0.25,   # V6.1: Tighter trail (was 0.3)
            'breakeven_pct': 0.25            # V6.1: Faster BE (was 0.3)
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
            'rsi_oversold': 42,  # V6.1: Aligned with EURUSD (was 45)
            'sl_atr_mult': 1.0,
            'tp_atr_mult': 4.0,  # V6.1: Increased from 3.5 to 4.0
            # V6.0 Trailing Stop Parameters
            'trailing_activation_pct': 0.4,  # V6.1: Aligned with EURUSD
            'trailing_distance_pct': 0.25,
            'breakeven_pct': 0.25
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
            'sl_atr_mult': 1.0,
            'tp_atr_mult': 4.5,  # V6.1: Increased from 4.0 to 4.5 (capture momentum)
            # V6.0 Trailing Stop Parameters
            'trailing_activation_pct': 0.6,  # V6.1: Earlier activation (was 0.8)
            'trailing_distance_pct': 0.4,    # V6.1: Tighter (was 0.5)
            'breakeven_pct': 0.35            # V6.1: Faster BE (was 0.4)
        }
    }
}

# Paramètres Globaux V6.1 OPTIMIZED
GLOBAL_SETTINGS = {
    'risk_per_trade': 0.02,  # 2% risk per trade
    'leverage': 20,  # V6.1 SAFETY: Reduced from 30x to 20x (margin call protection)
    'max_positions_per_pair': 1,
    'max_global_positions': 2,  # V6.1 NEW: Max 2 trades across ALL pairs (capital protection)
    # V6.0 Trailing Stop Global Config
    'trailing_stop_enabled': True,
    'use_atr_trailing': True,  # Use ATR-based trailing when available
    'atr_trailing_multiplier': 1.5
}
