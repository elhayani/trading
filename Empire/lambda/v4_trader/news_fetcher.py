import yfinance as yf
import logging
import re
import time
import os
from typing import List, Dict, Tuple
from decimal import Decimal
from datetime import datetime, timedelta, timezone

# Absolute imports (Critique #1 New)
import macro_context
import config
from config import TradingConfig

logger = logging.getLogger(__name__)

class NewsFetcher:
    """
    Fetches news sentiment with proximity-aware negation handling.
    Includes Circuit Breaker for Yahoo Finance (Audit #V11.5).
    """

    # Shared state between Lambda invocations (Global Scope)
    _circuit_state = {
        'consecutive_fails': 0,
        'blocked_until': 0,
        'last_success': 0
    }

    BULLISH_KEYWORDS = [
        'bullish', 'strong', 'growth', 'gain', 'rally', 'surge', 'breakout',
        'upside', 'upgrade', 'profit', 'positive', 'buy', 'expansion', 'adoption'
    ]
    
    BEARISH_KEYWORDS = [
        'bearish', 'weak', 'decline', 'loss', 'drop', 'dump', 'crash',
        'downside', 'downgrade', 'fear', 'negative', 'sell', 'recession', 'regulation'
    ]

    NEGATION_KEYWORDS = [
        'not', 'no', 'avoid', 'prevent', 'stop', 'dissipate', 'never', 'don\'t', 'won\'t'
    ]

    def _check_negation_proximity(self, text: str, keyword: str) -> bool:
        """Check if a negation exists within 3 words before the keyword."""
        pattern = rf"\b({'|'.join(self.NEGATION_KEYWORDS)})\b\s+(\w+\s+){{0,2}}{keyword}\b"
        return bool(re.search(pattern, text, re.IGNORECASE))

    def get_news_sentiment_score(self, symbol: str) -> float:
        try:
            news = self._fetch_raw_news(symbol)
            if not news: return 0.0

            total_score = 0.0
            weight_total = 0.0

            for i, article in enumerate(news):
                freshness = 1.0 / (1 + i * 0.2)
                content = (article.get('title', '') + " " + article.get('summary', '')).lower()
                
                article_score = 0.0
                bull_hits = 0
                bear_hits = 0
                
                for kw in self.BULLISH_KEYWORDS:
                    if kw in content:
                        if self._check_negation_proximity(content, kw):
                            bear_hits += 1
                        else:
                            bull_hits += 1
                            
                for kw in self.BEARISH_KEYWORDS:
                    if kw in content:
                        if self._check_negation_proximity(content, kw):
                            bull_hits += 1
                        else:
                            bear_hits += 1

                if bull_hits > bear_hits:
                    article_score = 1.0
                elif bear_hits > bull_hits:
                    article_score = -1.0
                
                total_score += article_score * freshness
                weight_total += freshness

            return max(-1.0, min(1.0, total_score / weight_total)) if weight_total > 0 else 0.0

        except Exception as e:
            logger.error(f"[ERROR] News analysis failed: {e}")
            return 0.0

    def _fetch_raw_news(self, symbol: str) -> List[Dict]:
        """
        Circuit Breaker Implementation for Yahoo Finance.
        """
        now = time.time()
        if now < self._circuit_state['blocked_until']:
            logger.warning(f"[CIRCUIT OPEN] Yahoo blocked until {datetime.fromtimestamp(self._circuit_state['blocked_until'])}")
            return []

        clean_symbol = symbol.replace('/USDT', '-USD').replace('/', '-')
        
        for attempt in range(3):
            try:
                ticker = yf.Ticker(clean_symbol)
                news = ticker.news
                if news:
                    # Success: Reset circuit
                    self._circuit_state['consecutive_fails'] = 0
                    self._circuit_state['last_success'] = now
                    logger.info(f"[OK] Yahoo news fetched: {len(news)} articles")
                    return news[:10]
            except Exception as e:
                logger.warning(f"[WARN] Yahoo attempt {attempt+1}/3 failed for {symbol}: {e}")
                time.sleep(2 ** attempt)

        # Failure: Increment counter
        self._circuit_state['consecutive_fails'] += 1
        if self._circuit_state['consecutive_fails'] >= 3:
            self._circuit_state['blocked_until'] = now + 3600 # 1 hour
            logger.error(f"[CIRCUIT BREAKER] Yahoo blocked for 1h after {self._circuit_state['consecutive_fails']} fails")
        
        # Fallback to AlphaVantage or others if keys exist (Optional based on user bonus)
        # Note: Implementation skipped for brevity unless keys provided in env
        return []

    def get_news_context(self, symbol: str, macro_data: Dict = None) -> Dict:
        sentiment_score = self.get_news_sentiment_score(symbol)
        if sentiment_score > TradingConfig.NEWS_SENTIMENT_THRESHOLD: tag = "BULLISH"
        elif sentiment_score < -TradingConfig.NEWS_SENTIMENT_THRESHOLD: tag = "BEARISH"
        else: tag = "NEUTRAL"

        return {
            'symbol': symbol,
            'score': round(sentiment_score, 3),
            'sentiment': tag,
            'summary': f"Sentiment is {tag} ({sentiment_score:.2f})"
        }
