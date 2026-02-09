# Empire Dashboard - Updates V2.0

## 🎯 Nouvelles Fonctionnalités

### 1. Vrais Budgets en Temps Réel
- **Binance (Crypto)** : Récupération du solde réel via API Binance (badge `LIVE`)
- **Oanda (Forex/Indices)** : Calcul basé sur allocations initiales + PnL (badge `CALC`)
  - *Note: Connexion Oanda directe en cours de création*

### 2. Filtres Interactifs pour les Trades
Le tableau des trades dispose maintenant de 3 filtres :
- **Bot** : Filtrer par système (Crypto/Forex/Indices/Commodities)
- **Mois** : Filtrer par mois de l'année
- **Statut** : Filtrer par statut (OPEN/CLOSED/SKIPPED)

### 3. Badges de Source
Chaque allocation affiche maintenant sa source :
- 🟢 **LIVE** : Données en temps réel depuis l'exchange
- ⚪ **CALC** : Calculé depuis les trades historiques

## 🔧 Configuration

### Credentials Binance (pour le solde LIVE)

Le dashboard essaie de récupérer les credentials dans cet ordre :

1. **Variables d'environnement** :
```bash
export BINANCE_API_KEY="votre_api_key"
export BINANCE_API_SECRET="votre_api_secret"
```

2. **DynamoDB** (EmpireConfig table) :
```json
{
  "ConfigKey": "BINANCE_CREDENTIALS",
  "ApiKey": "votre_api_key",
  "ApiSecret": "votre_api_secret"
}
```

### Ajouter les credentials via AWS CLI :
```bash
aws dynamodb put-item \
  --table-name EmpireConfig \
  --item '{
    "ConfigKey": {"S": "BINANCE_CREDENTIALS"},
    "ApiKey": {"S": "VOTRE_API_KEY"},
    "ApiSecret": {"S": "VOTRE_API_SECRET"}
  }'
```

## 📦 Déploiement

### Option 1: Script Automatique
```bash
cd EmpireDashboard/scripts
./deploy.sh
```

### Option 2: Manuel
```bash
# 1. Build le layer
cd EmpireDashboard/scripts
./build_layer.sh

# 2. Deploy le stack
cd ../infrastructure/cdk
cdk deploy EmpireDashboardStack --app "python3 app.py"
```

## 🔍 Structure des Modifications

### Backend (`lambda/dashboard_api/lambda_function.py`)
- ✅ Import de CCXT (avec fallback si non disponible)
- ✅ Fonction `fetch_binance_balance()` : Récupère le vrai solde Binance
- ✅ Fonction `fetch_oanda_balance()` : Préparée pour connexion Oanda future
- ✅ Logic d'allocations mise à jour avec source tracking

### Frontend (`frontend/index.html`)
- ✅ 3 dropdowns de filtres (Bot, Mois, Statut)
- ✅ Fonction `applyFilters()` : Filtre dynamique côté client
- ✅ Badges `LIVE`/`CALC` dans les allocations
- ✅ Storage de `allTrades` pour filtrage rapide

### Infrastructure (`infrastructure/cdk/stacks/dashboard_stack.py`)
- ✅ Lambda Layer avec CCXT ajouté
- ✅ Layer attaché à la fonction Lambda API

### Scripts
- ✅ `scripts/build_layer.sh` : Build le layer avec CCXT
- ✅ `scripts/deploy.sh` : Mis à jour pour build + deploy

## 🚀 Prochaines Étapes

### TODO: Connexion Oanda
Pour implémenter la connexion Oanda directe :

1. **Installer l'API v20 d'Oanda** :
```bash
pip install oandapyV20
```

2. **Implémenter `fetch_oanda_balance()` dans lambda_function.py** :
```python
def fetch_oanda_balance():
    import oandapyV20
    from oandapyV20.endpoints.accounts import AccountSummary

    # Récupérer credentials
    account_id = os.environ.get('OANDA_ACCOUNT_ID')
    access_token = os.environ.get('OANDA_ACCESS_TOKEN')

    client = oandapyV20.API(access_token=access_token)
    r = AccountSummary(account_id)
    client.request(r)

    balance = float(r.response['account']['balance'])
    return balance
```

3. **Ajouter oandapyV20 au layer** :
```bash
# Dans lambda/layer/requirements.txt
echo "oandapyV20>=0.6.3" >> requirements.txt
./build_layer.sh
```

## 📊 Utilisation

1. **Dashboard URL** : Accessible via le `DashboardUrl` dans les outputs CDK
2. **API Endpoint** : Disponible via l'`ApiEndpoint` dans les outputs CDK

### Endpoints API
- `GET /stats` : Statistiques globales + trades
- `GET /stats?year=2026` : Filtrer par année
- `GET /status` : État des panic switches
- `POST /status` : Modifier un panic switch

## 🐛 Troubleshooting

### Le badge reste sur "CALC" pour Crypto
- Vérifier que les credentials Binance sont configurés
- Vérifier les logs Lambda : `aws logs tail /aws/lambda/EmpireDashboardApi --follow`
- Vérifier les permissions IAM de la Lambda

### Filtres ne fonctionnent pas
- Vérifier la console browser (F12) pour les erreurs JavaScript
- Vérifier que les données ont bien les champs `AssetClass`, `Status`, `Timestamp`

### Layer trop gros
```bash
# Nettoyer le layer
cd EmpireDashboard/lambda/layer
rm -rf python/
./build_layer.sh
```

## 📝 Notes Techniques

- **CCXT Version** : >=4.0.0 (compatible Python 3.12)
- **Lambda Runtime** : Python 3.12
- **Lambda Timeout** : Default (3s), peut nécessiter augmentation si Binance API lente
- **Layer Size** : ~15-20 MB avec CCXT

---

**Version**: 2.0
**Date**: 2026-02-09
**Auteur**: Empire Trading Team
