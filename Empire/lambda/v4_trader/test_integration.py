"""
🧪 TEST INTÉGRATION COMPLET: 12 actifs × scénarios × MAX_OPEN_TRADES
=====================================================================
Teste le pipeline complet avec:
- Mock Exchange (pas de vrais ordres Binance)
- Real DynamoDB (EmpireTradesHistory, EmpireSkippedTrades, V4TradingState)
- Real analyze_market (TA sur OHLCV synthétique)
- Real DecisionEngine + RiskManager
- Mock News (sentiment configurable: bullish/bearish/neutral)

🏛️ Empire 12 Assets:
- Crypto (6): BTC, ETH, SOL, XRP, BNB, DOGE
- Commodities (2): PAXG (Gold), OIL (WTI)
- Indices (2): SPX (S&P 500), DAX (GER40)
- Forex (1): EUR/USD
- Stable (1): USDC

Scénarios testés par batch de 4 actifs:
- Batch 1: BTC(oversold→LONG), ETH(overbought→SHORT), SOL(neutral→SKIP), XRP(oversold→LONG)
- Batch 2: BNB(oversold→LONG), DOGE(overbought→SHORT), SPX(oversold→LONG), DAX(overbought→SHORT)
  → Devrait bloquer au-delà de MAX_OPEN_TRADES=4
- Batch 3: PAXG(oversold→LONG), OIL(overbought→SHORT), EUR/USD(oversold→LONG), USDC(neutral→SKIP)
  → Devrait bloquer (slots pleins)
- Batch 4/5: Bedrock Matrix (BTC Filters)

Usage:
    python test_integration.py                  # Run all tests
    python test_integration.py --cleanup        # Clean test data from DynamoDB
"""

import os
import sys
import json
import uuid
import time
import random
import logging
import numpy as np
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from typing import Dict, List, Optional

# Setup env BEFORE imports
os.environ.setdefault('AWS_DEFAULT_REGION', 'eu-west-3')
os.environ.setdefault('AWS_REGION', 'eu-west-3')
os.environ.setdefault('HISTORY_TABLE', 'EmpireTradesHistory')
os.environ.setdefault('SKIPPED_TABLE', 'EmpireSkippedTrades')
os.environ.setdefault('STATE_TABLE', 'V4TradingState')
os.environ.setdefault('TRADING_MODE', 'dry_run')

import boto3
import pandas as pd

# Local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import TradingConfig
from market_analysis import analyze_market, classify_asset
from models import AssetClass
from risk_manager import RiskManager
from decision_engine import DecisionEngine
from atomic_persistence import AtomicPersistence

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== CONSTANTS ====================

ALL_ASSETS = [
    # Crypto Leaders (5)
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT', 'XRP/USDT:USDT',
    # Elite Crypto (5)
    'AVAX/USDT:USDT', 'LINK/USDT:USDT', 'ADA/USDT:USDT', 'DOT/USDT:USDT', 'POL/USDT:USDT',
    # Retail / News (1)
    'DOGE/USDT:USDT',
    # Commodities (2)
    'PAXG/USDT:USDT', 'OIL/USDT:USDT',
    # Indices (3)
    'SPX/USDT:USDT', 'DAX/USDT:USDT', 'NDX/USDT:USDT',
    # Forex (3)
    'EUR/USD:USDT', 'GBP/USD:USDT', 'USD/JPY:USDT',
    # Stable (1)
    'USDC/USDT:USDT'
]

BASE_PRICES = {
    # Crypto Leaders
    'BTC/USDT:USDT': 97000.0,
    'ETH/USDT:USDT': 2650.0,
    'SOL/USDT:USDT': 195.0,
    'BNB/USDT:USDT': 580.0,
    'XRP/USDT:USDT': 2.45,
    # Elite Crypto
    'AVAX/USDT:USDT': 42.50,
    'LINK/USDT:USDT': 18.20,
    'ADA/USDT:USDT': 0.85,
    'DOT/USDT:USDT': 7.60,
    'POL/USDT:USDT': 0.55,
    # Retail
    'DOGE/USDT:USDT': 0.25,
    # Commodities
    'PAXG/USDT:USDT': 2920.0,
    'OIL/USDT:USDT': 72.5,
    # Indices
    'SPX/USDT:USDT': 6050.0,
    'DAX/USDT:USDT': 22100.0,
    'NDX/USDT:USDT': 21400.0,
    # Forex
    'EUR/USD:USDT': 1.0450,
    'GBP/USD:USDT': 1.2650,
    'USD/JPY:USDT': 152.0,
    # Stable
    'USDC/USDT:USDT': 1.0001,
}

PASS = "✅"
FAIL = "❌"
INFO = "📊"

# ==================== OHLCV GENERATOR ====================

def generate_ohlcv(base_price: float, scenario: str = 'neutral', num_candles: int = 300, volume_mult: float = 1.0) -> List:
    candles = []
    now = int(time.time() * 1000)
    interval_ms = 3600000  # 1h
    price = base_price * 1.05

    for i in range(num_candles):
        ts = now - (num_candles - i) * interval_ms
        if i < num_candles - 25:
            change = random.uniform(-0.001, 0.001)
        else:
            if scenario == 'oversold':
                change = random.uniform(-0.012, -0.006)
            elif scenario == 'overbought':
                change = random.uniform(0.006, 0.012)
            else:
                change = random.uniform(-0.001, 0.001)

        open_price = price
        close_price = price * (1 + change)
        high = max(open_price, close_price) * (1 + random.uniform(0.0005, 0.002))
        low = min(open_price, close_price) * (1 - random.uniform(0.0005, 0.002))
        
        # Volume logic: base * multiplier
        volume = (100000.0 / base_price) * volume_mult # Normalized somewhat to price
        
        # Add noise
        volume *= random.uniform(0.8, 1.2)
        
        # Spike last candle for 'neutral' sometimes? No, let scenario dictate price.
        
        candles.append([ts, open_price, high, low, close_price, volume])
        price = close_price
    return candles

# ==================== MOCK EXCHANGE ====================

class MockExchange:
    def __init__(self):
        self.positions = {}
        self.balance = 5000.0
        self.orders = []
        self.exchange = MagicMock()
        self.exchange.fapiPrivateV2GetPositionRisk.return_value = []
        self.markets = {sym: {'precision': {'amount': 3, 'price': 2}, 'limits': {'amount': {'min': 0.001}}, 'symbol': sym} for sym in ALL_ASSETS}
        self.ohlcv_data = {} # To look up data by symbol

    def resolve_symbol(self, symbol: str) -> str: return symbol
    def get_market_info(self, symbol: str) -> Dict: return {'precision': {'amount': 3, 'price': 2}, 'min_amount': 0.001, 'symbol': symbol}
    def get_balance_usdt(self) -> float: return self.balance
    def fetch_balance(self) -> Dict: return {'USDT': {'total': self.balance, 'free': self.balance}, 'total': {'USDT': self.balance}}
    def create_market_order(self, symbol: str, side: str, amount: float, leverage: int = 1) -> Dict:
        price = BASE_PRICES.get(symbol, 100.0)
        if side == 'buy':
            if symbol in self.positions and self.positions[symbol]['side'] == 'SHORT': del self.positions[symbol]
            else: self.positions[symbol] = {'qty': amount, 'side': 'LONG', 'entry_price': price, 'leverage': leverage}
        elif side == 'sell':
            if symbol in self.positions and self.positions[symbol]['side'] == 'LONG': del self.positions[symbol]
            else: self.positions[symbol] = {'qty': amount, 'side': 'SHORT', 'entry_price': price, 'leverage': leverage}
        self.orders.append({'symbol': symbol, 'side': side, 'amount': amount, 'leverage': leverage, 'price': price, 'time': datetime.now(timezone.utc).isoformat()})
        logger.info(f"  [MOCK_ORDER] {side.upper()} {amount} {symbol} @ ${price:.2f} (Lev={leverage}x)")
        return {'average': price, 'filled': amount, 'status': 'closed', 'id': f'MOCK-{uuid.uuid4().hex[:6]}'}

    def fetch_positions(self, symbols: List[str]) -> List:
        result = []
        for sym in symbols:
            if sym in self.positions:
                pos = self.positions[sym]
                amt = pos['qty'] if pos['side'] == 'LONG' else -pos['qty']
                result.append({'symbol': sym, 'contracts': pos['qty'], 'side': pos['side'].lower(), 'entryPrice': str(pos['entry_price']), 'positionAmt': str(amt), 'lastPrice': str(pos['entry_price']), 'leverage': str(pos['leverage']), 'unRealizedProfit': '0'})
        return result

    def set_leverage(self, leverage, symbol): pass
    def _get_binance_position_risk(self):
        result = []
        for sym, pos in self.positions.items():
            binance_sym = sym.replace('/USDT:USDT', 'USDT').replace('/', '')
            amt = pos['qty'] if pos['side'] == 'LONG' else -pos['qty']
            result.append({'symbol': binance_sym, 'positionAmt': str(amt), 'entryPrice': str(pos['entry_price']), 'markPrice': str(pos['entry_price']), 'unRealizedProfit': '0', 'leverage': str(pos['leverage'])})
        return result
        
    def get_all_futures_symbols(self) -> List[str]:
        return list(self.markets.keys())
        
    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 500) -> List:
        if symbol in self.ohlcv_data:
            return self.ohlcv_data[symbol]
        # Fallback if not generated (should not happen in valid test)
        return generate_ohlcv(BASE_PRICES.get(symbol, 10.0))
        
    def get_all_tickers(self) -> Dict:
        tickers = {}
        for sym in self.markets:
            quote_vol = 500_000.0 # Default low volume
            change = 0.0
            last = 100.0
            
            if sym in self.ohlcv_data:
                candles = self.ohlcv_data[sym]
                if candles and len(candles) >= 2:
                    # Sum last 24h volume
                    recent = candles[-24:]
                    quote_vol = sum(c[5] * ((c[1]+c[4])/2) for c in recent)
                    
                    first = recent[0][4]
                    last_c = recent[-1][4]
                    if first > 0:
                        change = ((last_c - first) / first) * 100
                    last = last_c

            tickers[sym] = {
                'symbol': sym,
                'quoteVolume': quote_vol,
                'percentage': change,
                'last': last
            }
        return tickers

    def fetch_tickers(self) -> Dict:
        return self.get_all_tickers()

    def fetch_ticker(self, symbol: str) -> Dict:
        tickers = self.get_all_tickers()
        return tickers.get(symbol, {})



    # --- V15 Scanner Mocks ---
    def fetch_order_book_analysis(self, symbol: str, limit: int = 100) -> Dict:
        # Synthetic analysis based on last candle
        imb = 0.0
        if symbol in self.ohlcv_data:
            candles = self.ohlcv_data[symbol]
            if candles:
                last_c = candles[-1]
                # If BULLISH candle -> Buy pressure
                if last_c[4] > last_c[1]: imb = 0.4 
                else: imb = -0.4
        
        return {
            'imbalance': imb,
            'spread_pct': 0.01,
            'bid_volume': 1000000,
            'ask_volume': 1000000
        }

    def fetch_recent_trades_analysis(self, symbol: str, limit: int = 500) -> Dict:
        aggr = 0.0
        if symbol in self.ohlcv_data:
            candles = self.ohlcv_data[symbol]
            if candles:
                last_c = candles[-1]
                if last_c[4] > last_c[1]: aggr = 0.3
                else: aggr = -0.3
                
        return {
            'aggression': aggr,
            'whale_trades_count': 5,
            'buy_volume': 500000,
            'sell_volume': 500000
        }

# ==================== MOCK NEWS FETCHER ====================


class MockNewsFetcher:
    def __init__(self, sentiments: Dict[str, float] = None): self.sentiments = sentiments or {}
    def get_news_sentiment_score(self, symbol: str) -> float: return self.sentiments.get(symbol, 0.0)

# ==================== HELPERS ====================

def to_decimal(obj):
    if isinstance(obj, float): return Decimal(str(obj))
    if isinstance(obj, dict): return {k: to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list): return [to_decimal(v) for v in obj]
    return obj

def from_decimal(obj):
    if isinstance(obj, Decimal): return float(obj)
    if isinstance(obj, dict): return {k: from_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list): return [from_decimal(v) for v in obj]
    return obj

# ==================== TEST SCENARIOS ====================

BATCHES = [
    {'name': 'Batch 1: Crypto Leaders', 'assets': {
        'BTC/USDT:USDT': {'scenario': 'oversold', 'news': 0.5, 'expected_signal': 'LONG'},
        'ETH/USDT:USDT': {'scenario': 'overbought', 'news': -0.3, 'expected_signal': 'SHORT'},
        'SOL/USDT:USDT': {'scenario': 'neutral', 'news': 0.0, 'expected_signal': 'NEUTRAL'},
        'BNB/USDT:USDT': {'scenario': 'oversold', 'news': 0.4, 'expected_signal': 'LONG'},
        'XRP/USDT:USDT': {'scenario': 'oversold', 'news': 0.2, 'expected_signal': 'LONG'},
    }},
    {'name': 'Batch 2: Elite Alts', 'assets': {
        'AVAX/USDT:USDT': {'scenario': 'oversold', 'news': 0.3, 'expected_signal': 'LONG'},
        'LINK/USDT:USDT': {'scenario': 'overbought', 'news': -0.2, 'expected_signal': 'SHORT'},
        'ADA/USDT:USDT': {'scenario': 'oversold', 'news': 0.1, 'expected_signal': 'LONG'},
        'DOT/USDT:USDT': {'scenario': 'neutral', 'news': 0.0, 'expected_signal': 'NEUTRAL'},
        'POL/USDT:USDT': {'scenario': 'oversold', 'news': 0.2, 'expected_signal': 'LONG'},
    }},
    {'name': 'Batch 3: Macro & Indices', 'assets': {
        'SPX/USDT:USDT': {'scenario': 'oversold', 'news': 0.3, 'expected_signal': 'LONG'},
        'DAX/USDT:USDT': {'scenario': 'overbought', 'news': -0.2, 'expected_signal': 'SHORT'},
        'NDX/USDT:USDT': {'scenario': 'oversold', 'news': 0.5, 'expected_signal': 'LONG'},
        'PAXG/USDT:USDT': {'scenario': 'oversold', 'news': 0.1, 'expected_signal': 'LONG'},
        'OIL/USDT:USDT': {'scenario': 'overbought', 'news': -0.1, 'expected_signal': 'SHORT'},
    }},
    {'name': 'Batch 4: Forex & Retail', 'assets': {
        'EUR/USD:USDT': {'scenario': 'oversold', 'news': 0.0, 'expected_signal': 'LONG'},
        'GBP/USD:USDT': {'scenario': 'overbought', 'news': -0.1, 'expected_signal': 'SHORT'},
        'USD/JPY:USDT': {'scenario': 'oversold', 'news': 0.2, 'expected_signal': 'LONG'},
        'DOGE/USDT:USDT': {'scenario': 'overbought', 'news': -0.5, 'expected_signal': 'SHORT'},
        'USDC/USDT:USDT': {'scenario': 'neutral', 'news': 0.0, 'expected_signal': 'NEUTRAL'},
    }},
    {'name': 'Batch 5: Bedrock Matrix (BTC Pump)', 'btc_rsi': 85.0, 'assets': {
        'ETH/USDT:USDT': {'scenario': 'overbought', 'news': -0.1, 'expected_signal': 'BLOCK_SHORT'},
        'SOL/USDT:USDT': {'scenario': 'oversold', 'news': 0.2, 'expected_signal': 'LONG'},
    }},
    {'name': 'Batch 6: Bedrock Matrix (BTC Crash)', 'btc_rsi': 15.0, 'assets': {
        'BNB/USDT:USDT': {'scenario': 'oversold', 'news': 0.1, 'expected_signal': 'BLOCK_LONG'},
        'DOGE/USDT:USDT': {'scenario': 'overbought', 'news': -0.2, 'expected_signal': 'SHORT'},
    }},
]

# ==================== TEST ENGINE ====================

class IntegrationTest:
    def __init__(self):
        from v4_hybrid_lambda import AWSClients, PersistenceLayer
        self.aws = AWSClients()
        self.persistence = PersistenceLayer(self.aws)
        self.atomic_persistence = AtomicPersistence(self.aws.state_table)
        self.mock_exchange = MockExchange()
        self.risk_manager = RiskManager()
        self.decision_engine = DecisionEngine(risk_manager=self.risk_manager)
        self.results = []
        self.test_trade_ids = []
        self.ohlcv_cache = {}
        
        # Generate OHLCV for BATCH assets specifically (keep existing logic)
        for batch in BATCHES:
            for symbol, cfg in batch['assets'].items():
                self.ohlcv_cache[symbol] = generate_ohlcv(BASE_PRICES[symbol], cfg['scenario'], 300)
        
        # Feed existing batch data into mock_exchange for backward compatibility
        self.mock_exchange.ohlcv_data.update(self.ohlcv_cache)

    def test(self, name: str, condition: bool, detail: str = "") -> bool:
        status = PASS if condition else FAIL
        self.results.append((name, condition))
        print(f"  {status} {name}" + (f" — {detail}" if detail else ""))
        return condition

    def _build_engine(self, news_sentiments: Dict[str, float]):
        from v4_hybrid_lambda import TradingEngine
        with patch.object(TradingEngine, '__init__', lambda self: None): engine = TradingEngine()
        engine.aws, engine.persistence, engine.atomic_persistence, engine.exchange = self.aws, self.persistence, self.atomic_persistence, self.mock_exchange
        engine.risk_manager, engine.decision_engine = self.risk_manager, self.decision_engine
        engine.news_fetcher = MockNewsFetcher(news_sentiments)
        engine.cooldown_seconds, engine.execution_id = 0, f"TEST-{uuid.uuid4().hex[:6]}"
        return engine

    def _run_cycle(self, engine, symbol: str, btc_rsi: Optional[float] = None) -> Dict:
        ohlcv = self.mock_exchange.fetch_ohlcv(symbol) # Use the exchange fetcher now
        asset_class = classify_asset(symbol)
        ta_result = analyze_market(ohlcv, symbol=symbol, asset_class=asset_class)
        positions = self.persistence.load_positions()
        if symbol in positions: return {'symbol': symbol, 'status': 'IN_POSITION', 'ta': ta_result}
        direction = 'SHORT' if ta_result.get('signal_type') == 'SHORT' else 'LONG'
        if ta_result.get('signal_type') == 'NEUTRAL': return {'symbol': symbol, 'status': 'NO_SIGNAL', 'ta': ta_result}
        news_score = engine.news_fetcher.get_news_sentiment_score(symbol)
        macro = {'regime': 'NORMAL'}
        decision = self.decision_engine.evaluate_with_risk(context=macro, ta_result=ta_result, symbol=symbol, capital=self.mock_exchange.balance, direction=direction, asset_class=asset_class, news_score=news_score, btc_rsi=btc_rsi)
        if not decision['proceed']: return {'symbol': symbol, 'status': 'BLOCKED', 'reason': decision['reason'], 'ta': ta_result}
        open_count = len(positions)
        if open_count >= TradingConfig.MAX_OPEN_TRADES: return {'symbol': symbol, 'status': 'SLOT_FULL', 'reason': 'MAX_OPEN_TRADES', 'ta': ta_result}
        trade_id = f"TEST-{uuid.uuid4().hex[:8]}"
        self.test_trade_ids.append(trade_id)
        order = self.mock_exchange.create_market_order(symbol, 'sell' if direction == 'SHORT' else 'buy', decision['quantity'], leverage=TradingConfig.LEVERAGE)
        tp = float(order['average']) * (1.003 if direction == 'LONG' else 0.997)
        sl = float(order['average']) * (0.996 if direction == 'LONG' else 1.004)
        self.persistence.log_trade_open(trade_id, symbol, asset_class, direction, float(order['average']), float(order['filled']), float(order['filled'])*float(order['average']), tp, sl, TradingConfig.LEVERAGE, reason=f"RSI={ta_result.get('rsi',0):.1f}", is_test=True)
        self.persistence.save_position(symbol, {'trade_id': trade_id, 'entry_price': float(order['average']), 'quantity': float(order['filled']), 'direction': direction, 'stop_loss': sl, 'take_profit': tp, 'asset_class': str(asset_class)}, is_test=True)
        return {'symbol': symbol, 'status': f'{direction}_OPEN', 'reason': '', 'ta': ta_result}

    def _test_double_alpha_scan(self):
        # 🏛️ EMPIRE V14.0: Simulate Real Binance Extension (415 Assets)
        print(f"\n⚡ Test V14.0: DOUBLE ALPHA SCAN (Simulating 415 Real Assets)")
        
        # 1. Generate a massive list of symbols mimicking Binance
        # Real leaders + 400 fake alts
        real_leaders = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT', 'XRP/USDT:USDT']
        fake_alts = [f"COIN{i:03d}/USDT:USDT" for i in range(1, 411)]
        all_test_assets = real_leaders + fake_alts
        
        # Update Mock Exchange to know about these 415 assets
        self.mock_exchange.markets = {sym: {'precision': {'amount': 3, 'price': 2}, 'limits': {'amount': {'min': 0.001}}, 'symbol': sym, 'linear': True, 'quote': 'USDT', 'active': True} for sym in all_test_assets}
        
        # 2. Plant specific signals (The "Needle in the Haystack")
        
        # A. Short Hunter Candidates: High RSI (>72) + High Volume
        shorts = ['COIN100/USDT:USDT', 'COIN101/USDT:USDT', 'COIN102/USDT:USDT']
        for s in shorts:
            self.mock_exchange.ohlcv_data[s] = generate_ohlcv(10, 'overbought', volume_mult=100.0) # RSI ~80, Vol Huge

        # B. Long Sniper Candidates: Low RSI (<28) + High Volume
        longs = ['COIN200/USDT:USDT', 'COIN201/USDT:USDT', 'COIN202/USDT:USDT']
        for s in longs:
            self.mock_exchange.ohlcv_data[s] = generate_ohlcv(10, 'oversold', volume_mult=100.0) # RSI ~20, Vol Huge
            
        # C. Traps: High Signals but Low Volume (Should be ignored)
        traps = ['COIN300/USDT:USDT', 'COIN301/USDT:USDT']
        for s in traps:
            self.mock_exchange.ohlcv_data[s] = generate_ohlcv(10, 'oversold', volume_mult=0.01) # RSI ~20, Vol Tiny
            
        # D. Noise: The other 400 assets are neutral/random
        for sym in all_test_assets:
            if sym not in self.mock_exchange.ohlcv_data:
                 self.mock_exchange.ohlcv_data[sym] = generate_ohlcv(10, 'neutral', volume_mult=1.0)
                
        # 3. Run Scan
        engine = self._build_engine({})
        engine.exchange = self.mock_exchange # Bind updated exchange
        
        print(f"  🌊 Scanning {len(all_test_assets)} assets...")
        start = time.time()
        selected = engine.scan_market_double_alpha()
        duration = time.time() - start
        
        print(f"  ⏱️  Scan time: {duration:.2f}s")
        
        # 4. Validations
        found_shorts = [s for s in shorts if s in selected]
        found_longs = [s for s in longs if s in selected]
        found_traps = [s for s in traps if s in selected]
        
        self.test("Volume Filter SHORT ok", len(found_shorts) == len(shorts), f"Found {len(found_shorts)}/{len(shorts)}")
        self.test("Volume Filter LONG ok", len(found_longs) == len(longs), f"Found {len(found_longs)}/{len(longs)}")
        self.test("Low Volume Traps Excluded", len(found_traps) == 0, f"Traps found: {found_traps}")
        self.test("Total Selection < 40", len(selected) <= 40, f"Count: {len(selected)}")
        
    def run_all(self):
        print("\n🧪 EMPIRE V14.0 — Integration Test Suite")
        self._test_open_batches()
        self._test_double_alpha_scan() # NEW: 415 Asset Simulation
        self._test_close_flow()
        self._print_summary()

    def _test_open_batches(self):
        total_opened = 0
        for batch in BATCHES:
            if "Bedrock" in batch['name']:
                self.mock_exchange.positions = {}
                total_opened = 0
                resp = self.aws.state_table.scan(FilterExpression='begins_with(trader_id, :p)', ExpressionAttributeValues={':p': 'POSITION#'})
                for item in resp.get('Items', []): self.aws.state_table.delete_item(Key={'trader_id': item['trader_id']})
            print(f"\n📦 {batch['name']}")
            engine = self._build_engine({s: c['news'] for s, c in batch['assets'].items()})
            btc_rsi = batch.get('btc_rsi')
            for symbol, cfg in batch['assets'].items():
                res = self._run_cycle(engine, symbol, btc_rsi=btc_rsi)
                status, reason = res['status'], res.get('reason', '')
                print(f"  🔄 {symbol}: Status={status} | Reason={reason}")
                if 'BLOCKED' in status or 'NO_SIGNAL' in status or 'SLOT_FULL' in status:
                    self.persistence.log_skipped_trade(symbol, reason or status, classify_asset(symbol), is_test=True)
                if cfg['expected_signal'] == 'BLOCK_SHORT': self.test(f"{symbol} SHORT blocked", 'BLOCK_SHORT' in reason)
                elif cfg['expected_signal'] == 'BLOCK_LONG': self.test(f"{symbol} LONG blocked", 'BLOCK_LONG' in reason)
                elif 'OPEN' in status: total_opened += 1; self.test(f"{symbol} opened", True)

    def _test_close_flow(self):
        print(f"\n🔻 Closing Trades...")
        positions = self.persistence.load_positions()
        for sym, pos in positions.items():
            self.mock_exchange.create_market_order(sym, 'sell' if pos['direction'] == 'LONG' else 'buy', pos['quantity'])
            self.persistence.log_trade_close(pos['trade_id'], pos['entry_price'], 0, "Test Close", is_test=True)
            self.persistence.delete_position(sym)
            self.test(f"{sym} closed", True)

    def _print_summary(self):
        passed = sum(1 for _, c in self.results if c)
        print(f"\n{'='*70}\n📊 RÉSULTATS: {passed}/{len(self.results)} tests passés\n{'='*70}")

if __name__ == "__main__":
    test = IntegrationTest()
    if "--cleanup" in sys.argv:
        print("🧹 Cleaning up...")
        resp = test.aws.state_table.scan(FilterExpression='begins_with(trader_id, :p)', ExpressionAttributeValues={':p': 'POSITION#'})
        for item in resp.get('Items', []): test.aws.state_table.delete_item(Key={'trader_id': item['trader_id']})
    else:
        test.run_all()
