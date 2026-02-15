"""
🧭 BTC Compass - Règle d'Or Absolue
BTC comme boussole directionnelle pour éviter 90% des pièges de scalping
"""

import logging
import time
from typing import Dict, Optional, Tuple
from config import TradingConfig

logger = logging.getLogger(__name__)

class BTCCompass:
    """
    Boussole BTC - Indicateur directionnel absolu
    Évite les pièges où tombent 90% des scalpeurs
    """
    
    def __init__(self):
        self.config = TradingConfig()
        self.btc_trend = None
        self.btc_strength = 0.0
        self.btc_volatility = 0.0
        self.last_btc_price = 0.0
        self.btc_history = []
        
    def analyze_btc_trend(self, btc_price: float, btc_volume: float) -> Dict:
        """
        Analyse la tendance BTC et retourne la direction de la boussole
        
        Args:
            btc_price: Prix actuel BTC
            btc_volume: Volume actuel BTC
            
        Returns:
            Dict avec tendance, force et recommandations
        """
        try:
            # Ajouter à l'historique
            self.btc_history.append({
                'price': btc_price,
                'volume': btc_volume,
                'timestamp': time.time()
            })
            
            # Garder seulement les 100 dernières minutes
            if len(self.btc_history) > 100:
                self.btc_history = self.btc_history[-100:]
            
            # Calculer la tendance
            if len(self.btc_history) >= 10:
                trend_data = self._calculate_trend()
                self.btc_trend = trend_data['direction']
                self.btc_strength = trend_data['strength']
                self.btc_volatility = trend_data['volatility']
                
                logger.info(f"🧭 BTC Compass: {self.btc_trend} (Force: {self.btc_strength:.2%})")
                
                return {
                    'trend': self.btc_trend,
                    'strength': self.btc_strength,
                    'volatility': self.btc_volatility,
                    'recommendation': self._get_recommendation()
                }
            
            return {'trend': 'NEUTRAL', 'strength': 0.0, 'volatility': 0.0, 'recommendation': 'WAIT'}
            
        except Exception as e:
            logger.error(f"❌ BTC Compass error: {e}")
            return {'trend': 'NEUTRAL', 'strength': 0.0, 'volatility': 0.0, 'recommendation': 'WAIT'}
    
    def _calculate_trend(self) -> Dict:
        """Calcule la tendance BTC basée sur l'historique"""
        try:
            recent_prices = [h['price'] for h in self.btc_history[-20:]]
            
            # Calcul des moyennes mobiles
            ma_short = sum(recent_prices[-5:]) / 5
            ma_long = sum(recent_prices[-20:]) / 20
            
            # Détermination de la tendance
            price_change_pct = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
            
            if price_change_pct > self.config.BTC_TREND_THRESHOLD:
                direction = 'BULLISH'
            elif price_change_pct < -self.config.BTC_TREND_THRESHOLD:
                direction = 'BEARISH'
            else:
                direction = 'NEUTRAL'
            
            # Calcul de la force
            strength = abs(price_change_pct)
            
            # Calcul de la volatilité
            volatility = self._calculate_volatility(recent_prices)
            
            return {
                'direction': direction,
                'strength': strength,
                'volatility': volatility,
                'ma_short': ma_short,
                'ma_long': ma_long
            }
            
        except Exception as e:
            logger.error(f"❌ Trend calculation error: {e}")
            return {'direction': 'NEUTRAL', 'strength': 0.0, 'volatility': 0.0}
    
    def _calculate_volatility(self, prices: list) -> float:
        """Calcule la volatilité des prix"""
        try:
            if len(prices) < 2:
                return 0.0
            
            returns = []
            for i in range(1, len(prices)):
                ret = (prices[i] - prices[i-1]) / prices[i-1]
                returns.append(ret)
            
            avg_return = sum(returns) / len(returns)
            variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
            
            return variance ** 0.5
            
        except Exception as e:
            logger.error(f"❌ Volatility calculation error: {e}")
            return 0.0
    
    def _get_recommendation(self) -> str:
        """Génère la recommandation basée sur la boussole BTC"""
        try:
            if not self.config.BTC_COMPASS_ENABLED:
                return 'BTC_COMPASS_DISABLED'
            
            if self.btc_trend == 'BULLISH':
                if self.btc_strength > 0.02:  # > 2%
                    return 'LONG_ONLY_STRONG'
                else:
                    return 'LONG_ONLY_MODERATE'
            
            elif self.btc_trend == 'BEARISH':
                if self.btc_strength > 0.02:  # > 2%
                    return 'SHORT_ONLY_STRONG'
                else:
                    return 'SHORT_ONLY_MODERATE'
            
            else:  # NEUTRAL - PAS DE TRADE!
                return 'WAIT_FOR_CLARITY'  # Marché latéral = piège mortel
                    
        except Exception as e:
            logger.error(f"❌ Recommendation error: {e}")
            return 'WAIT'
    
    def validate_trade_direction(self, symbol: str, trade_side: str, signal_strength: float) -> Tuple[bool, str]:
        """
        Valide si le trade est autorisé selon la boussole BTC
        
        Args:
            symbol: Symbole de la crypto
            trade_side: 'BUY' ou 'SELL'
            signal_strength: Force du signal (0-1)
            
        Returns:
            Tuple (allowed: bool, reason: str)
        """
        try:
            if not self.config.BTC_COMPASS_ENABLED:
                return True, 'BTC_COMPASS_DISABLED'
            
            if not self.btc_trend:
                return True, 'BTC_TREND_UNKNOWN'
            
            # Règle d'or absolue
            if self.config.BTC_DIRECTION_LOCK:
                if self.btc_trend == 'BULLISH' and trade_side == 'SELL':
                    return False, f'BTC_BULLISH_NO_SHORT_ALLOWED (Strength: {self.btc_strength:.2%})'
                
                elif self.btc_trend == 'BEARISH' and trade_side == 'BUY':
                    return False, f'BTC_BEARISH_NO_LONG_ALLOWED (Strength: {self.btc_strength:.2%})'
            
            # Validation de corrélation
            correlation = self._get_btc_correlation(symbol)
            if correlation < self.config.BTC_CORRELATION_MIN:
                return False, f'LOW_BTC_CORRELATION ({correlation:.2f} < {self.config.BTC_CORRELATION_MIN})'
            
            # Validation de tendance BTC neutre = PAS DE TRADE!
            if self.btc_trend == 'NEUTRAL':
                return False, 'BTC_NEUTRAL_NO_TRADING_ALLOWED (Market sideways = death trap)'
            
            # Validation de force de signal
            if signal_strength < 0.8 and self.btc_strength > 0.02:
                return False, f'WEAK_SIGNAL_IN_STRONG_BTC_TREND ({signal_strength:.2f} < 0.8)'
            
            return True, f'BTC_COMPASS_VALIDATED (Trend: {self.btc_trend}, Strength: {self.btc_strength:.2%})'
            
        except Exception as e:
            logger.error(f"❌ Trade validation error: {e}")
            return False, f'VALIDATION_ERROR: {e}'
    
    def _get_btc_correlation(self, symbol: str) -> float:
        """
        Estime la corrélation entre BTC et le symbole
        
        Args:
            symbol: Symbole de la crypto
            
        Returns:
            Corrélation estimée (0-1)
        """
        try:
            # Corrélations typiques basées sur les catégories
            correlations = {
                # Leaders (très haute corrélation)
                'ETHUSDT': 0.85,
                'BNBUSDT': 0.82,
                
                # L1/Tech (haute corrélation)
                'SOLUSDT': 0.78,
                'AVAXUSDT': 0.76,
                'LINKUSDT': 0.74,
                
                # Meme/News (moyenne corrélation)
                'DOGEUSDT': 0.65,
                
                # RWA (basse corrélation)
                'PAXGUSDT': 0.45,
                
                # Indices (très basse corrélation)
                'SPXUSDT': 0.30,
                
                # Stablecoins (aucune corrélation)
                'USDCUSDT': 0.05,
                'USDTUSDT': 0.05
            }
            
            return correlations.get(symbol, 0.70)  # Default 70% correlation
            
        except Exception as e:
            logger.error(f"❌ Correlation calculation error: {e}")
            return 0.70
    
    def get_position_sizing_adjustment(self) -> float:
        """
        Ajuste la taille de position selon la tendance BTC
        
        Returns:
            Multiplicateur de taille de position (0.5 - 1.5)
        """
        try:
            if not self.btc_trend or not self.config.BTC_COMPASS_ENABLED:
                return 1.0
            
            # Ajustement selon la force de tendance
            if self.btc_strength > 0.03:  # > 3% tendance forte
                return 1.2  # +20% taille
            elif self.btc_strength > 0.02:  # > 2% tendance modérée
                return 1.1  # +10% taille
            elif self.btc_trend == 'NEUTRAL':
                return 0.8  # -20% taille en marché latéral
            else:
                return 1.0
                
        except Exception as e:
            logger.error(f"❌ Position sizing error: {e}")
            return 1.0
    
    def get_risk_adjustment(self) -> float:
        """
        Ajuste le risque selon la volatilité BTC
        
        Returns:
            Multiplicateur de risque (0.5 - 1.5)
        """
        try:
            if not self.config.BTC_COMPASS_ENABLED:
                return 1.0
            
            # Ajustement selon la volatilité
            if self.btc_volatility > 0.04:  # > 4% volatilité élevée
                return 0.7  # -30% risque
            elif self.btc_volatility > 0.025:  # > 2.5% volatilité modérée
                return 0.85  # -15% risque
            elif self.btc_volatility < 0.015:  # < 1.5% volatilité faible
                return 1.1  # +10% risque
            else:
                return 1.0
                
        except Exception as e:
            logger.error(f"❌ Risk adjustment error: {e}")
            return 1.0

# Instance globale du BTC Compass
btc_compass = BTCCompass()

def validate_trade_with_btc_compass(symbol: str, trade_side: str, signal_strength: float) -> Tuple[bool, str]:
    """
    Fonction utilitaire pour valider un trade avec la boussole BTC
    
    Args:
        symbol: Symbole de la crypto
        trade_side: 'BUY' ou 'SELL'
        signal_strength: Force du signal (0-1)
        
    Returns:
        Tuple (allowed: bool, reason: str)
    """
    return btc_compass.validate_trade_direction(symbol, trade_side, signal_strength)

def get_btc_compass_recommendation() -> Dict:
    """Retourne la recommandation actuelle de la boussole BTC"""
    return {
        'trend': btc_compass.btc_trend,
        'strength': btc_compass.btc_strength,
        'volatility': btc_compass.btc_volatility,
        'recommendation': btc_compass._get_recommendation(),
        'position_sizing_adj': btc_compass.get_position_sizing_adjustment(),
        'risk_adj': btc_compass.get_risk_adjustment()
    }


