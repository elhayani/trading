# Configuration Indices V5 Fortress (2026 Updated)
# Validée par Backtest 2024-2026

CONFIGURATION = {
    # S&P 500 (Trend Mean Reversion)
    '^GSPC': {
        'strategy': 'TREND_PULLBACK',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'sma_period': 200,
            'rsi_period': 14,
            'rsi_oversold': 40, # V5 Optimized
            'sl_atr_mult': 2.0, # V5 Wider stop for noise
            'tp_atr_mult': 4.0  # V5 1:2 Risk Reward
        }
    },
    
    # Nasdaq 100 (High Momentum)
    # Switched to TREND_PULLBACK based on V5 Backtest (+21%)
    '^NDX': {
        'strategy': 'TREND_PULLBACK',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'sma_period': 200,
            'rsi_period': 14,
            'rsi_oversold': 40,
            'sl_atr_mult': 2.0,
            'tp_atr_mult': 4.0
        }
    },

    # Dow Jones (^DJI) - DISABLED
    # Backtest V5 showed -15% loss due to choppiness.
}

# Paramètres Globlaux
GLOBAL_SETTINGS = {
    'risk_per_trade': 0.02,  # 2% du capital
    'leverage': 10, # Reduced leverage for Indices safety
    'max_positions_per_pair': 1
}
