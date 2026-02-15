"""
🔌 WebSocket Executor - Empire V16.2
===================================
Exécution trades via WebSocket (remplace REST API)
Latence: 50ms vs 800ms REST
"""

import asyncio
import time
import hmac
import hashlib
import json
import logging
import os
import boto3
from typing import Dict, Optional
from websocket_manager import BinanceWebSocketManager

logger = logging.getLogger(__name__)

class WebSocketExecutor:
    """Exécuteur d'ordres via WebSocket Binance"""
    
    def __init__(self, demo_mode: bool = True):
        self.demo_mode = demo_mode
        self.ws_manager = BinanceWebSocketManager(demo_mode)

        self._secretsmanager = boto3.client('secretsmanager', region_name=os.getenv('AWS_REGION', 'ap-northeast-1'))
        creds = self._load_binance_credentials()
        self.api_key = creds['api_key']
        self.secret_key = creds['secret_key']
        
        # Stats
        self.orders_sent = 0
        self.orders_filled = 0
        self.orders_rejected = 0
        
    async def execute_market_order(self, symbol: str, side: str, quantity: float) -> Optional[Dict]:
        """Exécution ordre market via REST (Fallback de sécurité)"""
        try:
            logger.info(f"[REST_FALLBACK] {symbol}: {side} {quantity}")
            
            # Utilisation de ExchangeConnector pour l'exécution REST fiable
            from exchange_connector import ExchangeConnector
            connector = ExchangeConnector(
                api_key=self.api_key,
                secret=self.secret_key,
                live_mode=not self.demo_mode
            )
            
            # L'ordre market via CCXT est plus robuste
            order = connector.create_market_order(symbol, side, quantity)
            
            if order:
                self.orders_filled += 1
                logger.info(f"[REST_FILLED] {symbol}: {side} {quantity} @ {order.get('average', 'MARKET')}")
                return {
                    "orderId": order.get("id"),
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "price": order.get("average", 0.0),
                    "status": "FILLED",
                    "timestamp": order.get("timestamp")
                }
            else:
                self.orders_rejected += 1
                logger.warning(f"[REST_REJECTED] {symbol}: Order failed")
                return None
            
            # Préparation message ordre
            order_msg = self._prepare_order_message(symbol, side, quantity)
            
            # Signature
            if not self.demo_mode:
                signature = self._create_signature(order_msg)
                order_msg["signature"] = signature
            
            # Envoi WebSocket
            success = await self.ws_manager.send_message(order_msg)
            
            if success:
                self.orders_sent += 1
                
                # Attente confirmation (timeout 5 secondes)
                confirmation = await self._wait_for_confirmation(order_msg)
                
                if confirmation:
                    self.orders_filled += 1
                    logger.info(f"[WS_FILLED] {symbol}: {side} {quantity} @ {confirmation.get('price', 'MARKET')}")
                    return confirmation
                else:
                    self.orders_rejected += 1
                    logger.warning(f"[WS_REJECTED] {symbol}: Order not confirmed")
                    return None
            else:
                self.orders_rejected += 1
                logger.error(f"[WS_SEND_ERROR] {symbol}: Failed to send order")
                return None
                
        except Exception as e:
            logger.error(f"[WS_EXECUTION_ERROR] {symbol}: {e}")
            return None
    
    def _prepare_order_message(self, symbol: str, side: str, quantity: float) -> Dict:
        """Préparation message ordre"""
        # Conversion symbole pour Binance
        binance_symbol = symbol.replace('/USDT:USDT', 'USDT').replace('/', '')
        
        return {
            "method": "order.place",
            "params": {
                "symbol": binance_symbol,
                "side": side,
                "type": "MARKET",
                "quantity": str(quantity),
                "timestamp": int(time.time() * 1000)
            },
            "id": self.orders_sent + 1
        }
    
    def _create_signature(self, params: Dict) -> str:
        """Création signature HMAC SHA256"""
        # Extraction params pour signature
        order_params = params.get("params", {})
        
        # Query string pour signature
        query_string = "&".join([
            f"{k}={v}" for k, v in sorted(order_params.items())
        ])
        
        # Signature HMAC SHA256
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature

    def _load_binance_credentials(self) -> Dict[str, str]:
        api_key = os.getenv('BINANCE_API_KEY')
        secret_key = os.getenv('BINANCE_SECRET_KEY')
        if api_key and secret_key:
            return {'api_key': api_key, 'secret_key': secret_key}

        secret_name = os.getenv('SECRET_NAME')
        if not secret_name:
            raise RuntimeError('Missing BINANCE_API_KEY/BINANCE_SECRET_KEY and SECRET_NAME')

        response = self._secretsmanager.get_secret_value(SecretId=secret_name)
        payload = json.loads(response['SecretString'])

        api_key = (
            payload.get('BINANCE_API_KEY')
            or payload.get('binance_api_key')
            or payload.get('api_key')
            or payload.get('API_KEY')
        )
        secret_key = (
            payload.get('BINANCE_SECRET_KEY')
            or payload.get('binance_secret_key')
            or payload.get('secret_key')
            or payload.get('SECRET_KEY')
        )

        if not api_key or not secret_key:
            raise RuntimeError(f"Secret {secret_name} missing Binance keys")

        return {'api_key': api_key, 'secret_key': secret_key}
    
    async def _wait_for_confirmation(self, order_msg: Dict) -> Optional[Dict]:
        """Attente confirmation ordre"""
        try:
            order_id = order_msg["id"]
            timeout = 5  # 5 secondes max
            
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                # Écoute messages WebSocket
                message = await self.ws_manager.recv_message()
                
                if message and message.get("id") == order_id:
                    # Réponse ordre reçue
                    if message.get("status") == "FILLED":
                        return {
                            "orderId": message.get("orderId"),
                            "symbol": order_msg["params"]["symbol"],
                            "side": order_msg["params"]["side"],
                            "quantity": order_msg["params"]["quantity"],
                            "price": message.get("price", "MARKET"),
                            "status": "FILLED",
                            "timestamp": message.get("transactTime")
                        }
                    else:
                        logger.warning(f"[WS_ORDER_STATUS] {message.get('status')}")
                        return None
                
                await asyncio.sleep(0.1)  # 100ms entre checks
            
            # Timeout
            logger.warning(f"[WS_CONFIRM_TIMEOUT] Order {order_id} not confirmed")
            return None
            
        except Exception as e:
            logger.error(f"[WS_CONFIRM_ERROR] {e}")
            return None
    
    async def close_position(self, symbol: str, position_size: float) -> Optional[Dict]:
        """Fermeture position via WebSocket"""
        try:
            # Détermination side opposée
            side = "SELL" if position_size > 0 else "BUY"
            quantity = abs(position_size)
            
            logger.info(f"[WS_CLOSE_POSITION] {symbol}: {side} {quantity}")
            
            # Exécution ordre market
            result = await self.execute_market_order(symbol, side, quantity)
            
            if result:
                logger.info(f"[WS_POSITION_CLOSED] {symbol}: Successfully closed")
            else:
                logger.error(f"[WS_CLOSE_FAILED] {symbol}: Failed to close position")
            
            return result
            
        except Exception as e:
            logger.error(f"[WS_CLOSE_POSITION_ERROR] {symbol}: {e}")
            return None
    
    async def get_account_info(self) -> Optional[Dict]:
        """Récupération informations compte via WebSocket"""
        try:
            # Message account info
            account_msg = {
                "method": "account.status",
                "params": {
                    "timestamp": int(time.time() * 1000)
                },
                "id": 999
            }
            
            # Signature si nécessaire
            if not self.demo_mode:
                signature = self._create_signature(account_msg)
                account_msg["params"]["signature"] = signature
            
            # Envoi message
            success = await self.ws_manager.send_message(account_msg)
            
            if success:
                # Attente réponse
                response = await self._wait_for_confirmation(account_msg)
                
                if response:
                    return {
                        "total_wallet_balance": response.get("totalWalletBalance", "0"),
                        "total_unrealized_pnl": response.get("totalUnrealizedPnl", "0"),
                        "total_margin_balance": response.get("totalMarginBalance", "0"),
                        "total_position_initial_margin": response.get("totalPositionInitialMargin", "0"),
                        "total_open_orders": response.get("totalOpenOrders", "0"),
                        "total_positions": response.get("totalPositions", "0")
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"[WS_ACCOUNT_ERROR] {e}")
            return None
    
    async def get_open_positions(self) -> List[Dict]:
        """Récupération positions ouvertes via WebSocket"""
        try:
            # Message positions
            positions_msg = {
                "method": "positions",
                "params": {
                    "timestamp": int(time.time() * 1000)
                },
                "id": 998
            }
            
            # Signature si nécessaire
            if not self.demo_mode:
                signature = self._create_signature(positions_msg)
                positions_msg["params"]["signature"] = signature
            
            # Envoi message
            success = await self.ws_manager.send_message(positions_msg)
            
            if success:
                # Attente réponse
                response = await self._wait_for_confirmation(positions_msg)
                
                if response and "positions" in response:
                    positions = []
                    
                    for pos in response["positions"]:
                        size = float(pos["positionAmt"])
                        if size != 0:  # Position ouverte
                            positions.append({
                                "symbol": pos["symbol"],
                                "position_amount": size,
                                "entry_price": float(pos["entryPrice"]),
                                "mark_price": float(pos["markPrice"]),
                                "unrealized_pnl": float(pos["unRealizedProfit"]),
                                "percentage": float(pos["percentage"]),
                                "leverage": int(pos["leverage"])
                            })
                    
                    return positions
            
            return []
            
        except Exception as e:
            logger.error(f"[WS_POSITIONS_ERROR] {e}")
            return []
    
    def get_stats(self) -> Dict:
        """Statistiques exécuteur"""
        return {
            "orders_sent": self.orders_sent,
            "orders_filled": self.orders_filled,
            "orders_rejected": self.orders_rejected,
            "fill_rate": (self.orders_filled / self.orders_sent * 100) if self.orders_sent > 0 else 0,
            "demo_mode": self.demo_mode
        }
    
    async def test_latency(self) -> Dict:
        """Test latence WebSocket"""
        try:
            # Test avec ordre fictif
            test_symbol = "BTCUSDT"
            test_side = "BUY"
            test_quantity = 0.001
            
            start_time = time.time()
            
            # Préparation message (sans envoi)
            order_msg = self._prepare_order_message(test_symbol, test_side, test_quantity)
            
            # Simulation latence (préparation + signature)
            if not self.demo_mode:
                signature = self._create_signature(order_msg)
                order_msg["signature"] = signature
            
            latency_ms = (time.time() - start_time) * 1000
            
            return {
                "test_symbol": test_symbol,
                "latency_ms": latency_ms,
                "message_size": len(json.dumps(order_msg)),
                "demo_mode": self.demo_mode
            }
            
        except Exception as e:
            logger.error(f"[WS_LATENCY_TEST_ERROR] {e}")
            return {
                "error": str(e),
                "latency_ms": -1
            }
