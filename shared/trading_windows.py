"""
🏛️ TRADING WINDOWS MODULE - Empire V5 Fortress
===============================================
Golden Hours Filter: Ne trader que pendant les sessions à haute liquidité.

Principe:
- Forex/Indices: Éviter les heures mortes (spread élevé, faux signaux)
- Crypto: 24/7 mais avec filtre de volume
- Week-end: Forex/Indices fermés

Usage:
    from trading_windows import is_within_golden_window, get_session_info
    
    if not is_within_golden_window(symbol):
        logger.info(f"⏰ {symbol} - Hors session optimale, SKIP")
        return None
"""

import datetime
import pytz

# ==================== CONFIGURATION DES SESSIONS ====================

# Timezone de référence (Paris/CET)
PARIS_TZ = pytz.timezone('Europe/Paris')

# Sessions de trading par classe d'actif et symbole
# Format: (start_hour, end_hour) en heure Paris
TRADING_SESSIONS = {
    # --- INDICES (Session US uniquement) ---
    '^NDX': {
        'name': 'Nasdaq 100',
        'class': 'Indices',
        'windows': [(15, 22)],  # 15h30-22h00 (marge 30min avant)
        'reason': 'Session US - Volume réel uniquement après ouverture Wall Street'
    },
    '^GSPC': {
        'name': 'S&P 500',
        'class': 'Indices', 
        'windows': [(15, 22)],
        'reason': 'Session US - Évite le bruit des Futures européens'
    },
    '^DJI': {
        'name': 'Dow Jones',
        'class': 'Indices',
        'windows': [(15, 22)],
        'reason': 'Session US'
    },
    
    # --- FOREX EUR/GBP (Session Londres + NY Overlap) ---
    'EURUSD': {
        'name': 'EUR/USD',
        'class': 'Forex',
        'windows': [(8, 18)],  # 08h00-18h00
        'reason': 'Session Londres (8h-17h) + début NY overlap'
    },
    'GBPUSD': {
        'name': 'GBP/USD',
        'class': 'Forex',
        'windows': [(8, 18)],
        'reason': 'Session Londres - Liquidité maximale sur la Livre'
    },
    
    # --- FOREX JPY (Double session: Tokyo + NY) ---
    'USDJPY': {
        'name': 'USD/JPY',
        'class': 'Forex',
        'windows': [(1, 9), (14, 21)],  # Tokyo (01h-09h) + NY (14h-21h)
        'reason': 'Sessions Tokyo et New York - Le Yen bouge par impulsions'
    },
    
    # --- COMMODITIES (Session US/Chicago) ---
    'GC=F': {
        'name': 'Gold',
        'class': 'Commodities',
        'windows': [(14, 21)],  # 14h00-21h00
        'reason': 'Session US - COMEX/Chicago influence majeure sur l\'or'
    },
    'CL=F': {
        'name': 'Crude Oil',
        'class': 'Commodities',
        'windows': [(14, 20)],  # 14h00-20h00
        'reason': 'Pit de Chicago - Volume institutionnel'
    },
    
    # --- CRYPTO (24/7 mais avec awareness) ---
    'SOL/USDT': {
        'name': 'Solana',
        'class': 'Crypto',
        'windows': None,  # None = 24/7
        'reason': '24/7 - Marché continu, filtre par volume recommandé'
    },
    'BTC/USDT': {
        'name': 'Bitcoin',
        'class': 'Crypto',
        'windows': None,
        'reason': '24/7 - Marché continu'
    },
    'ETH/USDT': {
        'name': 'Ethereum',
        'class': 'Crypto',
        'windows': None,
        'reason': '24/7 - Marché continu'
    },
}

# Heures à éviter absolument (Rollover/Spread élargi)
ROLLOVER_HOURS = [22, 23, 0]  # 22h00-01h00 Paris


# ==================== FONCTIONS PRINCIPALES ====================

# ==================== FONCTIONS PRINCIPALES ====================

def get_paris_time(simulated_time=None):
    """
    Retourne l'heure actuelle en timezone Paris.
    Si simulated_time est fourni (pour backtest), l'utilise.
    """
    if simulated_time:
        if isinstance(simulated_time, str):
            # Si c'est une string ISO lors du backtest
            try:
                dt = datetime.datetime.fromisoformat(simulated_time)
            except ValueError:
                return datetime.datetime.now(PARIS_TZ)
        else:
            dt = simulated_time
            
        # Si le temps simulé n'a pas de timezone, on suppose que c'est UTC
        if dt.tzinfo is None:
            utc_tz = pytz.timezone('UTC')
            dt = utc_tz.localize(dt)
        return dt.astimezone(PARIS_TZ)
        
    return datetime.datetime.now(PARIS_TZ)


def is_weekend(simulated_time=None):
    """Vérifie si c'est le week-end (marché Forex/Indices fermé)"""
    now = get_paris_time(simulated_time)
    weekday = now.weekday()  # 0=Lundi, 6=Dimanche
    
    # Vendredi après 22h = fermé
    if weekday == 4 and now.hour >= 22:
        return True
    # Samedi = fermé
    if weekday == 5:
        return True
    # Dimanche avant 23h = fermé (réouverture Sydney)
    if weekday == 6 and now.hour < 23:
        return True
        
    return False


def is_in_rollover_period(simulated_time=None):
    """
    Vérifie si on est dans la période de rollover (22h-01h)
    Les spreads s'élargissent, risque de stop-out inutile
    """
    now = get_paris_time(simulated_time)
    return now.hour in ROLLOVER_HOURS


def is_within_golden_window(symbol: str, simulated_time=None) -> bool:
    """
    🎯 FONCTION PRINCIPALE
    Vérifie si l'heure actuelle est dans la fenêtre optimale pour cet actif
    """
    # Normaliser le symbole (retirer =X pour Forex)
    clean_symbol = symbol.replace('=X', '').upper()
    
    # Récupérer la config de ce symbole
    config = TRADING_SESSIONS.get(clean_symbol)
    
    if config is None:
        # Symbole inconnu = on autorise par défaut (prudence)
        return True
    
    asset_class = config.get('class', 'Unknown')
    windows = config.get('windows')
    
    # === 1. CRYPTO = 24/7 ===
    if asset_class == 'Crypto' or windows is None:
        return True
    
    # === 2. FOREX/INDICES: Vérifier le week-end ===
    if asset_class in ['Forex', 'Indices', 'Commodities']:
        if is_weekend(simulated_time):
            return False
    
    # === 3. Vérifier le Rollover (sauf Crypto) ===
    if asset_class != 'Crypto' and is_in_rollover_period(simulated_time):
        return False
    
    # === 4. Vérifier les fenêtres horaires ===
    now = get_paris_time(simulated_time)
    current_hour = now.hour
    
    for (start_hour, end_hour) in windows:
        if start_hour <= current_hour < end_hour:
            return True
    
    return False


def get_session_info(symbol: str, simulated_time=None) -> dict:
    """
    Retourne les informations de session pour un symbole
    Utile pour le logging et le dashboard
    """
    clean_symbol = symbol.replace('=X', '').upper()
    config = TRADING_SESSIONS.get(clean_symbol)
    
    if config is None:
        return {
            'symbol': symbol,
            'name': 'Unknown',
            'class': 'Unknown',
            'is_open': True,
            'reason': 'Symbole non configuré - Autorisé par défaut',
            'current_time': str(get_paris_time(simulated_time)),
            'windows': 'N/A'
        }
    
    is_open = is_within_golden_window(symbol, simulated_time)
    
    return {
        'symbol': symbol,
        'name': config.get('name', symbol),
        'class': config.get('class', 'Unknown'),
        'is_open': is_open,
        'reason': config.get('reason', ''),
        'current_time': str(get_paris_time(simulated_time)),
        'windows': config.get('windows', '24/7'),
        'is_weekend': is_weekend(simulated_time),
        'is_rollover': is_in_rollover_period(simulated_time)
    }


def get_all_active_symbols(simulated_time=None) -> list:
    """Retourne la liste de tous les symboles actuellement dans leur fenêtre optimale"""
    active = []
    for symbol in TRADING_SESSIONS.keys():
        if is_within_golden_window(symbol, simulated_time):
            active.append(symbol)
    return active


def get_session_phase(symbol: str, simulated_time=None) -> dict:
    """
    🎯 NOUVELLE FONCTION V5.1 - Horloge Biologique Centralisée
    Retourne la phase actuelle de trading avec le niveau d'agressivité.
    
    C'est cette fonction que le bot doit appeler pour savoir QUAND et COMMENT trader.
    """
    clean_symbol = symbol.replace('=X', '').upper()
    config = TRADING_SESSIONS.get(clean_symbol)
    
    # Défaut pour symbole inconnu
    default_response = {
        'session': 'UNKNOWN',
        'phase': 'UNKNOWN',
        'aggressiveness': 'MEDIUM',
        'is_tradeable': True,
        'description': 'Symbole non configuré - Mode standard'
    }
    
    if config is None:
        return default_response
    
    asset_class = config.get('class', 'Unknown')
    windows = config.get('windows')
    
    # Crypto = toujours tradeable mais avec aggressivité variable selon l'heure
    if asset_class == 'Crypto' or windows is None:
        now = get_paris_time(simulated_time)
        hour = now.hour
        
        # Micro-phases Crypto
        if 14 <= hour < 18:  # US Rush
            return {
                'session': 'US_CRYPTO_RUSH',
                'phase': 'CORE',
                'aggressiveness': 'HIGH',
                'is_tradeable': True,
                'description': '🇺🇸 Rush US - Volume maximum crypto'
            }
        elif 18 <= hour < 22:  # US Evening
            return {
                'session': 'US_EVENING',
                'phase': 'CORE',
                'aggressiveness': 'MEDIUM',
                'is_tradeable': True,
                'description': '🌙 Soirée US - Volume correct'
            }
        elif 5 <= hour < 8:  # Dead Zone
            return {
                'session': 'DEAD_ZONE',
                'phase': 'DEAD',
                'aggressiveness': 'LOW',
                'is_tradeable': True,  # Crypto = 24/7 mais prudent
                'description': '💀 Zone morte - Faible liquidité'
            }
        else:
            return {
                'session': 'STANDARD',
                'phase': 'CORE',
                'aggressiveness': 'MEDIUM',
                'is_tradeable': True,
                'description': '📊 Session standard'
            }
    
    # Vérifier si marché fermé (week-end)
    if asset_class in ['Forex', 'Indices', 'Commodities'] and is_weekend(simulated_time):
        return default_response
    
    # Vérifier rollover
    if asset_class != 'Crypto' and is_in_rollover_period(simulated_time):
        return {
            'session': 'ROLLOVER',
            'phase': 'DEAD',
            'aggressiveness': 'NONE',
            'is_tradeable': False,
            'description': '⚠️ Période de rollover - Spreads élevés'
        }
    
    # Vérifier les fenêtres horaires et déterminer la phase
    now = get_paris_time(simulated_time)
    current_hour = now.hour
    current_minute = now.minute
    
    for (start_hour, end_hour) in windows:
        if start_hour <= current_hour < end_hour:
            # On est dans une fenêtre - déterminer la sous-phase
            window_duration = end_hour - start_hour
            elapsed = current_hour - start_hour + (current_minute / 60)
            progress = elapsed / window_duration
            
            phase = 'CORE'
            aggressiveness = 'MEDIUM'
            prefix = '�'
            desc_phase = 'Session établie - Trend following'
            
            if progress < 0.25:  # Premier quart = Ouverture
                phase = 'OPENING'
                aggressiveness = 'HIGH'
                prefix = '�'
                desc_phase = 'Ouverture - Haute volatilité'
            elif progress < 0.75:  # Milieu = Core
                pass
            else:  # Dernier quart = Fermeture
                phase = 'CLOSING'
                aggressiveness = 'LOW'
                prefix = '🌅'
                desc_phase = 'Fermeture - Prudence'
            
            # Déterminer le nom de session selon l'asset class
            session_name = 'ACTIVE_SESSION'
            if asset_class == 'Indices':
                session_name = 'US_SESSION'
            elif asset_class == 'Commodities':
                session_name = 'COMEX_SESSION'
            elif asset_class == 'Forex':
                if 'JPY' in clean_symbol and 1 <= current_hour < 9:
                    session_name = 'TOKYO_SESSION'
                elif 14 <= current_hour < 18:
                    session_name = 'NY_OVERLAP'
                else:
                    session_name = 'LONDON_SESSION'
            
            return {
                'session': session_name,
                'phase': phase,
                'aggressiveness': aggressiveness,
                'is_tradeable': True,
                'description': f'{prefix} {desc_phase}'
            }
    
    # Hors fenêtre mais pas fermé
    return {
        'session': 'OFF_HOURS',
        'phase': 'DEAD',
        'aggressiveness': 'NONE',
        'is_tradeable': False,
        'description': '⏰ Hors heures optimales - Attente'
    }


def get_next_window_open(symbol: str, simulated_time=None) -> str:
    """
    Retourne l'heure d'ouverture de la prochaine fenêtre pour ce symbole
    Utile pour le dashboard
    """
    clean_symbol = symbol.replace('=X', '').upper()
    config = TRADING_SESSIONS.get(clean_symbol)
    
    if config is None or config.get('windows') is None:
        return "24/7"
    
    now = get_paris_time(simulated_time)
    current_hour = now.hour
    windows = config.get('windows', [])
    
    # Trouver la prochaine fenêtre
    for (start_hour, end_hour) in windows:
        if current_hour < start_hour:
            return f"{start_hour}:00 Paris"
    
    # Si on a passé toutes les fenêtres, c'est demain
    if windows:
        return f"Demain {windows[0][0]}:00 Paris"
    
    return "N/A"


# ==================== TEST (si exécuté directement) ====================

if __name__ == '__main__':
    print("=" * 60)
    print("🏛️ TRADING WINDOWS - État actuel")
    print("=" * 60)
    print(f"Heure Paris: {get_paris_time()}")
    print(f"Week-end: {is_weekend()}")
    print(f"Période Rollover: {is_in_rollover_period()}")
    print()
    
    print("📊 État des actifs:")
    print("-" * 60)
    for symbol in TRADING_SESSIONS:
        info = get_session_info(symbol)
        status = "🟢 OUVERT" if info['is_open'] else "🔴 FERMÉ"
        print(f"{info['class']:12} | {info['name']:12} | {status} | {info['reason'][:40]}")
    
    print()
    print("🎯 Symboles actuellement dans leur fenêtre optimale:")
    print(get_all_active_symbols())
