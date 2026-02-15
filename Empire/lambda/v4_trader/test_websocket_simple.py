"""
🔌 Test WebSocket Simple - Empire V16.2
=======================================
Test basique WebSocket sans dépendances lourdes
"""

import json
import os
import time
import asyncio
import logging
from datetime import datetime, timezone

# Test simple sans pandas
try:
    import websockets
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False

logger = logging.getLogger(__name__)

class SimpleWebSocketTest:
    """Test simple WebSocket Binance"""
    
    def __init__(self):
        self.demo_mode = True
        self.base_url = "wss://demo-stream.binance.com:9443/ws" if self.demo_mode else "wss://stream.binance.com:9443/ws"
        
    async def test_connection(self) -> dict:
        """Test connexion WebSocket basique"""
        try:
            if not WEBSOCKET_AVAILABLE:
                return {
                    'status': 'ERROR',
                    'reason': 'WebSockets not available',
                    'websockets_installed': False
                }
            
            logger.info(f"[WS_TEST] Connecting to {self.base_url}")
            
            # Test connexion simple
            async with websockets.connect(self.base_url) as websocket:
                logger.info("[WS_TEST] Connected successfully!")
                
                # Test abonnement BTC ticker
                subscribe_msg = {
                    "method": "SUBSCRIBE",
                    "params": ["btcusdt@ticker"],
                    "id": 1
                }
                
                await websocket.send(json.dumps(subscribe_msg))
                logger.info("[WS_TEST] Subscribed to BTCUSDT ticker")
                
                # Attente message (timeout 10 secondes)
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10)
                    data = json.loads(message)
                    
                    logger.info(f"[WS_TEST] Received message: {data}")
                    
                    return {
                        'status': 'SUCCESS',
                        'message': 'WebSocket connection successful',
                        'received_data': data,
                        'latency_ms': 50,  # Estimation
                        'websockets_installed': True
                    }
                    
                except asyncio.TimeoutError:
                    return {
                        'status': 'TIMEOUT',
                        'reason': 'No message received within 10 seconds',
                        'websockets_installed': True
                    }
            
        except Exception as e:
            logger.error(f"[WS_TEST_ERROR] {e}")
            return {
                'status': 'ERROR',
                'reason': str(e),
                'websockets_installed': WEBSOCKET_AVAILABLE
            }

# Lambda handler simple
async def lambda_handler(event, context):
    """Lambda handler test WebSocket"""
    
    # Configuration logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("[WS_LAMBDA_START] Simple WebSocket Test V16.2")
    
    try:
        # Création test
        test = SimpleWebSocketTest()
        
        # Lancement test
        result = await test.test_connection()
        
        # Log final
        logger.info(f"[WS_LAMBDA_END] Status: {result.get('status')}")
        
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

# Handler synchrone
def lambda_handler_sync(event, context):
    """Handler synchrone compatible AWS Lambda"""
    return asyncio.run(lambda_handler(event, context))
