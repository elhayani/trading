CONFIGURATION = {
    # Gold (GC=F) - V5 OPTIMIZED
    # Strategy: Trend Pullback (Relaxed Momentum, Wide Stops)
    # Backtest 2024-2026: +15.5%, WR 55%
    'GC=F': { 
        'strategy': 'TREND_PULLBACK', 
        'timeframe': '1h', 
        'enabled': True,
        'risk_usd': 200.0,
        'params': {
            'sl_atr_mult': 3.0, # Wide Stop (V5 finding)
            'tp_atr_mult': 3.0, # Conservative Target
            'rsi_oversold': 45, # Catch shallower dips (V5 finding)
            'max_atr': 25.0,
            'momentum_relaxed': True # Custom flag for strategies.py logic
        }
    },
    
    # Crude Oil (CL=F) - V5 STAR (+108%)
    'CL=F': { 
        'strategy': 'BOLLINGER_BREAKOUT', 
        'timeframe': '1h', 
        'enabled': True,
        'risk_usd': 200.0,
        'params': {
            'sl_atr_mult': 2.0,
            'tp_atr_mult': 4.0,
            'max_atr': 0.60,
            'momentum_relaxed': False
        }
    }
}
