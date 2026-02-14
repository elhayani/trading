# 👑 Empire Trading Ecosystem — V15.0 (Double Alpha)
**High-Frequency Algorithmic Trading Infrastructure with Double Alpha Scanner.**

## 📡 Architecture

### Core Trading Engine (`Empire/lambda/v4_trader/`)
AWS Lambda now utilizes **Double Alpha Scanner** to monitor **415+ Binance Futures assets** in real-time (approx. 2s scan time). The system dynamically selects the best opportunities using a multi-metric scoring engine.

| Catégorie | Description | Levier | TP | SL |
|---|---|---|---|---|
| **Crypto Leaders** | BTC, ETH, SOL, BNB, XRP | 5x | Ladder | Adaptive |
| **Elite Alts** | AVAX, LINK, ADA, DOT, etc. | 5x | Ladder | Adaptive |
| **Pump/Meme** | DOGE, SHIB, PEPE | 5x | Ladder | Adaptive |
| **Commodities** | PAXG (Gold), OIL (WTI) | 5x (PAXG 4x) | 0.35%+ | 0.50% |
| **Indices** | SPX, NDX, DAX | 5x | 0.25% | 0.40% |
| **Forex** | EUR, GBP, JPY | 5x | 0.25% | 0.40% |

> **Ladder Exit Strategy**:
> - **TP1 (Quick Capture)**: 70% of position @ 0.25% gain
> - **TP2 (Runner)**: 30% of position @ 0.50% gain

### 🧠 V15 Scanner Logic
The new **BinanceNativeScanner** evaluates 8 distinct metrics in parallel to generate a Composite Score (0-100):

1.  **Momentum Shift**: Detects acceleration in price movement.
2.  **Buy/Sell Pressure**: Net volume flow analysis (>52% buyer dominance).
3.  **Delta Volume**: Aggressive market buying/selling (±10% threshold).
4.  **Orderbook Imbalance**: Liquidity walls and bid/ask spread analysis.
5.  **Whale Activity**: Large trade detection (>10x average size).
6.  **Volatility**: Regimes (LOW, NORMAL, HIGH, SPIKE). *Spikes allow entry if Score > 80.*
7.  **POC Distance**: Proximity to Point of Control (Volume Profile).
8.  **Technical Convergence**: Multi-path signal confirmation (RSI + ADX + VWAP).

### Key Features
-   **Double Alpha Scan**: Scans all 400+ USDT perps, pre-filters by volume (>1M) and volatility.
-   **Multi-Path Scoring**: Signals can be triggered by RSI extremes (>70/<30), ADX Trends (>25), or VWAP breakouts.
-   **Anti-Fragile Filtering**:
    -   **ADX Filter**: Blocks trades against strong trends (ADX > 50).
    -   **VWAP Guard**: Prevents longs below VWAP / shorts above VWAP unless signal is extremely strong.
    -   **Volatility Opportunity**: Capitalizes on spikes if accompanied by strong whale/orderbook support.
-   **Smart Caching**: Local OHLCV cache reduces API latency by 82%.
-   **Parallel Processing**: ThreadPoolExecutor used for parallel I/O during scanning and analysis.

### Tech Stack
-   **Runtime**: Python 3.12, CCXT (Singleton/Warm), Pandas
-   **Infra**: AWS Lambda (1536MB), DynamoDB (GSI Optimized), EventBridge (1min Cron)
-   **Safety**: Atomic Persistence (conditional writes), Circuit Breaker (-5% daily).

## 🚀 Deployment

```bash
cd Empire/scripts && python3 deploy.py
```

## 📊 Safety & Risk Management
-   **Atomic Risk**: DynamoDB conditional writes prevent race conditions for double entries.
-   **Circuit Breaker**: Triggered at -5% daily loss or 20% total portfolio risk.
-   **Max Open Positions**: 10 (Dynamic slot allocation).
-   **Cooldown**: 5 minutes per asset (except during active volatility spikes).

---
*Capital: ~$4,677 | Objectif: +1% journalier net*
