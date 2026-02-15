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
        
        # 🆕 FORCE RESET en mode demo
        if not live_mode:
            _EXCHANGE_INSTANCE = None
            _MARKETS_CACHE = None
            logger.info("[DEMO] Forcing fresh CCXT instance for demo mode")
        
        # Singleton pattern
        if _EXCHANGE_INSTANCE is None:
            logger.info(f"[COLD START] Initializing Binance Connector (Live={live_mode})")
            
            # Clean credentials
            api_key = api_key.strip() if api_key else os.getenv('BINANCE_API_KEY')
            secret = secret.strip() if secret else os.getenv('BINANCE_SECRET_KEY')

            # Configure CCXT - Use specialized USDM class for Futures
            _EXCHANGE_INSTANCE = ccxt.binanceusdm({
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'options': {
                    'adjustForTimeDifference': True,
                    'fetchConfig': False,  # Disable SAPI config calls
                }
            })
            
            # Disable ALL API calls in demo mode (not available)
            if not live_mode:
                _EXCHANGE_INSTANCE.has['fetchBalance'] = False
                _EXCHANGE_INSTANCE.has['fetchAccountStatus'] = False
                _EXCHANGE_INSTANCE.has['fetchMyTrades'] = False
                _EXCHANGE_INSTANCE.has['fetchMarkets'] = False
                _EXCHANGE_INSTANCE.has['fetchTicker'] = True 
                _EXCHANGE_INSTANCE.has['loadMarkets'] = False
                # Désactiver aussi les appels internes qui causent le 404
                _EXCHANGE_INSTANCE.has['fetchCurrencies'] = False
                _EXCHANGE_INSTANCE.has['fetchTradingLimits'] = False
            else:
                _EXCHANGE_INSTANCE.has['fetchBalance'] = True
                _EXCHANGE_INSTANCE.has['fetchAccountStatus'] = False
                _EXCHANGE_INSTANCE.has['fetchMyTrades'] = True
            
            # FORCE DEMO ENDPOINTS (COMPLET)
            # 🆕 FORCE DEMO ENDPOINTS (COMPLET)
            if not live_mode:
                # 🏛️ EMPIRE V16: Use explicit Demo Training endpoints
                # Note: CCXT set_sandbox_mode is deprecated for Binance Futures
                demo_fapi = "https://demo-fapi.binance.com"
                
                # IMPORTANT: Hostname must match for signature validation
                _EXCHANGE_INSTANCE.hostname = "demo-fapi.binance.com"
                
                # Replace all relevant URLs in the instance
                if hasattr(_EXCHANGE_INSTANCE, 'urls'):
                    # FAPI endpoints (Private & Public) - All versions
                    for v in ['fapiPublic', 'fapiPublicV2', 'fapiPublicV3', 'fapiPrivate', 'fapiPrivateV2', 'fapiPrivateV3']:
                        if v in _EXCHANGE_INSTANCE.urls['api']:
                            version = 'v1'
                            if 'V2' in v: version = 'v2'
                            elif 'V3' in v: version = 'v3'
                            _EXCHANGE_INSTANCE.urls['api'][v] = f"{demo_fapi}/fapi/{version}"
                    
                    # Spot / SAPI endpoints (Redirect to demo-api)
                    demo_api = "https://demo-api.binance.com/api"
                    demo_sapi = "https://demo-api.binance.com/sapi"
                    _EXCHANGE_INSTANCE.urls['api']['public'] = f"{demo_api}/v3"
                    _EXCHANGE_INSTANCE.urls['api']['private'] = f"{demo_api}/v3"
                    _EXCHANGE_INSTANCE.urls['api']['v1'] = f"{demo_api}/v1"
                    _EXCHANGE_INSTANCE.urls['api']['sapi'] = f"{demo_sapi}/v1"
                    _EXCHANGE_INSTANCE.urls['api']['sapiV2'] = f"{demo_sapi}/v2"
                    _EXCHANGE_INSTANCE.urls['api']['sapiV3'] = f"{demo_sapi}/v3"
                
                    # Point SAPI to FAPI to trick CCXT into not complaining about missing sandbox URLs
                    # even if it tries to call them
                    _EXCHANGE_INSTANCE.urls['api']['sapi'] = f"{demo_fapi}/fapi/v1"
                    _EXCHANGE_INSTANCE.urls['api']['sapiV2'] = f"{demo_fapi}/fapi/v1"
                    _EXCHANGE_INSTANCE.urls['api']['sapiV3'] = f"{demo_fapi}/fapi/v1"
                
                # Disable selective features that trigger live SAPI
                _EXCHANGE_INSTANCE.options['fetchConfig'] = False
                _EXCHANGE_INSTANCE.options['warnOnFetchConfigFailure'] = False
                
                logger.info(f"[DEMO] Manual overrides applied for {demo_fapi}")
            
            # Warm cache (skip in demo mode to avoid 403 errors)
            if not live_mode:
                logger.info("[DEMO] Skipping market load (demo endpoints limited)")
                _MARKETS_CACHE = {}
            else:
                try:
                    _MARKETS_CACHE = _EXCHANGE_INSTANCE.load_markets()
                    logger.info(f"[OK] Markets loaded: {len(_MARKETS_CACHE)} symbols")
                except Exception as e:
                    logger.warning(f"[WARN] Market load failed: {e}")
        else:
            logger.info("[WARM START] Reusing existing CCXT instance")

        self.exchange = _EXCHANGE_INSTANCE
        self.markets = _MARKETS_CACHE
        self.live_mode = live_mode

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

    def fetch_positions(self, symbols: Optional[List[str]] = None) -> List:
        try:
            return self.exchange.fetch_positions(symbols)
        except Exception as e:
            logger.error(f"[ERROR] Failed to fetch positions: {e}")
            raise

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

    def create_market_order(self, symbol: str, side: str, amount: float, leverage: Optional[int] = None) -> Dict:
        try:
            # 🏛️ EMPIRE V14.2: Strict Leverage & Margin Enforcement
            # Skip leverage if closing or not provided
            is_closing = side.lower() == 'close' or leverage is None
            
            if not is_closing:
                # 1. Enforce ISOLATED Margin (Safe Mode)
                try:
                    self.exchange.set_margin_mode('ISOLATED', symbol)
                except Exception:
                    pass

                # 2. Enforce Leverage (Critical) 
                try:
                    self.exchange.set_leverage(leverage, symbol)
                    logger.info(f"[LEVERAGE] Set to {leverage}x for {symbol}")
                except Exception as lev_err:
                    # Ignore if reduction not supported while open (often means already set)
                    if "code\":-4161" in str(lev_err) or "Leverage reduction is not supported" in str(lev_err):
                        logger.warning(f"[LEVERAGE] Reduction blocked for {symbol} (likely already open), proceeding.")
                    else:
                        logger.error(f"[CRITICAL] Failed to set leverage {leverage}x for {symbol}: {lev_err}")
                        raise ValueError(f"Leverage failure: {lev_err}")
            
            logger.info(f"[INFO] Order: {side.upper()} {amount} {symbol}")
            
            # 🏛️ EMPIRE V16: Direct API Fallback for Demo Mode (CCXT SAPI issue)
            if not self.live_mode:
                try:
                    import requests, time, hmac, hashlib
                    base_url = "https://demo-fapi.binance.com/fapi/v1/order"
                    ts = int(time.time() * 1000)
                    clean_symbol = symbol.replace('/', '').split(':')[0]
                    side_val = 'SELL' if side.lower() == 'sell' or side.lower() == 'close' else 'BUY'
                    # Side adjustment: If side is 'close' but quantity > 0, we need to know the original side.
                    # Standard logic: if side is 'sell', it's a SELL order.
                    
                    params = f"symbol={clean_symbol}&side={side_val}&type=MARKET&quantity={amount}&timestamp={ts}"
                    if is_closing:
                        params += "&reduceOnly=true"
                    
                    signature = hmac.new(self.exchange.secret.encode('utf-8'), params.encode('utf-8'), hashlib.sha256).hexdigest()
                    headers = {'X-MBX-APIKEY': self.exchange.apiKey}
                    
                    logger.info(f"[DEMO] Executing direct signed order for {clean_symbol}")
                    resp = requests.post(f"{base_url}?{params}&signature={signature}", headers=headers)
                    
                    if resp.status_code == 200:
                        return resp.json()
                    else:
                        logger.error(f"[DEMO] Direct order failed ({resp.status_code}): {resp.text}")
                except Exception as direct_err:
                    logger.error(f"[DEMO] Direct fallback error: {direct_err}")

            return self.exchange.create_order(
                symbol=symbol,
                type='market',
                side='sell' if side.lower() == 'sell' else 'buy',
                amount=amount,
                params={'reduceOnly': True} if is_closing else {}
            )
        except Exception as e:
            logger.error(f"[ERROR] Order execution failed: {e}")
            raise

    def close_position(self, symbol: str, side: str, quantity: float) -> Dict:
        """
        Close position with market order - API DIRECT (no CCXT)
        """
        try:
            # 🏛️ EMPIRE V16: API DIRECT pour contourner CCXT
            import requests, time, hmac, hashlib
            
            # Nettoyer le symbole pour Binance
            clean_symbol = symbol.replace('/', '').replace(':USDT', '')
            side_val = 'SELL' if side.lower() in ['sell', 'close'] else 'BUY'
            
            # Timestamp et signature
            ts = int(time.time() * 1000)
            params = f"symbol={clean_symbol}&side={side_val}&type=MARKET&quantity={quantity}&timestamp={ts}&reduceOnly=true"
            signature = hmac.new(self.exchange.secret.encode('utf-8'), params.encode('utf-8'), hashlib.sha256).hexdigest()
            
            # URL selon mode
            if self.live_mode:
                url = f"https://fapi.binance.com/fapi/v1/order?{params}&signature={signature}"
            else:
                url = f"https://demo-fapi.binance.com/fapi/v1/order?{params}&signature={signature}"
            
            headers = {'X-MBX-APIKEY': self.exchange.apiKey}
            
            logger.info(f"[DIRECT] Closing {clean_symbol} {side_val} {quantity}")
            response = requests.post(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Position closed via API: {clean_symbol}")
                return result
            else:
                logger.error(f"❌ API Order failed ({response.status_code}): {response.text}")
                raise Exception(f"API Error: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Direct API execution failed: {e}")
            raise

    def create_sl_tp_orders(self, symbol: str, side: str, amount: float, stop_loss: float, take_profit: float) -> Dict:
        """ EMPIRE V13.9: Create GTC Sniper orders (LIMIT for TP, STOP_MARKET for SL)"""
        results = {}
        close_side = 'sell' if side.lower() == 'buy' else 'buy'
        
        try:
            # 1. Stop Loss (STOP_MARKET) - Hardware Security
            sl_order = self.exchange.create_order(
                symbol=symbol,
                type='STOP_MARKET',
                side=close_side,
                amount=amount,
                params={
                    'stopPrice': stop_loss,
                    'reduceOnly': True,
                    'workingType': 'MARK_PRICE' # EMPIRE V16: Safety against wicks
                }
            )
            results['sl'] = sl_order
            logger.info(f"[GTC_SL] STOP_MARKET at ${stop_loss} ({close_side.upper()} {amount})")
            
            # 2. Take Profit (LIMIT) - Maximum Profit Guarantee
            tp_order = self.exchange.create_order(
                symbol=symbol,
                type='LIMIT',
                side=close_side,
                amount=amount,
                price=take_profit,
                params={
                    'reduceOnly': True,
                    'timeInForce': 'GTC'
                }
            )
            results['tp'] = tp_order
            logger.info(f"[GTC_TP] LIMIT at ${take_profit} ({close_side.upper()} {amount})")
            
        except Exception as e:
            logger.warning(f"[WARN] V13.9 Sniper orders failed: {e}")
            
        return results

    def create_ladder_exit_orders(self, symbol: str, side: str, total_amount: float, stop_loss: float, 
                                tp1_price: float, tp1_amount: float, 
                                tp2_price: float, tp2_amount: float) -> Dict:
        """🏛️ EMPIRE V13.10: Create Ladder Exit orders (2 TPs + 1 SL)"""
        results = {}
        close_side = 'sell' if side.lower() == 'buy' else 'buy'
        
        try:
            # 1. Stop Loss (STOP_MARKET) - Full Position Protection
            sl_order = self.exchange.create_order(
                symbol=symbol,
                type='STOP_MARKET',
                side=close_side,
                amount=total_amount,
                params={
                    'stopPrice': stop_loss,
                    'reduceOnly': True,
                    'workingType': 'MARK_PRICE'
                }
            )
            results['sl'] = sl_order
            logger.info(f"[LADDER_SL] STOP_MARKET at ${stop_loss} ({close_side.upper()} {total_amount})")
            
            # 2. TP1 (Quick Exit) - First Rung
            tp1_order = self.exchange.create_order(
                symbol=symbol,
                type='LIMIT',
                side=close_side,
                amount=tp1_amount,
                price=tp1_price,
                params={
                    'reduceOnly': True,
                    'timeInForce': 'GTC'
                }
            )
            results['tp1'] = tp1_order
            logger.info(f"[LADDER_TP1] LIMIT at ${tp1_price} ({close_side.upper()} {tp1_amount})")
            
            # 3. TP2 (Final Exit) - Second Rung
            tp2_order = self.exchange.create_order(
                symbol=symbol,
                type='LIMIT',
                side=close_side,
                amount=tp2_amount,
                price=tp2_price,
                params={
                    'reduceOnly': True,
                    'timeInForce': 'GTC'
                }
            )
            results['tp2'] = tp2_order
            logger.info(f"[LADDER_TP2] LIMIT at ${tp2_price} ({close_side.upper()} {tp2_amount})")
            
        except Exception as e:
            logger.warning(f"[WARN] Ladder orders failed: {e}")
            try:
                for k in results: self.exchange.cancel_order(results[k]['id'], symbol)
            except: pass
            
        return results

    def cancel_all_orders(self, symbol: str):
        """🏛️ EMPIRE V13.9: Cancel all pending orders for a symbol (Reduce Only cleanup)"""
        try:
            self.exchange.cancel_all_orders(symbol)
            logger.info(f"[CANCEL_ALL] Orders cleaned for {symbol}")
        except Exception as e:
            logger.warning(f"[WARN] Order cleanup failed for {symbol}: {e}")
    def get_all_tickers(self) -> Dict:
        """Fetch all tickers in one call (Efficient for Volume/Price scanning)"""
        try:
            return self.exchange.fetch_tickers()
        except Exception as e:
            logger.error(f"[ERROR] Failed to fetch all tickers: {e}")
            return {}

    def get_all_futures_symbols(self) -> List[str]:
        """
        Fetch all linear futures symbols (USDT margined) dynamically from Binance API.
        This ignores CCXT local cache to avoid MATIC/POL outdated mappings.
        (User Request #DynamicList)
        """
        try:
            # Direct API call to bypass CCXT cache issues
            exchange_info = self.exchange.fapiPublicGetExchangeInfo()
            
            # Filter solely for TRADING status, USDT quote, and PERPETUAL contract type
            symbols = [
                s['symbol'] for s in exchange_info['symbols'] 
                if s['status'] == 'TRADING' 
                and s['quoteAsset'] == 'USDT'
                and s['contractType'] == 'PERPETUAL'
            ]
            
            # Format for Empire Engine (BTCUSDT -> BTC/USDT:USDT)
            formatted_symbols = []
            for s in symbols:
                try:
                    # Robust parsing: Find "USDT" index
                    base = s[:s.index('USDT')]
                    formatted_symbols.append(f"{base}/USDT:USDT")
                except:
                   pass
            
            logger.info(f"[DYNAMIC_LIST] Fetched {len(formatted_symbols)} active USDT perpetuals.")
            return formatted_symbols
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to fetch dynamic futures symbols: {e}")
            # Fallback to CCXT load_markets if direct call fails
            return self._get_all_futures_symbols_fallback()

    def _get_all_futures_symbols_fallback(self) -> List[str]:
        """Fallback method using standard CCXT load_markets"""
        try:
            if not self.markets:
                self.markets = self.exchange.load_markets()
            
            symbols = []
            for s, m in self.markets.items():
                if m.get('linear') and m.get('quote') == 'USDT' and m.get('active'):
                    symbols.append(s)
            return symbols
        except Exception as e:
            logger.error(f"[ERROR] Fallback symbol fetch failed: {e}")
            return []

    # --- EMPIRE V15: Binance Native Data Methods ---

    def fetch_binance_ticker_stats(self, symbol: str) -> Dict:
        """
        Récupère les statistiques 24h de Binance
        BEAUCOUP plus d'infos que fetch_ticker() standard
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'symbol': symbol,
                'price': ticker['last'],
                'volume_24h': ticker['quoteVolume'],  # Volume en USDT
                'volume_base_24h': ticker['baseVolume'],  # Volume en crypto
                'price_change_24h_pct': ticker['percentage'],
                'high_24h': ticker['high'],
                'low_24h': ticker['low'],
                'trades_count_24h': ticker.get('info', {}).get('count', 0),
                'bid': ticker['bid'],
                'ask': ticker['ask'],
                'bid_volume': ticker['bidVolume'],
                'ask_volume': ticker['askVolume'],
                'weighted_avg_price': float(ticker.get('info', {}).get('weightedAvgPrice', 0)),
                'prev_close': float(ticker.get('info', {}).get('prevClosePrice', 0)),
                'open_price': ticker['open']
            }
        except Exception as e:
            logger.error(f"Failed to fetch ticker stats for {symbol}: {e}")
            return {}

    def fetch_ohlcv_1min(self, symbol: str, limit: int = 50) -> List:
        """
        Récupère les dernières `limit` bougies 1 minute pour un symbole.
        Utilise l'API Binance Futures directement via requests (plus rapide que ccxt).
        Respecte le mode LIVE/DEMO.
        """
        import requests
        
        try:
            # Convertir le symbole du format interne vers format Binance
            binance_symbol = symbol.replace('/USDT:USDT', 'USDT').replace('/', '')
            
            # 🏛️ EMPIRE V16: Base URL dynamique selon le mode
            base_url = "https://fapi.binance.com" if self.live_mode else "https://demo-fapi.binance.com"
            url = f"{base_url}/fapi/v1/klines"
            
            params = {
                'symbol': binance_symbol,
                'interval': '1m',
                'limit': limit
            }
            
            # Appel API avec timeout
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            
            # Convertir toutes les valeurs en float
            ohlcv_data = []
            for candle in data:
                ohlcv_data.append([
                    float(candle[0]),  # timestamp
                    float(candle[1]),  # open
                    float(candle[2]),  # high
                    float(candle[3]),  # low
                    float(candle[4]),  # close
                    float(candle[5])   # volume
                ])
            
            return ohlcv_data
            
        except Exception as e:
            logger.error(f"Failed to fetch 1min OHLCV for {symbol}: {e}")
            return []  # Ne jamais lever d'exception

    
    
