# 🏛️ Empire Trading Bot V15.0 - Double Alpha
**Institutional-grade algorithmic scalping bot with Double Alpha Scanner and Multi-Path Signal Processing.**

## 🚀 Key Features (Version 15.0)

### 🎯 **Double Alpha Strategy**
-   **Scanner**: Monitors **415+ assets** in <2s using parallelized requests.
-   **Leverage**: **5x** (Dynamic risk management).
-   **Ladder Exits**: 
    -   **TP1**: 70% @ 0.25% gain (Quick bank)
    -   **TP2**: 30% @ 0.50% gain (Trend ride)
-   **Stop Loss**: Adaptive based on ATR/Volatility.

### 🧠 **V15 Scoring Engine**
Evaluation of 8 distinct metrics to generate a 0-100 score:
-   **Momentum**: Shift & Acceleration.
-   **Volume**: Net Flow & Delta (±10%).
-   **Orderbook**: Imbalance & Wall Detection.
-   **Whale Activity**: Large trade intensity.
-   **Technical**: RSI, ADX, VWAP convergence.
-   **Pattern**: Volatility Spikes (>4%) & POC proximity.

### 🛡️ **Anti-Fragile Guards**
-   **ADX Filter**: Rejects counter-trend trades if ADX > 50.
-   **VWAP Shield**: No longs below VWAP / shorts above VWAP (unless Score > 85).
-   **Volatility Opportunity**: Activates on valid spikes with strong volume support.

## 📁 Architecture
-   `binance_scanner.py`: **V15 Native Scanner**. Parallel fetch of Ticker, OHLCV, Orderbook, and Trades.
-   `trading_engine.py`: Core execution engine with market scanning and trading capabilities.
-   `market_analysis.py`: Multi-path signal generation (RSI/ADX/VWAP paths).
-   `exchange_connector.py`: Singleton CCXT with optimized `fetch_tickers` and V15 analysis methods.
-   `atomic_persistence.py`: Risk state management with conditional writes.

## 🛠️ Performance Optimizations
-   **Parallel I/O**: ThreadPoolExecutor for concurrent Binance API calls (30x faster scanning).
-   **Smart Caching**: Incremental OHLCV fetch reduces latency by 82%.
-   **DynamoDB GSI**: 18ms position retrieval.
-   **Memory**: Tuned for 1536MB Lambda profile.

## 📊 Monitoring
-   **Logs**: `aws logs tail /aws/lambda/V4HybridLiveTrader --follow`
-   **State**: `V4TradingState` (DynamoDB)
-   **History**: `EmpireTradesHistory` (DynamoDB)
