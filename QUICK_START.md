# ⚡ Empire V6.1 - Quick Start Guide

Guide de démarrage rapide pour déployer et monitorer le système Empire V6.1.

---

## 🚀 Déploiement Rapide (One-Liner)

### Déployer les 4 Bots en Séquence

```bash
cd ~/Trading/Indices && ./scripts/deploy.sh && \
cd ~/Trading/Forex && ./scripts/deploy.sh && \
cd ~/Trading/Commodities && ./scripts/deploy.sh && \
cd ~/Trading/Crypto && ./scripts/deploy.sh
```

### Déployer un Bot Individuel

```bash
# Indices
cd ~/Trading/Indices && ./scripts/deploy.sh

# Forex
cd ~/Trading/Forex && ./scripts/deploy.sh

# Commodities
cd ~/Trading/Commodities && ./scripts/deploy.sh

# Crypto
cd ~/Trading/Crypto && ./scripts/deploy.sh
```

---

## 📊 Monitoring Rapide

### Check Status des Lambdas

```bash
aws lambda list-functions --region eu-west-3 \
  --query 'Functions[?contains(FunctionName, `Trader`)].{Name:FunctionName, Runtime:Runtime, Updated:LastModified}' \
  --output table
```

### Logs en Temps Réel

```bash
# Indices
aws logs tail /aws/lambda/IndicesLiveTrader --follow --region eu-west-3

# Forex
aws logs tail /aws/lambda/ForexLiveTrader --follow --region eu-west-3

# Commodities
aws logs tail /aws/lambda/CommoditiesLiveTrader --follow --region eu-west-3

# Crypto
aws logs tail /aws/lambda/V4HybridLiveTrader --follow --region eu-west-3
```

### Check Derniers Trades (DynamoDB)

```bash
# Forex
aws dynamodb scan --table-name ForexTradeHistory --region eu-west-3 \
  --limit 5 --query 'Items[*].[Timestamp.S, Pair.S, Type.S, Price.S, PnL.S]' \
  --output table

# Indices
aws dynamodb scan --table-name IndicesTradeHistory --region eu-west-3 \
  --limit 5 --output table

# Commodities
aws dynamodb scan --table-name CommoditiesTradeHistory --region eu-west-3 \
  --limit 5 --output table

# Crypto
aws dynamodb scan --table-name V4TradeHistory --region eu-west-3 \
  --limit 5 --output table
```

---

## 🧪 Backtesting Rapide

### Backtest 60 Jours (Quick Test)

```bash
cd ~/Trading/Systeme_Test_Bedrock

# Forex EURUSD
python3 run_test_v2.py --asset-class Forex --symbol EURUSD=X --days 60

# Indices S&P500
python3 run_test_v2.py --asset-class Indices --symbol ^GSPC --days 60

# Commodities Gold
python3 run_test_v2.py --asset-class Commodities --symbol GC=F --days 60

# Crypto Bitcoin
python3 run_test_v2.py --asset-class Crypto --symbol BTC-USD --days 60
```

### Backtest 365 Jours (Full Year)

```bash
# Run all 4 bots in parallel
python3 run_test_v2.py --asset-class Forex --symbol EURUSD=X --days 365 &
python3 run_test_v2.py --asset-class Indices --symbol ^GSPC --days 365 &
python3 run_test_v2.py --asset-class Commodities --symbol GC=F --days 365 &
python3 run_test_v2.py --asset-class Crypto --symbol BTC-USD --days 365 &
wait
```

---

## 🔧 Commandes Maintenance

### Update Lambda Code (Sans CDK)

```bash
# Forex
cd ~/Trading/Forex/lambda
zip -r forex_trader.zip forex_trader/
aws lambda update-function-code \
  --function-name ForexLiveTrader \
  --zip-file fileb://forex_trader.zip \
  --region eu-west-3
```

### Activer/Désactiver Bot (Mode Test/Live)

```bash
# Passer en mode TEST
aws lambda update-function-configuration \
  --function-name ForexLiveTrader \
  --environment Variables={TRADING_MODE=test} \
  --region eu-west-3

# Passer en mode LIVE
aws lambda update-function-configuration \
  --function-name ForexLiveTrader \
  --environment Variables={TRADING_MODE=live} \
  --region eu-west-3
```

### Check EventBridge Rules

```bash
# Lister toutes les rules
aws events list-rules --region eu-west-3 --output table

# Check si rule est enabled
aws events describe-rule --name IndicesHourlyCron --region eu-west-3
```

### Disable/Enable Trading Cron

```bash
# Désactiver (pause trading)
aws events disable-rule --name IndicesHourlyCron --region eu-west-3

# Réactiver
aws events enable-rule --name IndicesHourlyCron --region eu-west-3
```

---

## 🎯 ARNs des Lambdas V6.1

```
Indices:     arn:aws:lambda:eu-west-3:946179054632:function:IndicesLiveTrader
Forex:       arn:aws:lambda:eu-west-3:946179054632:function:ForexLiveTrader
Commodities: arn:aws:lambda:eu-west-3:946179054632:function:CommoditiesLiveTrader
Crypto:      arn:aws:lambda:eu-west-3:946179054632:function:V4HybridLiveTrader
```

---

## 📋 Tables DynamoDB

```
Indices:     IndicesTradeHistory, IndicesTradingState
Forex:       ForexTradeHistory, ForexTradingState
Commodities: CommoditiesTradeHistory, CommoditiesTradingState
Crypto:      V4TradeHistory, V4TradingState
```

---

## 🚨 Troubleshooting Rapide

### Lambda ne s'exécute pas

```bash
# 1. Check si EventBridge rule est enabled
aws events describe-rule --name IndicesHourlyCron --region eu-west-3

# 2. Check dernière invocation
aws lambda get-function --function-name IndicesLiveTrader --region eu-west-3

# 3. Check logs pour erreurs
aws logs tail /aws/lambda/IndicesLiveTrader --since 1h --region eu-west-3
```

### Trades ne se ferment pas

```bash
# V6.1 fix appliqué: Two-phase architecture
# Si problème persiste, check:

# 1. Vérifier trailing_stop.py présent
aws lambda get-function --function-name ForexLiveTrader --region eu-west-3 \
  --query 'Code.Location'

# 2. Check positions ouvertes
aws dynamodb scan --table-name ForexTradingState --region eu-west-3 \
  --filter-expression "attribute_exists(Position)"
```

### High Error Rate

```bash
# Check errors dernière heure
aws logs filter-pattern "ERROR" \
  --log-group-name /aws/lambda/ForexLiveTrader \
  --start-time $(date -u -d '1 hour ago' +%s)000 \
  --region eu-west-3
```

---

## 📊 V6.1 Optimizations Recap

| Bot | Leverage | R/R | Trailing | Key Change |
|-----|----------|-----|----------|------------|
| **Forex** | 20x ✅ | 1:4.0 | 0.4% | Leverage reduced 30→20 |
| **Indices** | - | 1:5.0 | 0.8% | TP increased +11% |
| **Commodities** | - | 1:4.5 | NEW ⭐ | Trailing Stop added! |
| **Crypto** | - | 1:2.3 | 6% | R/R fixed 1:1→1:2.3 |

---

## 🔗 Liens Utiles

- **README Complet**: [README.md](README.md)
- **Backtest Results**: [V6_1_BACKTEST_RESULTS.md](V6_1_BACKTEST_RESULTS.md)
- **Optimization Report**: [V6_1_OPTIMIZATION_REPORT.md](V6_1_OPTIMIZATION_REPORT.md)
- **AWS Console**: https://console.aws.amazon.com/lambda/home?region=eu-west-3
- **CloudWatch Logs**: https://console.aws.amazon.com/cloudwatch/home?region=eu-west-3#logsV2:log-groups

---

**Version:** V6.1 "Maximum Performance"
**Date:** 2026-02-08
**Status:** ✅ DEPLOYED & OPERATIONAL
