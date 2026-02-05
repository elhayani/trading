# 🚀 Empire V4 Multi-Asset - AI-Powered Trading System

> **Système de trading multi-actifs automatisé** combinant analyse technique avancée, IA générative (AWS Bedrock), et gestion de risque institutionnelle.

## 🎯 Statut Actuel

```
✅ DÉPLOYÉ EN PRODUCTION AWS (eu-west-3)
📅 Date: 2026-02-04
💰 Mode: LIVE (Toutes les stratégies actives)
⏰ Cron: Toutes les heures
🎯 Portfolio: Crypto, Forex, Indices, Commodities
```

---

## 📊 Vue d'Ensemble

Ce projet implémente un système de trading complet **Empire V4** qui gère quatre classes d'actifs distinctes avec des stratégies spécialisées :

| Actif | Stratégie | IA Validation | Status |
|-------|-----------|---------------|--------|
| **Crypto** | V4 Hybrid (Adaptive Trend/Capitulation) | ✅ Bedrock | 🛡️ Active (Max 3 Trades) |
| **Forex** | Trend Pullback (Major Pairs) | ✅ Bedrock | ✅ Active |
| **Indices** | Quant Momentum (Nasdaq/S&P) | ✅ Bedrock | ✅ Active |
| **Commodities** | Trend & Breakout (Gold & Oil) | ✅ Bedrock | 🛡️ Active (Safety Captain) |

---

## 🛡️ Sécurité & Risk Management (Updated)

Nous avons intégré un "Safety Captain" (Capitaine de Sécurité) pour protéger le capital contre la volatilité extrême (comme observée en 2026).

### 1. Protection Crypto (DCA Safety & Anti-Crash) 🛡️₿
- **Anti-Overexposure** : Limite stricte de **3 trades ouverts maximum** par paire (ex: SOL/USDT).
- **BTC Master Switch** : Interdiction totale d'acheter des "Altcoins" si le **Bitcoin chute de >2% en 1h**. Corrélation dynamique pour éviter d'acheter pendant un crash global.
- **Time-Gap Cooldown** : Verrou de sécurité de **4 heures** minimum entre deux achats sur le même actif (empêche le "mitraillage" pendant une chute verticale).
- **Smart Exits** : 
  - **Global Take Profit** : Si le PnL global de la position atteint **+2.0%**, tout est clôturé automatiquement (sécurisation des gains).
  - **Reporting Autonome** : Un module indépendant envoie un rapport d'état par email toutes les 30 minutes (9h-21h UTC) avec PnL, exposition et alertes.

### 2. Protection Commodities (Safety Captain) 🛡️🛢️
- **ATR Cap** : Interdiction de trader si la volatilité (ATR) dépasse les normes historiques (ex: Gold > 25 ATR).
- **Position Sizing Dynamique** : La taille de position s'ajuste automatiquement inversement à la volatilité.
  - Risk Fixe : $200 par trade.
  - Formule : `Taille = $200 / (Entry - SL)`.
  - Impact : Si le Stop Loss est large (volatilité haute), la taille de position est réduite.

---

## 🏆 Détail des Stratégies par Système

### 1. Crypto (V4 Hybrid System) ₿
*   **Approche** : Adaptative (Multi-Régime)
*   **Timeframe** : 1H (Hourly)
*   **Paires** : SOL/USDT, BTC/USDT, ETH/USDT
*   **Logique** :
    *   **Régime BULL** (tendance haussière) : Stratégie *Dip Buying*. Achète sur repli modéré (RSI < 45).
    *   **Régime BEAR** (tendance baissière) : Stratégie *Capitulation*. N'achète QUE les crashs extrêmes (RSI < 25) pour jouer le rebond technique.
    *   **Sécurité** : Max 3 positions ouvertes (DCA Limité).

### 2. Commodities (Gold & Oil) 🛢️
*   **Approche** : Trend Following (Gold) & Breakout (Oil)
*   **Timeframe** : 1H (Hourly)
*   **Paires** : Gold (GC=F), Crude Oil (CL=F)
*   **Logique** :
    *   **Gold (Trend Pullback)** :
        *   Filtre : Prix > SMA 200 (Tendance Haussière).
        *   Entry : RSI < 35 (Repli profond).
        *   Exit : Target 4.0 ATR / Stop 2.5 ATR.
    *   **Oil (Bollinger Breakout)** :
        *   Entry : Clôture au-dessus de la bande de Bollinger supérieure (Explosion volatilité).
        *   Exit : Target 4.0 ATR / Stop 2.0 ATR.
    *   **Sécurité** : ATR Cap (Pas de trade si volatilité > 25.0).

### 3. Forex (Major Pairs) 💱
*   **Approche** : Trend Pullback Classique
*   **Timeframe** : 1H (Hourly)
*   **Paires** : EUR/USD, GBP/USD, USD/JPY
*   **Logique** :
    *   Identification de la tendance long terme (SMA 200).
    *   Attente d'un repli temporaire (RSI < 30 pour Long, RSI > 70 pour Short).
    *   Validation par Bedrock AI (Contexte Macro-économique).

### 4. Indices (US Markets) 📈
*   **Approche** : Quantitative Momentum
*   **Timeframe** : 1H (Hourly)
*   **Paires** : Nasdaq (NQ=F), S&P 500 (ES=F)
*   **Logique** :
    *   Exploite le biais haussier naturel des indices US.
    *   **RSI Dynamique** : Niveaux d'achat ajustés (40 au lieu de 30) pour rentrer plus tôt dans les tendances fortes.
    *   **Momentum Filter** : Bedrock instruit de ne "pas bloquer" le momentum sauf news catastrophique majeure.

---

## 🖥️ Empire Dashboard

Le système est piloté par un dashboard web moderne (React/Tailwind) hébergé sur AWS S3 + Lambda.

### Fonctionnalités
- **Performance Curve** : Suivi de l'Equity en temps réel.
- **Panic Switches** : Boutons d'arrêt d'urgence pour chaque bot individuellement.
- **Capital Allocation** : Vue camembert de l'exposition par classe d'actifs.
- **Live Feed** : Flux des trades avec **explication détaillée de l'IA** ("Pourquoi j'ai pris ce trade ?").

---

## 🏗️ Architecture Technique

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AWS CLOUD (eu-west-3)                            │
│                                                                         │
│  [EventBridge Cron] ───────────────────────────────────────────┐        │
│          │                                                     │        │
│          ▼                                                     ▼        │
│          ▼                                                     ▼        │
│  [Lambda: Crypto] ──► [SNS Email Reports]      [Lambda: Dashboard API]  │
│          │                    │                        ▲                │
│          ▼                    ▼                        │                │
│  [Bedrock AI (Claude)] [Bedrock AI (Claude)]      [DynamoDB State]      │
│          │                    │                        │                │
│          └────────────────────┴────────────────────────┘                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
           │
  [Exchanges APIs] (Binance, Yahoo Finance)
```

---

## 🚀 Deployment

Le déploiement est entièrement automatisé via AWS CDK (Infrastructure as Code).

```bash
# Déployer tout le système
cd infrastructure/cdk
cdk deploy --all
```

Ou par stack individuelle :
- `cdk deploy CryptoTradingStack`
- `cdk deploy CommoditiesTradingStack`
- `cdk deploy IndicesTradingStack`
- `cdk deploy ForexTradingStack`
- `cdk deploy EmpireDashboardStack`

---

## ⚠️ Disclaimer

**Ce système est un outil technologique puissant mais comporte des risques.**
- Les performances passées (backtests 2022-2025) ne garantissent pas les résultats futurs.
- Le trading automatisé peut entraîner des pertes rapides, surtout sur les marchés crypto à fort levier (bien que ce bot n'utilise pas de levier par défaut).
- Utilisez toujours le mode TEST avant le LIVE.

---

**© 2026 Empire Trading Systems** - *Built for the future.*
