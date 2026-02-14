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
        
        # Vérification score minimum pour momentum
        score = ta_result.get('score', 0)
        min_score = TradingConfig.MIN_MOMENTUM_SCORE
        
        if score < min_score:
            return False, f"LOW_MOMENTUM_SCORE_{score} (Min={min_score})", 0.0

        # Corridor check removed - module doesn't exist
        # All markets considered open for trading

        confidence = score / 100.0
        if news_score > 0.3: confidence *= 1.2
        elif news_score < -0.3: confidence *= 0.8
        
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

        sizing = self.risk_manager.calculate_position_size(
            capital=capital,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            confidence=confidence,
            atr=atr,
            direction=direction,
            compound_capital=compound_capital
        )

        if sizing["blocked"]:
            return {"proceed": False, "reason": f"RISK_BLOCKED_{sizing['reason']}", "quantity": 0}

        return {
            "proceed": True,
            "reason": "PROCEED",
            "quantity": sizing["quantity"],
            "stop_loss": stop_loss,
            "risk_dollars": sizing["risk_dollars"],
            "estimated_commission": sizing["estimated_commission"],
            "confidence": confidence,
            "direction": direction,
        }
