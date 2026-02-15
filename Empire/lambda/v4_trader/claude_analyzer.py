"""
Claude 3.5 Sonnet News Analyzer via AWS Bedrock
Elite prompt engineering for advanced sentiment analysis
"""
import json
import logging
import boto3
import botocore.config
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ClaudeNewsAnalyzer:
    """
    Advanced news analysis using Claude 3.5 Sonnet via AWS Bedrock.
    Optimized for cost efficiency with batching and system prompts.
    """
    
    def __init__(self, region: str = "us-east-1"):
        """
        Initialize Bedrock client for Claude 3.5 Sonnet.
        Model ID: anthropic.claude-3-5-sonnet-20241022-v2:0
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
            logger.info(f"[CLAUDE] Initialized with model: {self.model_id} (ULTRA-FAST HAIKU)")
        except Exception as e:
            logger.error(f"[CLAUDE] Failed to initialize: {e}")
            self.bedrock = None
    
    def analyze_news_batch(self, symbol: str, news_articles: List[Dict]) -> Dict:
        """
        Analyze multiple news articles at once (batching for cost optimization).
        
        Args:
            symbol: Trading symbol (e.g., "BTC/USDT:USDT")
            news_articles: List of news dicts with 'title' and 'summary' keys
        
        Returns:
            Dict with score (0-100), sentiment, reason, and confidence
        """
        if not self.bedrock:
            logger.warning("[CLAUDE] Bedrock client not available, returning neutral")
            return self._neutral_response()
        
        if not news_articles:
            return self._neutral_response()
        
        # Prepare news text for Claude (batched)
        news_text = self._format_news_for_claude(news_articles[:10])  # Max 10 articles
        
        # Elite System Prompt - Optimized for LONG & SHORT symmetry
        system_prompt = """Tu es "Empire AI", un analyste Senior en trading quantitatif avec 15 ans d'expérience.

Tu analyses les news financières pour déterminer leur impact immédiat sur les prix des actifs.

RÈGLES STRICTES:
1. Évalue l'impact sur le prix de 0 à 100 (0=très bearish, 50=neutre, 100=très bullish)
2. Identifie le sentiment: BULLISH, BEARISH, ou NEUTRAL
3. Détecte les fake news, les rumeurs non confirmées, ou les news majeures (Fed, régulation, adoption)
4. Prends en compte l'ironie, le sarcasme, et les négations dans les titres
5. Corrèle l'impact entre actifs (ex: une news Bitcoin peut affecter Solana)

RÈGLES SPÉCIALES POUR SHORTS (KRACHS & PANIQUES):
6. Détecte les signaux de CAPITULATION ou LIQUIDATIONS EN CASCADE (mots-clés: "crash", "liquidation", "panic sell", "margin call")
7. Si le sentiment est fortement BEARISH (score 0-20) ET l'urgence est HIGH, confirme le SHORT même si les indicateurs techniques sont en survente extrême
8. Pendant les krachs, le RSI peut rester à 10-20 pendant que le prix continue de plonger de 20%+ - le SHORT reste valide
9. Pour les Altcoins (ETH, SOL, XRP, etc.), vérifie d'abord le sentiment du BTC. Si BTC est en panique (score < 25), amplifie le score BEARISH de l'Altcoin de -10 points supplémentaires
10. Les SHORTS sont aussi profitables que les LONGS - ne favorise aucune direction, sois un prédateur opportuniste

GESTION D'OPPORTUNITÉ COMPARATIVE (TRIM & SWITCH):
11. Si une position est déjà ouverte, compare son potentiel de gain restant avec toute nouvelle opportunité détectée
12. Si une nouvelle opportunité a un score de confiance BIEN PLUS ÉLEVÉ (ex: SOL à 0.9 vs ETH actuel à 0.6), suggère explicitement "ACTION: REDUCE_AND_SWITCH" dans la raison
13. Priorise toujours l'actif qui a le MOMENTUM LE PLUS RAPIDE pour atteindre notre objectif de 1% du budget global
14. Détecte les signaux de "EXPLOSIVE MOMENTUM" (mots-clés: "surge", "breakout", "rally", "pump") qui justifient une réallocation immédiate
15. La VÉLOCITÉ DU CAPITAL est critique - un actif qui stagne pendant 2h coûte de l'argent par opportunité manquée

CONTRAINTE DE SORTIE:
Réponds UNIQUEMENT en JSON pur, sans markdown, sans explication supplémentaire.
Format exact:
{
  "score": 15,
  "sentiment": "BEARISH",
  "reason": "Liquidations cascade detected",
  "confidence": 0.95,
  "urgency": "HIGH"
}"""
        
        # Determine if symbol is an altcoin (not BTC or PAXG)
        # Normalize symbol format for comparison
        symbol_normalized = symbol.replace('/USDT:USDT', '').replace('USDT', '')
        is_btc = symbol_normalized in ['BTC']
        is_paxg = symbol_normalized in ['PAXG']
        is_altcoin = not (is_btc or is_paxg)
        
        altcoin_note = "\n\n⚠️ IMPORTANT: Cet actif est une ALTCOIN. Vérifie d'abord le sentiment du BTC. Si BTC est en panique, amplifie le score BEARISH." if is_altcoin else ""
        
        # User message with news
        user_message = f"""Analyse ces news récentes pour {symbol}:

{news_text}{altcoin_note}

Réponds en JSON pur uniquement."""
        
        try:
            # Call Claude via Bedrock
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,  # Keep low for cost optimization
                "temperature": 0.3,  # Lower temperature for more consistent JSON
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": user_message
                    }
                ]
            })
            
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=body
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            content = response_body.get('content', [])
            
            if not content:
                logger.warning("[CLAUDE] Empty response from model")
                return self._neutral_response()
            
            # Extract text from Claude's response
            text = content[0].get('text', '{}')
            
            # Parse JSON (handle markdown code blocks if present)
            text = text.strip()
            if text.startswith('```'):
                # Remove markdown code blocks
                text = text.split('```')[1]
                if text.startswith('json'):
                    text = text[4:]
                text = text.strip()
            
            result = json.loads(text)
            
            # Validate and normalize
            score = max(0, min(100, int(result.get('score', 50))))
            sentiment = result.get('sentiment', 'NEUTRAL').upper()
            if sentiment not in ['BULLISH', 'BEARISH', 'NEUTRAL']:
                sentiment = 'NEUTRAL'
            
            confidence = max(0.0, min(1.0, float(result.get('confidence', 0.5))))
            reason = result.get('reason', 'No reason provided')[:100]  # Cap length
            
            logger.info(f"[CLAUDE] Analysis: {symbol} | Score={score} | Sentiment={sentiment} | Confidence={confidence:.2f}")
            
            return {
                'score': score,
                'sentiment': sentiment,
                'reason': reason,
                'confidence': confidence,
                'analyzed_articles': len(news_articles)
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"[CLAUDE ERROR] Failed to parse JSON response: {e}")
            logger.error(f"[CLAUDE ERROR] Raw text: {text[:200]}")
            return self._neutral_response()
        except Exception as e:
            logger.error(f"[CLAUDE ERROR] Analysis failed: {e}")
            return self._neutral_response()
    
    def _format_news_for_claude(self, articles: List[Dict]) -> str:
        """Format news articles into readable text for Claude."""
        formatted = []
        for i, article in enumerate(articles, 1):
            title = article.get('title', 'No title')
            summary = article.get('summary', '')
            timestamp = article.get('providerPublishTime', 0)
            
            # Format timestamp
            if timestamp:
                dt = datetime.fromtimestamp(timestamp)
                time_str = dt.strftime('%Y-%m-%d %H:%M')
            else:
                time_str = 'Unknown time'
            
            formatted.append(f"[{i}] {time_str}\nTitle: {title}\nSummary: {summary[:200]}\n")
        
        return "\n".join(formatted)
    
    def pick_best_trades(self, candidates: List[Dict], empty_slots: int) -> Dict:
        """
        🏛️ ENSEMBLE SELECTION: Claude 3 Haiku selects the best trades from a pool of elites.
        Optimized for cost, latency, and quality.
        """
        if not self.bedrock or not candidates or empty_slots <= 0:
            return {"picks": [], "reasons": "AI unavailable or no slots"}

        try:
            # 1. Format the "Elite Dashboard" as requested by User
            dashboard = []
            for i, c in enumerate(candidates[:15], 1): # Max 15 to stay fast
                # [Symbole | Score | RSI | Vol_Surge | Histo_5m_Close]
                line = f"{i}. {c['symbol']} | {c['score']} | {c['rsi']:.0f} | {c['vol_surge']:.1f}x | {c['history']}"
                dashboard.append(line)
            
            dashboard_str = "\n".join(dashboard)
            
            # 2. Precise System Prompt for Batch Selection
            system_prompt = f"""Tu es l'Arbitre Élite d'un bot de scalping HFT.
TASK: Sélectionne les {empty_slots} meilleurs candidats pour un LONG scalping.

CRITÈRES DE SÉLECTION:
1. Évite le surachat extrême (RSI > 80).
2. Évite les "bougies verticales" (ex: [10, 10, 10, 10, 15] est suspect, [10, 11, 12, 13, 14] est sain).
3. Priorise les actifs avec un Vol_Surge important mais pas délirant (1.5x à 4.0x).
4. Préfère les scores les plus élevés si la structure de prix (historique) est stable.

DASHBOARD:
{dashboard_str}

OUTPUT: JSON pur uniquement: {{"picks": ["SYMBOL1", "SYMBOL2"], "reasons": "Court texte d'explication"}}"""

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
            picks = result.get("picks", [])[:empty_slots] # Force constraint
            
            logger.info(f"🏆 [HAIKU_PICK] Selected: {picks} | Reason: {result.get('reasons')}")
            return {"picks": picks, "reasons": result.get("reasons")}

        except Exception as e:
            logger.error(f"[CLAUDE_PICK_ERROR] {e}")
            # Fallback: return the first candidate by score
            return {"picks": [candidates[0]['symbol']] if candidates else [], "reasons": "Fallback (error)"}

    def market_veto(self, symbol: str, ohlcv: List[List], direction: str) -> bool:
        """
        🚀 FLASH VETO: High-speed trade validation using Claude 3.5 Sonnet.
        Analyzes the last 5-10 minutes of OHLCV data to detect rejection wicks
        or adverse price action that TA indicators might miss.
        """
        if not self.bedrock or not ohlcv:
            return True  # If AI is down, we trust TA (GO)
        
        try:
            # 1. Format data ultra-lightly (as suggested by User)
            # history is [timestamp, open, high, low, close, volume]
            prices = [str(b[4]) for b in ohlcv]
            vols = [f"{b[5]/1000:.1f}k" for b in ohlcv]
            
            data_str = f"Histo 5min: {' -> '.join(prices)}. Vol: {', '.join(vols)}."
            
            # 2. Ultra-short prompt for minimal latency
            system_prompt = f"""Tu es le VETO d'un robot de scalping 1 min.
Ta seule mission: Bloquer (VETO) ou Autoriser (GO) une entrée {direction} sur {symbol}.

CRITÈRES DE VETO:
- Mèche de rejet massive à l'opposé du mouvement.
- Volume qui explose sur une bougie de contre-tendance.
- Stagnation suspecte après un pump/dump.
- Si c'est un SHORT, refuse (VETO) si l'actif est déjà en survente ou s'il y a une mèche basse (rejet acheteur).

RÉPONSE: Commence par GO ou VETO, puis une raison de 5 mots max."""

            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 20, # Ultra low for speed
                "temperature": 0,
                "system": system_prompt,
                "messages": [{"role": "user", "content": data_str}]
            })
            
            # 3. Call with short timeout
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=body
            )
            
            response_body = json.loads(response['body'].read())
            text = response_body.get('content', [{}])[0].get('text', 'GO').upper()
            
            if text.startswith('VETO'):
                logger.warning(f"🚫 [VETO] Claude blocked {symbol}: {text}")
                return False
            
            logger.info(f"✅ [CLAUDE_GO] {symbol} authorized: {text}")
            return True
            
        except Exception as e:
            logger.error(f"[CLAUDE_VETO_ERROR] {e}")
            return True # Fallback to GO

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
