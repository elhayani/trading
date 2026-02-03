# 🚀 DÉPLOIEMENT V4 HYBRID SUR AWS

## 📋 Prérequis

```bash
# 1. AWS CLI configuré
aws configure
# Entrer: Access Key, Secret Key, Region (us-east-1)

# 2. CDK installé
npm install -g aws-cdk

# 3. Python dependencies
pip3 install aws-cdk-lib constructs boto3
```

---

## 🏗️ ARCHITECTURE DÉPLOYÉE

```
EventBridge (Cron hourly)
      ↓
Lambda V4 HYBRID Trader
      ↓
   ├──→ Bedrock (Claude 3 Haiku)
   ├──→ DynamoDB (State + History)
   └──→ CloudWatch Logs
```

---

## 📦 ÉTAPE 1: Préparation du Code

### A. Copier les dépendances Lambda

```bash
cd /Users/zakaria/Trading

# Copier les modules nécessaires
cp lambda/data_fetcher/market_analysis.py lambda/v4_trader/
cp lambda/data_fetcher/news_fetcher.py lambda/v4_trader/
cp scripts/exchange_connector.py lambda/v4_trader/
```

### B. Configurer les variables

Éditer `infrastructure/cdk/app_v4.py` :
```python
account="123456789012"  # Votre AWS Account ID
region="us-east-1"
```

---

## 🚢 ÉTAPE 2: Déploiement CDK

```bash
cd /Users/zakaria/Trading/infrastructure/cdk

# Bootstrap CDK (première fois seulement)
cdk bootstrap aws://ACCOUNT-ID/us-east-1

# Déployer la stack
cdk deploy V4TradingStack --app "python3 app_v4.py"
```

### Confirmation

CDK va afficher :
```
✅ V4TradingStack

Outputs:
V4TradingStack.TradingLambdaArn = arn:aws:lambda:us-east-1:...
V4TradingStack.StateTableName = V4TradingState
V4TradingStack.HistoryTableName = V4TradeHistory
V4TradingStack.ScheduleRuleName = V4HybridHourlyCron
```

Taper **y** pour confirmer.

---

## ⚙️ ÉTAPE 3: Configuration Post-Déploiement

### A. Vérifier les Tables DynamoDB

```bash
# State table
aws dynamodb describe-table --table-name V4TradingState

# History table
aws dynamodb describe-table --table-name V4TradeHistory
```

### B. Vérifier Lambda

```bash
# Lister les fonctions
aws lambda list-functions --query 'Functions[?contains(FunctionName, `V4`)].FunctionName'

# Output devrait montrer:
# - V4HybridLiveTrader
# - V4ManualTrigger
```

### C. Vérifier EventBridge Rule

```bash
aws events list-rules --name-prefix V4Hybrid
```

---

## 🧪 ÉTAPE 4: Test Manuel

### Option A: Via AWS Console

1. Aller sur Lambda Console
2. Ouvrir `V4ManualTrigger`
3. Cliquer "Test"
4. Voir les logs CloudWatch

### Option B: Via CLI

```bash
# Invoquer directement
aws lambda invoke \
  --function-name V4HybridLiveTrader \
  --payload '{"test": true}' \
  response.json

# Voir le résultat
cat response.json | jq .
```

### Option C: Via Script Python

```python
import boto3
import json

lambda_client = boto3.client('lambda', region_name='us-east-1')

response = lambda_client.invoke(
    FunctionName='V4HybridLiveTrader',
    InvocationType='RequestResponse',
    Payload=json.dumps({'manual_test': True})
)

result = json.loads(response['Payload'].read())
print(json.dumps(result, indent=2))
```

---

## 📊 ÉTAPE 5: Monitoring

### CloudWatch Logs

```bash
# Streamer les logs en temps réel
aws logs tail /aws/lambda/V4HybridLiveTrader --follow
```

### CloudWatch Insights Queries

```sql
-- Voir tous les trades
fields @timestamp, @message
| filter @message like /TRADE_EXECUTED/
| sort @timestamp desc
| limit 20

-- Voir les décisions Bedrock
fields @timestamp, @message
| filter @message like /Bedrock/
| sort @timestamp desc
```

### DynamoDB State

```bash
# Lire l'état actuel
aws dynamodb get-item \
  --table-name V4TradingState \
  --key '{"trader_id": {"S": "v4_hybrid"}}'
```

---

## 🎛️ ÉTAPE 6: Configuration Avancée

### A. Changer le Mode (TEST → LIVE)

```bash
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --environment "Variables={TRADING_MODE=live,CAPITAL=5000}"
```

⚠️ **ATTENTION**: Mode LIVE exécute de vrais trades !

### B. Pause temporaire

```bash
# Désactiver le cron
aws events disable-rule --name V4HybridHourlyCron

# Réactiver
aws events enable-rule --name V4HybridHourlyCron
```

### C. Changer les Symboles

```bash
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --environment "Variables={SYMBOLS='BTC/USDT,ETH/USDT,SOL/USDT'}"
```

---

## 🔒 ÉTAPE 7: Sécurité

### A. Ajouter API Keys Exchange (si LIVE mode)

```bash
# Créer secret dans Secrets Manager
aws secretsmanager create-secret \
  --name V4/BINANCE_API_KEYS \
  --secret-string '{"api_key":"YOUR_KEY","secret":"YOUR_SECRET"}'

# Donner permission à Lambda
aws lambda add-permission \
  --function-name V4HybridLiveTrader \
  --statement-id SecretsManagerAccess \
  --action secretsmanager:GetSecretValue \
  --principal secretsmanager.amazonaws.com
```

### B. Activer Encryption DynamoDB

```bash
aws dynamodb update-table \
  --table-name V4TradingState \
  --sse-specification Enabled=true,SSEType=KMS
```

---

## 📈 ÉTAPE 8: Dashboards

### CloudWatch Dashboard

```bash
# Créer dashboard automatique
aws cloudwatch put-dashboard \
  --dashboard-name V4HybridTradingDashboard \
  --dashboard-body file://dashboard_config.json
```

Voir fichier `dashboard_config.json` dans `/infrastructure/monitoring/`

---

## 🆘 DÉPANNAGE

### Problème 1: Lambda Timeout

```bash
# Augmenter timeout
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --timeout 300  # 5 minutes
```

### Problème 2: Out of Memory

```bash
# Augmenter mémoire
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --memory-size 1024  # 1GB
```

### Problème 3: Dependencies Missing

```bash
# Créer Lambda Layer avec ccxt
./scripts/create_lambda_layer.sh
# Upload layer et attacher à Lambda
```

---

## 🗑️ NETTOYAGE (Destroy Stack)

```bash
# Supprimer tout
cdk destroy V4TradingStack --app "python3 app_v4.py"

# Garder les tables DynamoDB
# (configuré avec RemovalPolicy.RETAIN)
```

---

## ✅ CHECKLIST DE DÉPLOIEMENT

- [ ] AWS CLI configuré
- [ ] CDK installé et bootstrappé
- [ ] Account ID modifié dans app_v4.py
- [ ] Code Lambda copié dans lambda/v4_trader/
- [ ] Stack déployée (cdk deploy)
- [ ] Tables DynamoDB créées
- [ ] Lambda testée manuellement
- [ ] EventBridge rule active
- [ ] CloudWatch logs streaming
- [ ] Mode TEST validé
- [ ] (Optionnel) API Keys configurés
- [ ] (Optionnel) Mode LIVE activé

---

## 📞 SUPPORT

En cas de problème :
1. Checker CloudWatch Logs
2. Vérifier IAM permissions
3. Tester Lambda manuellement
4. Voir DynamoDB state

---

*Created: 2026-02-01*  
*Version: 1.0*  
*Stack: V4TradingStack*
