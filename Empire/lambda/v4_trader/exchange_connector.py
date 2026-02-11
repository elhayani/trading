import ccxt
import logging
import os
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ExchangeConnector:
    """
    Unified connector for CCXT. Robust Testnet and Error Handling.
    """

    def __init__(self, exchange_id: str = 'binance', testnet: bool = True, api_key: str = None, secret: str = None):
        self.exchange_id = exchange_id
        self.testnet = testnet
        
        api_key = api_key or os.getenv('BINANCE_API_KEY')
        secret = secret or os.getenv('BINANCE_SECRET_KEY')

        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future' if exchange_id == 'binance' else 'spot'
            }
        })

        if testnet:
            self.exchange.set_sandbox_mode(True)
            self._verify_testnet_mode()

    def _verify_testnet_mode(self):
        """
        Critique #7: Robust Testnet verification.
        Checks for URL patterns and account state.
        """
        try:
            urls = str(self.exchange.urls['api'])
            safe_patterns = ['testnet', 'sandbox', 'demo', 'test', 'staging']
            live_patterns = ['api.binance.com', 'fapi.binance.com', 'api.binance.us']
            
            # Fatal block if LIVE URL is detected
            if any(p in urls.lower() for p in live_patterns) and not any(p in urls.lower() for p in safe_patterns):
                logger.error(f"[ERROR] CRITICAL: Testnet enabled but URLs are LIVE: {urls}")
                raise RuntimeError("Security Block: Live API detected in Testnet mode")
            
            # Check balance if keys available
            if self.exchange.apiKey:
                balance = self.exchange.fetch_balance()
                total_usdt = float(balance.get('USDT', {}).get('total', 0))
                
                # Testnet balances are usually suspiciously round or huge
                if total_usdt > 1000 and total_usdt % 1000 == 0:
                    logger.info(f"[OK] Testnet verification: Balance ${total_usdt:,.0f} matches patterns.")
                else:
                    logger.warning(f"[WARN] Testnet verification: Account balance ${total_usdt:,.2f} is non-standard.")
                    
        except Exception as e:
            if not os.getenv('EMPIRE_IGNORE_TESTNET_ERROR'):
                logger.error(f"[ERROR] Testnet verification failed: {e}")
                raise

    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 500) -> List:
        try:
            return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            logger.error(f"[ERROR] Failed to fetch OHLCV: {e}")
            raise

    def fetch_ticker(self, symbol: str) -> Dict:
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"[ERROR] Failed to fetch ticker for {symbol}: {e}")
            raise

    def get_market_info(self, symbol: str) -> Dict:
        try:
            markets = self.exchange.load_markets()
            if symbol not in markets: raise ValueError(f"Symbol {symbol} missing")
            m = markets[symbol]
            return {
                'precision': m.get('precision', {}),
                'min_amount': m.get('limits', {}).get('amount', {}).get('min', 0),
            }
        except Exception as e:
            logger.error(f"[ERROR] Market info failed: {e}")
            raise

    def fetch_balance(self) -> Dict:
        try: return self.exchange.fetch_balance()
        except Exception as e:
            logger.error(f"[ERROR] Balance fetch failed: {e}")
            raise

    def get_balance_usdt(self) -> float:
        try:
            balance = self.fetch_balance()
            total = balance.get('USDT', {}).get('free', 0.0)
            if total == 0.0: total = balance.get('total', {}).get('USDT', 0.0)
            return float(total)
        except Exception as e:
            logger.error(f"[ERROR] USDT balance fetch failed: {e}")
            raise

    def create_market_order(self, symbol: str, side: str, amount: float) -> Dict:
        try:
            logger.info(f"[INFO] Order: {side.upper()} {amount} {symbol}")
            return self.exchange.create_market_order(symbol, side.lower(), amount)
        except Exception as e:
            logger.error(f"[ERROR] Order execution failed: {e}")
            raise
