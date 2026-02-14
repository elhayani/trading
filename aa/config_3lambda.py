"""
⚙️ EMPIRE TRADING CONFIGURATION - 3-LAMBDA ARCHITECTURE
========================================================
Optimized for: +1% per day target with Quick Exit strategy
"""

class TradingConfig:
    # --- Technical Analysis ---
    MIN_REQUIRED_CANDLES = 250
    
    # --- Technical Score Thresholds (Adjusted for high frequency) ---
    MIN_TECHNICAL_SCORE_CRYPTO = 55  # Lowered from 60 for more opportunities
    MIN_TECHNICAL_SCORE_INDICES = 60
    MIN_TECHNICAL_SCORE_FOREX = 60
    MIN_TECHNICAL_SCORE_COMMODITIES = 60
    
    # --- Risk Management ---
    MAX_LOSS_PER_TRADE = 0.02
    MAX_DAILY_LOSS_PCT = 0.05
    MAX_PORTFOLIO_RISK_PCT = 0.20
    COMMISSION_RATE = 0.001  # 0.1% per leg
    SLIPPAGE_BUFFER = 0.001  # 0.1% slippage
    
    # ================================================================
    # SCALPING STRATEGY - ELITE QUICK EXIT (3-LAMBDA OPTIMIZED)
    # ================================================================
    
    LEVERAGE = 5  # x5 leverage to amplify micro-movements
    
    # Progressive TP Ladder (Quick Exit Strategy)
    # Lambda 2/3 will capture these TPs at 20s/40s intervals
    TP_QUICK = 0.0025   # 0.25% → First exit target (70% position)
    TP_FINAL = 0.0050   # 0.50% → Second exit target (30% position)
    
    # Stop Loss (tight for quick scalping)
    SL = 0.0020         # 0.20% stop loss
    
    # Backward compatibility (used by risk_manager.py)
    SCALP_TP_MIN = TP_QUICK
    SCALP_TP_MAX = TP_FINAL
    SCALP_SL = SL
    SCALP_SL_SHORT = SL
    
    # Quick Exit Settings
    USE_PROGRESSIVE_EXIT = True  # Enable TP ladder
    QUICK_EXIT_PERCENTAGE = 0.70  # 70% exit at TP_QUICK
    FINAL_EXIT_PERCENTAGE = 0.30  # 30% exit at TP_FINAL
    
    # Multi-Lambda Coordination
    MAX_OPEN_TRADES = 6  # Increased from 5 for high-frequency (12 trades/day target)
    USE_LIMIT_ORDERS = True
    
    # --- PAXG Specific (unchanged) ---
    PAXG_LEVERAGE = 6
    PAXG_TP = 0.0040
    PAXG_SL = 0.0030

    # --- Indices / Forex Specific (unchanged) ---
    INDICES_TP = 0.0030
    INDICES_SL = 0.0020
    FOREX_TP = 0.0030
    FOREX_SL = 0.0020
    
    # --- Confidence / Sizing ---
    MIN_CONFIDENCE = 0.65  # Lowered from 0.70 for more opportunities
    MAX_CONFIDENCE = 1.0
    
    # --- News Sentiment (disabled for speed) ---
    NEWS_FRESHNESS_MULTIPLIER = 1.0  # Disabled
    NEWS_SENTIMENT_THRESHOLD = 0.5    # Very high threshold = disabled
    
    # --- Macro Regime Adjustments ---
    RISK_OFF_HURDLE = 5
    CRASH_HURDLE = 12
    
    # --- Cache settings ---
    MACRO_CACHE_TTL_SECONDS = 3600
    
    # --- Exchange Configuration ---
    LIVE_MODE = True  # Set to True for production

    # ================================================================
    # VWAP Filters (Relaxed for micro-cap opportunities)
    # ================================================================
    VWAP_LONG_MIN_DIST = -8.0   # Can enter LONG up to -8% below VWAP
    VWAP_SHORT_MAX_DIST = 8.0   # Can enter SHORT up to +8% above VWAP
    
    # ================================================================
    # ADX Filters (Relaxed to capture more setups)
    # ================================================================
    ADX_MIN_TREND = 15.0        # Lowered from 20 (accept moderate trends)
    ADX_STRONG_TREND = 25.0
    
    # ================================================================
    # ATR Filters
    # ================================================================
    ATR_SL_MULTIPLIER = 1.5
    ATR_MAX_SL_MULTIPLIER = 2.5  # Cap SL at 2.5x base (prevents huge SLs)
    
    ATR_MAX_VOLATILITY = {
        'crypto': 5.0,
        'forex': 1.0,
        'indices': 2.0,
        'commodities': 3.0
    }

    # ================================================================
    # PERFORMANCE TARGETS (for monitoring)
    # ================================================================
    TARGET_DAILY_RETURN = 0.01      # +1% per day
    TARGET_TRADES_PER_DAY = 12      # 12 trades/day
    TARGET_WIN_RATE = 0.58          # 58% win rate
    
    # Expected performance per trade (with levier x5)
    EXPECTED_WIN_NET = 0.0128       # +1.28% net per win
    EXPECTED_LOSS_NET = -0.0140     # -1.40% net per loss
    
    # Breakeven win rate
    BREAKEVEN_WIN_RATE = 0.52       # 52% needed for profitability

    # ================================================================
    # EMPIRE ASSET CONFIGURATION (unchanged)
    # ================================================================
    EMPIRE_ASSETS = {
        "BTC/USDT:USDT": {"leverage": 5, "class": "crypto", "role": "Leader", "notes": "Global 24/7"},
        "ETH/USDT:USDT": {"leverage": 5, "class": "crypto", "role": "Major Altcoin", "notes": "Global 24/7"},
        "SOL/USDT:USDT": {"leverage": 5, "class": "crypto", "role": "High Volatility", "notes": "Global 24/7"},
        "AVAX/USDT:USDT": {"leverage": 5, "class": "crypto", "role": "V13.8 Elite", "notes": "Ecosystem Hub"},
        "LINK/USDT:USDT": {"leverage": 5, "class": "crypto", "role": "V13.8 Elite", "notes": "Oracle Backbone"},
        "ADA/USDT:USDT": {"leverage": 5, "class": "crypto", "role": "V13.8 Elite", "notes": "Research Based"},
        "DOT/USDT:USDT": {"leverage": 5, "class": "crypto", "role": "V13.8 Elite", "notes": "Interoperability"},
        "POL/USDT:USDT": {"leverage": 5, "class": "crypto", "role": "V13.8 Elite", "notes": "L2 Alpha"},
        "XRP/USDT:USDT": {"leverage": 5, "class": "crypto", "role": "News/Asia", "notes": "Night (Asia)"},
        "BNB/USDT:USDT": {"leverage": 5, "class": "crypto", "role": "Binance Eco", "notes": "Global 24/7"},
        "DOGE/USDT:USDT": {"leverage": 5, "class": "crypto", "role": "Retail Sentiment", "notes": "Random"},
        "PAXG/USDT:USDT": {"leverage": 6, "class": "commodities", "role": "Gold Shield", "notes": "Safe Haven"},
        "OIL/USDT:USDT": {"leverage": 5, "class": "commodities", "role": "WTI Crude", "notes": "Geopolitical"},
        "SPX/USDT:USDT": {"leverage": 5, "class": "indices", "role": "S&P 500", "notes": "15:30 (USA)"},
        "DAX/USDT:USDT": {"leverage": 5, "class": "indices", "role": "GER40", "notes": "09:00 (Europe)"},
        "NDX/USDT:USDT": {"leverage": 5, "class": "indices", "role": "NASDAQ 100", "notes": "V13.8 Elite High-Growth"},
        "EUR/USD:USDT": {"leverage": 5, "class": "forex", "role": "Major Pair", "notes": "24/7"},
        "GBP/USD:USDT": {"leverage": 5, "class": "forex", "role": "V13.8 Elite Sterling", "notes": "Volatile Forex"},
        "USD/JPY:USDT": {"leverage": 5, "class": "forex", "role": "V13.8 Elite Yen", "notes": "Safe Haven FX"},
    }
