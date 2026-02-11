# 📊 Empire Dashboard V11.6
**Premium monitoring and management interface for the Empire Trading System.**

The Empire Dashboard provides a consolidated view of live positions, historical performance, and system health across Crypto, Forex, Indices, and Commodities.

## ✨ Latest Features (V11.6)
- **🚫 Skipped Trades Tab**: Real-time log of the last 50 trades rejected by the bot with specific reasons.
- **Backend Filtering**: Pattern significance logic moved to backend (shows groups with ≥ 4 trades in history).
- **Consolidated Balance**: Real-time equity calculation from Binance API + DynamoDB history.
- **Panic Switches**: Global controls to pause trading systems instantly.
- **High-Perf API**: Lambda + GSI optimized backend (sub-50ms response times).

## 📁 Structure
- `frontend/index.html`: Modern, responsive UI using Tailwind CSS and Chart.js.
- `lambda/dashboard_api/`: Python-based API for data aggregation and reconciliation.
- `infrastructure/cdk/`: AWS CDK stack for serverless deployment.

## 🛠️ Setup & Deployment

### Automated Deployment
```bash
cd scripts
bash deploy.sh
```

### Manual Build
1. **Layer Build**: `./scripts/build_layer.sh` (installs CCXT and dependencies).
2. **Infrastructure**: `cd infrastructure/cdk && cdk deploy`.

## 🔍 Navigation
1. **🔴 LIVE POSITIONS**: Real-time data directly from Binance Futures.
2. **📜 TRADE HISTORY**: Significant trading patterns stored in DynamoDB.
3. **🚫 SKIPPED**: Investigation tab for rejected signals.
4. **☁️ CLOUDWATCH**: Live system logs aggregation.

---
**Version**: 11.6
**Maintenance**: Empire Trading Team
