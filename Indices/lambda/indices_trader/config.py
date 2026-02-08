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
            'rsi_oversold': 55, # OPTIMIZED V5.9 (Was 62/58) - Quality Dip Buying
            'sl_atr_mult': 1.5,
            'tp_atr_mult': 4.5, # V6.0: Increased target for better Risk/Reward (was 2.5)
            'min_volume_mult': 0.5,
            # V6.0 Trailing Stop Parameters
            'trailing_activation_pct': 1.0,  # Activate at +1.0%
            'trailing_distance_pct': 0.5,    # Trail 0.5% behind peak
            'breakeven_pct': 0.5             # Move SL to BE at +0.5%
        }
    },
    
    # Nasdaq 100 (High Momentum - Breakout Mode)
    '^NDX': {
        'strategy': 'BOLLINGER_BREAKOUT',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'sma_period': 200, # Still used for trend filter (EMA50) if applicable
            'rsi_period': 14,
            'rsi_oversold': 40, # Not used in BB but kept for consistency
            'sl_atr_mult': 1.5,
            'tp_atr_mult': 5.0,  # V6.0: Capture big momentum moves (was 3.0)
            # V6.0 Trailing Stop Parameters
            'trailing_activation_pct': 1.5,  # Activate at +1.5% (more room for NQ volatility)
            'trailing_distance_pct': 0.8,
            'breakeven_pct': 0.8
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
