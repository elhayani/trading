import logging
from typing import Dict, Tuple
from models import MarketRegime
import micro_corridors as corridors

logger = logging.getLogger(__name__)

class DecisionEngine:
    """
    Centralized 4-Level Decision Architecture (Audit #V10.5)
    
    Level 1: Macro Veto (Global Safety)
    Level 2: Technical Validation (Signal Quality)
    Level 3: Micro Timing (Corridor Awareness)
    Level 4: Macro Adjustment (Position Sizing)
    """

    @staticmethod
    def evaluate(context, ta_result: Dict, symbol: str) -> Tuple[bool, str, float]:
        """
        Evaluates a potential trade through 4 levels of hierarchy.
        Returns: (proceed: bool, reason: str, size_multiplier: float)
        """
        
        # LEVEL 1: MACRO VETO (Absolute Block)
        if not context.can_trade:
            return False, "MACRO_VETO", 0.0
            
        # LEVEL 2: TECHNICAL VALIDATION (Signal Quality)
        score = ta_result.get('score', 0)
        if score < 60:
            logger.warning(f"🚫 Level 2 Veto: Signal score {score}/100 < 60")
            return False, f"LOW_TECHNICAL_SCORE_{score}", 0.0
            
        # LEVEL 3: MICRO TIMING (Corridor Check)
        params = corridors.get_corridor_params(symbol)
        regime = params.get('regime')
        if regime in [MarketRegime.LOW_LIQUIDITY, MarketRegime.CLOSED]:
            logger.info(f"⏳ Level 3 Block: Timing bad ({regime})")
            return False, f"BAD_TIMING_{regime}", 0.0
            
        # LEVEL 4: MACRO ADJUSTMENT (Sizing)
        # Use the scaled confidence score (0.5 - 2.0)
        confidence = context.confidence_score
        
        # Final Safeguard: Ensure multiplier is within reasonable bounds
        confidence = max(0.5, min(2.0, confidence))
        
        return True, "PROCEED", confidence
