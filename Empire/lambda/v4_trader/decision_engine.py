import logging
from typing import Dict, Tuple, Union, Optional

# Absolute imports (Critique #1 New)
import models
from models import AssetClass, MarketRegime
import risk_manager
from risk_manager import RiskManager
import config
from config import TradingConfig
import micro_corridors as corridors

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
        history_context: Optional[Dict] = None
    ) -> Tuple[bool, str, float]:
        if not context.get('can_trade', True):
            return False, "MACRO_STOP", 0.0

        # 🏛️ EMPIRE V13.6: Memory of 20 Events (Injection for analysis only)
        if history_context:
            logger.info(f"[HISTORY_CONTEXT] Injected {len(history_context.get('skipped', []))} skipped and {len(history_context.get('history', []))} history events for analysis.")
        
        # 🏛️ EMPIRE V13.7: Volume Elite Filter (Volume Surge Requirement)
        vol_ratio = ta_result.get('vol_ratio', 1.0)
        if vol_ratio < 1.3:
            return False, f"Low Volume Momentum (Ratio: {vol_ratio:.1f}x < 1.3x)", 0.0
        
        # 🏛️ EMPIRE V13.5: The Bedrock Matrix (BTC Unified Filter)
        if asset_class == AssetClass.CRYPTO and btc_rsi is not None and "BTC" not in symbol:
            direction = 'SHORT' if ta_result.get('signal_type') == 'SHORT' else 'LONG'
            
            if btc_rsi > 70:
                if direction == 'SHORT':
                    return False, f"BEDROCK_BLOCK_SHORT (BTC_RSI={btc_rsi:.1f} > 70)", 0.0
            elif btc_rsi < 30:
                if direction == 'LONG':
                    return False, f"BEDROCK_BLOCK_LONG (BTC_RSI={btc_rsi:.1f} < 30)", 0.0

        base_thresholds = {
            AssetClass.CRYPTO: TradingConfig.MIN_TECHNICAL_SCORE_CRYPTO,
            AssetClass.INDICES: TradingConfig.MIN_TECHNICAL_SCORE_INDICES,
            AssetClass.FOREX: TradingConfig.MIN_TECHNICAL_SCORE_FOREX,
            AssetClass.COMMODITIES: TradingConfig.MIN_TECHNICAL_SCORE_COMMODITIES
        }
        min_score = base_thresholds.get(asset_class, TradingConfig.MIN_TECHNICAL_SCORE_CRYPTO)

        if macro_regime in ['RISK_OFF', 'BEARISH']:
            min_score += TradingConfig.RISK_OFF_HURDLE
        elif macro_regime == 'CRASH':
            min_score += TradingConfig.CRASH_HURDLE

        score = ta_result.get('score', 0)
        
        if score < min_score:
            return False, f"LOW_SCORE_{score} (Min={min_score})", 0.0

        corridor = corridors.get_corridor_params(symbol)
        if corridor.get('regime') == MarketRegime.CLOSED:
            return False, "MARKET_CLOSED", 0.0

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
        history_context: Optional[Dict] = None
    ) -> Dict[str, Union[bool, str, float]]:
        proceed, reason, confidence = self.evaluate(
            context, ta_result, symbol, 
            asset_class=asset_class,
            news_score=news_score,
            macro_regime=macro_regime,
            btc_rsi=btc_rsi,
            history_context=history_context
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
            direction=direction
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
