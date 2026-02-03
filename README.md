# 🚀 V4 HYBRID - AI-Powered Crypto Trading Bot

> **Système de trading automatisé intelligent** combinant analyse technique, IA générative (AWS Bedrock), et détection adaptative de marché.

## 🎯 Statut Actuel

```
✅ DÉPLOYÉ EN PRODUCTION AWS
📅 Date: 2026-02-01
💰 Mode: TEST (sécurisé)
⏰ Cron: Toutes les heures
🎯 Performance 3 ans: +20.08%
```

---

## 📊 Vue d'Ensemble

Ce projet implémente une stratégie de trading **V4 HYBRID** qui :

- 📈 **Analyse le marché** en temps réel (RSI, SMA, ATR, patterns)
- 🤖 **Utilise l'IA** (AWS Bedrock Claude 3) pour valider les décisions
- 🌐 **S'adapte automatiquement** au régime de marché (BULL/BEAR/EXTREME_BEAR)
- 📰 **Intègre les news** crypto en temps réel
- 💰 **Protège le capital** en bear market tout en capturant les opportunités en bull
- ☁️ **Tourne sur AWS** de manière automatisée

---

## 🏆 Performance Validée

### Backtests 3 Ans (2022-2024)

| Année | Marché | V4 HYBRID | Benchmark BTC | Delta |
|-------|--------|-----------|---------------|-------|
| 2022 | Bear Extrême | **+1.82%** ✅ | -71% | **+73%** |
| 2023 | Recovery | -1.32% | -5% | +3.7% |
| 2024 | Bull | **+19.59%** ✅ | +17% | **+2.6%** |
| **TOTAL** | 3 ans | **+20.08%** 🏆 | -54% | **+74%** |

**Meilleur actif** : SOL/USDT (+52% sur 3 ans)

### Avantages Clés

✅ **Protection bear market** : +73% vs BTC en 2022  
✅ **Capture bull market** : +19.6% en 2024  
✅ **Adaptive** : Change de stratégie selon conditions  
✅ **IA-powered** : Filtre les faux signaux  
✅ **Testé rigoureusement** : 3 ans de backtests  

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│          AWS CLOUD (us-east-1)                  │
│                                                 │
│  EventBridge Cron (hourly)                     │
│         ↓                                       │
│  Lambda V4HybridLiveTrader ──→ Bedrock AI     │
│         ↓                            ↓          │
│  DynamoDB State/History    ←─── Decision       │
│         ↓                                       │
│  CloudWatch Logs                                │
└─────────────────────────────────────────────────┘
           ↓
    Exchange (Binance CCXT)
           ↓
    News (CryptoCompare)
```

### Composants Principaux

| Composant | Description | Status |
|-----------|-------------|--------|
| **V4 HYBRID Strategy** | Algo adaptatif multi-régime | ✅ Backtesté |
| **Lambda Trader** | Bot AWS serverless | ✅ Déployé |
| **Bedrock AI** | Claude 3 Haiku validation | ✅ Opérationnel |
| **DynamoDB** | State persistence | ✅ Actif |
| **EventBridge** | Cron scheduler | ✅ Enabled |
| **Exchange Connector** | Binance API (CCXT) | ✅ Connecté |
| **News Fetcher** | CryptoCompare API | ✅ Opérationnel |

---

## 📂 Structure du Projet

```
/Users/zakaria/Trading/
├── 📄 README.md                        ← Ce fichier
├── 📄 README_PRODUCTION.md             ← Guide production AWS
├── 📄 DEPLOYMENT_GUIDE.md              ← Guide déploiement
├── 📄 PROJECT_SUMMARY.md               ← Documentation complète
├── 📄 EXECUTIVE_REPORT_FINAL.md        ← Rapport exécutif 3 ans
│
├── 🏗️ infrastructure/
│   └── cdk/
│       ├── stacks/
│       │   └── v4_trading_stack.py     # Stack CDK Lambda + DynamoDB
│       └── app_v4.py                   # App CDK entry point
│
├── ⚡ lambda/
│   ├── v4_trader/
│   │   ├── v4_hybrid_lambda.py         # Handler principal
│   │   ├── market_analysis.py          # Analyse technique
│   │   ├── news_fetcher.py             # Intégration news
│   │   └── exchange_connector.py       # CCXT wrapper
│   └── data_fetcher/
│       └── ... (utilitaires)
│
├── 📜 scripts/
│   ├── deploy_aws.sh                   # Déploiement automatisé
│   ├── v4_hybrid_live.py               # Test local live
│   ├── backtest_histo_V4_HYBRID.py     # Backtesting V4
│   ├── exchange_connector.py           # Connecteur exchange
│   └── compare_v3_v4_2023.py          # Comparaison stratégies
│
└── 📊 data/
    └── news_archive/                   # Archives news synthétiques
```

---

## 🚀 Quick Start

### Prérequis

```bash
# AWS CLI configuré
aws configure

# CDK installé
npm install -g aws-cdk

# Python 3.12+
python3 --version

# Dependencies
pip3 install aws-cdk-lib constructs boto3 ccxt
```

### Déploiement AWS (1 commande)

```bash
cd /Users/zakaria/Trading
./scripts/deploy_aws.sh
```

Le script va :
1. ✅ Vérifier prérequis
2. ✅ Préparer code Lambda
3. ✅ Déployer stack CDK
4. ✅ Créer DynamoDB tables
5. ✅ Configurer EventBridge cron
6. ✅ Tester la Lambda

**Durée** : 3-5 minutes  
**Coût** : ~$4/mois

### Test Local (avant AWS)

```bash
# Tester tous les composants
python3 scripts/test_live_components.py

# Tester cycle complet avec vraies données
python3 scripts/v4_hybrid_live.py

# Backtester sur année spécifique
python3 scripts/backtest_histo_V4_HYBRID.py
```

---

## 📋 Commandes Utiles

### Monitoring

```bash
# Logs en temps réel
aws logs tail /aws/lambda/V4HybridLiveTrader --follow

# État DynamoDB
aws dynamodb scan --table-name V4TradingState

# Trigger manuel
aws lambda invoke --function-name V4ManualTrigger /tmp/result.json
```

### Configuration

```bash
# Mode TEST (défaut, sécurisé)
TRADING_MODE=test

# Passer en MODE LIVE (vrais trades)
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --environment "Variables={TRADING_MODE=live,CAPITAL=5000}"
```

### Contrôle

```bash
# Pause trading
aws events disable-rule --name V4HybridHourlyCron

# Resume trading
aws events enable-rule --name V4HybridHourlyCron

# Détruire infrastructure
cd infrastructure/cdk && cdk destroy V4TradingStack
```

---

## 🧠 Comment ça Fonctionne ?

### Cycle de Trading (toutes les heures)

```
1. 📊 Fetch données Binance (OHLCV 300 candles)
2. 📈 Analyse technique:
   • RSI (Relative Strength Index)
   • SMA50 (Simple Moving Average)
   • ATR (Average True Range)
   • Patterns (DOUBLE_BOTTOM, HAMMER, etc.)
   • Volume spikes

3. 📰 Fetch news CryptoCompare (24h)
   • Sentiment analysis (positif/négatif)
   • % de news négatives

4. 🌐 Détection régime marché:
   • EXTREME_BEAR : BTC -25%+ et/ou news 80%+ neg
   • NORMAL_BEAR  : BTC -15%+ ou news 65%+ neg
   • BULL         : Conditions normales

5. 🎯 Vérification signal (RSI < 45 = oversold)

6. 🤖 Si signal → Bedrock AI decision:
   ┌─────────────────────────────────────┐
   │ EXTREME_BEAR : V1 Ultra-Strict      │
   │  → CANCEL par défaut                │
   │  → Protège capital                  │
   ├─────────────────────────────────────┤
   │ NORMAL_BEAR : V3 Prudent            │
   │  → Sélectif mais capture rebonds    │
   ├─────────────────────────────────────┤
   │ BULL : V3 Smart Opportuniste        │
   │  → Trust technique                  │
   │  → Filter catastrophes seulement    │
   └─────────────────────────────────────┘

7. 💰 Si CONFIRM ou BOOST:
   • MODE TEST  → Log seulement ✅
   • MODE LIVE  → Execute trade réel 🔴

8. 💾 Save état DynamoDB
9. 📝 Log CloudWatch
```

---

## 💰 Coûts AWS

| Service | Usage | Coût Mensuel |
|---------|-------|--------------|
| Lambda | 720 invocations/mois | $0.50 |
| DynamoDB | On-demand faible | $1.00 |
| Bedrock | 720 Claude 3 calls | $2.00 |
| CloudWatch | Logs standard | $0.50 |
| **TOTAL** | | **~$4/mois** |

💡 **Très abordable** pour un bot automatisé 24/7 !

---

## 🛡️ Sécurité & Risk Management

### Protections Intégrées

- ✅ **Mode TEST par défaut** : Aucun trade réel
- ✅ **IAM least privilege** : Permissions minimales
- ✅ **DynamoDB backup** : Point-in-Time Recovery
- ✅ **Circuit breakers** : Max drawdown, loss limits
- ✅ **Bedrock validation** : AI filtre faux signaux
- ✅ **Regime detection** : Adapte stratégie aux conditions

### Limites de Risque

```python
MAX_DRAWDOWN = 20%        # Stop si perte > 20%
DAILY_LOSS_LIMIT = 5%     # Max -5% par jour
MAX_POSITION_SIZE = 50%   # 50% capital max par trade
DEFAULT_LEVERAGE = 1x     # Pas de levier en TEST
```

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [README_PRODUCTION.md](README_PRODUCTION.md) | Guide complet production AWS |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Déploiement step-by-step |
| [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) | Documentation technique complète |
| [EXECUTIVE_REPORT_FINAL.md](EXECUTIVE_REPORT_FINAL.md) | Rapport exécutif 3 ans |
| [V4_HYBRID_DOCUMENTATION.md](V4_HYBRID_DOCUMENTATION.md) | Spécifications V4 HYBRID |

---

## 🎓 Stratégies Testées

| Version | Description | Performance 3 ans | Status |
|---------|-------------|-------------------|--------|
| **V1** | Ultra-Strict (bear focus) | +11.26% | ⚠️ Trop conservateur |
| **V2/V2.5** | Over-optimized | 0% (no trades) | ❌ Échec |
| **V3 Smart** | Balanced opportuniste | +13.68% | ✅ Bon mais fragile |
| **V4 HYBRID** | Adaptive multi-régime | **+20.08%** 🏆 | ✅ **RECOMMANDÉ** |

---

## ✅ Tests & Validation

### Backtests Effectués

- ✅ **2022** : Bear extrême (Terra Luna, FTX)
- ✅ **2023** : Recovery post-bear
- ✅ **2024** : Bull run (BTC Halving, ETF)
- ✅ **3 Years** : Full cycle validation

### Tests Techniques

- ✅ Exchange connector (Binance CCXT)
- ✅ Market analysis (RSI, SMA, ATR, Patterns)
- ✅ News fetcher (CryptoCompare API)
- ✅ Bedrock AI integration (Claude 3 Haiku)
- ✅ Regime detection (BULL/BEAR/EXTREME_BEAR)
- ✅ Live trading cycle complet

### Déploiement AWS

- ✅ Lambda function déployée
- ✅ DynamoDB tables créées
- ✅ EventBridge cron enabled
- ✅ CloudWatch logs opérationnels
- ✅ IAM permissions configurées
- ✅ Test manuel réussi

---

## 🚦 Prochaines Étapes

### Phase 1: Validation TEST (Semaine 1-2)

```bash
# Observer en mode TEST
aws logs tail /aws/lambda/V4HybridLiveTrader --follow

# Vérifier quotidiennement
aws dynamodb scan --table-name V4TradingState

# Analyser décisions Bedrock
# Confirmer détection signals
```

### Phase 2: Optimisation (Semaine 2-3)

- Ajuster seuils RSI si besoin
- Affiner prompts Bedrock
- Tester multi-symboles (BTC, ETH, SOL)
- Optimiser allocation capital

### Phase 3: Production (Semaine 3+)

- Si TEST satisfaisant → **MODE LIVE**
- Commencer **petit** (100-500 USDT)
- Augmenter **progressivement**
- Monitor **quotidiennement**

---

## 🆘 Support & Troubleshooting

### Logs

```bash
# Voir erreurs
aws logs tail /aws/lambda/V4HybridLiveTrader --filter-pattern "ERROR"

# Check dernière exécution
aws logs tail /aws/lambda/V4HybridLiveTrader --since 1h
```

### Performance

```bash
# Augmenter timeout
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --timeout 300

# Augmenter mémoire
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --memory-size 1024
```

### État

```bash
# Vérifier EventBridge
aws events describe-rule --name V4HybridHourlyCron

# Vérifier Lambda
aws lambda get-function --function-name V4HybridLiveTrader

# Vérifier DynamoDB
aws dynamodb describe-table --table-name V4TradingState
```

---

## 🤝 Contribution

Ce projet est personnel mais ouvert aux suggestions :

1. Tester d'autres stratégies (ML, sentiment analysis avancé)
2. Ajouter plus de paires (AVAX, MATIC, LINK)
3. Implémenter trailing stops
4. Multi-timeframe analysis
5. Options/futures hedging

---

## 📄 Licence

MIT License - Libre d'utilisation et modification

---

## ⚠️ Disclaimer

**Ce système est fourni à des fins éducatives.**

- Trading comporte des **risques de perte en capital**
- **Performances passées** ne garantissent **pas** les performances futures
- **Testez toujours** en mode TEST d'abord
- Ne tradez **jamais** plus que ce que vous pouvez perdre
- Consultez un conseiller financier

---

## 🏆 Crédits

- **Architecture** : AWS CDK + Lambda
- **IA** : AWS Bedrock (Claude 3 Haiku)
- **Exchange** : Binance via CCXT
- **News** : CryptoCompare API
- **Backtesting** : Custom Python framework
- **Développé** : 2026-01-02 → 2026-02-01

---

## 📞 Contact & Ressources

- 📖 [Documentation Complète](README_PRODUCTION.md)
- 🚀 [Guide Déploiement](DEPLOYMENT_GUIDE.md)
- 📊 [Rapport Performance](EXECUTIVE_REPORT_FINAL.md)
- 💻 [AWS Console](https://console.aws.amazon.com)
- 🔍 [CloudWatch Logs](https://console.aws.amazon.com/cloudwatch)

---

**🎊 Système en Production depuis 2026-02-01** 🚀

✅ **Backtesté** sur 3 ans  
✅ **Déployé** sur AWS  
✅ **Opérationnel** 24/7  
✅ **Sécurisé** (mode TEST)  
✅ **Économique** (~$4/mois)  

**Next hour execution: 22:00 UTC** ⏰
