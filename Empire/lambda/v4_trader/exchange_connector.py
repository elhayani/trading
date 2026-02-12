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

    def __init__(self, api_key: str = None, secret: str = None, live_mode: bool = False):
        global _EXCHANGE_INSTANCE, _MARKETS_CACHE
        
        # Singleton pattern
        if _EXCHANGE_INSTANCE is None:
            logger.info(f"[COLD START] Initializing Binance Connector (Live={live_mode})")
            
            # Clean credentials
            api_key = api_key.strip() if api_key else os.getenv('BINANCE_API_KEY')
            secret = secret.strip() if secret else os.getenv('BINANCE_SECRET_KEY')

            # Initialize CCXT
            _EXCHANGE_INSTANCE = ccxt.binance({
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True,
                    'fetchConfig': False,
                    'warnOnFetchAccountInfo': False
                }
            })

            # FORCE 2: Disable SAPI/Spot calls (Audit #V11.6.7)
            _EXCHANGE_INSTANCE.has['fetchBalance'] = True
            # FORCE 2: Disable SAPI/Spot metadata calls (Audit #V11.6.7)
            _EXCHANGE_INSTANCE.has['fetchAccountStatus'] = False
            _EXCHANGE_INSTANCE.has['fetchBalance'] = True
            _EXCHANGE_INSTANCE.has['fetchMyTrades'] = True

            if not live_mode:
                logger.info("[INFO] Applying Elite Sniper Fix for Demo URLs (Audit #V11.6.7)")
                
                # Force sandbox mode first
                _EXCHANGE_INSTANCE.set_sandbox_mode(True)
                
                # Elite Sniper Fix - preserve path structure, replace only domains
                demo_domain = "demo-fapi.binance.com"
                
                for collection in ['test', 'api']:
                    if collection in _EXCHANGE_INSTANCE.urls:
                        for key in _EXCHANGE_INSTANCE.urls[collection]:
                            if isinstance(_EXCHANGE_INSTANCE.urls[collection][key], str):
                                url = _EXCHANGE_INSTANCE.urls[collection][key]
                                # Replace only problematic domains, preserve exact paths
                                url = url.replace("fapi.binance.com", demo_domain)
                                url = url.replace("testnet.binancefuture.com", demo_domain)
                                url = url.replace("api.binance.com", demo_domain)
                                # Clean double prefixes
                                url = url.replace("demo-fdemo-fapi.binance.com", demo_domain)
                                _EXCHANGE_INSTANCE.urls[collection][key] = url
                
                # Disable SAPI config check
                _EXCHANGE_INSTANCE.options['fetchConfig'] = False
            
            logger.info("[COLD START] Pre-loading markets...")
            _MARKETS_CACHE = _EXCHANGE_INSTANCE.load_markets()
            logger.info(f"[OK] {len(_MARKETS_CACHE)} markets cached")
        else:
            logger.info("[WARM START] Reusing existing CCXT instance")

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

    def resolve_symbol(self, symbol: str) -> str:
        """Resolves symbol to canonical CCXT format (Audit #V11.6.8)"""
        if symbol in self.markets:
            return symbol
        try:
            # CCXT internal mapping (e.g., BTCUSDT -> BTC/USDT)
            return self.exchange.market(symbol)['symbol']
        except:
            # Fallback for new symbols
            try:
                self.markets = self.exchange.load_markets()
                return self.exchange.market(symbol)['symbol']
            except:
                return symbol

    def get_market_info(self, symbol: str) -> Dict:
        """Utilise le cache au lieu de load_markets() (Audit #V11.5)"""
        target = self.resolve_symbol(symbol)
        
        if target not in self.markets:
             raise ValueError(f"Symbol {symbol} missing in markets")
        
        m = self.markets[target]
        return {
            'precision': m.get('precision', {}),
            'min_amount': m.get('limits', {}).get('amount', {}).get('min', 0),
            'symbol': target
        }

    def fetch_balance(self) -> Dict:
        """Mode-aware balance fetch (Audit #V11.6.4)"""
        try:
            # Check if we are in Demo mode by looking at the URL
            is_demo = "demo-fapi" in self.exchange.urls['api']['fapiPrivate']
            
            if not is_demo:
                # Standard CCXT fetch_balance for Live
                return self.exchange.fetch_balance()
            
            # Optimized for Futures Demo: Use versioned method to avoid SAPI/Spot calls
            res = self.exchange.fapiPrivateV2GetAccount()
            balance = {'total': {}, 'free': {}, 'info': res}
            for asset in res.get('assets', []):
                name = asset['asset']
                total = float(asset['walletBalance'])
                free = float(asset['availableBalance'])
                balance['total'][name] = total
                balance['free'][name] = free
                balance[name] = {'total': total, 'free': free}
            return balance
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

    def create_market_order(self, symbol: str, side: str, amount: float, leverage: int = 1) -> Dict:
        try:
            # Set leverage before placing order (Binance Futures requirement)
            try:
                self.exchange.set_leverage(leverage, symbol)
                logger.info(f"[LEVERAGE] Set to {leverage}x for {symbol}")
            except Exception as lev_err:
                logger.warning(f"[WARN] Could not set leverage: {lev_err}")
            
            logger.info(f"[INFO] Order: {side.upper()} {amount} {symbol} @ {leverage}x leverage")
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
