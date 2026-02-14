"""
⚙️ EMPIRE TRADING CONFIGURATION - 3-LAMBDA ARCHITECTURE
========================================================
Optimized for: +1% per day target with Quick Exit strategy
"""

class TradingConfig:
    # --- Technical Analysis ---
    MIN_REQUIRED_CANDLES = 250
    
    # --- Technical Score Thresholds (Adjusted for high frequency) ---
    MIN_TECHNICAL_SCORE_CRYPTO = 45  # Lowered for V15.7 Scalp Mode
    MIN_TECHNICAL_SCORE_INDICES = 60
    MIN_TECHNICAL_SCORE_FOREX = 60
    MIN_TECHNICAL_SCORE_COMMODITIES = 60
    
    # Minimum 24H Volume in USDT for scalping eligibility
    MIN_VOLUME_24H = 10_000_000  # $10M USDT/day
    
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
    
    # Quick Exit Settings
    USE_PROGRESSIVE_EXIT = True  # Enable TP ladder
    QUICK_EXIT_PERCENTAGE = 0.70  # 70% exit at TP_QUICK
    FINAL_EXIT_PERCENTAGE = 0.30  # 30% exit at TP_FINAL
    
    # Multi-Lambda Coordination
    MAX_OPEN_TRADES = 4  # Limited as requested by user
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
    
    # --- News Sentiment ---
    NEWS_SENTIMENT_THRESHOLD = 0.5    # Very high threshold = disabled
    
    # --- Macro Regime Adjustments ---
    RISK_OFF_HURDLE = 5
    CRASH_HURDLE = 12
    
    # --- Cache settings ---
    MACRO_CACHE_TTL_SECONDS = 3600
    
    # --- Exchange Configuration ---
    LIVE_MODE = False  # Set to True for production

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
    ATR_MAX_SL_MULTIPLIER = 2.5

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
    # ASSET CONFIGURATION - Dynamic based on symbol detection
    # ================================================================
    
    @staticmethod
    def get_asset_config(symbol: str) -> dict:
        """Get dynamic asset configuration based on symbol"""
        # Normalize symbol for comparison
        symbol_normalized = symbol.replace('/USDT:USDT', '').replace('USDT', '')
        
        # Special configurations
        if symbol_normalized == 'PAXG':
            return {"leverage": TradingConfig.PAXG_LEVERAGE, "class": "commodities", "role": "Gold Shield", "notes": "Safe Haven"}
        elif symbol_normalized == 'BTC':
            return {"leverage": TradingConfig.LEVERAGE, "class": "crypto", "role": "Leader", "notes": "Global 24/7"}
        elif symbol_normalized == 'ETH':
            return {"leverage": TradingConfig.LEVERAGE, "class": "crypto", "role": "Major Altcoin", "notes": "Global 24/7"}
        else:
            # Default configuration for all other symbols
            return {"leverage": TradingConfig.LEVERAGE, "class": "crypto", "role": "Altcoin", "notes": "Dynamic"}
    
    @staticmethod
    def is_paxg(symbol: str) -> bool:
        """Check if symbol is PAXG"""
        return symbol.replace('/USDT:USDT', '').replace('USDT', '') == 'PAXG'
