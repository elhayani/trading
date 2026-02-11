import logging
import time
import yfinance as yf

# 🏛️ V5.1 Macro Context - Hedge Fund Intelligence
try:
    from macro_context import get_macro_context, format_for_bedrock
    MACRO_CONTEXT_AVAILABLE = True
except ImportError:
    MACRO_CONTEXT_AVAILABLE = False

logger = logging.getLogger()


def _retry(func, tries=3, delay=1, backoff=2):
    """Simple retry decorator for unreliable API calls (Audit Fix)"""
    last_exception = None
    for attempt in range(tries):
        try:
            return func()
        except Exception as e:
            last_exception = e
            if attempt < tries - 1:
                sleep_time = delay * (backoff ** attempt)
                logger.warning(f"⚠️ Retry {attempt+1}/{tries} after {sleep_time}s: {e}")
                time.sleep(sleep_time)
    raise last_exception


class NewsFetcher:
    def get_latest_news(self, symbol, hours=24, max_news=5):
        """
        Fetch news for a symbol with retry logic (Audit Fix).
        yfinance can crash/ratelimit without warning.
        """
        try:
            # yfinance expects e.g. BTC-USD
            # Audit Fix: Use robust mapping especially for .CC pairs (R3)
            SYMBOL_MAP = {
                'BTC/USDT': 'BTC-USD',
                'ETH/USDT': 'ETH-USD',
                'SOL/USDT': 'SOL-USD',
                'DOGE/USDT': 'DOGE-USD.CC',
                'PAXG/USDT': 'PAXG-USD', # Commodities
                'XAG/USDT': 'XAG-USD',   # Silver
            }
            symbol = SYMBOL_MAP.get(symbol, symbol.replace('/', '-'))
            
            def _fetch():
                ticker = yf.Ticker(symbol)
                return ticker.news
            
            # Audit Fix: Retry logic for unreliable yfinance
            news = _retry(_fetch, tries=3, delay=1, backoff=2)
            
            if not news:
                return []
                
            formatted_news = []
            for item in news[:max_news]:
                title = item.get('title', '')
                formatted_news.append({
                    'title': title,
                    'publisher': item.get('publisher', 'Unknown'),
                    'link': item.get('link', ''),
                    # Audit Fix: Basic keyword sentiment instead of useless placeholder
                    'sentiment': _quick_sentiment(title)
                })
            return formatted_news
            
        except Exception as e:
            logger.error(f"News fetch error after retries: {e}")
            return []


def _quick_sentiment(title: str) -> str:
    """
    Quick keyword-based sentiment (Audit Fix).
    Replaces the useless 'NEUTRAL' placeholder.
    Bedrock still does the deep analysis, but this gives a baseline.
    """
    if not title:
        return 'NEUTRAL'
    
    t = title.upper()
    
    bearish_keywords = ['CRASH', 'DUMP', 'SELL', 'FEAR', 'DROP', 'PLUNGE', 'DECLINE',
                        'BEAR', 'RECESSION', 'INFLATION', 'RATE HIKE', 'DEFAULT', 
                        'HACK', 'FRAUD', 'BANKRUPTCY', 'COLLAPSE', 'WARNING']
    
    bullish_keywords = ['SURGE', 'RALLY', 'BULL', 'BREAKOUT', 'ATH', 'MOON',
                        'PUMP', 'RATE CUT', 'RECOVERY', 'GROWTH', 'ADOPTION',
                        'APPROVAL', 'LAUNCH', 'UPGRADE', 'PARTNERSHIP']
    
    bear_count = sum(1 for kw in bearish_keywords if kw in t)
    bull_count = sum(1 for kw in bullish_keywords if kw in t)
    
    if bear_count > bull_count:
        return 'BEARISH'
    elif bull_count > bear_count:
        return 'BULLISH'
    return 'NEUTRAL'


def get_news_context(symbol, macro_data=None):
    """
    Returns a string summary of news for AI context.
    🏛️ V5.1: Now includes MACRO context (DXY, Yields, VIX)
    """
    fetcher = NewsFetcher()
    news = fetcher.get_latest_news(symbol)
    
    context_parts = []
    
    # 1. News de l'actif (now with real sentiment)
    if news:
        context_parts.append("ASSET NEWS:")
        for n in news:
            sentiment_tag = f" [{n['sentiment']}]" if n['sentiment'] != 'NEUTRAL' else ""
            context_parts.append(f"- {n['title']}{sentiment_tag} (Source: {n['publisher']})")
    else:
        context_parts.append("ASSET NEWS: None found.")
    
    # 2. Contexte Macro (DXY, Yields, VIX)
    if MACRO_CONTEXT_AVAILABLE:
        try:
            # 🔄 Use provided macro data or fetch fresh
            macro = macro_data if macro_data else get_macro_context()
            
            context_parts.append("")
            context_parts.append("MACRO CONTEXT:")
            context_parts.append(f"- Dollar (DXY): {macro['dxy']['value']:.2f} ({macro['dxy']['change_pct']:+.2f}%) → {macro['dxy']['signal']}")
            context_parts.append(f"- US 10Y Yield: {macro['yields']['value']:.2f}% ({macro['yields']['change_bps']:+.1f} bps) → {macro['yields']['signal']}")
            context_parts.append(f"- VIX: {macro['vix']['value']:.1f} → {macro['vix']['level']}")
            context_parts.append(f"- MACRO REGIME: {macro['regime']}")
            
            # Warning si événement majeur
            if macro.get('calendar', {}).get('has_high_impact'):
                events = [e['name'] for e in macro['calendar']['events']]
                context_parts.append(f"- ⚠️ HIGH IMPACT NEWS TODAY: {', '.join(events)}")
                
        except Exception as e:
            logger.warning(f"Macro context formatting error: {e}")
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
            logger.error(f"🛑 CRITICAL: Macro Context unavailable: {e}")
            macro_adjustments = {
                'can_trade': False, 
                'size_multiplier': 0.0, 
                'regime': 'ERROR',
                'dxy_signal': 'NEUTRAL',
                'vix_level': 20.0
            }
    
    return news_context, macro_adjustments
