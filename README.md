# 🏛️ Empire V16.7.8 — Ensemble Selection & News Blackout

> **Système de trading HFT haute performance** : Architecture V16.7.8 conçue pour une réactivité maximale, intégrant un arbitrage par IA (Claude 3 Haiku) et une protection contre les chocs de volatilité macro-économique.

## 🎯 Statut Production

```
✅ DÉPLOYÉ EN PRODUCTION AWS (ap-northeast-1 — Tokyo)
📅 Dernière MAJ : 2026-02-15 (Audit #V16.7.8)
💰 Mode : LIVE (Binance USD-M Futures)
🏛️ Architecture : V16.7.8 persistent Ensemble Selection
⏰ Smart Scheduling : Sessions persistantes de 13 min (Ticks 60s)
🎯 Actifs : Scan dynamique de ~150 actifs (> $5M vol 24h)
```

---

## 🏗️ Architecture V16.7.8 — "The Ensemble"

Le système fonctionne désormais sur un modèle de **sélection par consensus** entre indicateurs techniques et arbitrage IA qualitatif.

```
┌──────────────────────────────────────────────────────────────┐
│                  AWS CLOUD (ap-northeast-1)                   │
│                                                               │
│  [EventBridge — 13m Persistent Invocations]                   │
│          │                                                    │
│          ▼                                                    │
│  [🚀 Lambda 1 : Scanner (Session 13 min / Tick 1 min)]        │
│   ├── 1. 🔍 Scan ultra-rapide (~150 actifs filtrés)           │
│   ├── 2. 🏆 Calcul "Elite Score" (Momentum, ATR, Vol Surge)    │
│   ├── 3. 🧠 Arbitrage IA (Claude 3 Haiku)                     │
│   │    └── Sélection des "Meilleurs parmi les Elites"         │
│   └── 4. 📰 News Blackout Check (ForexFactory RSS)            │
│          │                                                    │
│          ▼                                                    │
│  [🛡️ Lambda 2 : Closer (Tick 7s / Protection Choc)]          │
│   ├── 1. ✅ Exit Management (TP/SL adaptatifs ATR)            │
│   └── 2. 🛑 News shockwave closure (Vente forcée avant news)  │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 🛡️ Les 3 Piliers de Sécurité V16.7.8

Chaque trade doit passer par un entonnoir de sécurité à trois niveaux :

### 1. News Blackout Rule (La Règle d'Or)
Le bot surveille en temps réel le calendrier économique mondial (RSS ForexFactory).
- **Entrées bloquées** : 5 minutes avant et 10 minutes après toute news `High Impact`.
- **Sortie forcée** : Toutes les positions ouvertes sont fermées immédiatement avant une news majeure via le **Closer**.

### 2. Ensemble Selection (Arbitrage IA)
Au lieu de prendre n'importe quel signal technique, le Scanner présente un "Dashboard Élite" à **Claude 3 Haiku**.
- **Analyse de structure** : Haiku rejette les bougies verticales isolées (risk of flash-crash).
- **Sanity Check** : Vérification de la cohérence RSI et diversification du portefeuille.

### 3. Zombie Loop & Persistent Sessions
- **Cold-start elimination** : Sessions de 13 minutes conservant les connexions d'échange actives.
- **Time Remaining Guard** : Monitoring constant du temps Lambda (fermeture propre à T-65s).

---

## ⚙️ Configuration Trading Elite

| Paramètre | Valeur | Description |
|-----------|--------|-------------|
| **Région** | ap-northeast-1 | Tokyo (Faible latence Binance) |
| **Max Open Trades** | 5 | Concentration sur la qualité |
| **Min Volume 24h** | $5,000,000 | Filtre anti-shitcoins |
| **TP Multiplier** | 2.5x ATR | Objectif profit dynamique |
| **SL Multiplier** | 1.8x ATR | Stop Loss adaptatif volatilité |
| **Min TP Pct** | 0.25% | Seuil de rentabilité scalping |
| **Blackout News** | -5min / +10min | Protection chocs économiques |

---

## 📈 Historique des Versions (Récents)

| Version | Date | Changement |
|---------|------|-----------|
| **V16.7.8** | 2026-02-15 | 🧠 **Ensemble Selection** : Arbitrage batch via Haiku. Dashboard Élite. |
| **V16.7.7** | 2026-02-15 | 🛑 **News Blackout Exit** : Closer ferme tout avant news High Impact. |
| **V16.7.6** | 2026-02-15 | 🌀 **Zombie Loop Protection** : Session 13 min avec monitoring "Time Remaining". |
| V16.0 | 2026-02-14 | 🎌 Migration Tokyo & Refonte HFT (Ticks 1 min). |
| V10.9 | 2026-02-10 | 🎯 Sniper Agile : Fix Binance Futures, RSI 35. |

---

## 🚀 Déploiement & Outils

```bash
# Déploiement CDK (Tokyo)
cd infrastructure/cdk && cdk deploy V4TradingStack --app "python3 app.py"

# Logs Scanner (Persistent)
aws logs tail /aws/lambda/Lambda1Scanner --follow --region ap-northeast-1
```

---

## ⚠️ Disclaimer

**Ce système est un bot HFT complexe opérant avec un effet de levier.**

- L'utilisation de l'IA (Claude) n'élimine pas les risques de perte.
- La latence réseau et les glissements (slippage) peuvent impacter les résultats réels.
- Ne jamais trader avec de l'argent dont vous avez besoin pour vivre.

---

**© 2026 Empire Trading Systems** — *V16.7.8 Persistent Intelligence Architecture*
