# Configuration Indices V5 Fortress (2026 Updated)
# Validée par Backtest 2024-2026

CONFIGURATION = {
    # S&P 500 (Trend Mean Reversion - Sniper Mode)
    '^GSPC': {
        'strategy': 'TREND_PULLBACK',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'sma_period': 200,
            'rsi_period': 14,
            'rsi_oversold': 48, # V5.1 Increased flexible threshold for strong trends
            'sl_atr_mult': 2.0, 
            'tp_atr_mult': 4.0  
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
            'sl_atr_mult': 1.5, # Tighter stop for momentum trades
            'tp_atr_mult': 3.0  # Quick profit taking on bursts
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
