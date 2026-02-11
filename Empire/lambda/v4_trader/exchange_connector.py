import ccxt
import logging
import os
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# --- WARM CACHE (Global Scope for Lambda reuse) ---
_EXCHANGE_INSTANCE = None
_MARKETS_CACHE = None

class ExchangeConnector:
    """
    Unified connector for CCXT. Optimized with Singleton & Markets Cache.
    (Audit #V11.5)
    """

    def __init__(self, exchange_id: str = 'binance', testnet: bool = True, api_key: str = None, secret: str = None):
        global _EXCHANGE_INSTANCE, _MARKETS_CACHE
        
        self.exchange_id = exchange_id
        self.testnet = testnet
        
        # Singleton pattern
        if _EXCHANGE_INSTANCE is None:
            logger.info("[COLD START] Initializing CCXT exchange...")
            
            api_key = api_key or os.getenv('BINANCE_API_KEY')
            secret = secret or os.getenv('BINANCE_SECRET_KEY')

            exchange_class = getattr(ccxt, exchange_id)
            _EXCHANGE_INSTANCE = exchange_class({
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future' if exchange_id == 'binance' else 'spot'
                }
            })

            if testnet:
                _EXCHANGE_INSTANCE.set_sandbox_mode(True)
                # Verification performed on COLD START
                self._verify_testnet_mode(_EXCHANGE_INSTANCE)
                
            logger.info("[COLD START] Pre-loading markets...")
            _MARKETS_CACHE = _EXCHANGE_INSTANCE.load_markets()
            logger.info(f"[OK] {len(_MARKETS_CACHE)} markets cached")
        else:
            logger.info("[WARM START] Reusing existing CCXT instance and markets cache")

        self.exchange = _EXCHANGE_INSTANCE
        self.markets = _MARKETS_CACHE

    def _verify_testnet_mode(self, exchange):
        """Robust Testnet verification."""
        try:
            urls = str(exchange.urls['api'])
            safe_patterns = ['testnet', 'sandbox', 'demo', 'test', 'staging']
            live_patterns = ['api.binance.com', 'fapi.binance.com', 'api.binance.us']
            
            if any(p in urls.lower() for p in live_patterns) and not any(p in urls.lower() for p in safe_patterns):
                logger.error(f"[ERROR] CRITICAL: Testnet enabled but URLs are LIVE: {urls}")
                raise RuntimeError("Security Block: Live API detected in Testnet mode")
            
            if exchange.apiKey:
                balance = exchange.fetch_balance()
                total_usdt = float(balance.get('USDT', {}).get('total', 0))
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
            logger.error(f"[ERROR] Failed to fetch OHLCV for {symbol}: {e}")
            raise

    def fetch_ticker(self, symbol: str) -> Dict:
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"[ERROR] Failed to fetch ticker for {symbol}: {e}")
            raise

    def get_market_info(self, symbol: str) -> Dict:
        """Utilise le cache au lieu de load_markets() (Audit #V11.5)"""
        if symbol not in self.markets:
            # Re-fetch if symbol is new, but generally it's in the cache
            self.markets = self.exchange.load_markets()
            if symbol not in self.markets:
                raise ValueError(f"Symbol {symbol} missing in markets")
        
        m = self.markets[symbol]
        return {
            'precision': m.get('precision', {}),
            'min_amount': m.get('limits', {}).get('amount', {}).get('min', 0),
        }

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
            return self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side.lower(),
                amount=amount,
                params={'reduceOnly': True} if side.lower() == 'close' else {}
            )
        except Exception as e:
            logger.error(f"[ERROR] Order execution failed: {e}")
            raise
