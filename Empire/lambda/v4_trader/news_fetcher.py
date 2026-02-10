import logging
import yfinance as yf

# 🏛️ V5.1 Macro Context - Hedge Fund Intelligence
try:
    from macro_context import get_macro_context, format_for_bedrock
    MACRO_CONTEXT_AVAILABLE = True
except ImportError:
    MACRO_CONTEXT_AVAILABLE = False

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
    🏛️ V5.1: Now includes MACRO context (DXY, Yields, VIX)
    """
    fetcher = NewsFetcher()
    news = fetcher.get_latest_news(symbol)
    
    context_parts = []
    
    # 1. News de l'actif
    if news:
        context_parts.append("ASSET NEWS:")
        for n in news:
            context_parts.append(f"- {n['title']} (Source: {n['publisher']})")
    else:
        context_parts.append("ASSET NEWS: None found.")
    
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


def get_full_context(symbol):
    """
    🏛️ Retourne le contexte complet (News + Macro) avec les ajustements.
    Utilisé pour la décision finale du bot.
    """
    news_context = get_news_context(symbol)
    
    macro_adjustments = {
        'can_trade': True,
        'size_multiplier': 1.0,
        'regime': 'UNKNOWN',
    }
    
    if MACRO_CONTEXT_AVAILABLE:
        try:
            macro = get_macro_context()
            macro_adjustments = {
                'can_trade': macro['can_trade'],
                'size_multiplier': macro['size_multiplier'],
                'regime': macro['regime'],
                'dxy_signal': macro['dxy']['signal'],
                'vix_level': macro['vix']['level'],
            }
        except Exception as e:
            logger.warning(f"Macro adjustments error: {e}")
    
    return news_context, macro_adjustments

