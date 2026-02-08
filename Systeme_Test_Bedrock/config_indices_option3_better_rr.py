# Configuration Indices V6.2 - Option 3: BETTER R/R
# 🎯 Objectif: RSI 58 + SL -5% + TP élargi (6.0 ATR)
# ⚖️ Meilleur équilibre risque/récompense

CONFIGURATION = {
    # S&P 500 (Trend Mean Reversion - Sniper Mode)
    '^GSPC': {
        'strategy': 'TREND_PULLBACK',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'sma_period': 200,
            'rsi_period': 14,
            'rsi_oversold': 58,  # ⬆️ +6 (was 52)
            'sl_atr_mult': 1.8,  # ⬆️ +0.4 (was 1.4)
            'tp_atr_mult': 6.0,  # ⬆️ +1.0 (was 5.0) for better R/R
            'min_volume_mult': 0.5,
            'trailing_activation_pct': 0.8,
            'trailing_distance_pct': 0.4,
            'breakeven_pct': 0.4
        }
    },

    '^NDX': {
        'strategy': 'BOLLINGER_BREAKOUT',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'sma_period': 200,
            'rsi_period': 14,
            'rsi_oversold': 45,  # ⬆️ +5 (was 40)
            'sl_atr_mult': 1.8,  # ⬆️ +0.4 (was 1.4)
            'tp_atr_mult': 6.5,  # ⬆️ +1.0 (was 5.5)
            'trailing_activation_pct': 1.2,
            'trailing_distance_pct': 0.6,
            'breakeven_pct': 0.6
        }
    },
}

GLOBAL_SETTINGS = {
    'risk_per_trade': 0.02,
    'leverage': 10,
    'max_positions_per_pair': 1,
    'trailing_stop_enabled': True,
    'use_atr_trailing': True,
    'atr_trailing_multiplier': 1.5
}

# NOTE: Aussi modifier dans lambda_function.py:
# STOP_LOSS_PCT = -5.0  # ⬆️ +1.0% (was -4.0%)

# Impact attendu:
# - Trades: 15-20/an
# - SL effectif: -5%
# - TP effectif: ~7.5% (6.0 × 1.24% ATR)
# - R/R: 1:1.50 ✅ (meilleur équilibre)
# - Trade-off: Moins de TP atteints, mais meilleur ratio quand hit
