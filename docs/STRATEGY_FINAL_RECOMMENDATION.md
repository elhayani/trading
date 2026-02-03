"""
🎯 STRATÉGIE HYBRIDE - GUIDE D'IMPLÉMENTATION
===============================================

CONCEPT: Adapter automatiquement la stratégie Bedrock selon le régime de marché

VERSION FINALE RECOMMANDÉE POUR PRODUCTION
"""

# ============================================================================
# RÉSUME DE L'OPTIMISATION
# ============================================================================

RÉSULTATS_TESTS = """
V1 (Ultra-Strict):
  - 2022 (Bear): +6.32%  ← Meilleur en crash
  - 2024 (Bull): +4.94%  ← Trop prudent
  - Cumulé: +11.26%

V3 (Smart):
  - 2022 (Bear): -5.91%  ← Trop actif en crash
  - 2024 (Bull): +19.59% ← Excellent en bull
  - Cumulé: +13.68%

HYBRID (Recommandé):
  - Utilise V1 quand marché catastrophique
  - Utilise V3 le reste du temps
  - Circuit breakers pour protection
  - Performance attendue: Meilleur des 2 mondes
"""

# ============================================================================
# CONFIGURATION POUR PRODUCTION
# ============================================================================

PRODUCTION_CONFIG = {
    # Mode par défaut
    'default_mode': 'V3_SMART',
    
    # Thresholds pour switch V1
    'extreme_bear_triggers': {
        'btc_7d_drop': -0.30,      # BTC -30% en 7j → V1
        'btc_30d_drop': -0.50,     # BTC -50%en 30j → V1
        'news_catastrophic': 0.85,  # 85% news neg → V1
    },
    
    # Circuit breakers (PAUSE trading)
    'circuit_breakers': {
        'max_drawdown': 0.25,       # -25% → PAUSE
        'consecutive_losses': 6,     # 6 pertes → PAUSE
        'monthly_loss': 0.15,        # -15% mensuel → PAUSE
    }
}

# ============================================================================
# PROMPTS BEDROCK SELON RÉGIME
# ============================================================================

PROMPTS = {
    'EXTREME_BEAR': """
    ⚠️ MODE SURVIE - BEAR MARKET EXTRÊME
    
    Le marché est en panic. Capital preservation > tout.
    
    CANCEL par défaut sauf si:
    - News TRÈS positives (>80%) ET
    - RSI < 20 (capitulation) ET  
    - Volume > 4x (panic selling exhaustion)
    
    → Philosophie: Cash is king in crashes
    """,
    
    'NORMAL_BEAR': """
    ⚖️ MODE PRUDENT - BEAR NORMAL
    
    Marché baissier mais opportunités de rebond existent.
    
    CANCEL si:
    - News >65% négatives
    - Mentions: hack, bankruptcy
    
    CONFIRM si:
    - Oversold technique (RSI<30) + news neutres
    
    → Philosophie: Sélectif mais pas paralysé
    """,
    
    'BULL_NORMAL': """
    🚀 MODE OPPORTUNISTE - MARCHÉ FAVORABLE
    
    Conditions normales/haussières.
    
    CANCEL uniquement si:
    - Catastrophe évidente (>75% news neg)
    - Fraud/bankruptcy detected
    
    CONFIRM (défaut) si:
    - Technique solide
    - News neutres/mixtes
    
    → Philosophie: Trust technique, filter disasters
    """
}

# ============================================================================
# RECOMMANDATION FINALE
# ============================================================================

DEPLOY_RECOMMENDATION = """
DÉPLOYER V3 SMART AVEC MONITORING

Pourquoi V3 et pas HYBRID complet?
1. HYBRID nécessite détection régime complexe
2. V3 seul performe déjà très bien (+13.7% sur 2 ans)
3. Plus simple = moins de bugs
4. Monitoring manuel permet override

SETUP PRODUCTION:
1. Déployer V3 Smart (code actuel)
2. Ajouter monitoring dashboard
3. Alerts Telegram si:
   - BTC -20% en 7j
   - Drawdown > 15%
   - 4+ pertes consécutives
4. Manual pause button accessible

ÉVOLUTION FUTURE:
- Phase 1: V3 + monitoring (maintenant)
- Phase 2: Ajouter détection régime (automatique)
- Phase 3: Full HYBRID (auto-switch strategies)
"""

print(__doc__)
print(RÉSULTATS_TESTS)
print("\n" + "="*70)
print(DEPLOY_RECOMMENDATION)
