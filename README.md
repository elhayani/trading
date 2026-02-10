# 🏛️ Empire V10.9 — Sniper Agile Mode

> **Système de trading multi-actifs unifié** : architecture V10 ultra-réactive. Une seule Lambda AWS traite les actifs majeurs avec une précision chirurgicale, une gestion des secrets sécurisée et une analyse technique hautement descriptive.

## 🎯 Statut Production

```
✅ DÉPLOYÉ EN PRODUCTION AWS (eu-west-3)
📅 Dernière MAJ : 2026-02-10 (Audit #V10.9)
💰 Mode : LIVE (Binance USD-M Futures)
🏛️ Architecture : V10 Hybrid Sniper
⏰ Smart Scheduling : 4 règles CRON adaptatives
🎯 Actifs : 5 (BTC, ETH, SOL, PAXG, SPX)
```

---

## 🎯 Actifs Actifs (Sniper Mode)

| Classe | Symbole | Description |
|--------|---------|-------------|
| **Crypto** | `BTCUSDT` | Bitcoin — Le Roi 👑 |
| **Crypto** | `ETHUSDT` | Ethereum — Alt-leader 💎 |
| **Crypto** | `SOLUSDT` | Solana — Turbo Mode ⚡ |
| **Commodities** | `PAXGUSDT` | Or (via PAX Gold) 🥇 |
| **Indices** | `SPXUSDT` | S&P 500 📈 |

---

## 🏗️ Architecture V7 — Super-Lambda

```
┌──────────────────────────────────────────────────────────────┐
│                   AWS CLOUD (eu-west-3)                       │
│                                                               │
│  [EventBridge — Smart Scheduling]                             │
│   ├── 🌙 ECO      (00h-06h Paris) → every 20 min             │
│   ├── 📊 STD AM   (06h-14h Paris) → every 5 min              │
│   ├── 🔥 TURBO    (14h-16h Paris) → every 1 min              │
│   └── 📊 STD PM   (16h-00h Paris) → every 5 min              │
│          │                                                    │
│          ▼                                                    │
│  [🏛️ V4HybridLiveTrader — Super-Lambda]                      │
│   └── Boucle séquentielle :                                   │
│       BTC → ETH → SOL → PAXG → SPX                            │
│          │                                                    │
│          ├── 🧠 micro_corridors.py   (Paramètres adaptatifs)  │
│          ├── 📊 market_analysis.py   (RSI, EMA, SMA200)       │
│          ├── 🌍 macro_context.py     (DXY, VIX, Yields)       │
│          ├── 📰 news_fetcher.py      (Yahoo Finance News)     │
│          └── 🤖 AWS Bedrock (Claude) (Devil's Advocate AI)    │
│          │                                                    │
│          ▼                                                    │
│  [DynamoDB: EmpireTradesHistory]  ←→  [EmpireDashboard]       │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Smart Scheduling (4 CRON Rules)

| Règle | Heures (Paris) | Intervalle | Raison |
|-------|----------------|------------|--------|
| 🌙 **ECO** | 00h → 06h | 20 min | Marchés calmes, économie de ressources |
| 📊 **Standard AM** | 06h → 14h | 5 min | Europe active, volatilité moyenne |
| 🔥 **Turbo** | 14h → 16h | **1 min** | US Open — volatilité maximale |
| 📊 **Standard PM** | 16h → 00h | 5 min | Wall Street actif, fin de journée |

---

## 🛡️ Filtres de Sécurité (Pipeline)

Chaque actif passe par **9 filtres** avant exécution :

```
1. ✅ Exit Management (SL/TP/Trailing)
2. ✅ Circuit Breaker (BTC -5%/-10%/-20%)
3. ✅ BTC Crash Filter (-8% horaire)
4. ✅ Max Exposure (2 positions max)
5. ✅ Cooldown (4h entre trades)
6. ✅ VIX Filter (blocage si VIX > 30)
7. ✅ Volume Confirmation (adaptatif par classe)
8. ✅ Multi-Timeframe (1h + 4h RSI)
9. ✅ AI Devil's Advocate (Bedrock Claude)
```

### Volume Adaptatif V7

| Classe | Seuil Volume | Ratio vs Crypto |
|--------|-------------|-----------------|
| Crypto | 1.2x | Référence |
| Forex | 0.6x | /2x |
| Indices | 0.24x | /5x |
| Commodities | 0.12x | /10x |

---

## 📁 Structure du Projet

```
Trading/
├── 🏛️ Empire/                        ← Moteur de Trading Unifié
│   ├── lambda/v4_trader/
│   │   ├── v4_hybrid_lambda.py       ← Super-Lambda (8 actifs)
│   │   ├── exchange_connector.py     ← Connexion Binance (ccxt)
│   │   ├── market_analysis.py        ← RSI, indicateurs techniques
│   │   ├── micro_corridors.py        ← Paramètres par actif/heure
│   │   ├── macro_context.py          ← DXY, VIX, US10Y
│   │   ├── news_fetcher.py           ← Actualités marché
│   │   └── reporter.py               ← Rapports SNS
│   ├── infrastructure/cdk/           ← Stack AWS (CDK)
│   └── scripts/deploy.sh             ← Déploiement one-click
│
├── 📊 EmpireDashboard/               ← Dashboard Web (S3 + API)
│   ├── frontend/                     ← HTML/JS (sous-onglets par classe)
│   └── lambda/                       ← API Lambda
│
├── README.md                         ← Ce fichier
├── QUICK_START.md
├── CHANGELOG.md
└── V7_OPTIMIZATIONS.md
```

---

## 🚀 Déploiement

### Pré-requis

```bash
aws configure          # AWS CLI configuré (eu-west-3)
python3 --version      # Python 3.12+
npm install -g aws-cdk # CDK CLI
```

### Déployer la Super-Lambda

```bash
cd /Users/zakaria/Trading/Empire && bash scripts/deploy.sh
```

### Vérification

```bash
# Test manuel de la Lambda
aws lambda invoke \
  --function-name V4HybridLiveTrader \
  --payload '{"manual": true}' \
  --cli-binary-format raw-in-base64-out \
  --region eu-west-3 \
  /tmp/response.json && cat /tmp/response.json

# Logs en temps réel
aws logs tail /aws/lambda/V4HybridLiveTrader --follow --region eu-west-3

# Vérifier les CRON rules
aws events list-rules --region eu-west-3
```

---

## 📊 Stacks AWS Actives

| Stack | Ressources | Status |
|-------|-----------|--------|
| `V4TradingStack` | Lambda + 4 CRON + DynamoDB + SNS | ✅ Active |
| `EmpireDashboardStack` | API Lambda + S3 Frontend | ✅ Active |
| `CDKToolkit` | Bootstrap CDK | ✅ Active |

---

## ⚙️ Configuration Trading

| Paramètre | Valeur | Description |
|-----------|--------|-------------|
| Capital/Trade | $200 | Par position |
| Max Exposure | 2 | Positions simultanées |
| Cooldown | 4h | Entre 2 trades même actif |
| Stop Loss | -3.5% | Protection capital |
| Take Profit | +8.0% | R/R = 1:2.3 |
| RSI Buy | **< 35.0** | **V10 Sniper Limit** |
| RSI Sell | > 78 | Confirmation sortie trailing |
| VIX Max | 35 | Blocage total au-dessus |
| Circuit Breaker | -5% / -10% / -20% | L1/L2/L3 BTC |

---

## 📈 Historique des Versions

| Version | Date | Changement |
|---------|------|-----------|
| **V10.9** | 2026-02-10 | 🎯 Sniper Agile : Fix Binance Futures, RSI 35, Skip logs descriptifs |
| V9.0 | 2026-02-10 | 🏛️ Super-Lambda unifiée, Architecture Level 4, Fail-safe |
| V6.2 | 2026-02-08 | Fix P&L reporting |
| V6.1 | 2026-02-08 | Maximum Performance (R/R optimisés) |
| V6.0 | 2026-02-07 | Trailing Stop universel |
| V5.1 | 2026-01-15 | Fortress Edition (sécurité) |
| V5.0 | 2025-12-20 | Bedrock AI Integration |

---

## ⚠️ Disclaimer

**Ce système comporte des risques inhérents au trading.**

- Les performances passées ne garantissent **jamais** les résultats futurs
- Le trading automatisé peut entraîner des pertes rapides
- Toujours utiliser un capital que vous pouvez vous permettre de perdre
- Tester en mode `test` avant d'activer le mode `live`

---

**© 2026 Empire Trading Systems** — *V7.0 Unified Architecture*
