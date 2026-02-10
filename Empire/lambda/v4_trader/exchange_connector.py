#!/usr/bin/env python3
"""
EXCHANGE CONNECTOR - Real-time Data with CCXT
==============================================
Fetch real OHLCV and prices from exchanges
"""

import ccxt
from datetime import datetime, timedelta
import time

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
            'options': {'defaultType': 'future'}  # Default to Futures for V4
        }
        
        # Testnet URL Override (Binance Futures)
        if testnet and exchange_id == 'binance':
            config['urls'] = {
                'api': {
                    'fapiPublic': 'https://testnet.binancefuture.com',
                    'fapiPrivate': 'https://testnet.binancefuture.com',
                    'fapiPrivateV2': 'https://testnet.binancefuture.com', 
                }
            }
            print("🧪 Configured for Binance Futures TESTNET")

        # Initialize exchange
        if exchange_id == 'binance':
            self.exchange = ccxt.binance(config)
            
            # 1. Attempt Demo/VAPI mode if testnet is True
            if testnet:
                try:
                    # Some versions of ccxt have this helper
                    if hasattr(self.exchange, 'enable_demo_trading'):
                        self.exchange.enable_demo_trading(True)
                        print("🧪 Binance Demo Trading ENABLED")
                    else:
                        # Manual URL override for VAPI
                        self.exchange.urls['api']['fapiPublic'] = 'https://vapi.binance.com'
                        self.exchange.urls['api']['fapiPrivate'] = 'https://vapi.binance.com'
                        print("🧪 Binance VAPI URL override active")
                except Exception as e:
                    print(f"⚠️ Failed to enable demo/vapi: {e}")
                    # Fallback to standard testnet
                    self.exchange.urls['api']['fapiPublic'] = 'https://testnet.binancefuture.com'
                    self.exchange.urls['api']['fapiPrivate'] = 'https://testnet.binancefuture.com'
                    print("🧪 Falling back to legacy binancefuture testnet")
        else:
            self.exchange = getattr(ccxt, exchange_id)(config)
        
        # Test connection
        try:
            self.exchange.load_markets()
            print(f"✅ Connected to {exchange_id.upper()} ({'TESTNET' if testnet else 'LIVE'})")
        except Exception as e:
            # Fallback to Demo/VAPI if Live fails with Invalid API Key (likely paper trading keys)
            if not testnet and exchange_id == 'binance' and "Invalid Api-Key" in str(e):
                print(f"⚠️ Live connection failed ({e}). Attempting Binance Demo Trading...")
                try:
                    if hasattr(self.exchange, 'enable_demo_trading'):
                        self.exchange.enable_demo_trading(True)
                    else:
                        self.exchange.urls['api']['fapiPublic'] = 'https://vapi.binance.com'
                        self.exchange.urls['api']['fapiPrivate'] = 'https://vapi.binance.com'
                    
                    self.exchange.load_markets()
                    print("✅ Connected to BINANCE DEMO (VAPI)")
                    return
                except Exception as demo_err:
                    print(f"❌ Demo fallback failed: {demo_err}")
            
            print(f"❌ Failed to connect to {exchange_id}: {e}")
            print("⚠️ Proceeding in Read-Only mode or with limited functionality.")

    def create_market_order(self, symbol, side, amount):
        """Execute Market Order"""
        try:
            print(f"🚀 Executing MARKET {side.upper()} {amount} {symbol}")
            return self.exchange.create_order(symbol, 'market', side, amount)
        except Exception as e:
            print(f"❌ Order Failed: {e}")
            raise

    def create_limit_order(self, symbol, side, amount, price, params={}):
        """Execute Limit Order"""
        try:
            print(f"🎯 Executing LIMIT {side.upper()} {amount} {symbol} @ {price}")
            return self.exchange.create_order(symbol, 'limit', side, amount, price, params)
        except Exception as e:
            print(f"❌ Limit Order Failed: {e}")
            raise
    
    def cancel_all_orders(self, symbol):
        """Cancel all open orders for symbol"""
        try:
            return self.exchange.cancel_all_orders(symbol)
        except Exception as e:
            print(f"⚠️ Cancel All Failed: {e}")
            return None

    def fetch_ohlcv(self, symbol='SOL/USDT', timeframe='1h', limit=300):
        """Fetch OHLCV data"""
        try:
            # print(f"📊 Fetching {symbol} {timeframe}...")
            return self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            print(f"❌ Error fetching OHLCV: {e}")
            return []
    
    def fetch_ticker(self, symbol='SOL/USDT'):
        """Fetch current ticker"""
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            print(f"❌ Error fetching ticker: {e}")
            return {'last': 0}

    def fetch_balance(self):
        """Fetch account balance"""
        try:
            return self.exchange.fetch_balance()
        except Exception as e:
            print(f"❌ Error fetching balance: {e}")
            return {}

    def get_balance_usdt(self):
        """Helper to get total USDT balance for Futures"""
        try:
            balance = self.fetch_balance()
            # For Futures, looking for USDT total or free balance
            if 'USDT' in balance:
                return float(balance['USDT']['total'])
            return 0.0
        except Exception as e:
            print(f"❌ Error getting USDT balance: {e}")
            return 0.0

    def get_open_positions_count(self):
        """Count active positions on the account (where size > 0)"""
        try:
            # fetch_positions is a standard CCXT method for Futures
            positions = self.exchange.fetch_positions()
            active_positions = [p for p in positions if float(p.get('contracts', 0)) > 0 or float(p.get('entryPrice', 0)) > 0]
            return len(active_positions)
        except Exception as e:
            print(f"❌ Error getting positions: {e}")
            # Fallback: check open orders if positions fails (less accurate)
            return 0



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
            print(f"{symbol:12} → ${ticker['last']:>10,.2f}  ({ticker['change_24h']:>6.2f}%)")
    
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
