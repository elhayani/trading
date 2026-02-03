# 🎉 V4 HYBRID - READY FOR AWS DEPLOYMENT

## ✅ CE QUI EST PRÊT

### 1. Infrastructure Code (CDK)
```
✅ infrastructure/cdk/stacks/v4_trading_stack.py
   → Lambda Function
   → DynamoDB Tables (State + History)
   → EventBridge Cron (hourly)
   → IAM Roles & Permissions
   → CloudWatch Logs

✅ infrastructure/cdk/app_v4.py
   → CDK App entry point
```

### 2. Lambda Handler
```
✅ lambda/v4_trader/v4_hybrid_lambda.py
   → Event handler for EventBridge
   → DynamoDB state persistence
   → Bedrock AI integration
   → Multi-symbol support
```

### 3. Deployment Scripts
```
✅ scripts/deploy_aws.sh
   → Automated deployment
   → Prerequisite checks
   → Post-deployment validation
   → Testing utilities

✅ DEPLOYMENT_GUIDE.md
   → Step-by-step manual
   → Configuration options
   → Monitoring setup
   → Troubleshooting
```

---

## 🚀 DÉPLOIEMENT EN 1 COMMANDE

```bash
cd /Users/zakaria/Trading
./scripts/deploy_aws.sh
```

Le script va :
1. ✅ Vérifier AWS CLI & CDK
2. ✅ Préparer le code Lambda
3. ✅ Bootstrap CDK (si nécessaire)
4. ✅ Déployer la stack
5. ✅ Vérifier les ressources
6. ✅ Tester la Lambda

**Temps estimé** : 3-5 minutes

---

## 📋 AVANT DE DÉPLOYER

### Prérequis AWS

```bash
# 1. Installer AWS CLI
brew install awscli  # macOS
# ou: pip3 install awscli

# 2. Configurer credentials
aws configure
# AWS Access Key ID: AKIAIOSFODNN7EXAMPLE
# AWS Secret Access Key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
# Default region: us-east-1
# Default output format: json

# 3. Installer CDK
npm install -g aws-cdk

# 4. Vérifier
aws sts get-caller-identity
cdk --version
```

### Coûts AWS Estimés

| Service | Usage | Coût Mensuel |
|---------|-------|--------------|
| **Lambda** | 720 exécutions/mois (hourly) | **~$0.50** |
| **DynamoDB** | On-demand, faible | **~$1.00** |
| **Bedrock** | 720 API calls | **~$2.00** |
| **CloudWatch** | Logs standard | **~$0.50** |
| **TOTAL** | | **~$4/mois** |

💡 **Très abordable pour un trading bot automatisé !**

---

## ⚙️ CONFIGURATION

### Mode TEST (par défaut)

```bash
# Lambda configurée en mode test
TRADING_MODE=test
CAPITAL=1000
SYMBOLS=SOL/USDT

# Pas de vrais trades exécutés
# Seulement simulation + logs
```

### Passer en Mode LIVE

```bash
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --environment "Variables={TRADING_MODE=live,CAPITAL=5000}"
```

⚠️ **Attention** : Mode LIVE exécute de **VRAIS TRADES** !

### Ajouter des Symboles

```bash
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --environment "Variables={SYMBOLS='BTC/USDT,ETH/USDT,SOL/USDT'}"
```

---

## 📊 MONITORING

### CloudWatch Logs (Temps Réel)

```bash
aws logs tail /aws/lambda/V4HybridLiveTrader --follow
```

### DynamoDB State

```bash
aws dynamodb scan --table-name V4TradingState
```

### EventBridge Schedule

```bash
aws events describe-rule --name V4HybridHourlyCron
```

---

## 🎯 ARCHITECTURE DÉPLOYÉE

```
┌─────────────────┐
│  EventBridge    │  Cron: 0 * * * * (hourly)
│  V4HybridCron   │
└────────┬────────┘
         │ Trigger
         ↓
┌─────────────────────────────────────┐
│  Lambda: V4HybridLiveTrader         │
│  ────────────────────────────────   │
│  • Fetch market data (Binance)      │
│  • Analyze (RSI, SMA, Patterns)     │
│  • Fetch news (CryptoCompare)       │
│  • Detect regime (BULL/BEAR)        │
│  • Ask Bedrock AI                   │  ────→  Bedrock Claude 3
│  • Execute trade (if confirmed)     │
│  • Save state                       │
└──────────┬──────────────────────────┘
           │
           ├────→  DynamoDB (State)
           ├────→  DynamoDB (History)
           └────→  CloudWatch Logs
```

---

## ✅ CHECKLIST FINALE

Avant de déployer :

- [ ] AWS CLI configuré (`aws configure`)
- [ ] CDK installé (`npm install -g aws-cdk`)
- [ ] Compte AWS avec permissions
- [ ] Région us-east-1 sélectionnée
- [ ] Budget AWS compris (~$4/mois)
- [ ] Mode TEST validé localement
- [ ] Documentation lue

Après déploiement :

- [ ] Lambda testée manuellement
- [ ] EventBridge rule activée
- [ ] CloudWatch logs consultés
- [ ] DynamoDB tables créées
- [ ] Première exécution hourly observée
- [ ] (Optionnel) Mode LIVE activé

---

## 🆘 SUPPORT & DÉPANNAGE

### Erreur Commune 1: CDK Not Bootstrapped

```bash
cdk bootstrap aws://ACCOUNT-ID/us-east-1
```

### Erreur Commune 2: Lambda Timeout

```bash
aws lambda update-function-configuration \
  --function-name V4HybridLiveTrader \
  --timeout 300
```

### Erreur Commune 3: Bedrock Permission

Vérifier que la région est **us-east-1** (Bedrock disponible)

---

## 📞 COMMANDES UTILES

```bash
# Voir tous les logs
aws logs tail /aws/lambda/V4HybridLiveTrader --follow

# Invoquer manuellement
aws lambda invoke \
  --function-name V4HybridLiveTrader \
  --payload '{}' \
  response.json

# Voir l'état
aws dynamodb get-item \
  --table-name V4TradingState \
  --key '{"trader_id": {"S": "v4_hybrid"}}'

# Désactiver temporairement
aws events disable-rule --name V4HybridHourlyCron

# Réactiver
aws events enable-rule --name V4HybridHourlyCron

# Détruire (cleanup)
cd infrastructure/cdk
cdk destroy V4TradingStack --app "python3 app_v4.py"
```

---

## 🎊 PRÊT POUR PRODUCTION !

Tout est configuré et testé :

1. ✅ **Code validé** : Tests locaux réussis
2. ✅ **Infrastructure CDK** : Prête à déployer
3. ✅ **Scripts automatisés** : `./scripts/deploy_aws.sh`
4. ✅ **Documentation complète** : Guide + README
5. ✅ **Mode TEST sécurisé** : Pas de risque financier
6. ✅ **Coût maîtrisé** : ~$4/mois

**Prochaine action** : `./scripts/deploy_aws.sh`

---

*Ready for AWS Deployment*  
*Version: 1.0*  
*Date: 2026-02-01*
