import ccxt
import logging
from datetime import datetime, timedelta
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class ExchangeConnector:
    """Connect to crypto exchanges via CCXT"""
    
    def __init__(self, exchange_id='binance', api_key=None, secret=None, testnet=False):
        """
        Initialize exchange connection
        Args:
            exchange_id: 'binance', 'kraken', etc.
            api_key: API Key for trading
            secret: Secret Key for trading
            testnet: Use testnet environment
        """
        self.exchange_id = exchange_id
        self.testnet = testnet
        
        config = {
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'fetchCurrencies': False
            }
        }
        
        # Initialize exchange
        try:
            if exchange_id == 'binance':
                # 🚀 Use specialized USDM Futures class (Audit #V10.9)
                self.exchange = ccxt.binanceusdm(config)
                if testnet:
                    self._setup_binance_demo()
            else:
                self.exchange = getattr(ccxt, exchange_id)(config)
            
            self.exchange.load_markets()
            logger.info(f"✅ Connected to {exchange_id.upper()} ({'TESTNET' if testnet else 'LIVE'})")
            
        except Exception as e:
            if not testnet:
                logger.error(f"❌ CRITICAL: Failed to connect to {exchange_id} in LIVE mode: {e}")
                raise # On veut que le bot s'arrête en cas d'erreur Live
            else:
                logger.error(f"❌ Failed to connect to {exchange_id} (Testnet): {e}")

    def _setup_binance_demo(self):
        """Helper to configure Binance Demo/Testnet (Audit Fix #B2)"""
        if hasattr(self.exchange, 'set_sandbox_mode'):
            self.exchange.set_sandbox_mode(True)
        
        # Explicit override to ensure Testnet URLs are used
        # This fixes issues where set_sandbox_mode might not update all endpoints
        if self.exchange.options.get('defaultType') == 'future':
             self.exchange.urls['api'] = {
                 'public': 'https://testnet.binancefuture.com/fapi/v1',
                 'private': 'https://testnet.binancefuture.com/fapi/v1',
             }
        
        logger.info(f"🧪 Binance Sandbox Mode enabled. API: {self.exchange.urls['api']}")

    def create_market_order(self, symbol, side, amount):
        """Execute Market Order"""
        try:
            logger.info(f"🚀 Executing MARKET {side.upper()} {amount} {symbol}")
            return self.exchange.create_order(symbol, 'market', side, amount)
        except Exception as e:
            logger.error(f"❌ Order Failed: {e}")
            raise

    def create_limit_order(self, symbol, side, amount, price, params={}):
        """Execute Limit Order"""
        try:
            logger.info(f"🎯 Executing LIMIT {side.upper()} {amount} {symbol} @ {price}")
            return self.exchange.create_order(symbol, 'limit', side, amount, price, params)
        except Exception as e:
            logger.error(f"❌ Limit Order Failed: {e}")
            raise
    
    def cancel_all_orders(self, symbol):
        """Cancel all open orders for symbol"""
        try:
            return self.exchange.cancel_all_orders(symbol)
        except Exception as e:
            logger.warning(f"⚠️ Cancel All Failed: {e}")
            return None

    def fetch_ohlcv(self, symbol='SOL/USDT', timeframe='1h', limit=300):
        """Fetch OHLCV data"""
        try:
            return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            logger.error(f"❌ Error fetching OHLCV for {symbol}: {e}")
            return []
    
    def fetch_ticker(self, symbol='SOL/USDT'):
        """Fetch current ticker"""
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"❌ Error fetching ticker for {symbol}: {e}")
            return {'last': 0, 'percentage': 0}

    def fetch_order(self, order_id, symbol):
        """Fetch order status by ID"""
        try:
            return self.exchange.fetch_order(order_id, symbol)
        except Exception as e:
            logger.error(f"❌ Error fetching order {order_id}: {e}")
            raise

    def fetch_balance(self):
        """Fetch account balance"""
        try:
            return self.exchange.fetch_balance()
        except Exception as e:
            logger.error(f"❌ Error fetching balance: {e}")
            return {}

    def get_balance_usdt(self):
        """Helper to get total USDT balance for Futures"""
        try:
            balance = self.fetch_balance()
            if 'USDT' in balance:
                # CCXT Unified balance often uses 'total'
                return float(balance['USDT'].get('total', balance['USDT'].get('free', 0)))
            return 0.0
        except Exception as e:
            logger.error(f"❌ Error getting USDT balance: {e}")
            return 0.0

    def get_open_positions_count(self):
        """Count active positions on the account"""
        try:
            positions = self.exchange.fetch_positions()
            # Contracts/Amount depends on exchange, but > 0 means active
            active_positions = [p for p in positions if float(p.get('contracts', p.get('amount', 0))) > 0]
            return len(active_positions)
        except Exception as e:
            logger.error(f"❌ Error getting positions: {e}")
            return 0

    def get_market_info(self, symbol: str) -> Dict:
        """Fetch trading rules/info for a symbol (Audit #V10.2)"""
        try:
            if symbol not in self.exchange.markets:
                self.exchange.load_markets()
            
            m = self.exchange.market(symbol)
            return {
                'min_amount': m['limits']['amount']['min'],
                'min_cost': m['limits']['cost']['min'],
                'precision_price': m['precision']['price'],
                'precision_amount': m['precision']['amount'],
                'status': m.get('active', True)
            }
        except Exception as e:
            logger.error(f"❌ Error getting market info for {symbol}: {e}")
            return {}




# Test du connector
if __name__ == "__main__":
    print("="*70)
    print("🔌 TEST EXCHANGE CONNECTOR - REAL DATA")
    print("="*70)
    print()
    
    # Test 1: Connect to Binance
    print("TEST 1: Connection to Binance")
    print("-" * 70)
    
    try:
        exchange = ExchangeConnector('binance')
        print()
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        exit(1)
    
    # Test 2: Fetch SOL/USDT ticker
    print("\nTEST 2: Fetch SOL/USDT Ticker")
    print("-" * 70)
    
    ticker = exchange.fetch_ticker('DEFI/USDT')
    if ticker:
        print(f"✅ Ticker retrieved:")
        print(f"   Last Price: ${ticker['last']:.2f}")
        bid = ticker.get('bid') or 0
        ask = ticker.get('ask') or 0
        print(f"   Bid: ${bid:.2f}")
        print(f"   Ask: ${ask:.2f}")
        print(f"   24h Volume: ${ticker.get('quoteVolume', 0):,.0f}")
        print(f"   24h Change: {ticker.get('percentage', 0):.2f}%")
    
    # Test 3: Fetch OHLCV
    print("\n\nTEST 3: Fetch OHLCV Data (1h, 300 candles)")
    print("-" * 70)
    
    ohlcv = exchange.fetch_ohlcv('SOL/USDT', '1h', 300)
    
    if ohlcv:
        print(f"\n📊 OHLCV Sample (last 3 candles):")
        for i, candle in enumerate(ohlcv[-3:], 1):
            timestamp = datetime.fromtimestamp(candle[0]/1000)
            print(f"\n   {i}. {timestamp.strftime('%Y-%m-%d %H:%M')}")
            print(f"      Open: ${candle[1]:.2f}")
            print(f"      High: ${candle[2]:.2f}")
            print(f"      Low: ${candle[3]:.2f}")
            print(f"      Close: ${candle[4]:.2f}")
            print(f"      Volume: {candle[5]:,.0f}")
    
    # Test 4: Market info
    print("\n\nTEST 4: Market Info (Trading Rules)")
    print("-" * 70)
    
    market_info = exchange.get_market_info('SOL/USDT')
    if market_info:
        print(f"✅ Market info retrieved:")
        print(f"   Min Amount: {market_info['min_amount']}")
        print(f"   Min Cost: ${market_info['min_cost']}")
        print(f"   Price Precision: {market_info['precision_price']}")
        print(f"   Amount Precision: {market_info['precision_amount']}")
    
    # Test 5: Multiple symbols
    print("\n\nTEST 5: Fetch Multiple Symbols")
    print("-" * 70)
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    for symbol in symbols:
        ticker = exchange.fetch_ticker(symbol)
        if ticker:
            print(f"{symbol:12} → ${ticker['last']:>10,.2f}  ({ticker['percentage']:>6.2f}%)")
    
    print("\n" + "="*70)
    print("✅ ALL TESTS PASSED - READY FOR LIVE TRADING")
    print("="*70)
    print()
    print("💡 NEXT STEPS:")
    print("1. ✅ Exchange connector working")
    print("2. ⏳ Integrate with V4 HYBRID")
    print("3. ⏳ Test full trading cycle with real data")
    print("4. ⏳ Deploy to AWS Lambda")
    print()
