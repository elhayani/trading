import yfinance as yf
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class NewsFetcher:
    def __init__(self):
        # We use yfinance which is more reliable than raw RSS scraping
        pass
        
    def get_news_context(self, symbol="EURUSD"):
        """
        Fetches news using yfinance for the specific forex pair.
        Returns formatted string for Bedrock.
        """
        # Convert symbol to Yahoo format (e.g., EURUSD -> EURUSD=X)
        ticker_symbol = f"{symbol}=X"
        
        try:
            ticker = yf.Ticker(ticker_symbol)
            news_items = ticker.news
            
            if not news_items:
                return "NO RELEVANT NEWS FOUND."
                
            return self._format_for_bedrock(news_items)
            
        except Exception as e:
            logger.error(f"Error fetching news for {ticker_symbol}: {e}")
            return "ERROR FETCHING NEWS."

    def _format_for_bedrock(self, news_items):
        formatted = "RECENT NEWS:\n"
        
        # Limit to top 5
        for item in news_items[:5]:
            title = item.get('title', 'No Title')
            link = item.get('link', '')
            
            # YFinance news objects sometimes differ, handle safely
            formatted += f"- {title}\n"
            formatted += f"  Link: {link}\n"
            
        return formatted

# Global instance
news_fetcher = NewsFetcher()
