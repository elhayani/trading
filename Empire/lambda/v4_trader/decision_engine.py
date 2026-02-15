import logging
from typing import Dict, Tuple, Union, Optional

# Absolute imports (Critique #1 New)
import models
from models import AssetClass, MarketRegime
import risk_manager
from risk_manager import RiskManager
import config
from config import TradingConfig

logger = logging.getLogger(__name__)

class DecisionEngine:
    """
    Validation engine with absolute imports.
    """

    def __init__(self, risk_manager: RiskManager):
        self.risk_manager = risk_manager

    def evaluate(
        self,
        context: Dict,
        ta_result: Dict,
        symbol: str,
        asset_class: AssetClass = AssetClass.CRYPTO,
        news_score: float = 0.0,
        macro_regime: str = "NORMAL",
        btc_rsi: Optional[float] = None,
        history_context: Optional[Dict] = None,
        intended_direction: Optional[str] = None
    ) -> Tuple[bool, str, float]:
        # 🧭 1. BTC COMPASS VALIDATION (Audit Fix #2)
        from btc_compass import btc_compass
        trade_side = 'BUY' if intended_direction == 'LONG' else 'SELL'
        signal_score = ta_result.get('score', 0)
        
        allowed, compass_reason = btc_compass.validate_trade_direction(
            symbol=symbol,
            trade_side=trade_side,
            signal_strength=signal_score / 100.0
        )
        
        if not allowed:
            logger.warning(f"🧭 [BTC_COMPASS_BLOCK] {symbol} {intended_direction} blocked: {compass_reason}")
            return False, f"BTC_COMPASS: {compass_reason}", 0.0

        if context.get('is_news_blackout'):
            return False, f"NEWS_BLACKOUT: {context.get('news_reason', 'Major Event')}", 0.0

        if not context.get('can_trade', True):
            return False, "MACRO_STOP", 0.0

        # 🏛️ EMPIRE V13.6: Memory of 20 Events (Injection for analysis only)
        if history_context:
            logger.info(f"[HISTORY_CONTEXT] Injected {len(history_context.get('skipped', []))} skipped and {len(history_context.get('history', []))} history events for analysis.")
        
        # 🏛️ EMPIRE V15.8: Absolute 24H Volume Filter
        volume_24h = ta_result.get('volume_24h_usdt', 0)
        min_vol = TradingConfig.MIN_VOLUME_24H
        
        if volume_24h > 0 and volume_24h < min_vol:
            logger.warning(f"⚠️ {symbol} - Low 24H Volume: ${volume_24h/1e6:.1f}M < ${min_vol/1e6:.0f}M")
            return False, f"Low 24H Volume (${volume_24h/1e6:.1f}M < ${min_vol/1e6:.0f}M)", 0.0
        
        # Momentum: Pas besoin de filtre BTC RSI - si le prix bouge fort maintenant, on trade maintenant
        
        # Momentum: Pas besoin de filtre macro_regime - trop lent pour du 1min
        
        # Vérification score minimum avec asymétrie SHORT (EMPIRE V16.7.5)
        score = ta_result.get('score', 0)
        min_score = TradingConfig.MIN_MOMENTUM_SCORE
        
        if intended_direction == 'SHORT':
            min_score = max(min_score, 85)
            
        if score < min_score:
            return False, f"LOW_MOMENTUM_SCORE_{score} (Min={min_score} for {intended_direction})", 0.0

        # Corridor check removed - module doesn't exist
        # All markets considered open for trading

        confidence = score / 100.0
        # News sentiment removed for momentum scalping (1-10min holding)
        # Price action only - no need for slow news impact
        
        return True, "PROCEED", min(1.0, confidence)

    def evaluate_with_risk(
        self,
        context: Dict,
        ta_result: Dict,
        symbol: str,
        capital: float,
        direction: str = "LONG",
        asset_class: AssetClass = AssetClass.CRYPTO,
        news_score: float = 0.0,
        macro_regime: str = "NORMAL",
        btc_rsi: Optional[float] = None,
        history_context: Optional[Dict] = None,
        compound_capital: float = None
    ) -> Dict[str, Union[bool, str, float]]:
        proceed, reason, confidence = self.evaluate(
            context, ta_result, symbol, 
            asset_class=asset_class,
            news_score=news_score,
            macro_regime=macro_regime,
            btc_rsi=btc_rsi,
            history_context=history_context,
            intended_direction=direction
        )
        
        if not proceed:
            return {"proceed": False, "reason": reason, "quantity": 0}

        entry_price = ta_result.get("price", 0)
        atr = ta_result.get("atr", 0)
        
        stop_loss = self.risk_manager.calculate_stop_loss(entry_price, atr, direction)

        vix = context.get('vix', 20.0)
        sizing = self.risk_manager.calculate_position_size(
            capital=capital,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            confidence=confidence,
            atr=atr,
            direction=direction,
            compound_capital=compound_capital,
            signal_score=ta_result.get('score', 60),
            symbol=symbol,
            vix=vix
        )

        if sizing["blocked"]:
            return {"proceed": False, "reason": f"RISK_BLOCKED_{sizing['reason']}", "quantity": 0}

        # 🏛️ EMPIRE V16.1: Filtre rentabilité minimum (frais de transaction)
        quantity = sizing["quantity"]
        notional_value = quantity * entry_price
        
        # Frais round-trip = notional × 0.001 × 2 = 0.2%
        estimated_fees = notional_value * 0.002
        
        # Profit minimum = frais + petite marge (0.05% de notional)
        min_profit_needed = estimated_fees + (notional_value * 0.0005)
        
        # TP attendu avec ATR
        tp_pct = atr * TradingConfig.TP_MULTIPLIER / entry_price
        tp_pct = max(tp_pct, TradingConfig.MIN_TP_PCT)  # Minimum 0.25% floor
        
        expected_profit = (entry_price * tp_pct) * quantity
        
        if notional_value < TradingConfig.MIN_NOTIONAL_VALUE:
            return {"proceed": False, "reason": f"MIN_NOTIONAL: ${notional_value:.0f} < ${TradingConfig.MIN_NOTIONAL_VALUE}", "quantity": 0}
        
        if expected_profit < min_profit_needed:
            return {"proceed": False, "reason": f"MIN_PROFIT: Expected ${expected_profit:.2f} < Needed ${min_profit_needed:.2f} (fees + target)", "quantity": 0}

        return {
            "proceed": True,
            "reason": "PROCEED",
            "quantity": sizing["quantity"],
            "stop_loss": stop_loss,
            "risk_dollars": sizing["risk"],
            "confidence": confidence,
            "leverage": sizing.get("adaptive_leverage", TradingConfig.LEVERAGE)
        }
