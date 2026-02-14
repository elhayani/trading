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
        """Helper to close a position without worrying about leverage"""
        logger.info(f"[CLOSE] Attempting to close {symbol} ({side.upper()} {quantity})")
        return self.create_market_order(symbol, side=side, amount=quantity, leverage=None)


    def create_sl_tp_orders(self, symbol: str, side: str, amount: float, stop_loss: float, take_profit: float) -> Dict:
        """🏛️ EMPIRE V13.9: Create GTC Sniper orders (LIMIT for TP, STOP_MARKET for SL)"""
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
                    'workingType': 'MARK_PRICE' # 🏛️ Safety against wicks
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

    def fetch_order_book_analysis(self, symbol: str, limit: int = 100) -> Dict:
        """
        Analyse du carnet d'ordres (Order Book)
        """
        try:
            orderbook = self.exchange.fetch_order_book(symbol, limit=limit)
            bids = orderbook['bids']
            asks = orderbook['asks']
            
            if not bids or not asks:
                return {}

            total_bid_volume = sum([bid[1] for bid in bids])
            total_ask_volume = sum([ask[1] for ask in asks])
            
            # Prix pondérés
            bid_weighted = sum([bid[0] * bid[1] for bid in bids]) / total_bid_volume if total_bid_volume > 0 else 0
            ask_weighted = sum([ask[0] * ask[1] for ask in asks]) / total_ask_volume if total_ask_volume > 0 else 0
            
            # Spread
            spread = (asks[0][0] - bids[0][0]) / bids[0][0] * 100
            
            # Déséquilibre (Buy pressure)
            imbalance = (total_bid_volume - total_ask_volume) / (total_bid_volume + total_ask_volume) if (total_bid_volume + total_ask_volume) > 0 else 0
            
            # Détection de murs (Wall detection)
            avg_bid_size = total_bid_volume / len(bids)
            avg_ask_size = total_ask_volume / len(asks)
            
            buy_walls = [bid for bid in bids if bid[1] > avg_bid_size * 5]
            sell_walls = [ask for ask in asks if ask[1] > avg_ask_size * 5]
            
            return {
                'bid_volume': total_bid_volume,
                'ask_volume': total_ask_volume,
                'imbalance': imbalance,
                'spread_pct': spread,
                'bid_weighted_price': bid_weighted,
                'ask_weighted_price': ask_weighted,
                'buy_walls_count': len(buy_walls),
                'sell_walls_count': len(sell_walls),
                'biggest_buy_wall': max([w[1] for w in buy_walls], default=0),
                'biggest_sell_wall': max([w[1] for w in sell_walls], default=0)
            }
        except Exception as e:
            logger.error(f"Failed to fetch orderbook for {symbol}: {e}")
            return {}

    def fetch_recent_trades_analysis(self, symbol: str, limit: int = 500) -> Dict:
        """
        Analyse des trades récents
        """
        try:
            trades = self.exchange.fetch_trades(symbol, limit=limit)
            if not trades:
                return {}
            
            buys = [t for t in trades if t['side'] == 'buy']
            sells = [t for t in trades if t['side'] == 'sell']
            
            buy_volume = sum([t['amount'] * t['price'] for t in buys])
            sell_volume = sum([t['amount'] * t['price'] for t in sells])
            
            aggression = (buy_volume - sell_volume) / (buy_volume + sell_volume) if (buy_volume + sell_volume) > 0 else 0
            
            avg_buy_size = buy_volume / len(buys) if buys else 0
            avg_sell_size = sell_volume / len(sells) if sells else 0
            
            total_volume = buy_volume + sell_volume
            avg_trade_size = total_volume / len(trades)
            whale_trades = [t for t in trades if (t['amount'] * t['price']) > avg_trade_size * 10]
            
            return {
                'buy_volume': buy_volume,
                'sell_volume': sell_volume,
                'aggression': aggression,
                'avg_buy_size': avg_buy_size,
                'avg_sell_size': avg_sell_size,
                'whale_trades_count': len(whale_trades),
                'whale_ratio': len(whale_trades) / len(trades)
            }
        except Exception as e:
            logger.error(f"Failed to fetch recent trades for {symbol}: {e}")
            return {}

    def fetch_funding_rate(self, symbol: str) -> Dict:
        """
        Taux de financement (Futures)
        """
        try:
            funding = self.exchange.fetch_funding_rate(symbol)
            return {
                'funding_rate': funding['fundingRate'],
                'funding_timestamp': funding['fundingTimestamp'],
                'next_funding_time': funding['info'].get('nextFundingTime'),
                'sentiment': 'BULLISH' if funding['fundingRate'] > 0.0001 else 'BEARISH' if funding['fundingRate'] < -0.0001 else 'NEUTRAL'
            }
        except Exception as e:
            # logger.warning(f"Funding rate not available for {symbol}: {e}")
            return {}

    def fetch_open_interest(self, symbol: str) -> Dict:
        """
        Open Interest
        """
        try:
            oi = self.exchange.fetch_open_interest(symbol)
            return {
                'open_interest': oi['openInterest'],
                'timestamp': oi['timestamp']
            }
        except Exception as e:
            # logger.warning(f"OI not available for {symbol}: {e}")
            return {}
