# � Empire Trading Ecosystem — V16.0 (Momentum Scalping)
**High-Frequency Algorithmic Trading Infrastructure with 1-Minute Momentum Strategy.**

## 📡 Architecture

### Core Trading Engine (`Empire/lambda/v4_trader/`)
AWS Lambda now utilizes **Momentum Scalping Scanner** to monitor **415+ Binance Futures assets** in real-time (approx. 16s scan time). The system dynamically selects the best opportunities using session-aware momentum scoring.

| Catégorie | Description | Levier | TP | SL |
|---|---|---|---|---|
| **Crypto Leaders** | BTC, ETH, SOL, BNB, XRP | **x2-x7** | 2×ATR | 1×ATR |
| **Elite Alts** | AVAX, LINK, ADA, DOT, etc. | **x2-x7** | 2×ATR | 1×ATR |
| **Pump/Meme** | DOGE, SHIB, PEPE | **x2-x7** | 2×ATR | 1×ATR |
| **Commodities** | PAXG (Gold) | **x4** | 0.40% | 0.30% |
| **Indices** | SPX, NDX, DAX | **x2-x7** | 2×ATR | 1×ATR |
| **Forex** | EUR, GBP, JPY | **x2-x7** | 2×ATR | 1×ATR |

> **Adaptive Leverage Strategy**:
> - **Score 90+**: x7 (Elite signals)
> - **Score 80+**: x5 (Strong signals)
> - **Score 70+**: x3 (Good signals)
> - **Score 60+**: x2 (Limit signals)

### 🧠 V16 Momentum Scanner Logic
The new **Momentum Scanner** evaluates 3 core metrics in real-time to generate a Momentum Score (0-100):

1.  **EMA Crossover**: EMA5 crosses EMA13 on 1min timeframe
2.  **Volume Surge**: Recent volume ≥ 1.5x average volume
3.  **Price Thrust**: Price movement ≥ 0.20% in 5 minutes

### Session-Aware Optimization (24/7 Trading)
| Heure UTC | Session | Actifs boostés | Multiplicateur |
|-----------|---------|----------------|---------------|
| **00H-08H** | Asie active | BNB, TRX, ADA, DOT, JASMY | **×2.0** |
| **07H-16H** | Europe active | BTC, ETH, LINK, UNI | **×1.8** |
| **13H-22H** | US active | SOL, AVAX, DOGE, PEPE | **×2.0** |
| **Autres** | Transition | Tous | **×1.0** |

### Key Features
-   **Momentum-First**: Pure momentum strategy (no mean reversion)
-   **Session Boosts**: Dynamic weighting by trading session
-   **Night Pump Detection**: Automatic detection of sudden moves
-   **Adaptive Leverage**: Risk-adjusted exposure based on signal strength
-   **Compound Capital**: Gains automatically reinvested
-   **Smart Pre-filter**: Eliminates 90% of flat assets before analysis

### Tech Stack
-   **Runtime**: Python 3.12, CCXT (Singleton/Warm), Pandas
-   **Infra**: AWS Lambda (1536MB), DynamoDB (GSI Optimized), EventBridge (1min Cron)
-   **Safety**: Atomic Persistence (conditional writes), Circuit Breaker (-5% daily)

## 🚀 Deployment

```bash
cd Empire/scripts && python3 deploy.py
```

## 📊 Safety & Risk Management
-   **Atomic Risk**: DynamoDB conditional writes prevent race conditions for double entries.
-   **Circuit Breaker**: Triggered at -5% daily loss or 20% total portfolio risk.
-   **Max Open Positions**: 3 (Dynamic slot allocation).
-   **Max Loss per Trade**: 2% of capital with automatic leverage reduction.
-   **Liquidity Protection**: Max 0.5% of 24h volume per position.
-   **Session-Aware**: Adaptive filters based on trading session volatility.

## 📈 Performance Expectations
- **Daily Trades**: 40-70 (vs 15 previously)
- **Win Rate**: 55-60% (vs 21.7% previously)
- **Daily Return**: +1% to +1.5% target
- **Max Drawdown**: <5% (vs 24.8% previously)
- **Coverage**: 24/7 trading with session optimization

## 🎯 Strategy Philosophy
> **Pure Momentum**: Buy when price rises with volume, sell when price falls with volume
> 
> **Quick Exits**: 2-10 minute holding periods with compound capital
> 
> **Session Optimization**: Different assets thrive during different market hours
> 
> **Adaptive Risk**: Higher conviction = higher leverage, lower conviction = reduced exposure

## 🔧 Configuration Highlights
```python
# Momentum Strategy
LEVERAGE = 5  # Adaptive 2-7 based on score
MAX_OPEN_TRADES = 3
MIN_VOLUME_24H = 5_000_000  # $5M minimum

# TP/SL Dynamic
TP_MULTIPLIER = 2.0  # TP = 2 × ATR_1min
SL_MULTIPLIER = 1.0  # SL = 1 × ATR_1min
MAX_HOLD_CANDLES = 10  # 10 minutes max

# Momentum Indicators
EMA_FAST = 5
EMA_SLOW = 13
MIN_MOMENTUM_SCORE = 60
MIN_ATR_PCT_1MIN = 0.25

# Features
USE_COMPOUND = True
SESSION_BOOST_ENABLED = True
NIGHT_PUMP_DETECTION = True
```

## 🚀 Deployment

```bash
cd Empire/scripts && python3 deploy.py
```

---
*Capital: $10,000 | Target: +1% daily net | Strategy: Momentum Scalping 1Min*
