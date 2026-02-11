# 🏛️ Empire Trading Bot V11.6
**Professional-grade algorithmic trading bot for Crypto, Forex, Indices, and Commodities.**

Empire is a high-performance trading system built for AWS Lambda, utilizing AI-driven decision engines (Claude 3 Haiku) and robust atomic risk management.

## 🚀 Key Features (Version 11.6)
- **Sniper Architecture (V11.5)**: Optimized for AWS Lambda warm starts (-82% latency).
- **Atomic Risk Management**: Prevents race conditions using DynamoDB conditional expressions.
- **Circuit Breaker Sentiment**: Intelligent Yahoo Finance news analysis with automated backoff.
- **Smart OHLCV Cache**: Persistently stores market data in `/tmp` (1GB storage) to minimize API calls.
- **Multi-Asset Class Support**: Specialized analysis for Crypto, Commodities, Forex, and Indices.
- **AI-Validation**: Optional Claude 3 Haiku validation for high-confidence entries.

## 📁 Architecture
- `v4_hybrid_lambda.py`: Core execution engine with smart caching and warm-start optimizations.
- `atomic_persistence.py`: Atomic DynamoDB operations for global risk caps and position tracking.
- `exchange_connector.py`: Singleton-based CCXT connector with persistent markets cache.
- `news_fetcher.py`: sentiment analysis with proximity-aware negation and circuit breakers.
- `market_analysis.py`: Multi-timeframe technical indicator calculations and regime detection.
- `decision_engine.py`: Multi-layered approval logic combining TA, Sentiment, and AI.
- `config.py`: Centralized configuration and trading parameters.

## 🛠️ Performance Optimizations (Audit V11.5)
- **DynamoDB GSI**: Position loading via GSI (`18ms` vs `500ms`).
- **Warm Start Cache**: CCXT instances and market data persist between invocations.
- **Smart OHLCV Fetch**: Only incremental candles are fetched once cache is established.
- **Lambda Profile**: 1.5GB RAM / 1GB Ephemeral Storage for peak efficiency.

## 🛠️ Setup & Deployment
1. **Credentials**: Store Binance API keys in AWS Secrets Manager (`trading/binance`).
2. **Configuration**: Edit `Empire/lambda/v4_trader/config.py` for trading limits and thresholds.
3. **Deploy**:
   ```bash
   cd Empire/scripts
   bash deploy.sh
   ```

## 📊 Monitoring
- **Dashboard**: Use the `EmpireDashboard` frontend for real-time tracking.
- **Logs**: `aws logs tail /aws/lambda/V4HybridLiveTrader --follow`
- **State**: Check `V4TradingState` table in DynamoDB for active portfolio risk.

---
*Disclaimer: Trading involves significant risk. This software is provided as-is with no guarantees of profit.*
