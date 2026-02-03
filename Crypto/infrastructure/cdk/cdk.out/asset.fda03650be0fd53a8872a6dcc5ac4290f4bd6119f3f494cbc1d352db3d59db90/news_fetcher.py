import logging
import yfinance as yf

logger = logging.getLogger()

class NewsFetcher:
    def get_latest_news(self, symbol, hours=24, max_news=5):
        """
        Fetch news for a symbol. 
        For crypto, we can use yfinance (e.g. BTC-USD) or external APIs.
        Here we stick to yfinance for simplicity/cost.
        """
        try:
            # yfinance expects e.g. BTC-USD
            if '/' in symbol:
                symbol = symbol.replace('/', '-')
            
            ticker = yf.Ticker(symbol)
            news = ticker.news
            
            if not news:
                return []
                
            formatted_news = []
            for item in news[:max_news]:
                formatted_news.append({
                    'title': item.get('title'),
                    'publisher': item.get('publisher'),
                    'link': item.get('link'),
                    'sentiment': 'NEUTRAL' # Placeholder, Bedrock will analyze context
                })
            return formatted_news
            
        except Exception as e:
            logger.error(f"News fetch error: {e}")
            return []

def get_news_context(symbol):
    """
    Returns a string summary of news for AI context.
    """
    fetcher = NewsFetcher()
    news = fetcher.get_latest_news(symbol)
    
    if not news:
        return "NO NEWS FOUND."
        
    context = "RECENT NEWS:\n"
    for n in news:
        context += f"- {n['title']} (Source: {n['publisher']})\n"
        
    return context
