import yfinance as yf
import logging
import re
import time
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
    """

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
        """
        Critique #6: Check if a negation exists within 3 words before the keyword.
        """
        # Regex to find negation within 3 words of the keyword
        # \bneg\b followed by 0 to 2 words, then the keyword
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
                            bear_hits += 1 # "not bullish" -> bearish intent
                        else:
                            bull_hits += 1
                            
                for kw in self.BEARISH_KEYWORDS:
                    if kw in content:
                        if self._check_negation_proximity(content, kw):
                            bull_hits += 1 # "crash avoided" -> bullish intent
                        else:
                            bear_hits += 1

                if bull_hits > bear_hits:
                    article_score = 1.0 if bull_hits > 0 else 0.0
                elif bear_hits > bull_hits:
                    article_score = -1.0 if bear_hits > 0 else 0.0
                
                total_score += article_score * freshness
                weight_total += freshness

            return max(-1.0, min(1.0, total_score / weight_total)) if weight_total > 0 else 0.0

        except Exception as e:
            logger.error(f"[ERROR] News analysis failed: {e}")
            return 0.0

    def _fetch_raw_news(self, symbol: str) -> List[Dict]:
        clean_symbol = symbol.replace('/USDT', '-USD').replace('/', '-')
        for attempt in range(3):
            try:
                ticker = yf.Ticker(clean_symbol)
                news = ticker.news
                if news: return news[:10]
            except:
                time.sleep(1)
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
