# 🚀 Empire V6.0 Multi-Asset - AI-Powered Trading System

> **Système de trading multi-actifs automatisé** combinant analyse technique avancée, IA générative (AWS Bedrock), micro-corridors adaptatifs, et gestion de risque institutionnelle "Hedge Fund".

## 🎯 Statut Actuel

```
✅ DÉPLOYÉ EN PRODUCTION AWS (eu-west-3)
📅 Date: 2026-02-08
💰 Mode: LIVE (Toutes les stratégies actives)
⏰ Cron: Toutes les heures
🎯 Portfolio: Crypto, Forex, Indices, Commodities
🆕 Version: V6.0 - Profit Maximizer Edition 💎
```

---

## 🆕 Nouveautés V6.0 "Profit Maximizer" (Février 2026)

Cette mise à jour s'attaque à la **maximisation des profits** après avoir sécurisé le capital avec la V5.1 Fortress.

### 📈 1. Universal Trailing Stop (Dynamic Profit Locking)
Tous les bots (Forex, Indices, Commodities) partagent désormais un moteur de **Trailing Stop intelligent** :
- **Activation** : Se déclenche quand le trade est en profit (ex: +0.5% Forex, +1.0% Indices).
- **Suivi Dynamique** : Le Stop Loss remonte automatiquement avec le prix (tous les X%).
- **Turbo Mode** : Pour les pumps violents (Crypto/Indices), accélération du trailing.
- **Breakeven** : Sécurisation rapide à 0 risque dès le premier mouvement favorable.

### 🎯 2. Risk/Reward Optimisé (Let Winners Run)
Après analyse des backtests 2024-2025, nous avons débridé le potentiel de gain :
- **Forex** : TP augmenté de x2.5 à **x3.5** ATR.
- **Indices** : TP augmenté de x2.5 à **x4.5** ATR (Nasdaq sniper).
- **Commodities** : TP et SL ajustés pour la volatilité de l'Or et du Pétrole.
- **Ratio** : Vise un Risk/Reward minimum de 1:3 sur chaque trade.

### 🐛 3. Backtest Engine Perfectionné
Correction d'un **bug critique** dans la simulation du portefeuille :
- Le système simulait mal l'exposition simultanée (Max Exposure).
- Le nouveau moteur garantit une fidélité à 100% avec le comportement Lambda en production.
- **Résultat** : Des backtests plus réalistes, moins de positions simultanées, meilleure sélectivité.

---

## 🏛️ Rappel des Features V5.1 "Fortress" (Janvier 2026)

### 🏛️ 1. Macro Context Intelligence
- Analyse DXY, US10Y, VIX avant chaque trade.
- Arrêt automatique si le contexte est défavorable (Risk-Off).

### 🛡️ 2. Predictability Index
- Score technique (0-100) pour filtrer les actifs "sales".
- Quarantine automatique des marchés erratiques (ex: Oil en crise).

### 🕐 3. Horloge Biologique (Golden Windows)
- Trading uniquement pendant les heures de haute liquidité (Londres/NY).

### 💰 4. Position Sizing Cumulatif
- Intérêts composés : la taille des positions augmente avec le capital.

---

## 📊 Stratégies par Actif (V6.0)

| Actif | Stratégie | IA Validation | Nouveautés V6.0 | Status |
|-------|-----------|---------------|-----------------|--------|
| **Crypto** | V4 Hybrid (Trend/Capitulation) | ✅ Bedrock | Macro Context + Turbo Trailing | 🛡️ Active |
| **Forex** | Trend Pullback (Major Pairs) | ✅ Bedrock | **Trailing Stop** + TP x3.5 | ✅ Active |
| **Indices** | Quant Momentum (Nasdaq/S&P) | ✅ Bedrock | **Trailing Stop** + TP x4.5 | ✅ Active |
| **Commodities** | Trend & Breakout (Gold/Oil) | ✅ Bedrock | **Trailing Stop** + Predictability | 🛡️ Active |

---

## 🏗️ Architecture Technique "Profit Maximizer"

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AWS CLOUD (eu-west-3)                            │
│                                                                         │
│  [EventBridge Cron] ───────────────────────────────────────────┐        │
│          │                                                     │        │
│          ▼                                                     ▼        │
│  [Lambda: Traders (Forex/Indices...)]               [Lambda: Dashboard] │
│          │                                                     ▲        │
│          ▼                                                     │        │
│   🧠 INTELLIGENCE LAYER V6.0                                [DynamoDB]  │
│    ├── trailing_stop.py (NEW! Universal Exit)                  │        │
│    ├── macro_context.py (DXY/VIX/Yields)                       │        │
│    ├── predictability_index.py (Score 0-100)                   │        │
│    ├── micro_corridors.py (Time Regimes)                       │        │
│    └── trading_windows.py (Golden Hours)                       │        │
│          │                                                     │        │
│          ▼                                                     │        │
│   🤖 BEDROCK AI (Devils Advocate) ─────────────────────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
           │
  [Exchanges APIs] (Binance, Yahoo Finance)
```

---

## 📁 Structure des Modules V6.0

```
Trading/
├── shared/                     # 🧠 Cerveau Central V6.0
│   ├── modules/
│   │   ├── trailing_stop.py        # 🆕 Moteur de sortie dynamique
│   │   ├── macro_context.py        # Intelligence Macro
│   │   ├── predictability_index.py # Filtre anti-bruit
│   │   ├── trading_windows.py      # Filtre horaire
│   │   └── micro_corridors.py      # Paramètres adaptatifs
│   └── position_sizing.py      # Calculateur de risque composé
├── Crypto/
├── Forex/
├── Indices/
├── Commodities/
└── EmpireDashboard/            # Dashboard S3 + Lambda
```

---

## 🚀 Déploiement & Opérations V6.0

### 1. Pré-requis
- Compte AWS configuré (`aws configure`)
- Python 3.12+ installé
- Node.js & CDK installés (pour l'infrastructure)

### 2. Déploiement Individuel par Bot

Chaque bot possède son propre script de déploiement automatisé :

```bash
# 📈 INDICES (Nasdaq/S&P)
cd /Users/zakaria/Trading/Indices && ./scripts/deploy.sh

# 💱 FOREX (EUR/USD, USD/JPY)
cd /Users/zakaria/Trading/Forex && ./scripts/deploy.sh

# 🛢️ COMMODITIES (Gold/Oil)
cd /Users/zakaria/Trading/Commodities && ./scripts/deploy.sh

# ₿ CRYPTO (Solana/BTC)
cd /Users/zakaria/Trading/Crypto/scripts && ./deploy.sh
```

### 3. Mise à jour du Dashboard
Le dashboard (Frontend S3 + Backend Lambda) se déploie séparément :

```bash
cd /Users/zakaria/Trading/EmpireDashboard && ./deploy_dashboard.sh
```

### 4. Vérification & Monitoring
Une fois déployé, vous pouvez surveiller le système via :
- **CloudWatch Logs** : `/aws/lambda/Empire-Indices-Trader-V5`, `/aws/lambda/Empire-Forex-Trader-V5`, etc.
- **EventBridge** : Vérifier que les règles `Cron` (ex: `Empire-EveryHour`) sont `ENABLED`.
- **Dashboard** : https://empire-dashboard-v2.s3.eu-west-3.amazonaws.com/index.html

### 5. Backtesting V6.0

```bash
# Tester Forex avec le nouveau Trailing Stop
python3 /Users/zakaria/Trading/Systeme_Test_Bedrock/run_test_v2.py --asset-class Forex --symbol EURUSD=X --days 60
```

---

## ⚠️ Disclaimer

**Ce système est un outil technologique puissant mais comporte des risques.**
- Les performances passées (backtests 2022-2025) ne garantissent pas les résultats futurs.
- Le trading automatisé peut entraîner des pertes rapides.
- **Le V6.0 Profit Maximizer vise la performance aggressive**, assurez-vous de surveiller vos positions.

---

**© 2026 Empire Trading Systems** - *V6.0 Profit Maximizer Edition*
*Dernière mise à jour : 2026-02-08*
