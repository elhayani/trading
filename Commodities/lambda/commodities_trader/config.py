CONFIGURATION = {
    'GC=F': { 
        'strategy': 'TREND_PULLBACK', 
        'timeframe': '1h', 
        'enabled': True,
        'risk_usd': 200.0,
        'params': {
            'sl_atr_mult': 2.5,
            'tp_atr_mult': 4.0,
            'rsi_oversold': 35,
            'max_atr': 25.0
        }
    },
    'CL=F': { 
        'strategy': 'BOLLINGER_BREAKOUT', 
        'timeframe': '1h', 
        'enabled': True,
        'risk_usd': 200.0,
        'params': {
            'sl_atr_mult': 2.0,
            'tp_atr_mult': 4.0,
            'max_atr': 0.60
        }
    }
}
