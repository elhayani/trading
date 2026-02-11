"""
📍 MICRO-CORRIDORS MODULE - Empire V11.2
========================================
Defines time-based trading corridors and their associated risk/TP/SL parameters.
Synchronizes strategy behavior with market sessions (London, NY, Asia).
"""

import logging
from datetime import datetime, time, timezone
from enum import Enum
from .models import MarketRegime

logger = logging.getLogger(__name__)

# --- Corridor Definitions ---
# Each corridor adjusts strategy parameters based on historical volatility patterns.
CRYPTO_CORRIDORS = [
    {
        'id': 'ASIA_CONSOLIDATION',
        'name': 'Asia Session',
        'start': (0, 0), 'end': (6, 0),
        'regime': MarketRegime.RANGE_BOUND,
        'params': {
            'tp_multiplier': 0.8,
            'sl_multiplier': 1.2,
            'risk_multiplier': 0.7,
            'scalping_mode': True
        }
    },
    {
        'id': 'LONDON_OPEN_VOL',
        'name': 'London Open',
        'start': (6, 0), 'end': (13, 0),
        'regime': MarketRegime.BULL_TREND,
        'params': {
            'tp_multiplier': 1.5,
            'sl_multiplier': 1.0,
            'risk_multiplier': 1.2,
            'scalping_mode': False
        }
    },
    {
        'id': 'NY_SESSION_PEAK',
        'name': 'NY Peak',
        'start': (13, 0), 'end': (20, 0),
        'regime': MarketRegime.HIGH_VOLATILITY,
        'params': {
            'tp_multiplier': 2.0,
            'sl_multiplier': 1.5,
            'risk_multiplier': 1.0,
            'scalping_mode': False
        }
    },
    {
        'id': 'LATE_NY_CONSOLIDATION',
        'name': 'Late NY',
        'start': (20, 0), 'end': (24, 0),
        'regime': MarketRegime.LOW_LIQUIDITY,
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.8,
            'risk_multiplier': 0.5,
            'scalping_mode': True
        }
    }
]

def get_current_minutes(dt: datetime = None) -> int:
    """Get UTC minutes since midnight."""
    now = dt or datetime.now(timezone.utc)
    return now.hour * 60 + now.minute

def _is_in_corridor(current_mins: int, start: tuple, end: tuple) -> bool:
    """Inclusive start, exclusive end logic [start, end)."""
    s_min = start[0] * 60 + start[1]
    e_min = end[0] * 60 + end[1]
    
    if s_min < e_min:
        return s_min <= current_mins < e_min
    else:
        # Crosses midnight
        return current_mins >= s_min or current_mins < e_min

def get_corridor_params(symbol: str) -> dict:
    """
    Returns the appropriate parameters for the current market time.
    Standardized UTC session mapping.
    """
    current_mins = get_current_minutes()
    
    # Check Crypto corridors (Default)
    for c in CRYPTO_CORRIDORS:
        if _is_in_corridor(current_mins, c['start'], c['end']):
            return c
            
    # Fallback to default safe mode
    return {
        'id': 'DEFAULT_OFF_HOURS',
        'name': 'Off-Hours',
        'regime': MarketRegime.LOW_LIQUIDITY,
        'params': {
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.5,
            'risk_multiplier': 0.5,
            'scalping_mode': False
        }
    }
