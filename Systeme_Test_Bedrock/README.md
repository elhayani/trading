# Système de Test Bedrock (Historique S3)

Ce dossier contient un environnement de test dédié pour valider les bots (Crypto, Forex, Indices, Commodities) en utilisant des données historiques et des news réelles stockées sur S3.
Il permet de tester toute la chaîne de décision, y compris les appels à AWS Bedrock (Claude 3 Haiku) et les filtres Macro (VIX/DXY), sans impacter la production (DynamoDB mocké, appels externes interceptés).

## Structure
- `run_test.py`: Script principal pour lancer les tests. Il patche dynamiquement les connecteurs de données et `requests.get` pour injecter l'historique.
- `s3_adapters.py`: Mocks intelligents (`S3ExchangeConnector`, `S3DataLoader`, `S3NewsFetcher`, `S3RequestsMock`) qui lisent les données depuis S3.
- `utils/s3_loader.py`: Charge les données historiques (Marché + News) depuis le bucket S3.
- `data_ingestion.py`: Outil pour télécharger et synchroniser les données (Marché, News, Macro) vers S3.

## Pré-requis
- Accès AWS configuré (pour lire S3 et invoquer Bedrock).
- Données historiques présentes dans le bucket S3 (`empire-trading-data-paris`).

## Utilisation

### 1. Préparer les données (Ingestion)
Pour que le test soit réaliste, il faut avoir les données de marché ET les données Macro dans S3.

```bash
# Données de l'actif principal (ex: EURUSD) pour 60 jours
python data_ingestion.py --asset-class Forex --symbol EURUSD --days 60

# Données Macro (Recommandé pour tester les filtres VIX/DXY)
python data_ingestion.py --asset-class Indices --symbol ^VIX --days 60
python data_ingestion.py --asset-class Indices --symbol DX-Y.NYB --days 60
python data_ingestion.py --asset-class Indices --symbol ^TNX --days 60
```

### 2. Lancer le Test
Lancer un test sur une période donnée (ex: les 30 derniers jours).

```bash
# Pour Crypto
python run_test.py --asset-class Crypto --symbol BTC/USDT --days 30

# Pour Forex
python run_test.py --asset-class Forex --symbol EURUSD --days 30

# Pour Indices (ex: S&P 500)
python run_test.py --asset-class Indices --symbol ^GSPC --days 30
```

### Options
- `--offset-days N`: Décale la période de test de N jours dans le passé (pour tester une crise spécifique, ex: crash 2022).
- `--days N`: Nombre de jours à tester.

## Fonctionnement Technique
1. **Chargement S3**: `run_test.py` télécharge OHLCV (actif + macro) et News depuis S3.
2. **Patching**: 
   - `ExchangeConnector` / `DataLoader` sont remplacés par des versions S3.
   - `NewsFetcher` est remplacé par une version S3.
   - `requests.get` est intercepté globalement pour rediriger les appels Yahoo (VIX, DXY) vers les données S3 chargées.
   - `boto3.resource('dynamodb')` est remplacé par une version en mémoire.
3. **Exécution**: Le handler Lambda de production est appelé bougie par bougie.
4. **Validation**: Les décisions (Signaux, filtres Bedrock, filtres VIX) sont loggées dans un JSON de sortie.

Ce système garantit que le code testé est **identique à la production** (via import direct), seule la couche d'acquisition de données est substituée ("Dependency Injection" via Patching).
