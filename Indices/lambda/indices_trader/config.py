# Configuration Indices V6.0 - Optimized Risk/Reward
# Validée par Backtest 2024-2026
# V6.0 UPDATE: Better R/R ratio (1:3.0) + Trailing Stop activation

CONFIGURATION = {
    # S&P 500 (Trend Mean Reversion - Sniper Mode)
    '^GSPC': {
        'strategy': 'TREND_PULLBACK',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'sma_period': 200,
            'rsi_period': 14,
            'rsi_oversold': 52,  # V6.1: Tighter filter (was 55) for premium setups
            'sl_atr_mult': 1.4,  # V6.1: Slightly tighter (was 1.5)
            'tp_atr_mult': 5.0,  # V6.1: Increased from 4.5 to 5.0 (R/R 1:3.6)
            'min_volume_mult': 0.5,
            # V6.0 Trailing Stop Parameters
            'trailing_activation_pct': 0.8,  # V6.1: Earlier activation (was 1.0)
            'trailing_distance_pct': 0.4,    # V6.1: Tighter trail (was 0.5)
            'breakeven_pct': 0.4             # V6.1: Faster BE (was 0.5)
        }
    },
    
    # Nasdaq 100 (High Momentum - Breakout Mode)
    '^NDX': {
        'strategy': 'BOLLINGER_BREAKOUT',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'sma_period': 200,
            'rsi_period': 14,
            'rsi_oversold': 40,
            'sl_atr_mult': 1.4,  # V6.1: Tighter SL (was 1.5)
            'tp_atr_mult': 5.5,  # V6.1: Even more aggressive (was 5.0) - Nasdaq rockets
            # V6.0 Trailing Stop Parameters
            'trailing_activation_pct': 1.2,  # V6.1: Earlier activation (was 1.5)
            'trailing_distance_pct': 0.6,    # V6.1: Tighter trail (was 0.8)
            'breakeven_pct': 0.6             # V6.1: Faster BE (was 0.8)
        }
    },

    # Dow Jones (^DJI) - DISABLED
    # Backtest V5 showed -15% loss due to choppiness.
}

# Paramètres Globlaux
GLOBAL_SETTINGS = {
    'risk_per_trade': 0.02,  # 2% du capital
    'leverage': 10, # Reduced leverage for Indices safety
    'max_positions_per_pair': 1,
    # V6.0 Trailing Stop Global Config
    'trailing_stop_enabled': True,
    'use_atr_trailing': True,
    'atr_trailing_multiplier': 1.5
}
