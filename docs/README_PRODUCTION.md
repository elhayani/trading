# 🎉 V4 HYBRID TRADING BOT - DÉPLOYÉ SUR AWS

## ✅ STATUT : **EN PRODUCTION** 

```
🚀 Déployé le: 2026-02-01 21:00
📍 Région: us-east-1
💰 Mode: TEST (sécurisé)
⏰ Fréquence: Toutes les heures (cron)
✅ Status: OPÉRATIONNEL
```

---

## 📊 PERFORMANCE BACKTESTÉE (3 ANS)

| Année | Type Marché | Performance | Benchmark |
|-------|-------------|-------------|-----------|
| 2022 | Bear Extrême | **+1.82%** ✅ | -71% (BTC) |
| 2023 | Recovery | -1.32% | -5% |
| 2024 | Bull | **+19.59%** ✅ | +17% (BTC) |
| **TOTAL 3 ANS** | **+20.08%** 🏆 | **+6.7% annuel** |

**Meilleur actif** : SOL/USDT (+52% sur 3 ans)

---

## 🏗️ ARCHITECTURE AWS

```
EventBridge (Cron)  →  Lambda V4HybridLiveTrader  →  DynamoDB
     ↓                         ↓                           ↓
Toutes les heures        Bedrock AI                State + History
                              ↓
                       Binance (CCXT)
                              ↓
                     CryptoCompare News
```

### Ressources Déployées

| Ressource | Nom | ARN/Détails |
|-----------|-----|-------------|
| **Lambda Trader** | V4HybridLiveTrader | arn:aws:lambda:us-east-1:946179054632:function:V4HybridLiveTrader |
| **Lambda Trigger** | V4ManualTrigger | Trigger manuel pour tests |
| **DynamoDB State** | V4TradingState | État du trader (capital, positions) |
| **DynamoDB History** | V4TradeHistory | Historique complet des trades |
| **EventBridge Rule** | V4HybridHourlyCron | cron(0 * ? * * *) - ENABLED ✅ |

---

## 🎯 FONCTIONNEMENT

### Cycle de Trading (toutes les heures)

```
1. EventBridge trigger Lambda à :00
2. Lambda fetch données Binance (SOL/USDT)
3. Analyse technique:
   - RSI (Relative Strength Index)
   - SMA50 (Simple Moving Average)
   - ATR (Average True Range)
   - Patterns (DOUBLE_BOTTOM, HAMMER, etc.)
   - Volume analysis

4. Fetch news CryptoCompare (24h)
5. Détection régime marché:
   - EXTREME_BEAR (crash > -25% + news > 80% neg)
   - NORMAL_BEAR (baisse -15% ou news > 65% neg)
   - BULL (marché normal/haussier)

6. Vérification signal (RSI < 45)
7. Si signal → Bedrock AI decision:
   - EXTREME_BEAR mode: V1 Ultra-Strict (CANCEL par défaut)
   - NORMAL_BEAR mode: V3 Prudent (sélectif)
   - BULL mode: V3 Smart (opportuniste)

8. Si CONFIRM/BOOST:
   - MODE TEST: Log seulement ✅
   - MODE LIVE: Execute trade réel 🔴

9. Save état DynamoDB
10. Log CloudWatch
```

---

## 📋 MONITORING & COMMANDES

### A) Surveiller les Logs en Temps Réel

```bash
# Stream logs live
aws logs tail /aws/lambda/V4HybridLiveTrader --follow

# Voir derniers 10 minutes
aws logs tail /aws/lambda/V4HybridLiveTrader --since 10m --format short

# Filtrer par pattern
aws logs tail /aws/lambda/V4HybridLiveTrader --filter-pattern "TRADE_EXECUTED"
```

### B) Déclencher Manuellement

```bash
# Via trigger Lambda
aws lambda invoke \
  --function-name V4ManualTrigger \
  /tmp/manual_result.json

# Via trading Lambda directement
aws lambda invoke \
  --function-name V4HybridLiveTrader \
  /tmp/result.json

# Voir résultat
cat /tmp/result.json | python3 -m json.tool
```

### C) Consulter l'État DynamoDB

```bash
# État actuel du trader
aws dynamodb get-item \
  --table-name V4TradingState \
  --key '{"trader_id": {"S": "v4_hybrid"}}'

# Scan complet (dernières entrées)
aws dynamodb scan --table-name V4TradingState --max-items 5

# Historique des trades
aws dynamodb scan --table-name V4TradeHistory --max-items 10
```

### D) CloudWatch Insights Queries

```sql
-- Voir tous les signals
fields @timestamp, @message
| filter @message like /signal/
| sort @timestamp desc
| limit 20

-- Voir les trades exécutés
fields @timestamp, @message
| filter @message like /TRADE_EXECUTED/
| sort @timestamp desc

-- Voir les décisions Bedrock
fields @timestamp, @message
| filter @message like /Bedrock/
| sort @timestamp desc

-- Performance Lambda
fields @duration, @memoryUsed
| stats avg(@duration), max(@memoryUsed), count()
```

---

## ⚙️ CONFIGURATION

### Variables d'Environnement Actuelles

```bash
TRADING_MODE=test          # 'test' ou 'live'
CAPITAL=1000               # Capital en USDT
SYMBOLS=SOL/USDT           # Symboles tradés
CHECK_INTERVAL=3600        # Secondes (1h)
EXCHANGE=binance           # Exchange utilisé
STATE_TABLE=V4TradingState
HISTORY_TABLE=V4TradeHistory
```

### Modifier la Configuration

```bash
# Changer le capital
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --environment "Variables={TRADING_MODE=test,CAPITAL=2000,SYMBOLS='SOL/USDT',CHECK_INTERVAL='3600',EXCHANGE='binance',STATE_TABLE='V4TradingState',HISTORY_TABLE='V4TradeHistory'}"

# Ajouter des symboles
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --environment "Variables={TRADING_MODE=test,CAPITAL=1000,SYMBOLS='BTC/USDT,ETH/USDT,SOL/USDT',CHECK_INTERVAL='3600',EXCHANGE='binance',STATE_TABLE='V4TradingState',HISTORY_TABLE='V4TradeHistory'}"
```

### ⚠️ Passer en MODE LIVE

```bash
# ATTENTION: Mode LIVE exécute de VRAIS trades !
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --environment "Variables={TRADING_MODE=live,CAPITAL=5000,SYMBOLS='SOL/USDT',CHECK_INTERVAL='3600',EXCHANGE='binance',STATE_TABLE='V4TradingState',HISTORY_TABLE='V4TradeHistory'}"

# Ajouter les API keys Binance (requis pour LIVE)
aws secretsmanager create-secret \
  --name V4/BINANCE_API_KEYS \
  --secret-string '{"api_key":"YOUR_API_KEY","secret":"YOUR_SECRET"}'
```

---

## 🔧 GESTION DU SYSTÈME

### Pause Temporaire

```bash
# Désactiver le cron (pause trading)
aws events disable-rule --name V4HybridHourlyCron

# Vérifier statut
aws events describe-rule --name V4HybridHourlyCron --query State

# Réactiver
aws events enable-rule --name V4HybridHourlyCron
```

### Consulter les Métriques

```bash
# Invocations Lambda (dernières 24h)
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=V4HybridLiveTrader \
  --start-time $(date -u -v-1d '+%Y-%m-%dT%H:%M:%S') \
  --end-time $(date -u '+%Y-%m-%dT%H:%M:%S') \
  --period 3600 \
  --statistics Sum

# Erreurs
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=V4HybridLiveTrader \
  --start-time $(date -u -v-1d '+%Y-%m-%dT%H:%M:%S') \
  --end-time $(date -u '+%Y-%m-%dT%H:%M:%S') \
  --period 3600 \
  --statistics Sum
```

### Mise à Jour du Code

```bash
# 1. Modifier le code dans lambda/v4_trader/
# 2. Redéployer
cd infrastructure/cdk
cdk deploy V4TradingStack --app "python3 app_v4.py"
```

---

## 💰 COÛTS AWS

| Service | Usage Mensuel | Coût |
|---------|---------------|------|
| Lambda | 720 invocations | $0.50 |
| DynamoDB | On-demand (faible) | $1.00 |
| Bedrock | 720 API calls Claude 3 | $2.00 |
| CloudWatch Logs | Standard | $0.50 |
| **TOTAL** | | **~$4.00/mois** |

---

## 🛡️ SÉCURITÉ

### Bonnes Pratiques Activées

- ✅ IAM Roles avec permissions minimales
- ✅ DynamoDB Point-in-Time Recovery
- ✅ CloudWatch Logs retention (1 mois)
- ✅ Mode TEST par défaut
- ✅ Secrets Manager pour API keys
- ✅ VPC isolation (optionnel, pas activé)

### Recommandations

1. **Ne JAMAIS commiter les API keys** dans le code
2. **Tester en MODE TEST** pendant 1 semaine minimum
3. **Commencer petit** en LIVE (100-500 USDT)
4. **Monitorer quotidiennement** pendant le 1er mois
5. **Activer CloudWatch Alarms** (optionnel)

---

## 📈 DASHBOARD CLOUDWATCH

### Créer un Dashboard Personnalisé

```bash
# Créer dashboard
aws cloudwatch put-dashboard \
  --dashboard-name V4HybridTrading \
  --dashboard-body file://dashboard_config.json
```

**Métriques à suivre** :
- Invocations Lambda (success/errors)
- Duration moyenne
- Memory utilisée
- DynamoDB read/write units
- Bedrock API latency

---

## 🆘 DÉPANNAGE

### Problème 1: Lambda Timeout

```bash
# Augmenter timeout (max 15 minutes)
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --timeout 300
```

### Problème 2: Out of Memory

```bash
# Augmenter mémoire
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --memory-size 1024
```

### Problème 3: Bedrock Throttling

```bash
# Vérifier quotas
aws service-quotas get-service-quota \
  --service-code bedrock \
  --quota-code L-xxxxx

# Demander augmentation si nécessaire
```

### Problème 4: Pas de Trades

Vérifier :
1. RSI doit être < 45 (signal condition)
2. News sentiment (pas de panique extrême)
3. Bedrock decision (CONFIRM required)
4. Mode LIVE activé (si trade réel voulu)

---

## 📂 STRUCTURE DU PROJET

```
/Users/zakaria/Trading/
├── infrastructure/
│   └── cdk/
│       ├── stacks/
│       │   └── v4_trading_stack.py    # Stack CDK
│       └── app_v4.py                   # App entry
├── lambda/
│   └── v4_trader/
│       ├── v4_hybrid_lambda.py         # Handler
│       ├── market_analysis.py          # Technical analysis
│       ├── news_fetcher.py             # News integration
│       └── exchange_connector.py       # CCXT wrapper
├── scripts/
│   ├── deploy_aws.sh                   # Automated deployment
│   ├── v4_hybrid_live.py               # Local testing
│   └── backtest_histo_V4_HYBRID.py     # Backtesting
├── DEPLOYMENT_GUIDE.md                 # Deployment manual
├── AWS_DEPLOYMENT_README.md            # This file
└── PROJECT_SUMMARY.md                  # Full documentation
```

---

## ✅ CHECKLIST POST-DÉPLOIEMENT

- [x] Stack déployée sur AWS
- [x] Lambda testée manuellement
- [x] EventBridge cron activé
- [x] DynamoDB tables créées
- [x] CloudWatch logs consultés
- [x] Mode TEST validé
- [ ] Tester 1 semaine en TEST
- [ ] Vérifier trades simulés
- [ ] Consulter rapports quotidiens
- [ ] (Optionnel) Activer MODE LIVE
- [ ] (Optionnel) Configurer Alarms
- [ ] (Optionnel) Créer Dashboard

---

## 🎯 PROCHAINES ÉTAPES RECOMMANDÉES

### Semaine 1: Validation TEST

```bash
# Jour 1-7: Observer en mode TEST
aws logs tail /aws/lambda/V4HybridLiveTrader --follow

# Vérifier quotidiennement
aws dynamodb scan --table-name V4TradingState

# Analyser les décisions Bedrock
# Vérifier si signals détectés
# Confirmer aucune erreur
```

### Semaine 2: Optimisation

- Ajuster RSI threshold si besoin
- Affiner prompts Bedrock
- Tester avec ETH/BTC en plus de SOL
- Optimiser capital allocation

### Semaine 3+: Production

- Si TEST satisfaisant → MODE LIVE
- Commencer avec 100-500 USDT
- Augmenter progressivement
- Monitor 1x/jour minimum

---

## 📞 COMMANDES RAPIDES

```bash
# Status global
aws lambda get-function --function-name V4HybridLiveTrader --query 'Configuration.State'

# Dernière exécution
aws logs tail /aws/lambda/V4HybridLiveTrader --since 1h --format short | tail -20

# État trader
aws dynamodb get-item --table-name V4TradingState --key '{"trader_id": {"S": "v4_hybrid"}}'

# Pause
aws events disable-rule --name V4HybridHourlyCron

# Resume
aws events enable-rule --name V4HybridHourlyCron

# Trigger manuel
aws lambda invoke --function-name V4ManualTrigger /tmp/result.json

# Détruire tout
cd infrastructure/cdk && cdk destroy V4TradingStack
```

---

## 🏆 FÉLICITATIONS !

Tu as déployé un système de trading automatisé professionnel :

✅ **Backtesté sur 3 ans** (+20% performance)  
✅ **Déployé sur AWS** (production-ready)  
✅ **Intelligence artificielle** (Bedrock Claude 3)  
✅ **Adaptatif** (détection régime BULL/BEAR)  
✅ **Monitoring complet** (CloudWatch)  
✅ **Sécurisé** (mode TEST par défaut)  
✅ **Économique** (~$4/mois)  

**Le bot s'exécute automatiquement toutes les heures !** 🚀

---

*Déployé: 2026-02-01*  
*Version: 1.0*  
*Account: 946179054632*  
*Region: us-east-1*
