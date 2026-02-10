# 🏛️ Empire V7 — Quick Start Guide

Guide de démarrage rapide pour déployer, tester et monitorer le système **Empire V7 Unified Architecture**.

---

## 🚀 Déploiement Rapide (One-Liner)

### Déployer le Moteur de Trading (Engine)
Déploie la Super-Lambda, les 4 règles de scheduling et la base de données.

```bash
cd ~/Trading/Empire && bash scripts/deploy.sh
```

### Déployer le Dashboard
Déploie l'interface web pour suivre les trades en direct.

```bash
cd ~/Trading/EmpireDashboard && bash scripts/deploy_dashboard.sh
```

---

## 📊 Monitoring & Logs

### Check Status de la Super-Lambda
Vérifie la version déployée et les derniers paramètres.

```bash
aws lambda get-function --function-name V4HybridLiveTrader --region eu-west-3
```

### Logs en Temps Réel (Multi-Actifs)
Suis la boucle séquentielle (BTC, ETH, SOL, PAXG, XAG, OIL, SPX, NDX).

```bash
aws logs tail /aws/lambda/V4HybridLiveTrader --follow --region eu-west-3
```

### Check des Actifs (Test Manuel)
Force une exécution immédiate pour tester la boucle complète.

```bash
aws lambda invoke \
  --function-name V4HybridLiveTrader \
  --payload '{"manual": true}' \
  --cli-binary-format raw-in-base64-out \
  --region eu-west-3 \
  /tmp/response.json && cat /tmp/response.json
```

---

## ⏰ Smart Scheduling rules

Le système s'adapte automatiquement à l'heure de la journée :

```bash
# Lister les 4 règles actives
aws events list-rules --region eu-west-3 --query "Rules[?contains(Name, 'Empire')].{Name:Name, Schedule:ScheduleExpression, State:State}" --output table
```

| Règle | Intervalle | Heures (Paris) | État |
|-------|------------|----------------|------|
| `EmpireEcoRule` | 20 min | 00h - 06h | 🌙 Actif |
| `EmpireStandardAMRule` | 5 min | 06h - 14h | 📊 Actif |
| `EmpireTurboRule` | **1 min** | 14h - 16h | 🔥 Actif (US Open) |
| `EmpireStandardPMRule` | 5 min | 16h - 00h | 📊 Actif |

---

## 📂 Gestion de la Base de Données (DynamoDB)

### Voir les positions ouvertes par catégorie
Utilise la table unifiée `EmpireTradesHistory`.

```bash
# Voir les trades Crypto
aws dynamodb scan --table-name EmpireTradesHistory --region eu-west-3 \
  --filter-expression "AssetClass = :c AND #s = :o" \
  --expression-attribute-names '{"#s": "Status"}' \
  --expression-attribute-values '{":c": {"S": "Crypto"}, ":o": {"S": "OPEN"}}' \
  --output table

# Voir les trades Commodities/Indices
aws dynamodb scan --table-name EmpireTradesHistory --region eu-west-3 \
  --filter-expression "AssetClass IN (:c, :i) AND #s = :o" \
  --expression-attribute-names '{"#s": "Status"}' \
  --expression-attribute-values '{":c": {"S": "Commodities"}, ":i": {"S": "Indices"}, ":o": {"S": "OPEN"}}' \
  --output table
```

---

## 🔧 Maintenance rapide

### Mises à jour du code (Sans redeploy complet)
Si tu n'as changé que le code Python de la Lambda.

```bash
cd ~/Trading/Empire/lambda/v4_trader
zip -r engine.zip .
aws lambda update-function-code \
  --function-name V4HybridLiveTrader \
  --zip-file fileb://engine.zip \
  --region eu-west-3
```

### Pause d'Urgence (Kill Switch)
Désactive le scheduling pour arrêter toutes les nouvelles analyses.

```bash
# Désactiver toutes les règles du moteur
for rule in EmpireEcoRule EmpireStandardAMRule EmpireTurboRule EmpireStandardPMRule; do
  aws events disable-rule --name $rule --region eu-west-3
done
```

---

## 🚨 Troubleshooting V7

### "Function Not Found"
Vérifie que tu utilises la région **`eu-west-3`**.
```bash
export AWS_DEFAULT_REGION=eu-west-3
```

### "Access Denied" (DynamoDB)
Vérifie que la variable d'env `HISTORY_TABLE` dans la Lambda est bien sur `EmpireTradesHistory`.

---

## 🔗 Raccourcis
- **Moteur Principal** : `~/Trading/Empire`
- **Dashboard UI** : `~/Trading/EmpireDashboard`
- **Logs CloudWatch** : [Lien Console AWS](https://eu-west-3.console.aws.amazon.com/cloudwatch/home?region=eu-west-3#logsV2:log-groups/log-group/%252Faws%252Flambda%252FV4HybridLiveTrader)

---

**Version:** V7.0 "Unified Architecture"
**Status:** ✅ OPERATIONAL
**© 2026 Empire Trading Systems**
