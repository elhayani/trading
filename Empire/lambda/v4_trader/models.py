from enum import Enum

class MarketRegime(Enum):
    """Unified Market Regime classification (Audit Fix P2.12)"""
    # Technical Regimes
    BULL_TREND = "BULL_TREND"
    BEAR_TREND = "BEAR_TREND"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    RANGE_BOUND = "RANGE_BOUND"
    CRASH = "CRASH"
    RECOVERY = "RECOVERY"
    NORMAL = "NORMAL"
    RISK_OFF = "RISK_OFF"
    BEARISH = "BEARISH"
    
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
    CRYPTO = "Crypto"
    FOREX = "Forex"
    COMMODITIES = "Commodities"
    INDICES = "Indices"
