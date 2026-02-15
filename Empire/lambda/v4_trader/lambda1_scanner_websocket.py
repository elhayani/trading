"""
🔌 Lambda Scanner WebSocket - Empire V16.2
===========================================
Scanner utilisant WebSocket Binance (remplace REST API)
Latence: 50ms vs 800ms REST
Performance: 16x plus rapide
"""

import json
import os
import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from websocket_manager import BinanceWebSocketManager
from market_analysis import analyze_market
from decision_engine import DecisionEngine
from risk_manager import RiskManager
from trading_engine import TradingEngine
from config import TradingConfig

logger = logging.getLogger(__name__)

class WebSocketScanner:
    """Scanner WebSocket pour trading momentum"""
    
    def __init__(self):
        self.ws_manager = BinanceWebSocketManager(demo_mode=not TradingConfig.LIVE_MODE)
        self.decision_engine = DecisionEngine(RiskManager())
        self.trading_engine = TradingEngine()
        
        # Symboles à surveiller
        self.symbols = self._get_trading_symbols()
        self.momentum_scores = {}
        self.processed_symbols = set()
        
        # Stats
        self.messages_processed = 0
        self.signals_detected = 0
        self.trades_executed = 0
        
        # Caches pour indicateurs glissants (V16.2)
        self.ema_cache = {}    # {symbol: {'fast': [v1, v2], 'slow': [v1, v2]}}
        self.volume_cache = {} # {symbol: [vol1, vol2, ...]}
        
    def _get_trading_symbols(self) -> List[str]:
        """Récupération symboles pour trading"""
        # Symboles principaux pour POC
        return [
            'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
            'AVAXUSDT', 'LINKUSDT', 'DOGEUSDT', 'ADAUSDT', 'DOTUSDT',
            'PEPEUSDT', 'SHIBUSDT', 'MATICUSDT', 'UNIUSDT', 'ATOMUSDT'
        ]
    
    async def scan_with_websocket(self, context) -> Dict:
        """Scanner principal utilisant WebSocket"""
        start_time = time.time()
        
        try:
            logger.info(f"[WS_SCANNER_START] Scanning {len(self.symbols)} symbols")
            
            # Connexion WebSocket klines 1min
            streams = [f"{symbol.lower()}@kline_1m" for symbol in self.symbols]
            
            if not await self.ws_manager.connect(streams):
                return {
                    'status': 'ERROR',
                    'reason': 'WebSocket connection failed',
                    'duration': time.time() - start_time
                }
            
            # Timeout Lambda (15 minutes max - 30s marge)
            timeout = (context.get_remaining_time_in_millis() - 30000) / 1000
            
            # Boucle scanning
            while time.time() - start_time < timeout:
                # Récupération kline
                kline_data = await self.ws_manager.get_next_kline()
                
                if kline_data:
                    await self._process_kline(kline_data)
                    self.messages_processed += 1
                
                # Stats toutes les 30 secondes
                if int(time.time()) % 30 == 0:
                    await self._log_stats()
            
            # Finalisation
            results = await self._finalize_scan()
            
            return {
                'status': 'SUCCESS',
                'duration': time.time() - start_time,
                'messages_processed': self.messages_processed,
                'signals_detected': self.signals_detected,
                'trades_executed': self.trades_executed,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"[WS_SCANNER_ERROR] {e}")
            return {
                'status': 'ERROR',
                'reason': str(e),
                'duration': time.time() - start_time
            }
        
        finally:
            await self.ws_manager.close()
    
    async def _process_kline(self, kline_data: Dict):
        """Traitement kline WebSocket"""
        try:
            symbol = kline_data['symbol']
            
            # Éviter doublons
            if symbol in self.processed_symbols:
                return
            
            # Analyse momentum
            momentum_score = await self._calculate_momentum_score(kline_data)
            self.momentum_scores[symbol] = momentum_score
            
            # Signal détecté?
            if momentum_score >= TradingConfig.MIN_MOMENTUM_SCORE:
                self.signals_detected += 1
                await self._handle_signal(symbol, kline_data, momentum_score)
            
            self.processed_symbols.add(symbol)
            
        except Exception as e:
            logger.error(f"[WS_KLINE_ERROR] {e}")
    
    async def _calculate_momentum_score(self, kline_data: Dict) -> float:
        """Calcul score momentum WebSocket amélioré (EMA, Volume, ATR)"""
        try:
            symbol = kline_data['symbol']
            
            # 1. EMA Crossover Score (0-40 points)
            ema_score = self._calculate_ema_score(kline_data)
            
            # 2. Mouvement prix pur (0-30 points)
            price_move = self._calculate_price_momentum(kline_data)
            
            # 3. Volume surge RELATIF (0-30 points)
            volume_score = self._calculate_volume_score(kline_data)
            
            # 4. Filtre ATR (Anti-noise)
            if not self._passes_atr_filter(kline_data):
                return 0.0
            
            total_score = ema_score + price_move + volume_score
            
            return min(100, total_score)
            
        except Exception as e:
            logger.error(f"[WS_MOMENTUM_ERROR] {e}")
            return 0.0

    def _update_ema_cache(self, symbol: str, close: float) -> Tuple[float, float]:
        """Mise à jour des EMA glissantes (V16.2)"""
        if symbol not in self.ema_cache:
            # Initialisation avec le prix actuel
            self.ema_cache[symbol] = {
                'fast': [close],
                'slow': [close]
            }
            return close, close
        
        fast_history = self.ema_cache[symbol]['fast']
        slow_history = self.ema_cache[symbol]['slow']
        
        # Facteurs de lissage (Alpha)
        alpha_fast = 2 / (TradingConfig.EMA_FAST + 1)
        alpha_slow = 2 / (TradingConfig.EMA_SLOW + 1)
        
        # Calcul EMA exponentielle basé sur la dernière valeur connue
        ema_fast = (close * alpha_fast) + (fast_history[-1] * (1 - alpha_fast))
        ema_slow = (close * alpha_slow) + (slow_history[-1] * (1 - alpha_slow))
        
        # Ajout à l'historique et limitation de taille
        fast_history.append(ema_fast)
        slow_history.append(ema_slow)
        
        if len(fast_history) > 50:
            fast_history.pop(0)
            slow_history.pop(0)
            
        return ema_fast, ema_slow

    def _calculate_ema_score(self, kline: Dict) -> float:
        """Score basé sur le crossover d'EMA réel (V16.2)"""
        symbol = kline['symbol']
        close = kline['close']
        
        ema_fast, ema_slow = self._update_ema_cache(symbol, close)
        
        # 1. Crossover Bullish (EMA5 > EMA13 et prix > EMA5)
        if ema_fast > ema_slow and close > ema_fast:
            return 40.0
        # 2. Support dynamique (Prix > EMA5 mais pas encore de crossover large)
        elif close > ema_fast:
            return 20.0
            
        return 0.0
    
    def _calculate_price_momentum(self, ohlc: Dict) -> float:
        """Calcul momentum prix avec validation de tendance"""
        try:
            open_price = float(ohlc['open'])
            close_price = float(ohlc['close'])
            high_price = float(ohlc['high'])
            low_price = float(ohlc['low'])
            
            # Mouvement prix en %
            price_change = abs(close_price - open_price) / open_price
            
            # Range (volatilité interne à la bougie)
            range_pct = (high_price - low_price) / open_price
            
            # Validation: bougie pleine (pas juste une mèche)
            body_size = abs(close_price - open_price)
            candle_range = high_price - low_price
            body_ratio = body_size / candle_range if candle_range > 0 else 0
            
            if body_ratio < 0.5: # Trop de mèche, signal faible
                return 0.0
            
            # Score basé sur mouvement et amplitude
            momentum = (price_change * 3000) + (range_pct * 500)
            
            return min(30, momentum)
            
        except Exception:
            return 0.0
    
    def _calculate_volume_score(self, ohlc: Dict) -> float:
        """Calcul score volume relatif vs moyenne mobile (V16.2)"""
        try:
            symbol = ohlc['symbol']
            volume = float(ohlc['volume'])
            
            # Mise à jour du cache de volume
            if symbol not in self.volume_cache:
                self.volume_cache[symbol] = []
            
            self.volume_cache[symbol].append(volume)
            
            # Limiter à 20 périodes pour la moyenne
            if len(self.volume_cache[symbol]) > 20:
                self.volume_cache[symbol].pop(0)
            
            # Calcul du ratio par rapport à la moyenne
            if len(self.volume_cache[symbol]) >= 10:
                avg_vol = sum(self.volume_cache[symbol]) / len(self.volume_cache[symbol])
                ratio = volume / avg_vol if avg_vol > 0 else 1.0
                
                if ratio >= TradingConfig.VOLUME_SURGE_RATIO: # 1.5x
                    return 30.0
                elif ratio >= 1.2:
                    return 15.0
            
            return 0.0
                
        except Exception:
            return 0.0

    def _passes_atr_filter(self, ohlc: Dict) -> bool:
        """Filtre ATR pour éviter le bruit de marché (sideways)"""
        try:
            high = float(ohlc['high'])
            low = float(ohlc['low'])
            open_p = float(ohlc['open'])
            
            volatility = (high - low) / open_p
            # Seuil minimal de volatilité 1min (0.1% minimum)
            return volatility >= 0.001
        except Exception:
            return False
    
    async def _handle_signal(self, symbol: str, kline_data: Dict, score: float):
        """Traitement signal de trading"""
        try:
            logger.info(f"[WS_SIGNAL] {symbol}: Score {score:.1f}")
            
            # 🧭 BTC Compass Validation (Anti-piège)
            from btc_compass import validate_trade_with_btc_compass
            direction = 'BUY' if kline_data['close'] > kline_data['open'] else 'SELL'
            btc_allowed, btc_reason = validate_trade_with_btc_compass(symbol, direction, score / 100)
            
            if not btc_allowed:
                logger.warning(f"[BTC_COMPASS_BLOCK] {symbol}: {btc_reason}")
                return

            # Contexte pour décision
            context = {
                'symbol': symbol,
                'price': kline_data['close'],
                'volume': kline_data['volume'],
                'timestamp': kline_data['timestamp'],
                'score': score,
                'btc_compass': btc_reason
            }
            
            # Analyse technique
            ta_result = {
                'price': kline_data['close'],
                'volume': kline_data['volume'],
                'atr': self._estimate_atr(kline_data),
                'score': score,
                'momentum': 'BULLISH' if kline_data['close'] > kline_data['open'] else 'BEARISH'
            }
            
            # Décision trading
            decision = self.decision_engine.evaluate_with_risk(
                context=context,
                ta_result=ta_result,
                symbol=symbol,
                capital=10000,  # Capital par défaut
                direction='LONG' if kline_data['close'] > kline_data['open'] else 'SHORT'
            )
            
            # Exécution si signal validé
            if decision.get('proceed', False):
                await self._execute_trade(symbol, decision, kline_data)
            
        except Exception as e:
            logger.error(f"[WS_SIGNAL_ERROR] {symbol}: {e}")
    
    def _estimate_atr(self, kline_data: Dict) -> float:
        """Estimation ATR (simplifiée)"""
        try:
            high = kline_data['high']
            low = kline_data['low']
            close = kline_data['close']
            
            # True Range
            tr = max(high - low, abs(high - close), abs(low - close))
            
            # ATR estimé (en réalité utiliser 14 périodes)
            return tr * 0.01  # 1% du prix comme approximation
            
        except Exception:
            return 0.01
    
    async def _execute_trade(self, symbol: str, decision: Dict, kline_data: Dict):
        """Exécution trade via WebSocket"""
        try:
            quantity = decision.get('quantity', 0)
            side = decision.get('side', 'LONG')
            
            if quantity <= 0:
                return
            
            # Exécution via trading engine
            result = await self.trading_engine.execute_trade_websocket(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=kline_data['close']
            )
            
            if result:
                self.trades_executed += 1
                logger.info(f"[WS_EXECUTION] {symbol}: {side} {quantity} @ {kline_data['close']}")
            
        except Exception as e:
            logger.error(f"[WS_EXECUTION_ERROR] {symbol}: {e}")
    
    async def _log_stats(self):
        """Logs statistiques"""
        try:
            logger.info(f"[WS_STATS] Messages: {self.messages_processed}, "
                       f"Signals: {self.signals_detected}, "
                       f"Trades: {self.trades_executed}")
            
            # Stats WebSocket
            ws_stats = self.ws_manager.get_stats()
            logger.info(f"[WS_CONNECTION] Connected: {ws_stats['connected']}, "
                       f"Buffer: {ws_stats['buffer_size']}")
            
        except Exception as e:
            logger.error(f"[WS_STATS_ERROR] {e}")
    
    async def _finalize_scan(self) -> Dict:
        """Finalisation scan"""
        try:
            # Top 5 symboles par score
            top_symbols = sorted(
                self.momentum_scores.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            
            return {
                'total_symbols': len(self.symbols),
                'processed_symbols': len(self.processed_symbols),
                'top_symbols': top_symbols,
                'avg_score': sum(self.momentum_scores.values()) / len(self.momentum_scores) if self.momentum_scores else 0,
                'websocket_stats': self.ws_manager.get_stats()
            }
            
        except Exception as e:
            logger.error(f"[WS_FINALIZE_ERROR] {e}")
            return {}

# Lambda handler
async def lambda_handler(event, context):
    """Lambda handler WebSocket Scanner"""
    
    # Configuration logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info(f"[WS_LAMBDA_START] Scanner WebSocket V16.2")
    
    try:
        # Création scanner
        scanner = WebSocketScanner()
        
        # Lancement scan
        result = await scanner.scan_with_websocket(context)
        
        # Log final
        logger.info(f"[WS_LAMBDA_END] Status: {result.get('status')}, "
                   f"Duration: {result.get('duration', 0):.2f}s")
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        logger.error(f"[WS_LAMBDA_ERROR] {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'ERROR',
                'reason': str(e)
            })
        }

# Handler synchrone pour AWS Lambda
def lambda_handler_sync(event, context):
    """Handler synchrone compatible AWS Lambda"""
    return asyncio.run(lambda_handler(event, context))
