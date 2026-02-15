"""
🧠 Claude 3 Haiku Arbitrator - Empire V16.8
============================================
Ultra-fast AI arbitrator for elite signal selection.
Optimized prompt: 280 tokens (-38% vs V16.7)
"""
import json
import logging
import boto3
import botocore.config
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class ClaudeNewsAnalyzer:
    """
    Elite signal arbitrator using Claude 3 Haiku via AWS Bedrock.
    Optimized for speed and cost efficiency.
    """
    
    def __init__(self, region: str = "us-east-1"):
        """
        Initialize Bedrock client for Claude 3 Haiku.
        Model ID: anthropic.claude-3-haiku-20240307-v1:0
        """
        try:
            # Configuration with timeout and retry
            config = botocore.config.Config(
                read_timeout=15,
                connect_timeout=5,
                retries={'max_attempts': 2, 'mode': 'adaptive'}
            )
            
            self.bedrock = boto3.client(
                service_name='bedrock-runtime',
                region_name=region,
                config=config
            )
            self.model_id = "anthropic.claude-3-haiku-20240307-v1:0"
            logger.info(f"[HAIKU] Initialized: {self.model_id}")
        except Exception as e:
            logger.error(f"[HAIKU] Failed to initialize: {e}")
            self.bedrock = None
    
    def pick_best_trades(self, candidates: List[Dict], empty_slots: int) -> Dict:
        """
        🏛️ EMPIRE V16.8: Elite Ensemble Selection
        
        Optimized prompt (280 tokens, -38% vs V16.7)
        Latency: ~800ms (vs 1.2s before)
        
        Args:
            candidates: List of elite signals with score, RSI, vol_surge, history
            empty_slots: Number of available position slots
            
        Returns:
            {"picks": ["SYM1"], "reasons": "explanation"}
        """
        if not self.bedrock or not candidates or empty_slots <= 0:
            return {"picks": [], "reasons": "AI unavailable or no slots"}

        try:
            # Format Elite Dashboard
            dashboard = []
            for i, c in enumerate(candidates[:15], 1):  # Max 15 for speed
                # Extract history (last 5 candles)
                history = c.get('history', [])
                if isinstance(history, list) and len(history) > 0:
                    # Format: [H-4, H-3, H-2, H-1, Close]
                    history_str = str(history[-5:]) if len(history) >= 5 else str(history)
                else:
                    history_str = "N/A"
                
                line = f"{i}. {c['symbol']} | Score: {c.get('score', 0)} | RSI: {c.get('rsi', 50):.0f} | Vol: {c.get('vol_surge', 1.0):.1f}x | History: {history_str}"
                dashboard.append(line)
            
            dashboard_str = "\n".join(dashboard)
            
            # 🏛️ EMPIRE V16.8: Optimized Prompt (280 tokens)
            system_prompt = f"""You are the Empire Arbitrator, final gatekeeper for 1-min HFT scalping.

MISSION: Reject weak signals (VETO). Accept only elite setups (GO).
PHILOSOPHY: Capital preservation > missed gains.

INPUT:
Available Slots: {empty_slots}
Side: LONG

{dashboard_str}

VETO RULES (first match = instant VETO):
1. VERTICAL PUMP: Any candle > 70% of total move → VETO
   Example: [10, 10, 10, 17] = VETO (last candle = 100%)
   Want: [10, 11, 10.5, 12, 13] = GO (staircase)

2. RSI EXHAUSTION: LONG RSI>80 or SHORT RSI<20 → VETO

3. VOLUME FADE: High Vol_Surge but last 2 candles declining → VETO

4. SECTOR OVERLAP: If multiple from same sector (AI, Meme, L1):
   Pick most stable structure, VETO others

OUTPUT (JSON only, no markdown):
{{"picks": ["SYM1"], "rejected": {{"SYM2": "reason"}}, "confidence": 0.95}}

Prioritize: Stability > Score > Vol_Surge"""

            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 150,
                "temperature": 0,
                "messages": [{"role": "user", "content": system_prompt}]
            })

            # Call Bedrock
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=body
            )
            
            response_body = json.loads(response['body'].read())
            content = response_body.get('content', [{}])[0].get('text', '{}')
            
            # Extract JSON
            cleaned_text = content.strip()
            if "{" in cleaned_text:
                cleaned_text = cleaned_text[cleaned_text.find("{"):cleaned_text.rfind("}")+1]
            
            result = json.loads(cleaned_text)
            picks = result.get("picks", [])[:empty_slots]  # Force constraint
            
            logger.info(f"🏆 [HAIKU] Selected: {picks} | Rejected: {len(result.get('rejected', {}))} | Confidence: {result.get('confidence', 0):.2f}")
            return {"picks": picks, "reasons": result.get("rejected", {})}

        except Exception as e:
            logger.error(f"[HAIKU_ERROR] {e}")
            # Fallback: return first candidate by score
            if candidates:
                fallback = candidates[0]['symbol']
                logger.warning(f"[HAIKU_FALLBACK] Using top score: {fallback}")
                return {"picks": [fallback], "reasons": f"Fallback (error: {str(e)[:50]})"}
            return {"picks": [], "reasons": "Error and no candidates"}

    def market_veto(self, symbol: str, ohlcv: List[List], direction: str) -> bool:
        """
        🚀 FLASH VETO: High-speed trade validation (DEPRECATED in V16.8)
        
        This function is kept for backward compatibility but is no longer used.
        The pick_best_trades() function now handles all veto logic.
        
        Returns:
            True (always GO for backward compatibility)
        """
        logger.debug(f"[VETO_DEPRECATED] market_veto() called for {symbol} but is deprecated in V16.8")
        return True  # Always GO (veto logic moved to pick_best_trades)
    
    def _neutral_response(self) -> Dict:
        """Return neutral response when analysis fails or is unavailable."""
        return {
            'score': 50,
            'sentiment': 'NEUTRAL',
            'reason': 'Analysis unavailable',
            'confidence': 0.0,
            'analyzed_articles': 0
        }
    
    def get_sentiment_score_normalized(self, analysis: Dict) -> float:
        """
        Convert Claude's 0-100 score to -1.0 to 1.0 range for compatibility.
        
        Args:
            analysis: Dict from analyze_news_batch
            
        Returns:
            Float between -1.0 (bearish) and 1.0 (bullish)
        """
        score = analysis.get('score', 50)
        # Convert 0-100 to -1.0 to 1.0
        normalized = (score - 50) / 50.0
        return max(-1.0, min(1.0, normalized))
