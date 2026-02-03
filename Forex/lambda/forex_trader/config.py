# Configuration Forex 2026 - Validée par Crash Test
# Période de validation : 2 ans (700 jours)

CONFIGURATION = {
    # Stratégie: Trend Pullback (Stable & Classique)
    'EURUSD': {
        'strategy': 'TREND_PULLBACK',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'sma_period': 200,
            'rsi_period': 14,
            'rsi_oversold': 35,  # Entrée Long
            'sl_atr_mult': 1.0,
            'tp_atr_mult': 3.0
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
            'rsi_oversold': 35,
            'sl_atr_mult': 1.0,
            'tp_atr_mult': 3.0
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
            'sl_atr_mult': 1.5,
            'tp_atr_mult': 3.0
        }
    }
}

# Paramètres Globlaux
GLOBAL_SETTINGS = {
    'risk_per_trade': 0.02,  # 2% du capital
    'leverage': 30,
    'max_positions_per_pair': 1
}
