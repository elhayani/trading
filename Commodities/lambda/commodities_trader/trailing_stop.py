"""
🚀 V5.2 TRAILING STOP MODULE
=============================
Module universel de trailing stop pour tous les bots de trading.
Implémente un trailing stop dynamique basé sur l'ATR et le PnL courant.

Features:
- Trailing Stop classique avec activation au-dessus d'un seuil
- Trailing Stop dynamique basé sur l'ATR
- Mode Turbo pour les assets volatils (SOL, etc.)
- Break-even automatique après un seuil de profit
"""

import logging
from datetime import datetime
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class TrailingStopManager:
    """
    Gestionnaire de Trailing Stop universel pour tous les assets.
    """
    
    # Configuration par asset class
    DEFAULT_CONFIG = {
        'Crypto': {
            'activation_pct': 2.0,      # Activer à +2%
            'trailing_pct': 1.5,        # Trail de 1.5%
            'breakeven_pct': 1.0,       # Move SL à BE à +1%
            'turbo_activation': 10.0,   # Mode turbo à +10%
            'turbo_trail': 3.0,         # Trail turbo de 3%
            'atr_multiplier': 2.0,      # Trail = 2x ATR
        },
        'Forex': {
            'activation_pct': 0.5,      # Activer à +0.5%
            'trailing_pct': 0.3,        # Trail de 0.3%
            'breakeven_pct': 0.3,       # Move SL à BE à +0.3%
            'turbo_activation': 2.0,    # Mode turbo à +2%
            'turbo_trail': 0.8,         # Trail turbo de 0.8%
            'atr_multiplier': 1.5,      # Trail = 1.5x ATR
        },
        'Indices': {
            'activation_pct': 1.5,      # Activer à +1.5%
            'trailing_pct': 1.0,        # Trail de 1.0%
            'breakeven_pct': 0.8,       # Move SL à BE à +0.8%
            'turbo_activation': 5.0,    # Mode turbo à +5%
            'turbo_trail': 2.0,         # Trail turbo de 2.0%
            'atr_multiplier': 1.5,      # Trail = 1.5x ATR
        },
        'Commodities': {
            'activation_pct': 1.5,      # Activer à +1.5%
            'trailing_pct': 1.0,        # Trail de 1.0%
            'breakeven_pct': 0.8,       # Move SL à BE à +0.8%
            'turbo_activation': 5.0,    # Mode turbo à +5%
            'turbo_trail': 2.0,         # Trail turbo de 2.0%
            'atr_multiplier': 2.0,      # Trail = 2x ATR (Gold volatile)
        }
    }
    
    def __init__(self, asset_class: str = 'Crypto'):
        self.asset_class = asset_class
        self.config = self.DEFAULT_CONFIG.get(asset_class, self.DEFAULT_CONFIG['Crypto'])
    
    def calculate_trailing_stop(
        self,
        entry_price: float,
        current_price: float,
        trade_type: str,  # 'LONG' or 'SHORT'
        current_sl: float,
        peak_price: Optional[float] = None,
        atr: Optional[float] = None
    ) -> Dict:
        """
        Calcule le nouveau Stop Loss basé sur le trailing.
        
        Returns:
            Dict avec:
            - new_sl: Nouveau stop loss (ou None si pas de changement)
            - triggered: True si le trailing stop a été touché
            - mode: 'BREAKEVEN', 'TRAILING', 'TURBO', ou None
            - peak: Nouveau peak price
        """
        result = {
            'new_sl': None,
            'triggered': False,
            'mode': None,
            'peak': peak_price or current_price,
            'pnl_pct': 0
        }
        
        # Calcul du PnL
        if trade_type in ['LONG', 'BUY']:
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            result['pnl_pct'] = pnl_pct
            
            # Update peak
            if peak_price is None or current_price > peak_price:
                result['peak'] = current_price
            
            peak = result['peak']
            pnl_from_peak = ((current_price - peak) / peak) * 100
            
            # Mode Turbo (pour les gros gains)
            if pnl_pct >= self.config['turbo_activation']:
                result['mode'] = 'TURBO'
                trail_distance = self.config['turbo_trail']
                
                if atr:
                    trail_distance = max(trail_distance, atr / entry_price * 100 * 2)
                
                new_sl = peak * (1 - trail_distance / 100)
                
                if new_sl > current_sl:
                    result['new_sl'] = new_sl
                    logger.info(f"🚀 TURBO TRAILING: Peak={peak:.4f} | Trail={trail_distance:.2f}% | New SL={new_sl:.4f}")
                
                # Check if triggered
                if current_price <= new_sl:
                    result['triggered'] = True
            
            # Mode Trailing Standard
            elif pnl_pct >= self.config['activation_pct']:
                result['mode'] = 'TRAILING'
                
                # ATR-based trailing si disponible
                if atr:
                    trail_distance = (atr / entry_price) * 100 * self.config['atr_multiplier']
                else:
                    trail_distance = self.config['trailing_pct']
                
                new_sl = peak * (1 - trail_distance / 100)
                
                if new_sl > current_sl:
                    result['new_sl'] = new_sl
                    logger.info(f"📈 TRAILING ACTIVE: Peak={peak:.4f} | Trail={trail_distance:.2f}% | New SL={new_sl:.4f}")
                
                # Check if triggered
                if current_price <= new_sl:
                    result['triggered'] = True
            
            # Mode Break-Even
            elif pnl_pct >= self.config['breakeven_pct']:
                if current_sl < entry_price:
                    result['mode'] = 'BREAKEVEN'
                    result['new_sl'] = entry_price
                    logger.info(f"🛡️ BREAK-EVEN: Moving SL to entry {entry_price:.4f}")
        
        # SHORT trades (inverse logic)
        elif trade_type in ['SHORT', 'SELL']:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
            result['pnl_pct'] = pnl_pct
            
            # Update peak (for short, peak is the lowest price)
            if peak_price is None or current_price < peak_price:
                result['peak'] = current_price
            
            peak = result['peak']
            
            # Mode Turbo
            if pnl_pct >= self.config['turbo_activation']:
                result['mode'] = 'TURBO'
                trail_distance = self.config['turbo_trail']
                
                new_sl = peak * (1 + trail_distance / 100)
                
                if new_sl < current_sl:
                    result['new_sl'] = new_sl
                
                if current_price >= new_sl:
                    result['triggered'] = True
            
            # Mode Trailing Standard
            elif pnl_pct >= self.config['activation_pct']:
                result['mode'] = 'TRAILING'
                
                if atr:
                    trail_distance = (atr / entry_price) * 100 * self.config['atr_multiplier']
                else:
                    trail_distance = self.config['trailing_pct']
                
                new_sl = peak * (1 + trail_distance / 100)
                
                if new_sl < current_sl:
                    result['new_sl'] = new_sl
                
                if current_price >= new_sl:
                    result['triggered'] = True
            
            # Mode Break-Even
            elif pnl_pct >= self.config['breakeven_pct']:
                if current_sl > entry_price:
                    result['mode'] = 'BREAKEVEN'
                    result['new_sl'] = entry_price
        
        return result


def check_trailing_stop(
    entry_price: float,
    current_price: float,
    trade_type: str,
    current_sl: float,
    asset_class: str = 'Crypto',
    peak_price: Optional[float] = None,
    atr: Optional[float] = None
) -> Dict:
    """
    Fonction helper pour vérifier le trailing stop sans instancier la classe.
    """
    manager = TrailingStopManager(asset_class)
    return manager.calculate_trailing_stop(
        entry_price=entry_price,
        current_price=current_price,
        trade_type=trade_type,
        current_sl=current_sl,
        peak_price=peak_price,
        atr=atr
    )


# ==================== TESTS ====================
if __name__ == "__main__":
    # Test Crypto LONG
    print("=== Test Crypto LONG ===")
    result = check_trailing_stop(
        entry_price=40000,
        current_price=42000,  # +5%
        trade_type='LONG',
        current_sl=38000,
        asset_class='Crypto'
    )
    print(f"Result: {result}")
    
    # Test Forex LONG avec ATR
    print("\n=== Test Forex LONG with ATR ===")
    result = check_trailing_stop(
        entry_price=1.0800,
        current_price=1.0850,  # +0.46%
        trade_type='LONG',
        current_sl=1.0750,
        asset_class='Forex',
        atr=0.0030
    )
    print(f"Result: {result}")
    
    # Test Turbo Mode
    print("\n=== Test Turbo Mode (SOL +15%) ===")
    result = check_trailing_stop(
        entry_price=100,
        current_price=115,  # +15%
        trade_type='LONG',
        current_sl=97,
        asset_class='Crypto',
        peak_price=118
    )
    print(f"Result: {result}")
