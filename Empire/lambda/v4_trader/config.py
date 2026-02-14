"""
⚙️ EMPIRE TRADING CONFIGURATION - MOMENTUM SCALPING ARCHITECTURE
================================================================
Optimized for: 1-minute momentum scalping with compound effect
"""

import os

class TradingConfig:
    # --- Technical Analysis ---
    MIN_REQUIRED_CANDLES = 250
    
    # --- Technical Score Thresholds (Adjusted for high frequency) ---
    MIN_TECHNICAL_SCORE_CRYPTO = 45  # Lowered for V15.7 Scalp Mode
    MIN_TECHNICAL_SCORE_INDICES = 60
    MIN_TECHNICAL_SCORE_FOREX = 60
    MIN_TECHNICAL_SCORE_COMMODITIES = 60
    
    # Minimum 24H Volume in USDT for scalping eligibility
    # Note: MIN_VOLUME_24H is defined below in momentum section
    
    # --- Risk Management ---
    MAX_LOSS_PER_TRADE = 0.02
    MAX_DAILY_LOSS_PCT = 0.05
    MAX_PORTFOLIO_RISK_PCT = 0.20
    MAX_LOSS_PER_TRADE_PCT = 2.0  # Jamais plus de 2% du capital sur un seul trade
    COMMISSION_RATE = 0.001  # 0.1% per leg
    SLIPPAGE_BUFFER = 0.001  # 0.1% slippage
    
    # ================================================================
    # MOMENTUM SCALPING STRATEGY - 1 MINUTE PURE MOMENTUM
    # ================================================================
    
    LEVERAGE = 5
    MAX_OPEN_TRADES = 3
    MIN_VOLUME_24H = 5_000_000      # $5M minimum
    
    # Momentum TP/SL (basés sur ATR 1 min)
    TP_MULTIPLIER = 2.0             # TP = 2 × ATR_1min
    SL_MULTIPLIER = 1.0             # SL = 1 × ATR_1min
    MAX_HOLD_CANDLES = 10           # Fermer de force après 10 bougies 1min
    
    # Momentum signal
    EMA_FAST = 5                    # EMA rapide sur bougies 1min
    EMA_SLOW = 13                   # EMA lente sur bougies 1min
    VOLUME_SURGE_RATIO = 1.5        # Volume doit être 1.5x la moyenne des 20 dernières bougies
    MIN_MOMENTUM_SCORE = 60         # Score minimum pour ouvrir
    
    # Compound
    USE_COMPOUND = True             # Le gain de chaque trade s'ajoute au capital
    COMPOUND_BASE_CAPITAL = float(os.getenv('CAPITAL', '10000'))
    
    # Capital scaling et protection liquidité
    MIN_ATR_PCT_1MIN = 0.25          # Rentable dès ce niveau avec $10K
    MAX_NOTIONAL_PCT_OF_VOLUME = 0.005  # 0.5% max du volume 24h par trade
    
    # Session optimization
    SESSION_BOOST_ENABLED = True       # Activer pondération par session
    NIGHT_PUMP_DETECTION = True        # Détecter pumps nocturnes
    MIN_VOL_1H_USDT = 150_000         # $150K/heure minimum
    
    # Multi-Lambda Coordination
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
    # REMOVED: News sentiment disabled for momentum scalping (1-10min holding)
    # NEWS_SENTIMENT_THRESHOLD = 0.5  # Not used - scalping relies on price action only
    
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
    
    @staticmethod
    def get_scaling_config(capital: float) -> dict:
        """Configuration automatique selon le capital pour 415 actifs"""
        if capital < 60_000:
            return {
                'min_volume':    5_000_000,
                'max_trades':    3,
                'leverage':      5,
                'eligible':      '~115 actifs',
                'note':          'Full universe - 415 actifs'
            }
        elif capital < 150_000:
            return {
                'min_volume':   20_000_000,
                'max_trades':    3,
                'leverage':      5,
                'eligible':      '~55 actifs',
                'note':          'Liquid mid-cap'
            }
        elif capital < 500_000:
            return {
                'min_volume':   50_000_000,
                'max_trades':    3,
                'leverage':      3,
                'eligible':      '~15 actifs',
                'note':          'Large cap only'
            }
        else:
            return {
                'min_volume':  200_000_000,
                'max_trades':    2,
                'leverage':      2,
                'eligible':      '~5 actifs',
                'note':          'BTC ETH SOL XRP BNB only'
            }
