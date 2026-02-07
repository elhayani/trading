import yfinance as yf
import logging
from datetime import datetime

# 🏛️ V5.1 Macro Context - Hedge Fund Intelligence
try:
    from macro_context import get_macro_context
    MACRO_CONTEXT_AVAILABLE = True
except ImportError:
    MACRO_CONTEXT_AVAILABLE = False

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class NewsFetcher:
    def __init__(self):
        # We use yfinance which is more reliable than raw RSS scraping
        pass
        
    def get_news_context(self, symbol="EURUSD"):
        """
        Fetches news using yfinance and adds MACRO Context (DXY, VIX, Yields).
        Returns formatted string for Bedrock.
        """
        # Forex: EURUSD -> EURUSD=X, USDJPY -> USDJPY=X
        ticker_symbol = symbol
        if "=" not in symbol and len(symbol) == 6:
             ticker_symbol = f"{symbol}=X"
        
        context_parts = []
        
        # 1. News de l'actif
        try:
            ticker = yf.Ticker(ticker_symbol)
            news_items = ticker.news
            
            if news_items:
                context_parts.append("ASSET NEWS:")
                context_parts.append(self._format_for_bedrock(news_items))
            else:
                context_parts.append("ASSET NEWS: None found.")
                
        except Exception as e:
            logger.error(f"Error fetching news for {ticker_symbol}: {e}")
            context_parts.append("ASSET NEWS: Error fetching.")

        # 2. Contexte Macro (DXY, Yields, VIX)
        if MACRO_CONTEXT_AVAILABLE:
            try:
                macro = get_macro_context()
                context_parts.append("")
                context_parts.append("MACRO CONTEXT:")
                context_parts.append(f"- Dollar (DXY): {macro['dxy']['value']:.2f} ({macro['dxy']['change_pct']:+.2f}%) → {macro['dxy']['signal']}")
                context_parts.append(f"- US 10Y Yield: {macro['yields']['value']:.2f}% ({macro['yields']['change_bps']:+.1f} bps) → {macro['yields']['signal']}")
                context_parts.append(f"- VIX: {macro['vix']['value']:.1f} → {macro['vix']['level']}")
                context_parts.append(f"- MACRO REGIME: {macro['regime']}")
                
                # Warning si événement majeur
                if macro['calendar']['has_high_impact']:
                    events = [e['name'] for e in macro['calendar']['events']]
                    context_parts.append(f"- ⚠️ HIGH IMPACT NEWS TODAY: {', '.join(events)}")
                    
            except Exception as e:
                logger.warning(f"Macro context error: {e}")
                context_parts.append("MACRO CONTEXT: Unavailable")
        
        return '\n'.join(context_parts)

    def _format_for_bedrock(self, news_items):
        formatted = ""
        # Limit to top 5
        for item in news_items[:5]:
            title = item.get('title', 'No Title')
            formatted += f"- {title}\n"
        return formatted

# Global instance
news_fetcher = NewsFetcher()
