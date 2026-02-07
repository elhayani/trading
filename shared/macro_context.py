"""
🏛️ MACRO CONTEXT MODULE - Empire V5.1 Hedge Fund Intelligence
==============================================================
Récupère les données macroéconomiques pour informer les décisions de trading.

Le Dollar (DXY) et l'Inflation (CPI) sont les deux forces dominantes depuis 2022.
Ce module injecte ces données dans le prompt Bedrock pour une vision "Hedge Fund".

Data Sources:
- Yahoo Finance (DXY, US10Y, VIX)
- Economic Calendar API (événements FOMC, CPI, NFP)

Usage:
    from macro_context import get_macro_context, get_macro_regime
    
    macro = get_macro_context()
    regime = get_macro_regime(macro)
    
    # Injecter dans le prompt Bedrock
    prompt = f'''
    <macro_context>
    {macro['summary']}
    </macro_context>
    '''
"""

import requests
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple, Optional
import json

logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

# Yahoo Finance API endpoints
YAHOO_API_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

# Symboles des indicateurs macro
MACRO_SYMBOLS = {
    'DXY': 'DX-Y.NYB',      # Dollar Index
    'US10Y': '^TNX',         # US 10-Year Treasury Yield
    'VIX': '^VIX',           # Volatility Index (Fear Gauge)
    'GOLD': 'GC=F',          # Gold (Safe Haven)
    'SPY': 'SPY',            # S&P 500 ETF (Risk barometer)
}

# Seuils pour déterminer le régime macro
THRESHOLDS = {
    'DXY': {
        'strong_dollar': 0.005,   # +0.5% = Dollar fort
        'weak_dollar': -0.005,    # -0.5% = Dollar faible
    },
    'US10Y': {
        'rising_yields': 0.02,    # +2 bps = Yields montent
        'falling_yields': -0.02,  # -2 bps = Yields baissent
    },
    'VIX': {
        'fear': 25,               # VIX > 25 = Peur
        'greed': 15,              # VIX < 15 = Complaisance
        'extreme_fear': 30,       # VIX > 30 = Panique
    }
}

# Événements économiques majeurs (source: calendrier fixe)
# Ces événements sont les plus market-moving
MAJOR_EVENTS = {
    'CPI': 'Consumer Price Index (Inflation)',
    'FOMC': 'Federal Reserve Meeting',
    'NFP': 'Non-Farm Payrolls (Employment)',
    'PPI': 'Producer Price Index',
    'GDP': 'Gross Domestic Product',
    'PCE': 'Personal Consumption Expenditures (Fed preferred)',
}


# ==================== DATA FETCHERS ====================

def _fetch_yahoo_data(symbol: str, period: str = '2d') -> Optional[Dict]:
    """
    Récupère les données Yahoo Finance pour un symbole.
    Retourne le prix actuel et le changement sur 24h.
    """
    try:
        url = f"{YAHOO_API_BASE}/{symbol}"
        params = {
            'interval': '1d',
            'range': period,
        }
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; EmpireBot/5.1)'}
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code != 200:
            logger.warning(f"Yahoo API error for {symbol}: {response.status_code}")
            return None
        
        data = response.json()
        result = data.get('chart', {}).get('result', [])
        
        if not result:
            return None
        
        meta = result[0].get('meta', {})
        current_price = float(meta.get('regularMarketPrice', 0))
        prev_close = float(meta.get('chartPreviousClose', current_price))
        
        if prev_close > 0:
            change_pct = (current_price - prev_close) / prev_close
        else:
            change_pct = 0
        
        return {
            'symbol': symbol,
            'price': current_price,
            'prev_close': prev_close,
            'change_pct': change_pct,
            'change_abs': current_price - prev_close,
        }
        
    except requests.Timeout:
        logger.warning(f"Timeout fetching {symbol}")
        return None
    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
        return None


def get_dxy_data() -> Dict:
    """
    🇺🇸 Récupère les données du Dollar Index (DXY).
    Le DXY est LA référence pour le Risk-On/Risk-Off.
    """
    data = _fetch_yahoo_data(MACRO_SYMBOLS['DXY'])
    
    if data is None:
        return {
            'value': 0,
            'change_pct': 0,
            'trend': 'UNKNOWN',
            'signal': 'NEUTRAL',
        }
    
    change_pct = data['change_pct']
    
    # Déterminer la tendance
    if change_pct > THRESHOLDS['DXY']['strong_dollar']:
        trend = 'RISING'
        signal = 'RISK_OFF'  # Dollar fort = mauvais pour crypto/indices
    elif change_pct < THRESHOLDS['DXY']['weak_dollar']:
        trend = 'FALLING'
        signal = 'RISK_ON'   # Dollar faible = bon pour crypto/indices
    else:
        trend = 'STABLE'
        signal = 'NEUTRAL'
    
    return {
        'value': data['price'],
        'change_pct': change_pct * 100,  # En pourcentage
        'change_abs': data['change_abs'],
        'trend': trend,
        'signal': signal,
    }


def get_yields_data() -> Dict:
    """
    📈 Récupère les données des taux US à 10 ans.
    Quand les yields montent, la tech (Nasdaq) souffre.
    """
    data = _fetch_yahoo_data(MACRO_SYMBOLS['US10Y'])
    
    if data is None:
        return {
            'value': 0,
            'change_bps': 0,
            'trend': 'UNKNOWN',
            'signal': 'NEUTRAL',
        }
    
    # Les yields sont en pourcentage, le changement en bps
    change_bps = data['change_abs'] * 100  # Conversion en basis points
    
    if change_bps > 2:  # +2 bps
        trend = 'RISING'
        signal = 'BEARISH_TECH'  # Mauvais pour Nasdaq/Growth
    elif change_bps < -2:  # -2 bps
        trend = 'FALLING'
        signal = 'BULLISH_TECH'  # Bon pour Nasdaq/Growth
    else:
        trend = 'STABLE'
        signal = 'NEUTRAL'
    
    return {
        'value': data['price'],
        'change_bps': round(change_bps, 1),
        'trend': trend,
        'signal': signal,
    }


def get_vix_data() -> Dict:
    """
    😱 Récupère les données du VIX (indice de peur).
    VIX > 25 = Peur, VIX < 15 = Complaisance.
    """
    data = _fetch_yahoo_data(MACRO_SYMBOLS['VIX'])
    
    if data is None:
        return {
            'value': 20,  # Valeur neutre par défaut
            'level': 'UNKNOWN',
            'signal': 'NEUTRAL',
        }
    
    vix_value = data['price']
    
    if vix_value >= THRESHOLDS['VIX']['extreme_fear']:
        level = 'EXTREME_FEAR'
        signal = 'STOP_TRADING'
    elif vix_value >= THRESHOLDS['VIX']['fear']:
        level = 'FEAR'
        signal = 'REDUCE_SIZE'
    elif vix_value <= THRESHOLDS['VIX']['greed']:
        level = 'GREED'
        signal = 'FULL_SIZE'
    else:
        level = 'NEUTRAL'
        signal = 'NORMAL'
    
    return {
        'value': round(vix_value, 1),
        'change_pct': data['change_pct'] * 100,
        'level': level,
        'signal': signal,
    }


def get_economic_calendar() -> Dict:
    """
    📅 Vérifie s'il y a des événements économiques majeurs aujourd'hui.
    Utilise une approche simplifiée basée sur le calendrier connu.
    
    Note: Pour une version production, utiliser une API comme:
    - Trading Economics API
    - Forex Factory scraping
    - Investing.com calendar
    """
    today = datetime.now(timezone.utc)
    events_today = []
    
    # Jours typiques des annonces (approximatif)
    # CPI: généralement le 10-15 du mois
    # NFP: premier vendredi du mois
    # FOMC: 8 fois par an (dates fixes)
    
    day_of_month = today.day
    day_of_week = today.weekday()  # 0=Lundi, 4=Vendredi
    
    # Période CPI (10-15 du mois)
    if 10 <= day_of_month <= 15:
        events_today.append({
            'event': 'CPI_WINDOW',
            'name': 'Possible CPI Release Window',
            'impact': 'HIGH',
        })
    
    # Premier vendredi du mois = NFP
    if day_of_week == 4 and day_of_month <= 7:
        events_today.append({
            'event': 'NFP',
            'name': 'Non-Farm Payrolls (Employment)',
            'impact': 'HIGH',
        })
    
    # Dates FOMC 2025-2026 (approximatives)
    fomc_months = [1, 3, 5, 6, 7, 9, 11, 12]
    if today.month in fomc_months and 14 <= day_of_month <= 16:
        events_today.append({
            'event': 'FOMC_WINDOW',
            'name': 'Possible FOMC Meeting',
            'impact': 'EXTREME',
        })
    
    has_high_impact = any(e['impact'] in ['HIGH', 'EXTREME'] for e in events_today)
    
    return {
        'events': events_today,
        'has_high_impact': has_high_impact,
        'event_count': len(events_today),
        'warning': '⚠️ HIGH IMPACT NEWS TODAY' if has_high_impact else None,
    }


# ==================== RÉGIMES MACRO ====================

def determine_macro_regime(dxy: Dict, yields: Dict, vix: Dict) -> str:
    """
    🎯 Détermine le régime macro global.
    
    Régimes:
    - RISK_ON: Dollar faible + Yields stables/baissants + VIX bas
    - RISK_OFF: Dollar fort + Yields montants + VIX haut
    - MIXED: Signaux contradictoires
    - DANGER: VIX extrême ou événement majeur
    """
    
    # VIX extrême = DANGER absolu
    if vix.get('level') == 'EXTREME_FEAR':
        return 'DANGER'
    
    # Compter les signaux
    risk_on_signals = 0
    risk_off_signals = 0
    
    # DXY
    if dxy.get('signal') == 'RISK_ON':
        risk_on_signals += 2  # DXY a un poids plus important
    elif dxy.get('signal') == 'RISK_OFF':
        risk_off_signals += 2
    
    # Yields
    if yields.get('signal') == 'BULLISH_TECH':
        risk_on_signals += 1
    elif yields.get('signal') == 'BEARISH_TECH':
        risk_off_signals += 1
    
    # VIX
    if vix.get('level') == 'GREED':
        risk_on_signals += 1
    elif vix.get('level') == 'FEAR':
        risk_off_signals += 2  # Peur a plus de poids
    
    # Décision
    if risk_on_signals >= 3 and risk_off_signals <= 1:
        return 'RISK_ON'
    elif risk_off_signals >= 3 and risk_on_signals <= 1:
        return 'RISK_OFF'
    else:
        return 'MIXED'


def get_regime_adjustments(regime: str) -> Dict:
    """
    Retourne les ajustements de trading basés sur le régime macro.
    """
    adjustments = {
        'RISK_ON': {
            'can_trade': True,
            'size_multiplier': 1.2,     # Position légèrement plus grosse
            'rsi_adjustment': 5,         # RSI peut être plus haut
            'aggressive_mode': True,
            'description': '🟢 RISK-ON: Conditions macro favorables. Agressivité autorisée.',
        },
        'RISK_OFF': {
            'can_trade': True,
            'size_multiplier': 0.5,     # Réduire la taille de 50%
            'rsi_adjustment': -10,       # RSI doit être plus bas
            'aggressive_mode': False,
            'description': '🔴 RISK-OFF: Dollar fort, prudence maximale.',
        },
        'MIXED': {
            'can_trade': True,
            'size_multiplier': 0.8,     # Légèrement réduit
            'rsi_adjustment': 0,
            'aggressive_mode': False,
            'description': '🟡 MIXED: Signaux contradictoires. Mode standard.',
        },
        'DANGER': {
            'can_trade': False,
            'size_multiplier': 0,
            'rsi_adjustment': -20,
            'aggressive_mode': False,
            'description': '🚨 DANGER: VIX extrême ou crash en cours. STOP TRADING!',
        },
    }
    
    return adjustments.get(regime, adjustments['MIXED'])


# ==================== FONCTION PRINCIPALE ====================

def get_macro_context() -> Dict:
    """
    🏛️ FONCTION PRINCIPALE
    Récupère tout le contexte macro et génère un résumé pour Bedrock.
    """
    
    # Récupérer toutes les données
    dxy = get_dxy_data()
    yields = get_yields_data()
    vix = get_vix_data()
    calendar = get_economic_calendar()
    
    # Déterminer le régime
    regime = determine_macro_regime(dxy, yields, vix)
    adjustments = get_regime_adjustments(regime)
    
    # Générer le résumé pour le prompt Bedrock
    summary_lines = [
        f"- Dollar Index (DXY): {dxy['value']:.2f} ({dxy['change_pct']:+.2f}% today) → {dxy['signal']}",
        f"- US 10Y Yield: {yields['value']:.2f}% ({yields['change_bps']:+.1f} bps) → {yields['signal']}",
        f"- VIX (Fear Index): {vix['value']:.1f} → {vix['level']}",
        f"- Macro Regime: {regime}",
    ]
    
    if calendar['has_high_impact']:
        event_names = [e['name'] for e in calendar['events']]
        summary_lines.append(f"- ⚠️ HIGH IMPACT NEWS: {', '.join(event_names)}")
    
    summary = '\n'.join(summary_lines)
    
    return {
        # Données brutes
        'dxy': dxy,
        'yields': yields,
        'vix': vix,
        'calendar': calendar,
        
        # Analyse
        'regime': regime,
        'adjustments': adjustments,
        
        # Pour injection dans le prompt
        'summary': summary,
        'can_trade': adjustments['can_trade'],
        'size_multiplier': adjustments['size_multiplier'],
        
        # Timestamp
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }


def get_macro_regime() -> Tuple[str, Dict]:
    """
    🎯 Fonction simplifiée pour juste obtenir le régime et les ajustements.
    """
    context = get_macro_context()
    return context['regime'], context['adjustments']


def format_for_bedrock(context: Dict = None) -> str:
    """
    📝 Formate le contexte macro pour injection dans le prompt Bedrock.
    """
    if context is None:
        context = get_macro_context()
    
    return f"""<macro_context>
{context['summary']}
TRADING RECOMMENDATION: {context['adjustments']['description']}
</macro_context>"""


# ==================== TEST ====================

if __name__ == '__main__':
    print("=" * 60)
    print("🏛️ MACRO CONTEXT - Empire V5.1 Hedge Fund Intelligence")
    print("=" * 60)
    
    context = get_macro_context()
    
    print("\n📊 DONNÉES MACRO EN TEMPS RÉEL:")
    print("-" * 50)
    print(f"💵 DXY (Dollar): {context['dxy']['value']:.2f} ({context['dxy']['change_pct']:+.2f}%)")
    print(f"   → Signal: {context['dxy']['signal']}")
    print()
    print(f"📈 US 10Y Yield: {context['yields']['value']:.2f}% ({context['yields']['change_bps']:+.1f} bps)")
    print(f"   → Signal: {context['yields']['signal']}")
    print()
    print(f"😱 VIX: {context['vix']['value']:.1f}")
    print(f"   → Level: {context['vix']['level']}")
    
    print("\n📅 CALENDRIER ÉCONOMIQUE:")
    print("-" * 50)
    if context['calendar']['events']:
        for event in context['calendar']['events']:
            print(f"   ⚠️ {event['name']} (Impact: {event['impact']})")
    else:
        print("   ✅ Pas d'événement majeur aujourd'hui")
    
    print("\n🎯 RÉGIME MACRO:")
    print("-" * 50)
    print(f"   Régime: {context['regime']}")
    print(f"   {context['adjustments']['description']}")
    print(f"   Position Size: x{context['adjustments']['size_multiplier']}")
    print(f"   Can Trade: {context['can_trade']}")
    
    print("\n📝 PROMPT BEDROCK:")
    print("-" * 50)
    print(format_for_bedrock(context))
