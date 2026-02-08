# 🎯 Plan d'Action Complet - Optimisation Bot Indices

## 📋 RÉSUMÉ EXÉCUTIF

Le bot Indices est sous-utilisé (3 trades/an) à cause de **3 filtres cumulatifs trop stricts**:
1. ❌ **RSI 52** - Trop strict pour bull market (RSI moyen 55.6)
2. ⚠️ **Stop Loss** - Juste suffisant pour RSI 52, mais limite pour RSI 58
3. ⚠️ **Prompt Bedrock** - Pas adapté aux marchés à momentum fort

---

## 🔍 ANALYSE DÉTAILLÉE

### 1. RSI Threshold Analysis

| Métrique | Valeur | Impact |
|----------|--------|--------|
| RSI Moyen (2025-2026) | 55.6 | Marché BULL |
| Opportunités capturées (RSI ≤52) | 14.9% | ❌ Trop restrictif |
| Opportunités capturées (RSI ≤58) | 66.0% | ✅ Sweet spot |

**Problème**: Avec RSI ≤52, on attend des pullbacks profonds qui arrivent rarement en bull market.

---

### 2. Stop Loss Adequacy Analysis ⚠️

**Configuration actuelle:**
```python
'sl_atr_mult': 1.4    # ATR-based
STOP_LOSS_PCT = -4.0  # Fixed
```

**Analyse des drawdowns:**
```
ATR Moyen:              1.24%
SL ATR-based:          -1.73% (1.4 × 1.24%)
SL Fixed:              -4.00%
SL Effectif:           -4.00% (le plus large)

Drawdown observé (RSI 52):    -1.56%
Buffer actuel:                 +2.44% ✅

Drawdown attendu (RSI 58):     -2.02% (+30% estimate)
Buffer avec RSI 58:            +1.98% ⚠️ (plus tight)
```

**⚠️ RISQUE IDENTIFIÉ:**
Avec RSI 58, tu achètes plus près du sommet local → drawdown initial plus fort → besoin d'un SL plus large pour laisser le trade "respirer".

**Risk/Reward Impact:**
```
Current:
  TP: +6.20% (5.0 ATR)
  SL: -4.00%
  R/R: 1:1.55 ⚠️ (Below 1:2 minimum)

Recommended:
  TP: +6.20% (keep)
  SL: -5.00% (widen for safety)
  R/R: 1:1.24 ⚠️ (worse, but safer)

OR Better:
  TP: +7.50% (widen to 6.0 ATR)
  SL: -5.00%
  R/R: 1:1.50 ✅ (acceptable)
```

---

### 3. Prompt Bedrock Analysis

**Prompt actuel** (Generic):
```
You are a professional Indices Risk Manager.
TASK: Validate this trade.
[strategy_instruction varies by strategy]
```

**Problème**: Pas d'instruction spécifique pour les marchés à **momentum fort** où:
- Une consolidation latérale = signal d'achat valide
- Un petit pullback dans un uptrend = opportunité, pas danger

**Risque**: Même avec RSI 58, Bedrock peut dire "CANCEL" sur des setups valides s'il perçoit du "risque" dans une consolidation.

---

## ✅ PLAN D'ACTION RECOMMANDÉ

### Phase 1: Ajustements Simultanés (Configuration)

#### A. RSI Threshold
```python
# config.py - S&P 500
'rsi_oversold': 58,  # ⬆️ +6 points (was 52)
```

#### B. Stop Loss (3 Options)

**Option 1 - Conservative (Recommandée)**
```python
'sl_atr_mult': 1.8,   # ⬆️ +0.4 (was 1.4)
# Fixed SL reste à -4.0%
# Résultat: SL effectif ≈ -2.2% (1.8 × 1.24%)
#           ou -4.0% si marché volatile
```

**Option 2 - Hybrid (Plus sûr)**
```python
'sl_atr_mult': 1.8,   # ⬆️ +0.4
STOP_LOSS_PCT = -5.0  # ⬆️ +1.0% (was -4.0%)
# Résultat: SL effectif = -5.0% (fixed prend le dessus)
# Buffer: ~3% (très confortable)
```

**Option 3 - Aggressive TP (Meilleur R/R)**
```python
'sl_atr_mult': 1.8,
'tp_atr_mult': 6.0,   # ⬆️ +1.0 (was 5.0)
STOP_LOSS_PCT = -5.0
# R/R: 1:1.50 (meilleur équilibre)
```

**💡 Ma Recommandation: Option 2 (Hybrid)**
- Raison: Maximise la sécurité pour les nouveaux setups RSI 58
- Trade-off: R/R légèrement moins bon mais win rate plus stable

---

#### C. Prompt Bedrock (Assouplissement pour Momentum)

**Ajout à `ask_bedrock()`:**
```python
# AVANT la définition du prompt, ajouter:

# Custom instruction for S&P 500 TREND_PULLBACK in Bull Markets
if 'TREND_PULLBACK' in signal_data.get('strategy', '') and pair == '^GSPC':
    # Check if we're in bull mode (RSI > 50)
    rsi = signal_data.get('rsi', 50)
    if rsi > 50:
        strategy_instruction = """
        This is a PULLBACK in a BULL MARKET (RSI > 50).

        KEY RULES:
        1. Lateral consolidation (sideways) is BULLISH → CONFIRM
        2. Small pullback in uptrend is an OPPORTUNITY → CONFIRM
        3. Only CANCEL if:
           - Major bearish reversal pattern (Head & Shoulders, etc.)
           - Extremely negative news (War, Financial Crisis, etc.)

        BIAS: In strong uptrends, prefer CONFIRM unless evidence is overwhelming.
        """
```

**Rationale:**
- En bull market, Bedrock doit être **momentum-friendly**
- Une consolidation = accumulation, pas distribution
- Évite les faux négatifs sur des setups valides

---

### Phase 2: Validation par Backtest 🧪

**CRITIQUE**: Cette étape est **NON-NÉGOCIABLE**.

Le win rate de 100% sur 3 trades ne garantit RIEN sur 20 trades.

#### Test 1: Configuration Conservative
```bash
# Appliquer:
# - RSI: 58
# - SL ATR: 1.8
# - Fixed SL: -5.0%
# - Prompt: Assouplir

python3 run_test_v2.py --asset-class Indices --symbol ^GSPC --days 365 --offset-days 365

# Objectifs:
# ✅ Trades: 15-25
# ✅ Win Rate: > 65%
# ✅ ROI: > 15%
# ✅ Drawdown Max: < 10%
```

#### Test 2: Configuration Aggressive (Si Test 1 trop timide)
```bash
# Si Test 1 donne encore < 10 trades:
# - RSI: 60 (au lieu de 58)
# - Retest
```

#### Test 3: Comparaison Multi-Années
```bash
# Valider sur 2024 aussi (out-of-sample)
python3 run_test_v2.py --asset-class Indices --symbol ^GSPC --days 365 --offset-days 730
```

---

### Phase 3: Analyse des Résultats

#### Métriques Critiques à Valider

| Métrique | Minimum Acceptable | Optimal |
|----------|-------------------|---------|
| **Trades/an** | 15 | 20-25 |
| **Win Rate** | 65% | 70%+ |
| **ROI** | 15% | 25%+ |
| **Avg Win** | €200 | €400+ |
| **Max Drawdown** | -10% | -5% |
| **Profit Factor** | 1.5 | 2.0+ |

#### Questions à se poser:

1. **Si Win Rate baisse à 60%**:
   - ✅ Acceptable SI Profit Factor > 1.5
   - ❌ Problématique SI Avg Win < €150

2. **Si Trades < 10**:
   - → Bedrock bloque encore trop
   - → Assouplir davantage le prompt
   - → Vérifier Predictability Score (ligne 299)

3. **Si Max Drawdown > 10%**:
   - → SL trop tight, passer à Option 2 (SL -5%)
   - → Ou réduire exposition (MAX_EXPOSURE 5 → 3)

---

### Phase 4: Ajustements Itératifs

#### Si Win Rate 50-60% (Trop Agressif)
```python
# Resserrer légèrement:
'rsi_oversold': 58 → 56
# Ou ajouter filtre volume:
'min_volume_mult': 0.5 → 0.7
```

#### Si Trades < 10 (Trop Timide)
```python
# Vérifier cumul de filtres:
INDICES_MIN_SCORE = 15 → 10  # Ligne 297, lambda_function.py
# Ou assouplir davantage Bedrock prompt
```

#### Si R/R < 1:1.5 (Mauvais ratio)
```python
# Élargir TP:
'tp_atr_mult': 5.0 → 6.0
# Ou resserrer SL SI drawdowns faibles
```

---

## 🎯 RÉSUMÉ DES CHANGEMENTS

### Fichier 1: `config.py`
```python
'^GSPC': {
    'params': {
        'rsi_oversold': 58,      # ⬆️ +6 (was 52)
        'sl_atr_mult': 1.8,      # ⬆️ +0.4 (was 1.4)
        'tp_atr_mult': 5.0,      # ✅ Keep (or 6.0 if R/R needed)
        # ... autres inchangés
    }
}
```

### Fichier 2: `lambda_function.py`
```python
# Ligne 65:
STOP_LOSS_PCT = -5.0  # ⬆️ +1.0% (was -4.0%)

# Ligne ~340 (dans ask_bedrock, avant prompt):
# Ajouter logique pour S&P 500 TREND_PULLBACK en bull market
# (Voir code détaillé ci-dessus)
```

---

## 📊 IMPACT ATTENDU

### Scénario Base (Objectifs Minimums)
```
Capital Initial:  €20,000
Trades/an:        15-20
Win Rate:         65-70%
Avg Win:          €300
ROI:              +18-25%
Capital Final:    €23,600 - €25,000
```

### Scénario Optimal
```
Capital Initial:  €20,000
Trades/an:        20-25
Win Rate:         70%+
Avg Win:          €400
ROI:              +25-35%
Capital Final:    €25,000 - €27,000
```

### Scénario Pessimiste (Validation Failed)
```
Si Win Rate < 60% après backtest:
→ Rollback RSI à 55 (milieu de gamme)
→ Garder SL élargi (sécurité)
→ Retester
```

---

## ⚠️ RISQUES ET MITIGATIONS

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| Win Rate baisse < 60% | Moyenne | Élevé | Backtest AVANT prod |
| Drawdowns > 10% | Faible | Moyen | SL élargi à -5% |
| Bedrock bloque encore | Moyenne | Moyen | Assouplir prompt |
| Overtrading | Faible | Faible | MAX_EXPOSURE = 5 |

---

## ✅ CHECKLIST AVANT PRODUCTION

- [ ] Modifier `config.py` (RSI 58, SL 1.8)
- [ ] Modifier `lambda_function.py` (SL -5%, prompt)
- [ ] Backtest 2025-2026 (Test 1)
- [ ] Valider Win Rate > 65%
- [ ] Valider ROI > 15%
- [ ] Backtest 2024 (Out-of-sample)
- [ ] Comparer avec Forex (benchmark)
- [ ] Paper Trading 1 semaine
- [ ] Production

---

## 🎓 LESSONS LEARNED

1. **RSI seul ne suffit pas** - Il faut adapter aux conditions de marché
2. **SL doit "respirer"** - Surtout pour entrées à RSI élevé
3. **Prompt Bedrock = filtre critique** - Doit être momentum-aware
4. **Backtest = validation obligatoire** - 3 trades ne prouvent rien
5. **Cumul de filtres = effet multiplicatif** - Assouplir plusieurs à la fois

---

## 📞 NEXT STEPS

1. **Maintenant**: Appliquer les changements (config + lambda)
2. **Dans 10 min**: Lancer backtest Test 1
3. **Dans 1h**: Analyser résultats, ajuster si besoin
4. **Demain**: Backtest multi-années, valider robustesse

**Question pour toi**: Veux-tu que j'applique directement les changements Option 2 (Hybrid), ou préfères-tu commencer plus conservateur avec Option 1?

---

*Rapport créé le 8 février 2026*
*Basé sur analyse complète RSI + SL + Prompt Bedrock*
