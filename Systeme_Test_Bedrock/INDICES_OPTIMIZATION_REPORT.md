# 🎯 Rapport d'Optimisation - Bot Indices

## 🔴 PROBLÈME IDENTIFIÉ

Le bot Indices est **extrêmement timide** avec seulement **3 trades** sur toute l'année 2025-2026.

### Taux d'activité
- **WAIT signals**: 47 (71% du temps)
- **Trades pris**: 3 seulement
- **Trade rate**: 0% (dans le CSV analysé, aucun signal RSI valide)

---

## 📊 ANALYSE RSI - Cause Racine

### Distribution RSI observée (S&P 500)
```
Min RSI:     38.9
Max RSI:     62.7
Moyenne:     55.6 ⚠️ (Market is BULLISH)
Médiane:     56.9
```

### Répartition du temps par zone RSI
| Zone | Temps | Commentaire |
|------|-------|-------------|
| **50-60** | **74.5%** | Zone neutre-haute (marché bull) |
| **60-70** | **17.0%** | Zone forte |
| **40-50** | **6.4%** | Zone neutre-basse |
| **30-40** | **2.1%** | Zone faible |
| **<30** | **0.0%** | Jamais atteint |

---

## 🎯 ANALYSE DU SEUIL ACTUEL

### Configuration actuelle
```python
'rsi_oversold': 52  # Seuil TROP STRICT pour bull market
```

### Opportunités capturées selon le seuil

| Seuil RSI | Opportunités | % Capturé | Commentaire |
|-----------|--------------|-----------|-------------|
| **≤ 52** (actuel) | **7** | **14.9%** | ❌ Trop restrictif |
| ≤ 55 | 15 | 31.9% | ⚠️ Encore limité |
| **≤ 58** | **31** | **66.0%** | ✅ **RECOMMANDÉ** |
| ≤ 60 | 39 | 83.0% | ⚠️ Peut-être trop agressif |

---

## 💡 RECOMMANDATIONS

### Option 1: Conservative (Recommandée) ⭐
**Objectif**: Doubler l'activité tout en gardant la qualité

```python
'^GSPC': {
    'strategy': 'TREND_PULLBACK',
    'params': {
        'rsi_oversold': 58,  # ⬆️ +6 points (était 52)
        'sl_atr_mult': 1.4,  # ✅ Keep (déjà optimisé)
        'tp_atr_mult': 5.0,  # ✅ Keep (bon R/R)
        # ... autres params inchangés
    }
}
```

**Impact attendu**:
- Trades: 3 → ~20 par an (+566%)
- Win rate: Maintenu (setups de qualité)
- Capture: 66% des opportunités (vs 15% actuellement)

---

### Option 2: Balanced
**Objectif**: Activité modérée, sélectivité élevée

```python
'rsi_oversold': 55,  # ⬆️ +3 points (était 52)
```

**Impact attendu**:
- Trades: 3 → ~10 par an (+233%)
- Capture: 32% des opportunités
- Très haute sélectivité

---

### Option 3: Aggressive (Pour Bull Markets uniquement)
**Objectif**: Maximiser l'exposition aux hausses

```python
'rsi_oversold': 60,  # ⬆️ +8 points (était 52)
```

**Impact attendu**:
- Trades: 3 → ~30 par an (+900%)
- Capture: 83% des opportunités
- ⚠️ Win rate possiblement plus bas

---

## 🔍 AUTRES FILTRES À VÉRIFIER

### 1. Predictability Index
```python
INDICES_MIN_SCORE = 15  # Actuellement dans lambda_function.py
```
✅ Ce seuil semble raisonnable (15/100 = très permissif pour indices)

### 2. Volume Filter
```python
'min_volume_mult': 0.5  # Vérifier si ce filtre bloque des trades
```
💡 Considérer de baisser à 0.3 si nécessaire

### 3. Cooldown
```python
COOLDOWN_HOURS = 2  # Déjà optimisé en V5.8
```
✅ Acceptable

---

## 📈 SCÉNARIOS DE BACKTEST SUGGÉRÉS

Pour valider les recommandations, relancer des backtests avec:

### Test 1: RSI 58 (Recommandé)
```bash
# Modifier config.py: rsi_oversold = 58
python3 run_test_v2.py --asset-class Indices --symbol ^GSPC --days 365 --offset-days 365
```

### Test 2: RSI 55 (Conservative)
```bash
# Modifier config.py: rsi_oversold = 55
python3 run_test_v2.py --asset-class Indices --symbol ^GSPC --days 365 --offset-days 365
```

### Test 3: RSI 60 (Aggressive)
```bash
# Modifier config.py: rsi_oversold = 60
python3 run_test_v2.py --asset-class Indices --symbol ^GSPC --days 365 --offset-days 365
```

---

## 🎯 COMPARAISON AVEC AUTRES BOTS

| Bot | Trades/An | Win Rate | ROI | Commentaire |
|-----|-----------|----------|-----|-------------|
| **Forex EURUSD** | 12 | 100% | +29% | ⭐ Excellent |
| **Indices S&P500** | **3** | 100% | +0% | ❌ **Sous-utilisé** |
| Commodities Gold | 14 | 57% | +0% | ⚠️ Sizing issue |
| Crypto BTC | 0 | - | 0% | ⚠️ Aucun trade |

**Conclusion**: Le Forex montre qu'on peut avoir 12 trades/an avec 100% win rate. Les Indices devraient viser 15-20 trades/an.

---

## ✅ PLAN D'ACTION

### Phase 1: Ajustement Immédiat
1. ✏️ Modifier `config.py` → `rsi_oversold: 52 → 58`
2. 🧪 Relancer backtest 2025-2026
3. 📊 Comparer résultats (nombre de trades, win rate, ROI)

### Phase 2: Validation
4. 🔍 Analyser les nouveaux trades (qualité des setups)
5. ⚖️ Ajuster si nécessaire (58 → 55 ou 60)
6. ✅ Valider avec backtest sur 2024 également

### Phase 3: Déploiement
7. 🚀 Déployer en paper trading
8. 📈 Monitorer 1 semaine
9. 💰 Activer en production si validé

---

## 📌 CONCLUSION

Le bot Indices est actuellement **sous-optimisé** avec un seuil RSI trop strict (52) pour un marché en mode bull (RSI moyen 55.6).

**Action recommandée**: Passer le seuil RSI de **52 à 58** pour capturer 66% des opportunités au lieu de 15%, tout en maintenant une haute sélectivité.

**Gain attendu**:
- Activité: 3 → 20 trades/an
- ROI: 0% → ~15-25% (estimation basée sur le ratio Forex)

---

*Rapport généré le 8 février 2026*
*Basé sur l'analyse du backtest S&P 500 2025-2026*
