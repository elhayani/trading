# 👑 Empire Trading Ecosystem
**Modular Algorithmic Trading Infrastructure for the Modern Markets.**

This workspace contains the complete suite of tools for the **Empire Trading System**, ranging from high-frequency execution bots to real-time administrative dashboards.

## 📡 Workspace Structure

### 1. [Empire](./Empire) (Core Trading Engine)
The brain of the system, running as a high-performance AWS Lambda function.
- **Bot Version**: V11.6 (Hybrid Sniper)
- **Tech Stack**: Python 3.12, CCXT, Pandas, Boto3, Bedrock (Claude 3).
- **Architecture**: Atomic persistence, Singleton exchange connectors, Smart OHLCV caching.
- **Deployment**: CDK (Infrastructure as Code) with automated dependency layering.

### 2. [EmpireDashboard](./EmpireDashboard) (Management UI)
State-of-the-art monitoring and control dashboard.
- **Tech Stack**: HTML5/TailwindCSS (Vanilla), JavaScript, Chart.js.
- **Features**: Live Binance positions, Atomic PnL tracking, Pattern significance filters, Skipped trades log.
- **Backend**: AWS Lambda + API Gateway for lightning-fast data aggregation.

## 🚀 Quick Start

### Deployment (CDK required)
```bash
# Deploy the Trading Bot
cd Empire/scripts
bash deploy.sh

# Deploy the Dashboard
cd EmpireDashboard/scripts
bash deploy.sh
```

### Key Optimizations
- **Latency**: Sub-300ms execution on warm starts via Singleton patterns.
- **Data Efficiency**: 98% reduction in OHLCV data transfer via smart delta-caching.
- **Safety**: Conditional DynamoDB writes prevent race conditions on concurrent executions.

## 📊 Feature Highlights
- **Atomic Position Tracking**: Single source of truth in DynamoDB.
- **Sentiment Circuit Breaker**: Prevents API bans while maintaining quality data.
- **Pattern Filtering**: Only shows trade reasons with ≥ 4 occurrences in the main view for clarity.
- **Skipped Logs**: Dedicated view for bot trade rejections (last 50 skips).

---
**Maintained by the Empire Trading Team.**
*Disclaimer: Use at your own risk.*
