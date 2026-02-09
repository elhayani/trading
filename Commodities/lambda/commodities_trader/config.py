CONFIGURATION = {
    # Gold (GC=F) - V6.1 OPTIMIZED WITH TRAILING STOP
    # Strategy: Trend Pullback (Relaxed Momentum, Wide Stops)
    # Backtest 2024-2026: +15.5%, WR 55%
    'GC=F': {
        'strategy': 'TREND_PULLBACK',
        'timeframe': '1h',
        'enabled': True,
        'risk_usd': 200.0,
        'params': {
            'sl_atr_mult': 2.5,  # V6.1: Tighter (was 3.0) for better R/R
            'tp_atr_mult': 4.5,  # V6.1: CRITICAL FIX - Increased from 3.0 to match Indices
            'rsi_oversold': 55,  # V7: Commodity-Friendly - Relaxed from 43 to catch more dips
            'max_atr': 25.0,
            'momentum_relaxed': True,
            # V6.1 NEW: Trailing Stop Parameters
            'trailing_activation_pct': 2.0,  # Activate at +2% (Gold moves slower)
            'trailing_distance_pct': 1.0,    # Trail 1% behind peak
            'breakeven_pct': 1.0             # Move SL to BE at +1%
        }
    },

    # Crude Oil (CL=F) - V6.1 STAR ENHANCED (+108% → Target +150%)
    'CL=F': {
        'strategy': 'BOLLINGER_BREAKOUT',
        'timeframe': '1h',
        'enabled': True,
        'risk_usd': 200.0,
        'params': {
            'sl_atr_mult': 1.8,  # V6.1: Tighter SL (was 2.0)
            'tp_atr_mult': 5.0,  # V6.1: Wider TP (was 4.0) - Oil can rocket
            'max_atr': 0.60,
            'momentum_relaxed': False,
            # V6.1 NEW: Trailing Stop Parameters
            'trailing_activation_pct': 3.0,  # Activate at +3% (Oil volatile)
            'trailing_distance_pct': 1.5,    # Trail 1.5% behind peak
            'breakeven_pct': 1.5             # Move SL to BE at +1.5%
        }
    }
}
