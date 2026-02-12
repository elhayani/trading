# 👑 Empire Trading Ecosystem — V13.2
**Modular Algorithmic Trading Infrastructure for Multi-Asset Scalping.**

## 📡 Architecture

### Core Trading Engine (`Empire/lambda/v4_trader/`)
AWS Lambda scanning **11 assets every minute** on Binance Futures.

| Catégorie | Actifs | Levier | TP | SL |
|---|---|---|---|---|
| **Leaders** | BTC, ETH, SOL, XRP, BNB | 1x | 0.25% | 0.40% |
| **Pump/News** | DOGE | 1x | 0.25% | 0.40% |
| **Tech L1** | AVAX | 1x | 0.25% | 0.40% |
| **Oracle** | LINK | 1x | 0.25% | 0.40% |
| **Gold (RWA)** | PAXG | **4x** | **0.35%** (~0.30% net) | **0.50%** |
| **Indices** | SPX | 1x | 0.25% | 0.40% |
| **Parking** | USDC | 1x | 0.25% | 0.40% |

### Tech Stack
- **Runtime**: Python 3.12, CCXT, Pandas, Boto3
- **Infra**: AWS Lambda, DynamoDB, EventBridge, CDK
- **Patterns**: Atomic persistence, Singleton connectors, Smart OHLCV caching

### Dashboard (`EmpireDashboard/`)
- **Frontend**: HTML5/TailwindCSS, Chart.js
- **Backend**: AWS Lambda + API Gateway
- **Features**: Live Binance positions, PnL tracking, Skipped trades, CloudWatch logs

## 🚀 Deployment

```bash
cd Empire/scripts && bash deploy.sh
```

### Key Strategies
- **PAXG Gold Mode**: Levier x4, TP 0.35% brut pour compenser la faible volatilité
- **Flash Exit**: Ejection USDC parking si opportunité prioritaire (score >85)
- **Trim & Switch**: Réduit positions profitables pour meilleures opportunités
- **Nouvelle Page Blanche**: Pas de cooldown, re-entry immédiate après exit
- **TIME_EXIT adaptatif**: 30min crypto, 45min indices, 90min commodities

## 📊 Safety
- **Atomic Risk**: DynamoDB conditional writes (no race conditions)
- **Circuit Breaker**: Daily loss limit 5%, Portfolio risk cap 20%
- **Max 4 positions simultanées**

---
*Capital: ~$4,677 | Objectif: +1% journalier net*
