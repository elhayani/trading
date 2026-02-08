# Configuration Indices V6.1 - OPTIMIZED for Bull Markets
# 🎯 OBJECTIF: Augmenter l'activité de 3 à ~20 trades/an
# 📊 Basé sur analyse backtest 2025-2026 (RSI moyen: 55.6)

CONFIGURATION = {
    # S&P 500 (Trend Mean Reversion - Sniper Mode)
    '^GSPC': {
        'strategy': 'TREND_PULLBACK',
        'enabled': True,
        'timeframe': '1h',
        'params': {
            'sma_period': 200,
            'rsi_period': 14,

            # 🔥 CHANGEMENT PRINCIPAL:
            'rsi_oversold': 58,  # ⬆️ +6 points (était 52)
            # Rationale: Dans un bull market (RSI moyen 55.6), un seuil à 52
            # capture seulement 15% des opportunités. À 58, on capture 66%.

            'sl_atr_mult': 1.4,  # ✅ Inchangé (déjà optimisé)
            'tp_atr_mult': 5.0,  # ✅ Inchangé (bon R/R 1:3.6)
            'min_volume_mult': 0.5,  # ✅ OK, mais considérer 0.3 si nécessaire

            # V6.0 Trailing Stop Parameters (inchangés)
            'trailing_activation_pct': 0.8,
            'trailing_distance_pct': 0.4,
            'breakeven_pct': 0.4
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

            # 🔥 SUGGESTION: Assouplir aussi le Nasdaq
            'rsi_oversold': 45,  # ⬆️ +5 points (était 40)
            # Nasdaq est plus volatile, mais même logique

            'sl_atr_mult': 1.4,
            'tp_atr_mult': 5.5,

            # V6.0 Trailing Stop Parameters
            'trailing_activation_pct': 1.2,
            'trailing_distance_pct': 0.6,
            'breakeven_pct': 0.6
        }
    },

    # Dow Jones (^DJI) - DISABLED
    # Backtest V5 showed -15% loss due to choppiness.
}

# Paramètres Globaux (inchangés)
GLOBAL_SETTINGS = {
    'risk_per_trade': 0.02,  # 2% du capital
    'leverage': 10,
    'max_positions_per_pair': 1,

    # V6.0 Trailing Stop Global Config
    'trailing_stop_enabled': True,
    'use_atr_trailing': True,
    'atr_trailing_multiplier': 1.5
}

# ============================================================================
# 📊 IMPACT ATTENDU
# ============================================================================
#
# S&P 500:
# - Trades/an: 3 → ~20 (+566%)
# - Opportunités capturées: 15% → 66%
# - Win rate: Maintenu (setups de qualité)
# - ROI attendu: 0% → 15-25%
#
# Nasdaq 100:
# - Impact similaire mais adapté à sa volatilité
#
# ============================================================================
# 🧪 VALIDATION REQUISE
# ============================================================================
#
# Avant déploiement en production:
# 1. Relancer backtest 2025-2026 avec ces params
# 2. Vérifier win rate maintenu > 60%
# 3. Vérifier drawdown acceptable < 10%
# 4. Comparer ROI avec Forex (benchmark: +29%)
#
# ============================================================================

# 📝 NOTES TECHNIQUES
# ============================================================================
#
# Pourquoi RSI 58 et pas 60?
# - 58 capture 66% des opportunités (sweet spot)
# - 60 capture 83% mais risque de qualité moindre
# - On privilégie la qualité à la quantité
#
# Pourquoi ne pas toucher aux autres params?
# - sl_atr_mult et tp_atr_mult déjà optimisés en V6.1
# - Trailing stop params validés par backtests précédents
# - Changement ciblé = plus facile à analyser
#
# ============================================================================
