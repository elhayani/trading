"""
Empire Decision Engine V11 - Safety Hardened
=============================================
4-Level hierarchy with integrated RiskManager.
"""

import logging
from typing import Dict, Tuple
from models import MarketRegime
import micro_corridors as corridors
from risk_manager import RiskManager

logger = logging.getLogger(__name__)


class DecisionEngine:
    """
    Centralized 4-Level Decision Architecture (V11 Safety Hardened)
    
    Level 1: Macro Veto (Global Safety)
    Level 2: Technical Validation (Signal Quality ≥ 60)
    Level 3: Micro Timing (Corridor Awareness)
    Level 4: Risk-Based Position Sizing (RiskManager)
    """

    def __init__(self, commission_rate: float = 0.001):
        self.risk_manager = RiskManager()
        self.commission_rate = commission_rate

    @staticmethod
    def evaluate(context, ta_result: Dict, symbol: str) -> Tuple[bool, str, float]:
        """
        Lightweight evaluation (backward-compatible).
        Returns: (proceed: bool, reason: str, size_multiplier: float)
        Used by existing callers that don't need full risk sizing.
        """

        # LEVEL 1: MACRO VETO (Absolute Block)
        if not context.can_trade:
            return False, "MACRO_VETO", 0.0

        # LEVEL 2: TECHNICAL VALIDATION (Signal Quality)
        score = ta_result.get('score', 0)
        if score < 60:  # Audit Fix V11: restored to 60
            logger.warning(f"🚫 Level 2 Veto: Signal score {score}/100 < 60")
            return False, f"LOW_TECHNICAL_SCORE_{score}", 0.0

        # LEVEL 3: MICRO TIMING (Corridor Check)
        params = corridors.get_corridor_params(symbol)
        regime = params.get('regime')
        if regime == MarketRegime.CLOSED:
            logger.info(f"⏳ Level 3 Block: Market CLOSED for {symbol}")
            return False, f"BAD_TIMING_{regime}", 0.0

        # LOW_LIQUIDITY = reduce size 50% instead of veto
        liquidity_multiplier = 0.5 if regime == MarketRegime.LOW_LIQUIDITY else 1.0
        if regime == MarketRegime.LOW_LIQUIDITY:
            logger.info(f"⚠️ Low liquidity for {symbol} - reducing size 50%")

        # LEVEL 4: MACRO ADJUSTMENT (Sizing) - Capped at 1.0
        confidence = context.confidence_score
        confidence = max(0.3, min(1.0, confidence)) * liquidity_multiplier

        return True, "PROCEED", confidence

    def evaluate_with_risk(
        self,
        context,
        ta_result: Dict,
        symbol: str,
        capital: float,
        direction: str = "LONG",
    ) -> Dict:
        """
        Full evaluation with risk-based position sizing.
        Returns a Dict with proceed, reason, quantity, stop_loss, risk_dollars, estimated_commission.
        """

        # Run Levels 1-3
        proceed, reason, confidence = self.evaluate(context, ta_result, symbol)
        if not proceed:
            return {"proceed": False, "reason": reason, "quantity": 0}

        # LEVEL 4: RISK-BASED SIZING
        entry_price = ta_result.get("price", 0)
        atr = ta_result.get("atr", 0)

        # If ATR is not directly in ta_result, try indicators
        if atr == 0 and "indicators" in ta_result:
            atr = ta_result["indicators"].get("atr", 0)

        # Dynamic Stop-Loss from ATR
        stop_loss = RiskManager.calculate_stop_loss(entry_price, atr, direction)

        # Position size from RiskManager
        sizing = self.risk_manager.calculate_position_size(
            capital=capital,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            confidence=confidence,
            atr=atr  # Audit Fix: Critical for stop safety check
        )

        if sizing["blocked"]:
            return {
                "proceed": False,
                "reason": f"RISK_BLOCKED_{sizing['reason']}",
                "quantity": 0,
            }

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
