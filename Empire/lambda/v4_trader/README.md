# 🏛️ Empire Trading Bot V11.2

Empire is a professional-grade algorithmic trading bot designed for high-frequency scalping and trend-following across multiple asset classes (Crypto, Forex, Indices, Commodities).

## 🚀 Key Features
- **4-Level Validation**: Macro Regime -> Technical Score -> Micro Timing -> Risk Management.
- **Sentiment Analysis**: Integrated with Yahoo Finance news and negation handling.
- **Risk Management**: Dynamic position sizing, ATR-based stops, and portfolio-level risk caps.
- **Micro-Corridors**: Adapts trading parameters based on time-of-day volatility sessions.
- **Walk-Forward Optimizer**: Backtests and optimizes parameters to prevent overfitting.

## 📁 Architecture
- `v4_hybrid_lambda.py`: AWS Lambda entry point and execution loop.
- `market_analysis.py`: Technical indicator calculations and trend detection.
- `decision_engine.py`: Approval logic and threshold adjustments.
- `risk_manager.py`: Core risk calculations and trade registration.
- `news_fetcher.py`: NLP-lite sentiment analysis for news articles.
- `macro_context.py`: High-level market regime monitoring (DXY, Yields, VIX).
- `config.py`: Centralized configuration for all modules.

## 🛠️ Setup
1. **Environment Variables**:
   - `BINANCE_API_KEY`, `BINANCE_SECRET_KEY`: Exchange credentials.
   - `TRADING_MODE`: `dry_run` or `live`.
   - `SYMBOLS`: Comma-separated list (e.g., `BTC/USDT,ETH/USDT`).
   - `EMPIRE_MACRO_EVENT`: (Optional) Manual override for economic events.

2. **Dependencies**:
   - `ccxt`, `pandas`, `numpy`, `yfinance`, `boto3`.

## 🧪 Testing
Run unit tests with:
```bash
python -m unittest lambda/v4_trader/tests/test_risk_manager.py
```

## 📊 Backtesting
Simulate performance over historical data:
```bash
python lambda/v4_trader/backtester.py BTC/USDT 30
```

---
*Disclaimer: Trading involves significant risk. This software is provided as-is with no guarantees of profit.*
