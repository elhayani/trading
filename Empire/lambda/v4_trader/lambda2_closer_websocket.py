"""
🔌 Lambda Closer WebSocket - Empire V16.2
==========================================
Closer utilisant WebSocket Binance (remplace REST API)
Monitoring temps réel des positions
Latence: 50ms vs 800ms REST
"""

import json
import os
import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from websocket_manager import BinanceWebSocketManager
from trading_engine import TradingEngine
from config import TradingConfig

logger = logging.getLogger(__name__)

class WebSocketCloser:
    """Closer WebSocket pour monitoring positions"""
    
    def __init__(self):
        self.ws_manager = BinanceWebSocketManager(demo_mode=not TradingConfig.LIVE_MODE)
        self.trading_engine = TradingEngine()
        
        # Seuils TP/SL
        self.tp_threshold = 1.0  # 1% TP
        self.sl_threshold = -0.5  # -0.5% SL
        self.fast_exit_threshold = 0.3  # 0.3% pour fast exit
        
        # Stats
        self.positions_monitored = 0
        self.positions_closed = 0
        self.tp_hits = 0
        self.sl_hits = 0
        self.fast_exits = 0
        
        # Positions tracking
        self.active_positions = {}
        self.position_history = []
        
    async def monitor_positions(self, context) -> Dict:
        """Monitoring principal des positions via WebSocket"""
        start_time = time.time()
        
        try:
            logger.info("[WS_CLOSER_START] Starting position monitoring")
            
            # Connexion WebSocket positions et mark prices
            if not await self.ws_manager.subscribe_positions():
                return {
                    'status': 'ERROR',
                    'reason': 'WebSocket connection failed',
                    'duration': time.time() - start_time
                }
            
            # Timeout Lambda (15 minutes max - 30s marge)
            timeout = (context.get_remaining_time_in_millis() - 30000) / 1000
            
            # Boucle monitoring
            while time.time() - start_time < timeout:
                # Récupération mise à jour position
                position_update = await self.ws_manager.get_position_update()
                
                if position_update:
                    await self._process_position_update(position_update)
                
                # Stats toutes les 60 secondes
                if int(time.time()) % 60 == 0:
                    await self._log_stats()
                
                await asyncio.sleep(0.1)  # 100ms entre checks
            
            # Finalisation
            results = await self._finalize_monitoring()
            
            return {
                'status': 'SUCCESS',
                'duration': time.time() - start_time,
                'positions_monitored': self.positions_monitored,
                'positions_closed': self.positions_closed,
                'tp_hits': self.tp_hits,
                'sl_hits': self.sl_hits,
                'fast_exits': self.fast_exits,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"[WS_CLOSER_ERROR] {e}")
            return {
                'status': 'ERROR',
                'reason': str(e),
                'duration': time.time() - start_time
            }
        
        finally:
            await self.ws_manager.close()
    
    async def _process_position_update(self, position_update: Dict):
        """Traitement mise à jour position"""
        try:
            if position_update.get('type') == 'mark_prices':
                # Mise à jour mark prices
                await self._update_mark_prices(position_update['data'])
                return
            
            # Position individuelle
            symbol = position_update['symbol']
            position_amount = position_update['position_amount']
            
            # Ignorer positions sans montant
            if position_amount == 0:
                if symbol in self.active_positions:
                    # Position fermée
                    await self._handle_position_closed(symbol)
                return
            
            # Mise à jour position active
            self.active_positions[symbol] = {
                'symbol': symbol,
                'position_amount': position_amount,
                'entry_price': position_update['entry_price'],
                'mark_price': position_update['mark_price'],
                'unrealized_pnl': position_update['unrealized_pnl'],
                'percentage': position_update['percentage'],
                'last_update': time.time()
            }
            
            self.positions_monitored += 1
            
            # Check conditions de sortie
            await self._check_exit_conditions(symbol, self.active_positions[symbol])
            
        except Exception as e:
            logger.error(f"[WS_POSITION_ERROR] {e}")
    
    async def _update_mark_prices(self, mark_prices: List[Dict]):
        """Mise à jour mark prices pour toutes les positions"""
        try:
            for price_data in mark_prices:
                symbol = price_data['s']
                mark_price = float(price_data['p'])
                
                # Mise à jour mark price si position active
                if symbol in self.active_positions:
                    self.active_positions[symbol]['mark_price'] = mark_price
                    
                    # Recalcul PnL
                    position = self.active_positions[symbol]
                    entry_price = position['entry_price']
                    position_amount = position['position_amount']
                    
                    if position_amount > 0:  # LONG
                        pnl_pct = ((mark_price - entry_price) / entry_price) * 100
                    else:  # SHORT
                        pnl_pct = ((entry_price - mark_price) / entry_price) * 100
                    
                    position['percentage'] = pnl_pct
                    position['unrealized_pnl'] = (mark_price - entry_price) * abs(position_amount)
                    
                    # Check conditions après mise à jour
                    await self._check_exit_conditions(symbol, position)
            
        except Exception as e:
            logger.error(f"[WS_MARK_PRICE_ERROR] {e}")
    
    async def _check_exit_conditions(self, symbol: str, position: Dict):
        """Vérification conditions de sortie"""
        try:
            pnl_pct = position['percentage']
            entry_time = position.get('entry_time', time.time())
            time_open = time.time() - entry_time
            
            # 1. Take Profit
            if pnl_pct >= self.tp_threshold:
                await self._close_position(symbol, "TAKE_PROFIT", pnl_pct)
                self.tp_hits += 1
                return
            
            # 2. Stop Loss
            if pnl_pct <= self.sl_threshold:
                await self._close_position(symbol, "STOP_LOSS", pnl_pct)
                self.sl_hits += 1
                return
            
            # 3. Fast Exit (V16.1)
            if time_open > TradingConfig.FAST_EXIT_MINUTES * 60:
                if abs(pnl_pct) < TradingConfig.FAST_EXIT_PNL_THRESHOLD * 100:
                    await self._close_position(symbol, "FAST_EXIT", pnl_pct)
                    self.fast_exits += 1
                    return
            
            # 4. Max Hold Time
            if time_open > TradingConfig.MAX_HOLD_MINUTES * 60:
                await self._close_position(symbol, "MAX_HOLD", pnl_pct)
                return
            
        except Exception as e:
            logger.error(f"[WS_EXIT_CHECK_ERROR] {symbol}: {e}")
    
    async def _close_position(self, symbol: str, reason: str, pnl_pct: float):
        """Fermeture position via WebSocket"""
        try:
            if symbol not in self.active_positions:
                return
            
            position = self.active_positions[symbol]
            
            logger.info(f"[WS_CLOSE] {symbol}: {reason} (PnL: {pnl_pct:+.2f}%)")

            # Fermeture via REST (production-safe)
            side = 'SELL' if position['position_amount'] > 0 else 'BUY'
            quantity = abs(position['position_amount'])
            success = False
            try:
                res = self.trading_engine.exchange.create_market_order(symbol, side.lower(), quantity)
                success = bool(res)
            except Exception as e:
                logger.error(f"[WS_CLOSE_REST_ERROR] {symbol}: {e}")
            
            if success:
                self.positions_closed += 1
                
                # Historique
                self.position_history.append({
                    'symbol': symbol,
                    'reason': reason,
                    'pnl_pct': pnl_pct,
                    'entry_price': position['entry_price'],
                    'exit_price': position['mark_price'],
                    'duration': time.time() - position.get('entry_time', time.time()),
                    'timestamp': time.time()
                })
                
                # Suppression positions actives
                del self.active_positions[symbol]
                
                # Log dans DynamoDB
                await self._log_trade_close(symbol, reason, pnl_pct, position)
            
        except Exception as e:
            logger.error(f"[WS_CLOSE_ERROR] {symbol}: {e}")
    
    async def _handle_position_closed(self, symbol: str):
        """Gestion position fermée (externe)"""
        try:
            if symbol in self.active_positions:
                position = self.active_positions[symbol]
                pnl_pct = position['percentage']
                
                logger.info(f"[WS_EXTERNAL_CLOSE] {symbol}: Closed externally (PnL: {pnl_pct:+.2f}%)")
                
                # Historique
                self.position_history.append({
                    'symbol': symbol,
                    'reason': 'EXTERNAL_CLOSE',
                    'pnl_pct': pnl_pct,
                    'entry_price': position['entry_price'],
                    'exit_price': position['mark_price'],
                    'timestamp': time.time()
                })
                
                del self.active_positions[symbol]
                
        except Exception as e:
            logger.error(f"[WS_EXTERNAL_CLOSE_ERROR] {symbol}: {e}")
    
    async def _log_trade_close(self, symbol: str, reason: str, pnl_pct: float, position: Dict):
        """Log fermeture trade dans DynamoDB"""
        try:
            # Utiliser trading engine pour persistance
            await self.trading_engine.log_trade_close(
                symbol=symbol,
                reason=reason,
                pnl_pct=pnl_pct,
                entry_price=position['entry_price'],
                exit_price=position['mark_price'],
                quantity=abs(position['position_amount'])
            )
            
        except Exception as e:
            logger.error(f"[WS_LOG_CLOSE_ERROR] {symbol}: {e}")
    
    async def _log_stats(self):
        """Logs statistiques"""
        try:
            logger.info(f"[WS_CLOSER_STATS] Monitored: {self.positions_monitored}, "
                       f"Closed: {self.positions_closed}, "
                       f"TP: {self.tp_hits}, SL: {self.sl_hits}, FastExit: {self.fast_exits}")
            
            # Positions actives
            active_count = len(self.active_positions)
            if active_count > 0:
                total_pnl = sum(pos['percentage'] for pos in self.active_positions.values())
                avg_pnl = total_pnl / active_count
                logger.info(f"[WS_ACTIVE_POSITIONS] Count: {active_count}, Avg PnL: {avg_pnl:+.2f}%")
            
            # Stats WebSocket
            ws_stats = self.ws_manager.get_stats()
            logger.info(f"[WS_CONNECTION] Connected: {ws_stats['connected']}, "
                       f"Buffer: {ws_stats['buffer_size']}")
            
        except Exception as e:
            logger.error(f"[WS_STATS_ERROR] {e}")
    
    async def _finalize_monitoring(self) -> Dict:
        """Finalisation monitoring"""
        try:
            # Calcul performance
            if self.position_history:
                total_pnl = sum(trade['pnl_pct'] for trade in self.position_history)
                winning_trades = len([t for t in self.position_history if t['pnl_pct'] > 0])
                win_rate = (winning_trades / len(self.position_history)) * 100
            else:
                total_pnl = 0
                win_rate = 0
            
            return {
                'active_positions': len(self.active_positions),
                'total_closed': self.positions_closed,
                'total_pnl_pct': total_pnl,
                'win_rate': win_rate,
                'exit_reasons': {
                    'tp': self.tp_hits,
                    'sl': self.sl_hits,
                    'fast_exit': self.fast_exits,
                    'max_hold': self.positions_closed - self.tp_hits - self.sl_hits - self.fast_exits
                },
                'position_history': self.position_history[-10:],  # Derniers 10 trades
                'websocket_stats': self.ws_manager.get_stats()
            }
            
        except Exception as e:
            logger.error(f"[WS_FINALIZE_ERROR] {e}")
            return {}

# Lambda handler
async def lambda_handler(event, context):
    """Lambda handler WebSocket Closer"""
    
    # Configuration logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info(f"[WS_CLOSER_LAMBDA_START] Closer WebSocket V16.2")
    
    try:
        # Création closer
        closer = WebSocketCloser()
        
        # Lancement monitoring
        result = await closer.monitor_positions(context)
        
        # Log final
        logger.info(f"[WS_CLOSER_LAMBDA_END] Status: {result.get('status')}, "
                   f"Duration: {result.get('duration', 0):.2f}s")
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        logger.error(f"[WS_CLOSER_LAMBDA_ERROR] {e}")
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
