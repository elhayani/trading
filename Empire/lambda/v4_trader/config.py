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
    
    # --- Scalping Strategy (Levier 1) - 8 Symbols / 20 Trades/Day ---
    LEVERAGE = 1                # Force leverage to 1 for safety
    SCALP_TP_MIN = 0.0025       # 0.25% profit target (optimized for fees)
    SCALP_TP_MAX = 0.0025       # 0.25% profit target (fixed)
    SCALP_SL = 0.0050           # 0.50% stop loss (enhanced protection)
    USE_LIMIT_ORDERS = True     # Use limit orders for better execution
    MAX_OPEN_TRADES = 4         # Maximum 4 concurrent positions (slot management)
    
    # --- Confidence / Sizing ---
    MIN_CONFIDENCE = 0.7        # Raised to 70% for scalping (high-probability only)
    MAX_CONFIDENCE = 1.0
    
    # --- News Sentiment ---
    NEWS_FRESHNESS_MULTIPLIER = 1.5
    NEWS_SENTIMENT_THRESHOLD = 0.1 # Absolute value
    
    # --- Macro Regime Adjustments ---
    RISK_OFF_HURDLE = 7         # +7 to min technical score
    CRASH_HURDLE = 15           # +15 to min technical score
    
    # --- Cache settings ---
    MACRO_CACHE_TTL_SECONDS = 3600 # 1 hour

    # --- Exchange Configuration ---
    LIVE_MODE = False  # Set to True for Real Trading, False for Demo/Testnet

