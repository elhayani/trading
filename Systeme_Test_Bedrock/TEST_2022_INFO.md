# 📊 Backtest 2022 - Information & Usage

## ✅ Données 2022 Disponibles

Les données pour l'année **2022** sont **DISPONIBLES** via YFinance, mais avec une contrainte importante.

---

## 🔍 Limitation YFinance

### Intervalle 1h (Hourly)
- **Limite**: 730 jours (~2 ans)
- **2022**: ❌ **NON ACCESSIBLE** (trop ancien, > 730 jours depuis 2026-02-08)
- **Erreur**: `"1h data not available for startTime=... The requested range must be within the last 730 days."`

### Intervalle 1d (Daily)
- **Limite**: Plusieurs années (5-10+ ans selon l'actif)
- **2022**: ✅ **ACCESSIBLE** sans problème
- **Données disponibles**:
  - **Forex (EURUSD)**: 260 jours (trading days)
  - **Indices (S&P 500)**: 251 jours (trading days)
  - **Commodities (Gold)**: 251 jours (trading days)
  - **Crypto (BTC)**: 365 jours (24/7)

---

## 🚀 Comment Tester 2022

### Option 1: Script Automatique (Recommandé)

```bash
cd /Users/zakaria/Trading/Systeme_Test_Bedrock

# Lance les 4 backtests en parallèle
./test_2022.sh
```

**Durée estimée**: 10-15 minutes (en parallèle)

**Résultats**: `backtest_results_2022/`
- `forex_eurusd_2022.log`
- `indices_sp500_2022.log`
- `commodities_gold_2022.log`
- `crypto_btc_2022.log`

### Option 2: Tests Individuels

```bash
cd /Users/zakaria/Trading/Systeme_Test_Bedrock

# Forex (EURUSD)
python3 run_test_v2.py --asset-class Forex --symbol EURUSD=X --days 365

# Indices (S&P 500)
python3 run_test_v2.py --asset-class Indices --symbol ^GSPC --days 365

# Commodities (Gold)
python3 run_test_v2.py --asset-class Commodities --symbol GC=F --days 365

# Crypto (Bitcoin)
python3 run_test_v2.py --asset-class Crypto --symbol BTC-USD --days 365
```

**Note**: Le script `run_test_v2.py` détecte automatiquement la limite 1h et bascule sur 1d si nécessaire.

---

## 📈 Différences 1h vs 1d

### Intervalle 1h (Hourly)
- **Avantages**:
  - Granularité fine (24 candles/jour)
  - Simule mieux la réalité du bot (exécution horaire)
  - Meilleur timing d'entrée/sortie
- **Limites**:
  - Seulement 730 derniers jours disponibles
  - Indices/Forex souvent limités à 60 jours

### Intervalle 1d (Daily)
- **Avantages**:
  - Historique long (plusieurs années)
  - Données stables et complètes
  - Parfait pour backtests multi-années
- **Limites**:
  - 1 seul candle par jour
  - Timing d'entrée/sortie moins précis
  - Ne simule pas l'exécution horaire réelle

---

## 🎯 Objectif du Test 2022

### Pourquoi Tester 2022?

**2022 = Année de Crise** (parfait pour validation robustesse):
- **Janvier-Mars**: Correction marchés (inflation, Fed hawkish)
- **Mai-Juin**: Crash crypto (-50% BTC), bear market actions
- **Septembre**: Pic inflation, crash GBP/USD
- **Octobre-Décembre**: Rebond partiel, volatilité

### Métriques Clés à Vérifier

1. **Drawdown Maximum**
   - ✅ < 15% acceptable
   - ⚠️ 15-25% attention
   - ❌ > 25% dangereux

2. **Recovery Time**
   - Combien de temps pour récupérer après drawdown?
   - ✅ < 30 jours
   - ⚠️ 30-60 jours
   - ❌ > 60 jours

3. **Win Rate en Bear Market**
   - ✅ > 50% excellent
   - ⚠️ 40-50% acceptable
   - ❌ < 40% problématique

4. **Risk/Reward**
   - ✅ > 1:2.5 excellent
   - ⚠️ 1:1.5 - 1:2.5 acceptable
   - ❌ < 1:1.5 problématique

5. **False Signals**
   - Combien de trades perdants consécutifs?
   - ✅ < 3 consécutifs
   - ⚠️ 3-5 consécutifs
   - ❌ > 5 consécutifs

---

## 📊 Analyse des Résultats

### Après Exécution du Test

```bash
cd backtest_results_2022

# Voir résumé des trades
grep -E "ENTRY|EXIT|PROFIT|LOSS" forex_eurusd_2022.log | tail -50

# Compter trades
echo "Forex Entries: $(grep -c "ENTRY\|BUY" forex_eurusd_2022.log)"
echo "Forex Exits: $(grep -c "EXIT\|CLOSE" forex_eurusd_2022.log)"

# Check erreurs
grep -i "error" forex_eurusd_2022.log
```

### CSV Output (si généré)

Le backtest peut générer un CSV avec:
- Date/Time
- Pair
- Action (ENTRY/EXIT)
- Price
- PnL
- Reason

---

## ⚠️ Limitations & Considérations

### 1. Intervalle Daily (1d)
- Les bots sont conçus pour tourner **toutes les heures** en production
- Le backtest 1d ne capture qu'**1 décision par jour**
- **Impact**: Peut manquer des opportunités intraday ou des sorties rapides

### 2. Slippage & Frais
- Le backtest n'inclut pas:
  - Slippage d'exécution
  - Frais de courtage
  - Spread bid/ask
- **Impact**: Performance réelle sera légèrement inférieure

### 3. Bedrock AI Calls
- Le backtest peut utiliser AWS Bedrock pour validation
- **Coût**: ~$0.01 par appel (peut s'accumuler sur 365 jours)
- **Solution**: Désactiver Bedrock en mode test (si implémenté)

### 4. Macro Context
- VIX, DXY, US10Y en 2022 peuvent être limités en 1h
- Fallback automatique sur 1d pour macro data

---

## 🔧 Troubleshooting

### Erreur: "No data available"

```bash
# Vérifier manuellement
python3 -c "
import yfinance as yf
from datetime import datetime
df = yf.download('EURUSD=X', start='2022-01-01', end='2023-01-01', interval='1d')
print(f'Rows: {len(df)}')
print(df.head())
"
```

### Erreur: "1h data not available"

✅ **Normal!** Le script bascule automatiquement sur 1d.

### Backtest trop lent

- **Solution 1**: Tester bot par bot (pas en parallèle)
- **Solution 2**: Réduire période (ex: 180 jours au lieu de 365)
- **Solution 3**: Désactiver Bedrock AI si activé

---

## 📚 Fichiers Liés

- **Script automatique**: `test_2022.sh`
- **Engine backtest**: `run_test_v2.py`
- **Adapters**: `s3_adapters.py`
- **Loader**: `s3_loader.py`

---

## 🎯 Commandes Rapides

```bash
# Test 2022 complet (tous les bots)
./test_2022.sh

# Test 2022 Forex seulement
python3 run_test_v2.py --asset-class Forex --symbol EURUSD=X --days 365

# Voir résultats
tail -100 backtest_results_2022/forex_eurusd_2022.log

# Compter trades
grep -c "ENTRY" backtest_results_2022/*.log
```

---

**Date de création**: 2026-02-08
**Version**: V6.1
**Status**: ✅ Prêt à utiliser
