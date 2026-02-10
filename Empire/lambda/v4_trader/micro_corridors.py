"""
🏛️ MICRO-CORRIDORS MODULE - Empire V5 Scalping System
=======================================================
Découpage de la journée en micro-fenêtres de 30-60 minutes.
Chaque corridor a sa propre stratégie, agressivité et paramètres.

Principe:
- L'OUVERTURE (15h30-17h) → Agressif, breakout, gros gains rapides
- LE MILIEU (17h-20h) → Trend following, stabilité
- LA FERMETURE (20h-22h) → Prudent, mean reversion, petits TP

Usage:
    from micro_corridors import get_corridor_params, get_current_regime
    
    params = get_corridor_params(symbol, asset_class)
    regime = get_current_regime(symbol)
    
    # Adapter les paramètres de la stratégie
    take_profit = defaults['tp'] * params['tp_multiplier']
    stop_loss = defaults['sl'] * params['sl_multiplier']
"""

import datetime
import pytz
from typing import Dict, Optional, Tuple

# Timezone de référence (Paris/CET)
PARIS_TZ = pytz.timezone('Europe/Paris')

# ==================== RÉGIMES DE MARCHÉ ====================
# Ces régimes s'appliquent selon l'heure et les conditions

from models import MarketRegime


# ==================== MICRO-CORRIDORS PAR CLASSE D'ACTIF ====================

# Format: 'start_time': Tuple(hour, minute), 'end_time': Tuple(hour, minute)
# Tous les horaires sont en heure Paris (CET)

INDICES_CORRIDORS = {
    # === SESSION US MORNING (L'Ouverture) ===
    'US_OPEN_IMPACT': {
        'start': (15, 30), 'end': (16, 0),
        'name': '💥 Impact Zone',
        'regime': MarketRegime.AGGRESSIVE_BREAKOUT,
        'description': 'Volatilité maximale, spreads instables. On cherche le sens du flux.',
        'params': {
            'tp_multiplier': 0.4,     # TP court (0.6-1.2% au lieu de 3%)
            'sl_multiplier': 0.5,     # SL serré
            'risk_multiplier': 1.5,   # Position plus grosse
            'rsi_threshold': 35,      # Moins sélectif (on veut capter l'impulsion)
            'min_volume_ratio': 2.0,  # Volume doit être 2x la moyenne
            'max_trades': 3,          # Maximum 3 trades dans cette fenêtre
            'scalping_mode': True,    # Mode scalping activé
        }
    },
    'US_OPEN_PULLBACK': {
        'start': (16, 0), 'end': (16, 30),
        'name': '📉 First Pullback',
        'regime': MarketRegime.PULLBACK_SNIPER,
        'description': 'Correction de l\'impulsion initiale. On achète le repli.',
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.6,
            'risk_multiplier': 1.2,
            'rsi_threshold': 30,      # RSI plus bas = meilleur pullback
            'min_volume_ratio': 1.5,
            'max_trades': 2,
            'scalping_mode': True,
        }
    },
    
    # === SESSION US CORE (Le Milieu - Flow Institutionnel) ===
    'US_CORE_TREND': {
        'start': (16, 30), 'end': (18, 0),
        'name': '🏛️ Institutional Flow',
        'regime': MarketRegime.TREND_FOLLOWING,
        'description': 'Les banques ont choisi leur camp. Trend stable.',
        'params': {
            'tp_multiplier': 0.6,     # TP modéré
            'sl_multiplier': 0.8,
            'risk_multiplier': 1.0,   # Position standard
            'rsi_threshold': 40,
            'min_volume_ratio': 1.2,
            'max_trades': 4,
            'scalping_mode': True,
        }
    },
    'US_LUNCH_SLOW': {
        'start': (18, 0), 'end': (19, 0),
        'name': '🍔 US Lunch (Lull)',
        'regime': MarketRegime.SCALPING,
        'description': 'Pause déjeuner US. Volume baisse, ranges serrés.',
        'params': {
            'tp_multiplier': 0.3,     # TP très court
            'sl_multiplier': 0.4,
            'risk_multiplier': 0.8,   # Position réduite
            'rsi_threshold': 35,
            'min_volume_ratio': 0.8,
            'max_trades': 2,
            'scalping_mode': True,
        }
    },
    'US_AFTERNOON_PUSH': {
        'start': (19, 0), 'end': (20, 0),
        'name': '🚀 Afternoon Push',
        'regime': MarketRegime.TREND_FOLLOWING,
        'description': 'Retour des traders US après le lunch. Nouvelle impulsion.',
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.6,
            'risk_multiplier': 1.1,
            'rsi_threshold': 40,
            'min_volume_ratio': 1.3,
            'max_trades': 3,
            'scalping_mode': True,
        }
    },
    
    # === SESSION US CLOSE (La Fermeture) ===
    'US_CLOSE_PROFIT': {
        'start': (20, 0), 'end': (21, 0),
        'name': '💰 Profit Taking',
        'regime': MarketRegime.CAUTIOUS_REVERSAL,
        'description': 'Prises de profits. Risque de retournement.',
        'params': {
            'tp_multiplier': 0.4,
            'sl_multiplier': 0.5,
            'risk_multiplier': 0.7,   # Position réduite
            'rsi_threshold': 28,      # Plus sélectif
            'min_volume_ratio': 1.0,
            'max_trades': 2,
            'scalping_mode': True,
        }
    },
    'US_CLOSE_FINAL': {
        'start': (21, 0), 'end': (22, 0),
        'name': '🔚 Final Hour',
        'regime': MarketRegime.LOW_LIQUIDITY,
        'description': 'Dernière heure. Mouvement erratiques possibles.',
        'params': {
            'tp_multiplier': 0.3,
            'sl_multiplier': 0.4,
            'risk_multiplier': 0.5,   # Position minimale
            'rsi_threshold': 25,      # Très sélectif
            'min_volume_ratio': 0.8,
            'max_trades': 1,
            'scalping_mode': True,
        }
    },
}

FOREX_EUR_GBP_CORRIDORS = {
    # === SESSION LONDRES (Matin européen) ===
    'LONDON_OPEN': {
        'start': (9, 0), 'end': (10, 0),
        'name': '🇬🇧 London Open',
        'regime': MarketRegime.AGGRESSIVE_BREAKOUT,
        'description': 'Ouverture Londres. Volatilité sur EUR/GBP/AUD.',
        'params': {
            'tp_multiplier': 0.4,
            'sl_multiplier': 0.5,
            'risk_multiplier': 1.3,
            'rsi_threshold': 35,
            'min_volume_ratio': 1.5,
            'max_trades': 2,
            'scalping_mode': True,
        }
    },
    'LONDON_MORNING': {
        'start': (10, 0), 'end': (12, 0),
        'name': '☕ London Morning',
        'regime': MarketRegime.TREND_FOLLOWING,
        'description': 'Session Londres établie. Tendance claire.',
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.6,
            'risk_multiplier': 1.0,
            'rsi_threshold': 40,
            'min_volume_ratio': 1.2,
            'max_trades': 4,
            'scalping_mode': True,
        }
    },
    'LONDON_LUNCH': {
        'start': (12, 0), 'end': (14, 0),
        'name': '🥐 London Lunch',
        'regime': MarketRegime.SCALPING,
        'description': 'Pause déjeuner. Ranges serrés.',
        'params': {
            'tp_multiplier': 0.3,
            'sl_multiplier': 0.4,
            'risk_multiplier': 0.7,
            'rsi_threshold': 35,
            'min_volume_ratio': 0.8,
            'max_trades': 2,
            'scalping_mode': True,
        }
    },
    
    # === OVERLAP LONDRES-NY (Le moment optimal) ===
    'NY_OVERLAP': {
        'start': (14, 0), 'end': (16, 0),
        'name': '🔥 NY Overlap',
        'regime': MarketRegime.AGGRESSIVE_BREAKOUT,
        'description': 'Overlap Londres-NY. Maximum de liquidité.',
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.5,
            'risk_multiplier': 1.5,   # Position max
            'rsi_threshold': 35,
            'min_volume_ratio': 2.0,
            'max_trades': 4,
            'scalping_mode': True,
        }
    },
    'NY_AFTERNOON': {
        'start': (16, 0), 'end': (18, 0),
        'name': '🇺🇸 NY Afternoon',
        'regime': MarketRegime.TREND_FOLLOWING,
        'description': 'Session NY seule. Suivi de tendance.',
        'params': {
            'tp_multiplier': 0.4,
            'sl_multiplier': 0.5,
            'risk_multiplier': 1.0,
            'rsi_threshold': 40,
            'min_volume_ratio': 1.2,
            'max_trades': 3,
            'scalping_mode': True,
        }
    },
}

FOREX_JPY_CORRIDORS = {
    # === SESSION TOKYO ===
    'TOKYO_OPEN': {
        'start': (1, 0), 'end': (3, 0),
        'name': '🇯🇵 Tokyo Open',
        'regime': MarketRegime.AGGRESSIVE_BREAKOUT,
        'description': 'Ouverture Tokyo. Mouvements brusques du Yen.',
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.6,
            'risk_multiplier': 1.3,
            'rsi_threshold': 35,
            'min_volume_ratio': 1.5,
            'max_trades': 2,
            'scalping_mode': True,
        }
    },
    'TOKYO_MORNING': {
        'start': (3, 0), 'end': (7, 0),
        'name': '🌸 Tokyo Morning',
        'regime': MarketRegime.TREND_FOLLOWING,
        'description': 'Session Tokyo établie.',
        'params': {
            'tp_multiplier': 0.4,
            'sl_multiplier': 0.5,
            'risk_multiplier': 1.0,
            'rsi_threshold': 40,
            'min_volume_ratio': 1.2,
            'max_trades': 3,
            'scalping_mode': True,
        }
    },
    'TOKYO_CLOSE': {
        'start': (7, 0), 'end': (9, 0),
        'name': '🌅 Tokyo Close',
        'regime': MarketRegime.CAUTIOUS_REVERSAL,
        'description': 'Fermeture Tokyo. Prudence.',
        'params': {
            'tp_multiplier': 0.3,
            'sl_multiplier': 0.4,
            'risk_multiplier': 0.7,
            'rsi_threshold': 30,
            'min_volume_ratio': 0.8,
            'max_trades': 1,
            'scalping_mode': True,
        }
    },
    
    # === SESSION NY (pour USD/JPY) ===
    'NY_JPY_OPEN': {
        'start': (14, 0), 'end': (16, 0),
        'name': '🗽 NY JPY Rush',
        'regime': MarketRegime.AGGRESSIVE_BREAKOUT,
        'description': 'US ouvre, le Yen réagit.',
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.5,
            'risk_multiplier': 1.4,
            'rsi_threshold': 35,
            'min_volume_ratio': 1.8,
            'max_trades': 3,
            'scalping_mode': True,
        }
    },
    'NY_JPY_CORE': {
        'start': (16, 0), 'end': (21, 0),
        'name': '📊 NY JPY Core',
        'regime': MarketRegime.TREND_FOLLOWING,
        'description': 'Session NY établie pour USD/JPY.',
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.6,
            'risk_multiplier': 1.0,
            'rsi_threshold': 40,
            'min_volume_ratio': 1.2,
            'max_trades': 4,
            'scalping_mode': True,
        }
    },
}

COMMODITIES_CORRIDORS = {
    # === SESSION US (Gold & Oil) ===
    'COMEX_OPEN': {
        'start': (14, 0), 'end': (15, 30),
        'name': '🥇 COMEX Pre-Open',
        'regime': MarketRegime.PULLBACK_SNIPER,
        'description': 'Avant ouverture NYSE. Positioning.',
        'params': {
            'tp_multiplier': 0.4,
            'sl_multiplier': 0.5,
            'risk_multiplier': 1.0,
            'rsi_threshold': 40,
            'min_volume_ratio': 1.2,
            'max_trades': 2,
            'scalping_mode': True,
        }
    },
    'COMMODITIES_CORE': {
        'start': (15, 30), 'end': (18, 0),
        'name': '⛏️ Commodities Core',
        'regime': MarketRegime.TREND_FOLLOWING,
        'description': 'Session active. Volume institutionnel.',
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.6,
            'risk_multiplier': 1.2,
            'rsi_threshold': 45,
            'min_volume_ratio': 1.5,
            'max_trades': 3,
            'scalping_mode': True,
        }
    },
    'COMMODITIES_CLOSE': {
        'start': (18, 0), 'end': (21, 0),
        'name': '🌆 Commodities Close',
        'regime': MarketRegime.CAUTIOUS_REVERSAL,
        'description': 'Fermeture COMEX. Prises de profits.',
        'params': {
            'tp_multiplier': 0.4,
            'sl_multiplier': 0.5,
            'risk_multiplier': 0.8,
            'rsi_threshold': 35,
            'min_volume_ratio': 1.0,
            'max_trades': 2,
            'scalping_mode': True,
        }
    },
}

CRYPTO_CORRIDORS = {
    # === 24/7 mais avec zones de qualité ===
    'ASIA_MORNING': {
        'start': (1, 0), 'end': (5, 0),
        'name': '🌏 Asia Morning',
        'regime': MarketRegime.TREND_FOLLOWING,
        'description': 'Marché asiatique actif.',
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.6,
            'risk_multiplier': 1.0,
            'rsi_threshold': 40,
            'min_volume_ratio': 1.0,
            'max_trades': 3,
            'scalping_mode': True,
        }
    },
    'DEAD_ZONE': {
        'start': (5, 0), 'end': (8, 0),
        'name': '💀 Dead Zone',
        'regime': MarketRegime.LOW_LIQUIDITY,
        'description': 'Zone morte. Basse liquidité, manipulation.',
        'params': {
            'tp_multiplier': 0.3,
            'sl_multiplier': 0.4,
            'risk_multiplier': 0.5,   # Position minimale
            'rsi_threshold': 25,      # Très sélectif
            'min_volume_ratio': 0.5,
            'max_trades': 1,
            'scalping_mode': False,   # Pas de scalping ici
        }
    },
    'EUROPE_WAKE': {
        'start': (8, 0), 'end': (14, 0),
        'name': '🇪🇺 Europe Active',
        'regime': MarketRegime.TREND_FOLLOWING,
        'description': 'Europe se réveille. Volume correct.',
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.6,
            'risk_multiplier': 1.0,
            'rsi_threshold': 40,
            'min_volume_ratio': 1.2,
            'max_trades': 4,
            'scalping_mode': True,
        }
    },
    'US_CRYPTO_RUSH': {
        'start': (14, 0), 'end': (18, 0),
        'name': '🇺🇸 US Crypto Rush',
        'regime': MarketRegime.AGGRESSIVE_BREAKOUT,
        'description': 'US ouvre. Volume maximum crypto.',
        'params': {
            'tp_multiplier': 0.6,
            'sl_multiplier': 0.5,
            'risk_multiplier': 1.5,   # Position max
            'rsi_threshold': 35,
            'min_volume_ratio': 2.0,
            'max_trades': 5,
            'scalping_mode': True,
        }
    },
    'US_EVENING': {
        'start': (18, 0), 'end': (22, 0),
        'name': '🌙 US Evening',
        'regime': MarketRegime.TREND_FOLLOWING,
        'description': 'Soirée US. Volume encore bon.',
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.6,
            'risk_multiplier': 1.1,
            'rsi_threshold': 40,
            'min_volume_ratio': 1.3,
            'max_trades': 4,
            'scalping_mode': True,
        }
    },
    'LATE_NIGHT': {
        'start': (22, 0), 'end': (1, 0),
        'name': '🌌 Late Night',
        'regime': MarketRegime.SCALPING,
        'description': 'Nuit. Volume baisse mais ranges exploitables.',
        'params': {
            'tp_multiplier': 0.3,
            'sl_multiplier': 0.4,
            'risk_multiplier': 0.8,
            'rsi_threshold': 35,
            'min_volume_ratio': 0.8,
            'max_trades': 2,
            'scalping_mode': True,
        }
    },
}


# ==================== MAPPING SYMBOLE -> CORRIDORS ====================

SYMBOL_CORRIDOR_MAP = {
    # Indices (Legacy Yahoo + New Crypto-CFD)
    '^NDX': INDICES_CORRIDORS,
    '^GSPC': INDICES_CORRIDORS,
    '^DJI': INDICES_CORRIDORS,
    'SPX/USDT': INDICES_CORRIDORS,    # V7
    'US30/USDT': INDICES_CORRIDORS,   # V7 (Dow Jones)
    'NDX/USDT': INDICES_CORRIDORS,    # V7 (Nasdaq)
    'DEFI/USDT': INDICES_CORRIDORS,   # V7 (Crypto Index)
    
    # Forex EUR/GBP/AUD
    'EURUSD': FOREX_EUR_GBP_CORRIDORS,
    'GBPUSD': FOREX_EUR_GBP_CORRIDORS,
    'AUDUSD': FOREX_EUR_GBP_CORRIDORS,
    'EUR/USDT': FOREX_EUR_GBP_CORRIDORS, 
    'GBP/USDT': FOREX_EUR_GBP_CORRIDORS, 
    'AUD/USDT': FOREX_EUR_GBP_CORRIDORS,
    
    # Commodities (V7: Tokenized)
    'PAXG/USDT': COMMODITIES_CORRIDORS,  # Gold
    'XAG/USDT': COMMODITIES_CORRIDORS,   # Silver
    'USOIL/USDT': COMMODITIES_CORRIDORS, # Oil (if available)
    'OIL/USDT': COMMODITIES_CORRIDORS,   # Oil (Binance symbol)
    
    # Crypto
    'SOL/USDT': CRYPTO_CORRIDORS,
    'BTC/USDT': CRYPTO_CORRIDORS,
    'ETH/USDT': CRYPTO_CORRIDORS,
}


# ==================== FONCTIONS PRINCIPALES ====================

def get_paris_time() -> datetime.datetime:
    """Retourne l'heure actuelle en timezone Paris"""
    return datetime.datetime.now(PARIS_TZ)


def _time_to_minutes(hour: int, minute: int) -> int:
    """Convertit heure:minute en minutes depuis minuit"""
    return hour * 60 + minute


def _is_in_corridor(current_minutes: int, start: Tuple[int, int], end: Tuple[int, int]) -> bool:
    """Vérifie si on est dans un corridor (gère le passage minuit)"""
    start_mins = _time_to_minutes(*start)
    end_mins = _time_to_minutes(*end)
    
    if start_mins < end_mins:
        # Corridor normal (ex: 14h-18h)
        return start_mins <= current_minutes < end_mins
    else:
        # Corridor qui passe minuit (ex: 22h-01h)
        return current_minutes >= start_mins or current_minutes < end_mins


def get_current_corridor(symbol: str) -> Optional[Dict]:
    """
    Retourne le corridor actuel pour un symbole donné.
    
    Args:
        symbol: Le symbole à vérifier (ex: '^NDX', 'EURUSD', 'SOL/USDT')
        
    Returns:
        Dict avec les infos du corridor, ou None si aucun corridor actif
    """
    clean_symbol = symbol.replace('=X', '').upper()
    
    corridors = SYMBOL_CORRIDOR_MAP.get(clean_symbol)
    if corridors is None:
        return None
    
    now = get_paris_time()
    current_minutes = _time_to_minutes(now.hour, now.minute)
    
    for corridor_name, corridor_config in corridors.items():
        start = corridor_config['start']
        end = corridor_config['end']
        
        if _is_in_corridor(current_minutes, start, end):
            return {
                'corridor_id': corridor_name,
                **corridor_config,
                'current_time': str(now),
            }
    
    return None


def get_corridor_params(symbol: str, asset_class: str = None) -> Dict:
    """
    🎯 FONCTION PRINCIPALE
    Retourne les paramètres de trading adaptés au corridor actuel.
    
    Args:
        symbol: Le symbole (ex: '^NDX', 'EURUSD')
        asset_class: Optionnel, classe d'actif pour fallback
        
    Returns:
        Dict avec tp_multiplier, sl_multiplier, risk_multiplier, etc.
    """
    corridor = get_current_corridor(symbol)
    
    if corridor is None:
        # Pas de corridor défini = paramètres par défaut (prudents)
        return {
            'corridor_id': 'DEFAULT',
            'name': '⚠️ Off-Hours',
            'regime': MarketRegime.LOW_LIQUIDITY,
            'description': 'Hors des corridors définis - Mode prudent',
            'params': {
                'tp_multiplier': 0.3,
                'sl_multiplier': 0.4,
                'risk_multiplier': 0.5,
                'rsi_threshold': 25,
                'min_volume_ratio': 0.5,
                'max_trades': 1,
                'scalping_mode': False,
            }
        }
    
    return corridor


def get_current_regime(symbol: str) -> str:
    """
    Retourne le régime de marché actuel pour un symbole.
    
    Returns:
        Une des constantes MarketRegime
    """
    corridor = get_current_corridor(symbol)
    if corridor is None:
        return MarketRegime.LOW_LIQUIDITY
    return corridor.get('regime', MarketRegime.TREND_FOLLOWING)


def calculate_adaptive_tp_sl(symbol: str, base_tp: float, base_sl: float) -> Tuple[float, float]:
    """
    Calcule le TP et SL adaptatifs basés sur le corridor actuel.
    
    Args:
        symbol: Le symbole
        base_tp: Take Profit de base (en %)
        base_sl: Stop Loss de base (en %)
        
    Returns:
        Tuple (new_tp, new_sl) ajustés selon le corridor
    """
    corridor = get_corridor_params(symbol)
    params = corridor.get('params', {})
    
    tp_mult = params.get('tp_multiplier', 1.0)
    sl_mult = params.get('sl_multiplier', 1.0)
    
    new_tp = base_tp * tp_mult
    new_sl = base_sl * sl_mult
    
    return (new_tp, new_sl)


def should_increase_position_size(symbol: str) -> Tuple[bool, float]:
    """
    Détermine si on doit augmenter la taille de position (High Confidence Window).
    
    Returns:
        Tuple (should_increase: bool, multiplier: float)
    """
    corridor = get_corridor_params(symbol)
    params = corridor.get('params', {})
    
    risk_mult = params.get('risk_multiplier', 1.0)
    
    return (risk_mult > 1.0, risk_mult)


def is_scalping_enabled(symbol: str) -> bool:
    """Vérifie si le mode scalping est activé pour ce corridor"""
    corridor = get_corridor_params(symbol)
    params = corridor.get('params', {})
    return params.get('scalping_mode', False)


def get_max_trades_in_corridor(symbol: str) -> int:
    """Retourne le nombre maximum de trades autorisés dans ce corridor"""
    corridor = get_corridor_params(symbol)
    params = corridor.get('params', {})
    return params.get('max_trades', 1)


def get_rsi_threshold_adaptive(symbol: str, base_rsi: int = 40) -> int:
    """
    Retourne le seuil RSI adaptatif.
    En mode agressif (ouverture), on est moins sélectif (RSI plus haut).
    En mode prudent (fermeture), on exige un RSI plus bas.
    """
    corridor = get_corridor_params(symbol)
    params = corridor.get('params', {})
    return params.get('rsi_threshold', base_rsi)


def get_corridor_summary(symbol: str) -> str:
    """Retourne un résumé lisible du corridor actuel"""
    corridor = get_corridor_params(symbol)
    
    name = corridor.get('name', 'Unknown')
    regime = corridor.get('regime', 'Unknown')
    desc = corridor.get('description', '')
    params = corridor.get('params', {})
    
    tp_mult = params.get('tp_multiplier', 1.0)
    risk_mult = params.get('risk_multiplier', 1.0)
    scalping = params.get('scalping_mode', False)
    
    summary = f"""
🏛️ CORRIDOR ACTUEL: {name}
┣ Régime: {regime}
┣ Description: {desc}
┣ TP Multiplier: {tp_mult}x ({"Gains plus courts" if tp_mult < 1 else "Gains normaux"})
┣ Risk Multiplier: {risk_mult}x ({"Agressif" if risk_mult > 1 else "Prudent" if risk_mult < 1 else "Standard"})
┗ Scalping: {"✅ Activé" if scalping else "❌ Désactivé"}
"""
    return summary.strip()


# ==================== AFFICHAGE DES CORRIDORS DU JOUR ====================

def print_daily_schedule(symbol: str):
    """Affiche le planning des micro-corridors pour un symbole"""
    clean_symbol = symbol.replace('=X', '').upper()
    corridors = SYMBOL_CORRIDOR_MAP.get(clean_symbol)
    
    if corridors is None:
        print(f"❌ Aucun corridor défini pour {symbol}")
        return
    
    print(f"\n📅 PLANNING DES MICRO-CORRIDORS: {symbol}")
    print("=" * 70)
    
    # Trier par heure de début
    sorted_corridors = sorted(
        corridors.items(),
        key=lambda x: _time_to_minutes(*x[1]['start'])
    )
    
    for corridor_id, config in sorted_corridors:
        start = config['start']
        end = config['end']
        name = config['name']
        regime = config['regime']
        params = config['params']
        
        tp = params.get('tp_multiplier', 1.0)
        risk = params.get('risk_multiplier', 1.0)
        
        print(f"{start[0]:02d}:{start[1]:02d} - {end[0]:02d}:{end[1]:02d} | {name:25} | {regime:20} | TP: {tp:.1f}x | Risk: {risk:.1f}x")
    
    print("=" * 70)


# ==================== TEST ====================

if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("🏛️ MICRO-CORRIDORS MODULE - TEST")
    print("=" * 70)
    print(f"Heure Paris: {get_paris_time()}")
    print()
    
    # Test pour chaque symbole
    test_symbols = ['^NDX', '^GSPC', 'EURUSD', 'GBPUSD', 'USDJPY', 'GC=F', 'CL=F', 'SOL/USDT', 'BTC/USDT']
    
    print("📊 ÉTAT ACTUEL DES CORRIDORS:")
    print("-" * 70)
    
    for symbol in test_symbols:
        corridor = get_corridor_params(symbol)
        name = corridor.get('name', 'N/A')
        regime = corridor.get('regime', 'N/A')
        params = corridor.get('params', {})
        
        tp_mult = params.get('tp_multiplier', 1.0)
        risk_mult = params.get('risk_multiplier', 1.0)
        scalping = "🟢" if params.get('scalping_mode', False) else "🔴"
        
        print(f"{symbol:12} | {name:25} | {regime:22} | TP:{tp_mult:.1f}x | Risk:{risk_mult:.1f}x | Scalp:{scalping}")
    
    print()
    print("📅 PLANNING COMPLET (Exemple Nasdaq):")
    print_daily_schedule('^NDX')
    
    print("\n📅 PLANNING COMPLET (Exemple Crypto):")
    print_daily_schedule('BTC/USDT')
