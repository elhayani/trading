# 🚀 GUIDE DÉPLOIEMENT - ARCHITECTURE 3-LAMBDA

## Vue d'Ensemble

```
┌─────────────────────────────────────────────────────────┐
│              Architecture 3-Lambda                       │
├──────────────┬──────────────────┬───────────────────────┤
│  Lambda 1    │    Lambda 2      │     Lambda 3          │
│  SCANNER     │    CLOSER 20s    │     CLOSER 40s        │
│  (1 minute)  │    (20 sec)      │     (40 sec)          │
├──────────────┼──────────────────┼───────────────────────┤
│ • Scan 50    │ • Check OPEN     │ • Check OPEN          │
│ • Filter TA  │ • Fetch price    │ • Fetch price         │
│ • Bedrock    │ • Close TP/SL    │ • Close TP/SL         │
│ • OPEN only  │ • NO scan        │ • NO scan             │
│ • 1536 MB    │ • 256 MB         │ • 256 MB              │
│ • 55s timeout│ • 18s timeout    │ • 18s timeout         │
└──────────────┴──────────────────┴───────────────────────┘
```

## 📋 PRÉREQUIS

### 1. AWS CLI Configuré
```bash
aws configure
# Entrer: Access Key, Secret Key, Region (eu-west-3)
```

### 2. CDK Installé
```bash
npm install -g aws-cdk
cdk --version  # Doit être >= 2.100.0
```

### 3. Python 3.12
```bash
python3 --version  # >= 3.12
```

### 4. Secrets Manager - Clés Binance
```bash
aws secretsmanager create-secret \
    --name trading/binance \
    --secret-string '{"api_key":"YOUR_KEY","api_secret":"YOUR_SECRET"}' \
    --region eu-west-3
```

---

## 📁 STRUCTURE FICHIERS

```
lambda/
├── v4_trader/
│   ├── lambda1_scanner.py          # ⭐ NOUVEAU
│   ├── lambda2_closer.py           # ⭐ NOUVEAU
│   ├── v4_hybrid_lambda.py         # Existant (TradingEngine class)
│   ├── config.py                   # ⭐ REMPLACER par config_3lambda.py
│   ├── binance_scanner.py          # Existant
│   ├── market_analysis.py          # Existant
│   ├── decision_engine.py          # Existant
│   ├── risk_manager.py             # Existant
│   ├── exchange_connector.py       # Existant
│   ├── models.py                   # Existant
│   ├── news_fetcher.py             # Existant
│   ├── binance_metrics.py          # Existant
│   ├── atomic_persistence.py       # Existant
│   ├── anti_spam_helpers.py        # Existant
│   ├── trim_switch.py              # Existant
│   ├── macro_context.py            # Existant
│   ├── micro_corridors.py          # Existant
│   └── reporter.py                 # Existant (Reporter)
│
├── layer/
│   └── python/
│       └── (ccxt, pandas, boto3, etc.)
│
cdk/
├── app.py                          # Existant (point d'entrée CDK)
├── stacks/
│   ├── v4_trading_stack.py         # ⭐ REMPLACER par v4_trading_stack_3lambdas.py
│   
requirements.txt
cdk.json
```

---

## 🔧 ÉTAPE 1: PRÉPARER LES FICHIERS

### 1.1 Copier les nouveaux fichiers Lambda

```bash
# Aller dans le dossier lambda
cd lambda/v4_trader/

# Copier les nouveaux handlers
cp /home/claude/lambda1_scanner.py ./
cp /home/claude/lambda2_closer.py ./

# Remplacer config.py
cp /home/claude/config_3lambda.py ./config.py

# Vérifier
ls -lh lambda*.py config.py
```

### 1.2 Mettre à jour le stack CDK

```bash
cd cdk/stacks/

# Backup ancien stack
cp v4_trading_stack.py v4_trading_stack_BACKUP.py

# Copier nouveau stack
cp /home/claude/v4_trading_stack_3lambdas.py ./v4_trading_stack.py
```

---

## 🚀 ÉTAPE 2: DÉPLOYER L'INFRASTRUCTURE

### 2.1 Bootstrap CDK (première fois seulement)

```bash
cd cdk/
cdk bootstrap aws://946179054632/eu-west-3
```

### 2.2 Synthétiser le stack

```bash
cdk synth
```

**Vérifier la sortie** :
- ✅ 3 Lambdas créées : `V4_Lambda1_Scanner`, `V4_Lambda2_Closer20s`, `V4_Lambda3_Closer40s`
- ✅ 3 EventBridge rules : `V4_Scanner_1min`, `V4_Closer_20s`, `V4_Closer_40s`
- ✅ DynamoDB tables : `V4TradingState`, `EmpireTradesHistory`, `EmpireSkippedTrades`

### 2.3 Déployer

```bash
cdk deploy --all
```

**Confirmer** : Tape `y` quand demandé

**Durée attendue** : 5-10 minutes

---

## ✅ ÉTAPE 3: VÉRIFICATION POST-DÉPLOIEMENT

### 3.1 Vérifier les Lambdas

```bash
# Lister les lambdas
aws lambda list-functions --region eu-west-3 --query 'Functions[?starts_with(FunctionName, `V4_`)].FunctionName'

# Devrait afficher:
# - V4_Lambda1_Scanner
# - V4_Lambda2_Closer20s
# - V4_Lambda3_Closer40s
# - V4StatusReporter
# - V4ManualTrigger
```

### 3.2 Vérifier EventBridge

```bash
# Lister les rules
aws events list-rules --region eu-west-3 --name-prefix V4_

# Devrait afficher:
# - V4_Scanner_1min (cron: * * * * ? *)
# - V4_Closer_20s (cron: * * * * ? *)
# - V4_Closer_40s (cron: * * * * ? *)
```

### 3.3 Vérifier DynamoDB

```bash
# Lister les tables
aws dynamodb list-tables --region eu-west-3

# Devrait inclure:
# - V4TradingState
# - EmpireTradesHistory
# - EmpireSkippedTrades
```

---

## 🧪 ÉTAPE 4: TESTS MANUELS

### 4.1 Test Lambda 1 (Scanner)

```bash
# Invoquer manuellement
aws lambda invoke \
    --function-name V4_Lambda1_Scanner \
    --region eu-west-3 \
    --payload '{"manual": true}' \
    response.json

# Voir la réponse
cat response.json | jq '.'
```

**Résultat attendu** :
```json
{
  "statusCode": 200,
  "body": {
    "lambda": "SCANNER",
    "candidates_found": 15,
    "positions_opened": 2,
    "opportunities_skipped": 13,
    "duration_seconds": 12.5
  }
}
```

### 4.2 Test Lambda 2 (Closer 20s)

```bash
aws lambda invoke \
    --function-name V4_Lambda2_Closer20s \
    --region eu-west-3 \
    response2.json

cat response2.json | jq '.'
```

**Résultat attendu** :
```json
{
  "statusCode": 200,
  "body": {
    "lambda": "CLOSER_20S",
    "positions_checked": 2,
    "positions_closed": 0,
    "duration_seconds": 0.8
  }
}
```

### 4.3 Test Lambda 3 (Closer 40s)

```bash
aws lambda invoke \
    --function-name V4_Lambda3_Closer40s \
    --region eu-west-3 \
    response3.json

cat response3.json | jq '.'
```

---

## 📊 ÉTAPE 5: MONITORING

### 5.1 CloudWatch Logs

```bash
# Logs Lambda 1
aws logs tail /aws/lambda/V4_Lambda1_Scanner --follow

# Logs Lambda 2
aws logs tail /aws/lambda/V4_Lambda2_Closer20s --follow

# Logs Lambda 3
aws logs tail /aws/lambda/V4_Lambda3_Closer40s --follow
```

### 5.2 CloudWatch Metrics

Aller dans **AWS Console > CloudWatch > Dashboards**

Créer un dashboard avec :
- **Lambda 1** : Invocations, Duration, Errors
- **Lambda 2** : Invocations, Duration
- **Lambda 3** : Invocations, Duration
- **DynamoDB** : ConsumedReadCapacityUnits, ConsumedWriteCapacityUnits

### 5.3 Métriques Custom (via CloudWatch Insights)

```sql
-- Nombre de positions ouvertes par heure
fields @timestamp, body.positions_opened as opened
| filter @message like /SCANNER/
| stats sum(opened) by bin(1h)

-- Win rate (positions fermées)
fields body.closed_details[0].pnl_pct as pnl
| filter pnl > 0 or pnl < 0
| stats count(*) as total, 
        sum(case when pnl > 0 then 1 else 0 end) as wins,
        avg(pnl) as avg_pnl

-- Durée moyenne des Lambdas
fields @duration
| stats avg(@duration) by @log
```

---

## ⚠️ ÉTAPE 6: TROUBLESHOOTING

### Problème 1: Lambda timeout

**Symptôme** : Lambda 1 timeout après 55s

**Solution** :
```bash
# Augmenter timeout
aws lambda update-function-configuration \
    --function-name V4_Lambda1_Scanner \
    --timeout 90 \
    --region eu-west-3
```

### Problème 2: Positions ne se ferment pas

**Symptôme** : Lambdas 2/3 ne closent pas les positions

**Causes possibles** :
1. TP/SL non atteints
2. Pas de positions OPEN dans DynamoDB
3. Erreur connexion Binance

**Diagnostic** :
```bash
# Vérifier positions dans DynamoDB
aws dynamodb query \
    --table-name V4TradingState \
    --index-name status-timestamp-index \
    --key-condition-expression "#status = :open" \
    --expression-attribute-names '{"#status":"status"}' \
    --expression-attribute-values '{":open":{"S":"OPEN"}}' \
    --region eu-west-3
```

### Problème 3: Trop de trades ouverts simultanément

**Symptôme** : MAX_OPEN_TRADES dépassé

**Solution** : Ajuster config.py
```python
MAX_OPEN_TRADES = 8  # Augmenter de 6 à 8
```

Puis redéployer :
```bash
cdk deploy
```

---

## 📈 ÉTAPE 7: OPTIMISATION

### 7.1 Ajuster les seuils TP/SL

Si win rate < 55% après 50 trades :

```python
# config.py
TP_QUICK = 0.0030  # Augmenter de 0.25% à 0.30%
SL = 0.0025        # Augmenter de 0.20% à 0.25%
```

### 7.2 Ajuster fréquence scan

Si pas assez de trades (< 8/jour) :

```python
# config.py
MIN_TECHNICAL_SCORE_CRYPTO = 50  # Baisser de 55 à 50
ADX_MIN_TREND = 12.0              # Baisser de 15 à 12
```

### 7.3 Ajuster levier

Si drawdowns trop élevés (> -5% jour) :

```python
# config.py
LEVERAGE = 4  # Réduire de 5 à 4
```

---

## 🎯 PERFORMANCE ATTENDUE

### Objectifs (Config actuelle)

- **Trades/jour** : 10-12
- **Win Rate** : 58%
- **Gain moyen par trade** : +1.28% (win) / -1.40% (loss)
- **Gain journalier** : +1% (espérance)
- **Gain mensuel** : +22% (composé sur 20 jours)

### Seuils d'Alerte

🔴 **STOP si** :
- Win rate < 50% sur 30 trades
- Daily loss > -5%
- 3 pertes consécutives

🟡 **REVIEW si** :
- Win rate 50-55% sur 50 trades
- Daily gain < +0.5% pendant 3 jours
- Moins de 5 trades/jour pendant 2 jours

🟢 **ON TRACK si** :
- Win rate 55-65%
- Daily gain +0.8% à +1.5%
- 8-15 trades/jour

---

## 🔄 ÉTAPE 8: ROLLBACK (si besoin)

Si problèmes majeurs, revenir à l'ancien système :

```bash
cd cdk/stacks/

# Restaurer ancien stack
cp v4_trading_stack_BACKUP.py v4_trading_stack.py

# Redéployer
cd ..
cdk deploy
```

---

## 📞 SUPPORT

### Logs utiles

```bash
# Derniers 100 logs Lambda 1
aws logs tail /aws/lambda/V4_Lambda1_Scanner --since 1h

# Rechercher erreurs
aws logs filter-log-events \
    --log-group-name /aws/lambda/V4_Lambda1_Scanner \
    --filter-pattern "ERROR" \
    --region eu-west-3
```

### Métriques DynamoDB

```bash
# Nombre d'items dans chaque table
aws dynamodb describe-table \
    --table-name V4TradingState \
    --query 'Table.ItemCount' \
    --region eu-west-3
```

---

## ✅ CHECKLIST FINALE

- [ ] 3 Lambdas déployées
- [ ] 3 EventBridge rules actives
- [ ] DynamoDB tables créées
- [ ] Secrets Manager configuré
- [ ] Test manuel Lambda 1 réussi
- [ ] Test manuel Lambda 2 réussi
- [ ] Test manuel Lambda 3 réussi
- [ ] CloudWatch logs visibles
- [ ] Au moins 1 position ouverte après 1h
- [ ] Au moins 1 position fermée après 2h
- [ ] Monitoring dashboard configuré

---

## 🚀 NEXT STEPS

1. **Jour 1-3** : Mode TEST avec capital $100
2. **Jour 4-7** : Mode LIVE avec capital $1,000
3. **Semaine 2** : Ajuster config selon win rate observé
4. **Mois 1** : Atteindre +20% mensuel stable
5. **Mois 2+** : Augmenter capital progressivement

Bonne chance ! 🎯
