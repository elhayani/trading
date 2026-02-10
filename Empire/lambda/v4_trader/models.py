from enum import Enum

class MarketRegime(Enum):
    """Unified Market Regime classification"""
    # Technical Regimes
    BULL_TREND = "bull_trend"
    BEAR_TREND = "bear_trend"
    HIGH_VOLATILITY = "high_volatility"
    RANGE_BOUND = "range_bound"
    CRASH = "crash"
    RECOVERY = "recovery"
    
    # Corridor/Session Regimes
    AGGRESSIVE_BREAKOUT = "AGGRESSIVE_BREAKOUT"
    TREND_FOLLOWING = "TREND_FOLLOWING"
    PULLBACK_SNIPER = "PULLBACK_SNIPER"
    CAUTIOUS_REVERSAL = "CAUTIOUS_REVERSAL"
    SCALPING = "SCALPING"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    CLOSED = "CLOSED"

class AssetClass(Enum):
    """Asset classification"""
    CRYPTO = "crypto"
    FOREX = "forex"
    COMMODITIES = "commodities"
    INDICES = "indices"
