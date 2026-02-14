# Scripts de Téléchargement Binance Futures

Scripts pour télécharger l'historique de TOUS les actifs de Binance Futures pour la semaine dernière.
**Aucune limitation** - tous les symboles disponibles sont téléchargés.

## 📁 Fichiers

### 1. `download_binance_public.py` (Recommandé)
- **Mode**: Public (pas besoin d'API keys)
- **Vitesse**: Moyenne
- **Limite**: 1 requête/200ms
- **Usage**: `python3 download_binance_public.py`

### 2. `download_binance_fast.py` (Plus rapide)
- **Mode**: Public avec parallélisation
- **Vitesse**: Rapide (10 workers)
- **Limite**: 10 requêtes simultanées
- **Usage**: `python3 download_binance_fast.py`

### 3. `download_binance_history.py` (Complet)
- **Mode**: Avec API keys (plus de données)
- **Vitesse**: Variable
- **Limite**: Dépend du compte API
- **Usage**: `export BINANCE_API_KEY="xxx" && python3 download_binance_history.py`

## 🚀 Installation

```bash
# Installer les dépendances
pip install -r requirements.txt

# Ou manuellement
pip install ccxt pandas requests
```

## 📊 Sortie

Les scripts créent un répertoire avec la date du jour:
```
binance_history_20260214/
├── all_futures_history_7days.csv     # Toutes les données combinées
├── symbols_stats.csv                  # Statistiques par symbole
├── summary.json                       # Résumé détaillé
├── BTCUSDT.csv                        # Données individuelles
├── ETHUSDT.csv
└── ... (415 fichiers CSV)
```

## 📈 Données par CSV

Chaque fichier CSV contient:
- `timestamp`: Date/heure de la bougie
- `open/high/low/close`: Prix OHLC
- `volume`: Volume en base asset
- `quote_volume`: Volume en USDT
- `range`: Fourchette de prix
- `change`: Changement en % de la bougie

## 📋 Résumé JSON

Le fichier `summary.json` contient:
- Top 10 performeurs (meilleurs %)
- Pires 10 performeurs
- Plus volatiles
- Plus gros volumes
- Statistiques générales

## 🚫 PAS DE LIMITATION

**Important**: Tous les scripts téléchargent TOUS les symboles disponibles sans aucune limitation:
- Pas de limite à 415 symboles
- Tous les perpétuels USDT actifs sont inclus
- Le nombre réel peut varier (typiquement 200-500+ symboles)

### Lambda Scanner
Le lambda scanner utilise également TOUS les symboles disponibles:
- Récupération dynamique depuis l'API Binance
- Fallback sur liste par défaut si API indisponible
- Scan complet de l'univers Futures USDT

## ⚡ Performance

| Script | Temps estimé | CPU | Mémoire |
|--------|-------------|-----|---------|
| public | 15-20 min | Bas | Moyenne |
| fast | 5-10 min | Élevé | Haute |
| history | 10-15 min | Moyen | Moyenne |

## 🔧 Personnalisation

Modifier les paramètres dans les scripts:

```python
# Changer la période
days=14  # 2 semaines au lieu de 7

# Changer le timeframe
timeframe='4h'  # 4 heures au lieu de 1h

# Limiter le nombre de symboles
max_symbols=100  # 100 symboles au lieu de 415
```

## 📝 Exemple d'utilisation

```bash
# Lancer le téléchargement rapide
python3 download_binance_fast.py

# Résultat attendu:
# 🚀 Téléchargement de 415 symboles avec 10 workers...
# ✅ BTCUSDT: 168 candles | Change: +2.34%
# ✅ ETHUSDT: 168 candles | Change: -1.45%
# 🎉 TÉLÉCHARGEMENT TERMINÉ!
# 📊 Succès: 415/415 symboles
# 📈 Total candles: 69,720
```

## 🐛 Dépannage

### Erreur "Rate limit"
- Augmenter les delays dans le script
- Réduire le nombre de workers

### Erreur "Timeout"
- Augmenter le timeout dans les requests
- Vérifier la connexion internet

### Symboles manquants
- Certains symboles peuvent être delistés
- Vérifier le fichier `failed_symbols` dans summary.json

## 📊 Analyse rapide

Après téléchargement, vous pouvez analyser les données:

```python
import pandas as pd

# Charger les statistiques
stats = pd.read_csv('binance_history_20260214/symbols_stats.csv')

# Top 10 performeurs
top_performers = stats.nlargest(10, 'total_change')
print(top_performers[['symbol', 'total_change', 'volatility']])

# Plus volatiles
most_volatile = stats.nlargest(10, 'volatility')
print(most_volatile[['symbol', 'volatility', 'total_change']])
```
