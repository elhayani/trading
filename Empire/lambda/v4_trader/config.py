"""
⚙️ EMPIRE TRADING CONFIGURATION
===============================
Centralized settings for the Empire Trading Bot.
"""

class TradingConfig:
    # --- Technical Analysis ---
    MIN_REQUIRED_CANDLES = 250
    
    # --- Technical Score Thresholds ---
    MIN_TECHNICAL_SCORE_CRYPTO = 68
    MIN_TECHNICAL_SCORE_INDICES = 62
    MIN_TECHNICAL_SCORE_FOREX = 65
    MIN_TECHNICAL_SCORE_COMMODITIES = 66
    
    # --- Risk Management ---
    MAX_LOSS_PER_TRADE = 0.02   # 2% of capital
    MAX_DAILY_LOSS_PCT = 0.05   # 5% of capital
    MAX_PORTFOLIO_RISK_PCT = 0.20 # 20% of capital
    COMMISSION_RATE = 0.001     # 0.1% per leg
    SLIPPAGE_BUFFER = 0.001     # 0.1% buffer
    
    # --- Confidence / Sizing ---
    MIN_CONFIDENCE = 0.3
    MAX_CONFIDENCE = 1.0
    
    # --- News Sentiment ---
    NEWS_FRESHNESS_MULTIPLIER = 1.5
    NEWS_SENTIMENT_THRESHOLD = 0.1 # Absolute value
    
    # --- Macro Regime Adjustments ---
    RISK_OFF_HURDLE = 7         # +7 to min technical score
    CRASH_HURDLE = 15           # +15 to min technical score
    
    # --- Cache settings ---
    MACRO_CACHE_TTL_SECONDS = 3600 # 1 hour
