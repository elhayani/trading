# 🚀 Empire V5.1 Multi-Asset - AI-Powered Trading System

> **Système de trading multi-actifs automatisé** combinant analyse technique avancée, IA générative (AWS Bedrock), micro-corridors adaptatifs, et gestion de risque institutionnelle "Hedge Fund".

## 🎯 Statut Actuel

```
✅ DÉPLOYÉ EN PRODUCTION AWS (eu-west-3)
📅 Date: 2026-02-07
💰 Mode: LIVE (Toutes les stratégies actives)
⏰ Cron: Toutes les heures
🎯 Portfolio: Crypto, Forex, Indices, Commodities
🆕 Version: V5.1 - Fortress Balanced Edition 🏰
```

---

## 🆕 Nouveautés V5.1 "Fortress Balanced" (Février 2026)

Cette mise à jour majeure transforme le bot d'un simple trader technique en un véritable **gestionnaire de fonds algorithmique**.

### 🏛️ 1. Macro Context Intelligence (Hedge Fund Vision)
Le bot ne regarde plus seulement le graphique, il analyse le monde macro-économique avant chaque décision :
- **DXY (Dollar Index)** : Analyse Risk-On/Risk-Off en temps réel.
- **US 10Y Yields** : Surveille les taux pour protéger les positions Tech/Nasdaq.
- **VIX (Peur)** : Ajuste la taille des positions selon la volatilité du marché.
- **Calendrier Éco** : Détecte les jours de CPI/FOMC/NFP pour adapter la prudence.

```python
MACRO CONTEXT:
- Dollar (DXY): 104.2 (+0.5% today) → RISK_OFF
- US 10Y Yield: 4.2% (Rising) → BEARISH_TECH
- VIX: 18.0 → NEUTRAL
- MACRO REGIME: RISK_OFF
```

### 🛡️ 2. Predictability Index (Anti-Erratic Filter)
Fini le trading sur des actifs "sales" ou manipulés. Le bot calcule un score de propreté technique (0-100) :
- **Score > 80** (EXCELLENT) : Taille x1.2, Filtres réduits (ex: Nasdaq)
- **Score < 40** (POOR) : Taille x0.5, TP court sécure
- **Score < 25** (ERRATIC) : **QUARANTINE** 🚫 (ex: Oil en crise, Shitcoins)

### 🕐 3. Horloge Biologique Centralisée (Golden Windows)
Chaque actif possède maintenant une "horloge biologique" parfaite :
- **Indices** : 15h30-22h (Session US uniquement)
- **Forex** : 08h-17h (Londres + Overlap)
- **Commodities** : 14h-20h (Session COMEX)
- **Crypto** : 24/7 avec adaptation aux volumes

### 💰 4. Position Sizing Cumulatif (Compound Interest)
Le bot utilise la puissance des intérêts composés :
```python
Position_Size = (Capital_Actuel × Risk_Multiplier) / Nombre_Actifs
```
Les gains font boule de neige trade après trade ! 🎱

---

## 📊 Stratégies par Actif

| Actif | Stratégie | IA Validation | Nouveautés V5.1 | Status |
|-------|-----------|---------------|-----------------|--------|
| **Crypto** | V4 Hybrid (Trend/Capitulation) | ✅ Bedrock | Macro Context + Predictability | 🛡️ Active |
| **Forex** | Trend Pullback (Major Pairs) | ✅ Bedrock | Macro Context + RSI Adaptatif | ✅ Active |
| **Indices** | Quant Momentum (Nasdaq/S&P) | ✅ Bedrock | Micro-Corridors (6 régimes) | ✅ Active |
| **Commodities** | Trend & Breakout (Gold/Oil) | ✅ Bedrock | **Predictability Filter** (Crucial Oil) | 🛡️ Active |

---

## 🎯 Micro-Corridors & Régimes (V5.1)

Le système découpe chaque session en **micro-tranches horaires** avec des paramètres adaptatifs :

### Indices (Session US : 15h30-22h Paris)
| Corridor | Heure | Régime | TP/SL | Risque |
|----------|-------|--------|-------|--------|
| 💥 Impact Zone | 15h30-16h30 | Breakout | × 0.7 | × 1.3 |
| 🔥 Morning Power | 16h30-18h00 | Trend | × 0.8 | × 1.2 |
| 🍽️ Mid-Day | 18h00-19h30 | Range | × 0.6 | × 0.8 |
| 🚀 Power Hour | 19h30-21h00 | Aggressive | × 0.9 | × 1.2 |
| 💰 Profit Taking | 21h00-21h30 | Scalping | × 0.5 | × 0.7 |
| 🔚 Final Hour | 21h30-22h00 | Cautious | × 0.5 | × 0.5 |

---

## 🏗️ Architecture Technique "Fortress"

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AWS CLOUD (eu-west-3)                            │
│                                                                         │
│  [EventBridge Cron] ───────────────────────────────────────────┐        │
│          │                                                     │        │
│          ▼                                                     ▼        │
│  [Lambda: Traders (Crypto/Forex/Indices)]           [Lambda: Dashboard] │
│          │                                                     ▲        │
│          ▼                                                     │        │
│   🧠 INTELLIGENCE LAYER V5.1                                [DynamoDB]  │
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

## 📁 Structure des Modules V5.1

```
Trading/
├── shared/                     # 🧠 Cerveau Central V5.1
│   ├── macro_context.py        # Intelligence Macro (DXY, Yields, VIX)
│   ├── predictability_index.py # Filtre anti-bruit technique
│   ├── trading_windows.py      # Filtre horaire (Golden Windows)
│   ├── micro_corridors.py      # Paramètres adaptatifs par heure
│   └── position_sizing.py      # Calculateur de risque composé
├── Crypto/
├── Forex/
├── Indices/
├── Commodities/
└── EmpireDashboard/            # Dashboard S3 + Lambda
```

## 🚀 Déploiement & Opérations V5.1

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

### 5. Tests Locaux (Avant déploiement) V5.1

```bash
# Tester l'intégration de tous les modules V5.1 (Macro, Predictability, Corridors)
python3 /Users/zakaria/Trading/test_v51_integration.py
```

---

## ⚠️ Disclaimer

**Ce système est un outil technologique puissant mais comporte des risques.**
- Les performances passées (backtests 2022-2025) ne garantissent pas les résultats futurs.
- Le trading automatisé peut entraîner des pertes rapides.
- **Le V5.1 Fortress est conçu pour protéger le capital avant tout**, mais le risque zéro n'existe pas.

---

**© 2026 Empire Trading Systems** - *V5.1 Fortress Balanced Edition*
*Dernière mise à jour : 2026-02-07*
