# 💱 Forex Trading Bot - Déploiement AWS

## ✅ Statut
**Le bot Forex est en cours de déploiement sur AWS.**

Ce déploiement est **séparé** du bot V4 Hybrid (Crypto), pour isoler les stratégies et la gestion des risques.

---

## 🏗️ Architecture

- **Stack CDK** : `ForexTradingStack`
- **Lambda** : `ForexLiveTrader` (Python 3.12)
- **Déclencheur** : EventBridge (**Toutes les heures à H+05min**)
- **Layer** :
  - `AWSSDKPandas` (Optimisé AWS)
  - `ForexDependencyLayer` (`yfinance`, `pandas_ta`, `requests`)

## 🚀 Commandes

### Redéployer
```bash
./scripts/deploy_forex.sh
```

### Logs en temps réel
```bash
aws logs tail /aws/lambda/ForexLiveTrader --follow
```

### Tester manuellement
```bash
aws lambda invoke \
  --function-name ForexLiveTrader \
  /tmp/forex_result.json

cat /tmp/forex_result.json | python3 -m json.tool
```

## ⚙️ Configuration
Le bot utilise la configuration définie dans `lambda/forex_trader/config.py`.
Actuellement activé :
- **EURUSD** (Trend Pullback)
- **GBPUSD** (Trend Pullback)
- **USDJPY** (Bollinger Breakout)

## ⚠️ Notes
- Le bot est en mode **SIGNAL ONLY** (pas d'exécution d'ordres réels pour l'instant).
- Il utilise `yfinance` pour les données (gratuit, mais backup recommended pour prod).
