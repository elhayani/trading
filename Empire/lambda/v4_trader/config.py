"""
⚙️ EMPIRE TRADING CONFIGURATION - MOMENTUM SCALPING ARCHITECTURE
================================================================
Optimized for: 1-minute momentum scalping with compound effect
"""

import os

class TradingConfig:
    # --- V16.0 Momentum Scalping Configuration ---
    
    # Momentum Strategy (1-minute pure momentum)
    LEVERAGE_BASE = 5              # Base leverage (adaptive 2-7)
    MAX_OPEN_TRADES = 3
    MIN_VOLUME_24H = 5_000_000     # $5M minimum
    
    # 🏛️ EMPIRE V16.1: Filtres anti-pertes (frais de transaction)
    MIN_NOTIONAL_VALUE = 300      # $300 minimum par trade (Optimisé pour la balance réelle)
    MIN_TP_PCT = 0.0025            # TP minimum 0.25% (Objectif net)
    FAST_EXIT_MINUTES = 3          # 3 minutes (Délai de stagnation)
    FAST_EXIT_PNL_THRESHOLD = 0.0002 # Sortie si stagnant au-dessus de +0.02% (couvre frais BNB)
    
    # TP/SL Dynamic (ATR-based)
    TP_MULTIPLIER = 2.0            # TP = 2 × ATR_1min
    SL_MULTIPLIER = 1.0            # SL = 1 × ATR_1min
    MAX_HOLD_CANDLES = 10          # Force exit after 10 minutes
    MAX_HOLD_MINUTES = 10          # Explicit time limit
    FORCE_EXIT_AFTER_CANDLES = 10  # Same as MAX_HOLD_CANDLES
    
    # Momentum Indicators
    EMA_FAST = 5
    EMA_SLOW = 13
    VOLUME_SURGE_RATIO = 1.5
    MIN_MOMENTUM_SCORE = 60
    MIN_ATR_PCT_1MIN = 0.25
    
    # Session Boost
    SESSION_BOOST_MULTIPLIER = 2.0  # Max boost
    
    # Technical Analysis
    MIN_REQUIRED_CANDLES = 250
    
    # --- Risk Management ---
    MAX_LOSS_PER_TRADE = 0.02
    MAX_DAILY_LOSS_PCT = 0.05
    MAX_PORTFOLIO_RISK_PCT = 0.20
    MAX_LOSS_PER_TRADE_PCT = 2.0  # Jamais plus de 2% du capital sur un seul trade
    COMMISSION_RATE = 0.001  # 0.1% per leg
    SLIPPAGE_BUFFER = 0.001  # 0.1% slippage
    
    # ================================================================
    # V16.0 MOMENTUM SCALPING - 1 MINUTE PURE MOMENTUM
    # ================================================================
    
    # Compound
    USE_COMPOUND = True             # Le gain de chaque trade s'ajoute au capital
    COMPOUND_BASE_CAPITAL = float(os.getenv('CAPITAL', '0')) # 0 = Utilise la balance réelle au démarrage
    
    # Capital scaling et protection liquidité (Dynamique selon balance réelle)
    MIN_ATR_PCT_1MIN = 0.25          # Seuil de rentabilité
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
    SECRET_NAME = "trading/binance"

    # ================================================================
    # V16.0: Legacy parameters removed (not used in momentum strategy)
    # - VWAP, ADX, ATR_SL_MULTIPLIER (replaced by TP/SL_MULTIPLIERS)
    # ================================================================

    # ================================================================
    # V16.0 MOMENTUM SCALPING TARGETS
    # ================================================================
    TARGET_DAILY_RETURN = 0.01      # +1% per day
    TARGET_TRADES_PER_DAY = 50      # 40-70 range (median)
    TARGET_WIN_RATE = 0.58          # 58% win rate
    TARGET_AVG_HOLD_TIME = 5        # 5 minutes average
    
    # Legacy compatibility
    LEVERAGE = LEVERAGE_BASE         # Alias for existing code
    
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
