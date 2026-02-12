# 🏛️ Empire Trading Bot V12.8
**Professional-grade algorithmic scalping bot with AI-driven decision making and adaptive time management.**

Empire is a high-performance trading system built for AWS Lambda, utilizing Claude 3.5 Sonnet for advanced market analysis, adaptive time exits per asset class, and dynamic capital reallocation strategies.

## 🚀 Key Features (Version 12.8)

### 🎯 **Scalping Strategy**
- **Leverage**: 1x (safety-first approach)
- **Take Profit**: 0.25% (rapid capital rotation)
- **Stop Loss**: 0.40% (sweet spot protection)
- **1% Profit Protection**: Auto-secure significant gains to prevent round-trips
- **Minimum Confidence**: 70% (high-probability trades only)

### ⏱️ **Adaptive TIME_EXIT by Asset Class**
- **Crypto** (BTC, ETH, SOL, XRP): 30min (high volatility, fast momentum)
- **Indices** (SPX): 45min (medium volatility)
- **Commodities** (PAXG): 1h (low volatility, slow momentum)
- **Forex**: 1h (gradual movements)

### 🔄 **"Nouvelle Page Blanche" Philosophy**
- No cooldown timer - allows immediate re-entry after exit
- Forces re-evaluation: "Would I buy this asset NOW at this price?"
- Captures multiple 1% moves on same asset during strong trends
- Profit secured before any re-entry decision

### 💰 **Dynamic Capital Management**
- **Trim & Switch**: Reduce profitable positions (50%) for better opportunities
- **Cut Loss & Switch**: Exit losing positions (-0.5% to 0%) when better signals appear
- **FAST_DISCARD**: Close after 15min if PnL < 0.10% (no momentum)
- **Agnosticisme**: LONG → SHORT switches without delay

### 🤖 **AI-Powered Analysis (Claude 3.5 Sonnet)**
- Advanced news sentiment analysis
- Capitulation/liquidation cascade detection
- BTC correlation analysis for altcoins
- Comparative opportunity analysis for position switching
- Exit decision support for profitable positions

### 📊 **Detailed Logging & Transparency**
- **OPEN reasons**: RSI, Volume, AI confidence, Technical score
- **CLOSE reasons**: TP/SL prices, Duration, PnL, Exit type
- **SKIP reasons**: RSI conditions, Technical score, Trend analysis
- All trades logged with full context for post-analysis

## 📁 Architecture
- `v4_hybrid_lambda.py`: Core execution engine with smart caching and warm-start optimizations.
- `atomic_persistence.py`: Atomic DynamoDB operations for global risk caps and position tracking.
- `exchange_connector.py`: Singleton-based CCXT connector with persistent markets cache.
- `news_fetcher.py`: sentiment analysis with proximity-aware negation and circuit breakers.
- `market_analysis.py`: Multi-timeframe technical indicator calculations and regime detection.
- `decision_engine.py`: Multi-layered approval logic combining TA, Sentiment, and AI.
- `config.py`: Centralized configuration and trading parameters.

## 🛠️ Performance Optimizations

- **DynamoDB GSI**: Position loading via GSI (`18ms` vs `500ms`)
- **Warm Start Cache**: CCXT instances and market data persist between invocations
- **Smart OHLCV Fetch**: Only incremental candles fetched once cache established
- **Lambda Profile**: 1.5GB RAM / 1GB Ephemeral Storage for peak efficiency
- **Float Strict**: All Decimal/Float conversions handled to prevent type errors
- **Atomic Operations**: DynamoDB conditional expressions prevent race conditions

## 📈 Performance Targets

- **Daily Target**: +1.00% net of capital
- **Risk/Reward Ratio**: 1:1.6 (0.25% TP / 0.40% SL)
- **Win Rate Needed**: ~62% (achievable with Claude 3.5 Sonnet filtering)
- **Capital Velocity**: 
  - Crypto: 16 cycles/day possible (30min rotation)
  - Indices: 10 cycles/day possible (45min rotation)
  - Commodities: 8 cycles/day possible (1h rotation)

## 🛠️ Setup & Deployment

1. **Credentials**: Store Binance API keys in AWS Secrets Manager (`trading/binance`)
2. **Configuration**: Edit `Empire/lambda/v4_trader/config.py` for trading limits and thresholds
3. **Deploy**:

   ```bash
   cd Empire/scripts
   bash deploy.sh
   ```

## 📊 Monitoring

- **Dashboard**: Real-time 4-line equity graph (crypto, indices, commodities, forex)
- **Logs**: `aws logs tail /aws/lambda/V4HybridLiveTrader --follow`
- **State**: Check `V4TradingState` table in DynamoDB for active positions
- **Trades**: `EmpireTradesHistory` table contains all OPEN, CLOSED, and SKIPPED trades with detailed reasons

---
*Disclaimer: Trading involves significant risk. This software is provided as-is with no guarantees of profit.*
