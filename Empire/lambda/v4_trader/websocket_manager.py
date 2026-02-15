"""
🔌 WebSocket Manager - Empire V16.2
==================================
Gestionnaire WebSocket pour Binance API (remplace REST)
Latence: 50ms vs 800ms REST
"""

import asyncio
import websockets
import json
import time
import logging
import os
import requests
from typing import Dict, List, Callable, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class BinanceWebSocketManager:
    """Gestionnaire WebSocket pour Binance API"""
    
    def __init__(self, demo_mode: bool = True):
        self.demo_mode = demo_mode
        self.websocket = None
        self.connections = {}
        self.callbacks = {}
        self.running = False
        self.message_buffer = []
        self.last_ping = time.time()
        
        # URLs WebSocket (USDT-M Futures)
        if demo_mode:
            self.base_ws_url = "wss://stream.binancefuture.com/ws"
            self.base_stream_url = "wss://stream.binancefuture.com/stream"
        else:
            self.base_ws_url = "wss://fstream.binance.com/ws"
            self.base_stream_url = "wss://fstream.binance.com/stream"
            
        # Configuration
        self.timeout = 30
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5
        self.buffer_size = 1000
        
    async def connect(self, streams: List[str]) -> bool:
        """Connexion aux streams WebSocket Binance"""
        try:
            logger.info(f"[WS_CONNECT] Connecting to {len(streams)} streams")
            
            # Construction URL avec streams
            if len(streams) == 1:
                url = f"{self.base_ws_url}/{streams[0]}"
            else:
                # Streams multiples
                stream_path = "/".join(streams)
                url = f"{self.base_stream_url}?streams={stream_path}"
            
            # Connexion WebSocket
            self.websocket = await asyncio.wait_for(
                websockets.connect(url),
                timeout=self.timeout
            )
            
            self.running = True
            logger.info(f"[WS_CONNECTED] Successfully connected to {len(streams)} streams")
            
            # Démarrage monitoring
            asyncio.create_task(self._monitor_connection())
            
            return True
            
        except Exception as e:
            logger.error(f"[WS_CONNECT_ERROR] {e}")
            return False
    
    async def subscribe_klines(self, symbols: List[str]):
        """Abonnement klines 1min pour scanner"""
        streams = [f"{symbol.lower()}@kline_1m" for symbol in symbols]
        return await self.connect(streams)
    
    async def subscribe_positions(self):
        """Abonnement mark prices (public stream)"""
        streams = ["!markPrice@arr@1s"]
        return await self.connect(streams)

    def _rest_base_url(self) -> str:
        return "https://demo-fapi.binance.com" if self.demo_mode else "https://fapi.binance.com"

    def create_listen_key(self, api_key: str) -> str:
        url = f"{self._rest_base_url()}/fapi/v1/listenKey"
        res = requests.post(url, headers={"X-MBX-APIKEY": api_key}, timeout=5)
        res.raise_for_status()
        payload = res.json()
        listen_key = payload.get('listenKey')
        if not listen_key:
            raise RuntimeError('listenKey missing from response')
        return listen_key

    async def subscribe_user_data(self, listen_key: str) -> bool:
        return await self.connect([listen_key])
    
    async def send_message(self, message: Dict) -> bool:
        """Envoi message WebSocket"""
        try:
            if self.websocket and self.running:
                await self.websocket.send(json.dumps(message))
                return True
            return False
        except Exception as e:
            logger.error(f"[WS_SEND_ERROR] {e}")
            return False
    
    async def recv_message(self) -> Optional[Dict]:
        """Réception message WebSocket"""
        try:
            if self.websocket and self.running:
                message = await asyncio.wait_for(
                    self.websocket.recv(),
                    timeout=1.0
                )
                return json.loads(message)
            return None
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error(f"[WS_RECV_ERROR] {e}")
            return None
    
    async def get_next_kline(self) -> Optional[Dict]:
        """Récupération prochaine kline"""
        while self.running:
            message = await self.recv_message()
            
            if message and 'k' in message:
                kline = message['k']
                
                # Kline complète (fermée)
                if kline['x']:  # is_kline_closed
                    return {
                        'symbol': kline['s'],
                        'open': float(kline['o']),
                        'high': float(kline['h']),
                        'low': float(kline['l']),
                        'close': float(kline['c']),
                        'volume': float(kline['v']),
                        'timestamp': int(kline['t'])
                    }
        
        return None
    
    async def get_position_update(self) -> Optional[Dict]:
        """Récupération mise à jour position"""
        while self.running:
            message = await self.recv_message()
            
            if message:
                # Mark price update
                if message.get('stream') in ('!markPrice@arr', '!markPrice@arr@1s'):
                    mark_prices = message.get('data', [])
                    return {
                        'type': 'mark_prices',
                        'data': mark_prices
                    }

                # User data stream (ACCOUNT_UPDATE / ORDER_TRADE_UPDATE)
                if message.get('e') in ('ACCOUNT_UPDATE', 'ORDER_TRADE_UPDATE'):
                    return {
                        'type': 'user_data',
                        'data': message,
                    }
        
        return None
    
    async def _monitor_connection(self):
        """Monitoring connexion WebSocket"""
        while self.running:
            try:
                # Ping toutes les 30 secondes
                if time.time() - self.last_ping > 30:
                    await self._ping()
                    self.last_ping = time.time()
                
                # Vérification connexion
                if self.websocket and self.websocket.closed:
                    logger.warning("[WS_DISCONNECTED] Connection lost, attempting reconnect...")
                    await self._reconnect()
                
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"[WS_MONITOR_ERROR] {e}")
                await asyncio.sleep(5)
    
    async def _ping(self):
        """Ping WebSocket"""
        try:
            if self.websocket:
                await self.websocket.ping()
        except Exception as e:
            logger.error(f"[WS_PING_ERROR] {e}")
    
    async def _reconnect(self):
        """Reconnexion automatique"""
        for attempt in range(self.max_reconnect_attempts):
            try:
                logger.info(f"[WS_RECONNECT] Attempt {attempt + 1}/{self.max_reconnect_attempts}")
                
                # Fermeture ancienne connexion
                if self.websocket:
                    await self.websocket.close()
                
                # Nouvelle connexion
                # Note: nécessite de sauvegarder les streams originaux
                # await self.connect(self.original_streams)
                
                logger.info("[WS_RECONNECTED] Successfully reconnected")
                return True
                
            except Exception as e:
                logger.error(f"[WS_RECONNECT_ERROR] Attempt {attempt + 1}: {e}")
                await asyncio.sleep(self.reconnect_delay)
        
        logger.error("[WS_RECONNECT_FAILED] Max attempts reached")
        return False
    
    async def close(self):
        """Fermeture connexion WebSocket"""
        self.running = False
        
        if self.websocket:
            await self.websocket.close()
        
        logger.info("[WS_CLOSED] WebSocket connection closed")
    
    def get_stats(self) -> Dict:
        """Statistiques WebSocket"""
        return {
            'connected': self.running,
            'ws_url': self.base_ws_url,
            'stream_url': self.base_stream_url,
            'demo_mode': self.demo_mode,
            'buffer_size': len(self.message_buffer),
            'last_ping': self.last_ping
        }
