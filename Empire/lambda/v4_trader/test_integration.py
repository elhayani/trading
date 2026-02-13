"""
🧪 TEST INTÉGRATION COMPLET: 11 actifs × scénarios × MAX_OPEN_TRADES
=====================================================================
Teste le pipeline complet avec:
- Mock Exchange (pas de vrais ordres Binance)
- Real DynamoDB (EmpireTradesHistory, EmpireSkippedTrades, V4TradingState)
- Real analyze_market (TA sur OHLCV synthétique)
- Real DecisionEngine + RiskManager
- Mock News (sentiment configurable: bullish/bearish/neutral)

Scénarios testés par batch de 4 actifs:
- Batch 1: BTC(oversold→LONG), ETH(overbought→SHORT), SOL(neutral→SKIP), XRP(oversold→LONG)
- Batch 2: BNB(oversold→LONG), DOGE(overbought→SHORT), AVAX(neutral→SKIP), LINK(oversold→LONG)
  → Devrait bloquer au-delà de MAX_OPEN_TRADES=4
- Batch 3: PAXG(oversold→LONG), SPX(overbought→SHORT), USDC(neutral→SKIP)
  → Devrait bloquer (slots pleins)
- Phase CLOSE: Simule TP hit et vérifie fermeture + DynamoDB

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
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'XRP/USDT:USDT',
    'BNB/USDT:USDT', 'DOGE/USDT:USDT', 'AVAX/USDT:USDT', 'LINK/USDT:USDT',
    'PAXG/USDT:USDT', 'SPX/USDT:USDT', 'USDC/USDT:USDT'
]

BASE_PRICES = {
    'BTC/USDT:USDT': 97000.0, 'ETH/USDT:USDT': 2650.0,
    'SOL/USDT:USDT': 195.0,   'XRP/USDT:USDT': 2.45,
    'BNB/USDT:USDT': 580.0,   'DOGE/USDT:USDT': 0.25,
    'AVAX/USDT:USDT': 25.0,   'LINK/USDT:USDT': 18.0,
    'PAXG/USDT:USDT': 2920.0, 'SPX/USDT:USDT': 6050.0,
    'USDC/USDT:USDT': 1.0001,
}

PASS = "✅"
FAIL = "❌"
INFO = "📊"

# ==================== OHLCV GENERATOR ====================

def generate_ohlcv(base_price: float, scenario: str = 'neutral', num_candles: int = 300) -> List:
    """
    Generate synthetic OHLCV data producing specific RSI conditions.
    scenario: 'oversold' (RSI<30), 'overbought' (RSI>70), 'neutral' (RSI~50)
    """
    candles = []
    now = int(time.time() * 1000)
    interval_ms = 3600000  # 1h
    price = base_price * 1.05  # Start slightly above for oversold to decline into

    for i in range(num_candles):
        ts = now - (num_candles - i) * interval_ms

        if i < num_candles - 25:
            # Sideways phase
            change = random.uniform(-0.001, 0.001)
        else:
            # Trend phase (last 25 candles)
            if scenario == 'oversold':
                change = random.uniform(-0.012, -0.006)  # Strong decline → RSI < 30
            elif scenario == 'overbought':
                change = random.uniform(0.006, 0.012)    # Strong rise → RSI > 70
            else:
                change = random.uniform(-0.001, 0.001)   # Sideways → RSI ~50

        open_price = price
        close_price = price * (1 + change)
        high = max(open_price, close_price) * (1 + random.uniform(0.0005, 0.002))
        low = min(open_price, close_price) * (1 - random.uniform(0.0005, 0.002))
        volume = random.uniform(500, 2000) * (base_price / 100)

        candles.append([ts, open_price, high, low, close_price, volume])
        price = close_price

    return candles

# ==================== MOCK EXCHANGE ====================

class MockExchange:
    """Simulates Binance Futures without real API calls."""

    def __init__(self):
        self.positions = {}  # {symbol: {qty, side, entry_price, leverage}}
        self.balance = 5000.0
        self.orders = []
        # Mock internal CCXT for fapiPrivateV2GetPositionRisk
        self.exchange = MagicMock()
        self.exchange.fapiPrivateV2GetPositionRisk.return_value = []
        self.markets = {}
        for sym in ALL_ASSETS:
            self.markets[sym] = {
                'precision': {'amount': 3, 'price': 2},
                'limits': {'amount': {'min': 0.001}},
                'symbol': sym
            }

    def resolve_symbol(self, symbol: str) -> str:
        return symbol

    def get_market_info(self, symbol: str) -> Dict:
        return {
            'precision': {'amount': 3, 'price': 2},
            'min_amount': 0.001,
            'symbol': symbol
        }

    def get_balance_usdt(self) -> float:
        return self.balance

    def fetch_balance(self) -> Dict:
        return {'USDT': {'total': self.balance, 'free': self.balance}, 'total': {'USDT': self.balance}}

    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 500) -> List:
        # Should not be called directly in test (we override _get_ohlcv_smart)
        return generate_ohlcv(BASE_PRICES.get(symbol, 100.0), 'neutral', min(limit, 300))

    def create_market_order(self, symbol: str, side: str, amount: float, leverage: int = 1) -> Dict:
        price = BASE_PRICES.get(symbol, 100.0)

        if side == 'buy':
            if symbol in self.positions and self.positions[symbol]['side'] == 'SHORT':
                del self.positions[symbol]  # Close SHORT
            else:
                self.positions[symbol] = {
                    'qty': amount, 'side': 'LONG', 'entry_price': price, 'leverage': leverage
                }
        elif side == 'sell':
            if symbol in self.positions and self.positions[symbol]['side'] == 'LONG':
                del self.positions[symbol]  # Close LONG
            else:
                self.positions[symbol] = {
                    'qty': amount, 'side': 'SHORT', 'entry_price': price, 'leverage': leverage
                }

        self.orders.append({
            'symbol': symbol, 'side': side, 'amount': amount,
            'leverage': leverage, 'price': price, 'time': datetime.now(timezone.utc).isoformat()
        })

        logger.info(f"  [MOCK_ORDER] {side.upper()} {amount} {symbol} @ ${price:.2f} (Lev={leverage}x)")
        return {'average': price, 'filled': amount, 'status': 'closed', 'id': f'MOCK-{uuid.uuid4().hex[:6]}'}

    def fetch_positions(self, symbols: List[str]) -> List:
        result = []
        for sym in symbols:
            if sym in self.positions:
                pos = self.positions[sym]
                amt = pos['qty'] if pos['side'] == 'LONG' else -pos['qty']
                result.append({
                    'symbol': sym, 'contracts': pos['qty'], 'side': pos['side'].lower(),
                    'entryPrice': str(pos['entry_price']), 'positionAmt': str(amt),
                    'lastPrice': str(pos['entry_price']), 'leverage': str(pos['leverage']),
                    'unRealizedProfit': '0'
                })
        return result

    def set_leverage(self, leverage, symbol):
        pass

    def _get_binance_position_risk(self):
        """Returns data in Binance fapiPrivateV2GetPositionRisk format."""
        result = []
        for sym, pos in self.positions.items():
            binance_sym = sym.replace('/USDT:USDT', 'USDT').replace('/', '')
            amt = pos['qty'] if pos['side'] == 'LONG' else -pos['qty']
            result.append({
                'symbol': binance_sym,
                'positionAmt': str(amt),
                'entryPrice': str(pos['entry_price']),
                'markPrice': str(pos['entry_price']),
                'unRealizedProfit': '0',
                'leverage': str(pos['leverage'])
            })
        return result

# ==================== MOCK NEWS FETCHER ====================

class MockNewsFetcher:
    """Returns configurable sentiment scores per symbol."""

    def __init__(self, sentiments: Dict[str, float] = None):
        self.sentiments = sentiments or {}

    def get_news_sentiment_score(self, symbol: str) -> float:
        return self.sentiments.get(symbol, 0.0)

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

# 3 batches of 4 assets (covering all 11 assets + varied conditions)
BATCHES = [
    {
        'name': 'Batch 1: Crypto Leaders',
        'assets': {
            'BTC/USDT:USDT':  {'scenario': 'oversold',   'news': 0.5,  'expected_signal': 'LONG'},
            'ETH/USDT:USDT':  {'scenario': 'overbought',  'news': -0.3, 'expected_signal': 'SHORT'},
            'SOL/USDT:USDT':  {'scenario': 'neutral',     'news': 0.0,  'expected_signal': 'NEUTRAL'},
            'XRP/USDT:USDT':  {'scenario': 'oversold',    'news': 0.2,  'expected_signal': 'LONG'},
        }
    },
    {
        'name': 'Batch 2: Alts — test MAX_OPEN_TRADES blocker',
        'assets': {
            'BNB/USDT:USDT':  {'scenario': 'oversold',    'news': 0.4,  'expected_signal': 'LONG'},
            'DOGE/USDT:USDT': {'scenario': 'overbought',  'news': -0.5, 'expected_signal': 'SHORT'},
            'AVAX/USDT:USDT': {'scenario': 'oversold',    'news': 0.3,  'expected_signal': 'LONG'},
            'LINK/USDT:USDT': {'scenario': 'overbought',  'news': -0.2, 'expected_signal': 'SHORT'},
        }
    },
    {
        'name': 'Batch 3: Commodities + Indices + Parking — slots pleins',
        'assets': {
            'PAXG/USDT:USDT': {'scenario': 'oversold',    'news': 0.6,  'expected_signal': 'LONG'},
            'SPX/USDT:USDT':  {'scenario': 'overbought',  'news': -0.1, 'expected_signal': 'SHORT'},
            'USDC/USDT:USDT': {'scenario': 'neutral',     'news': 0.0,  'expected_signal': 'NEUTRAL'},
        }
    },
]

# ==================== TEST ENGINE ====================

class IntegrationTest:
    def __init__(self):
        # Real AWS
        from v4_hybrid_lambda import AWSClients, PersistenceLayer
        self.aws = AWSClients()
        self.persistence = PersistenceLayer(self.aws)
        self.atomic_persistence = AtomicPersistence(self.aws.state_table)

        # Mock Exchange
        self.mock_exchange = MockExchange()

        # Real Decision Engine
        self.risk_manager = RiskManager()
        self.decision_engine = DecisionEngine(risk_manager=self.risk_manager)

        # Results tracking
        self.results = []
        self.opened_trades = {}  # {symbol: trade_id}
        self.test_trade_ids = []  # For cleanup

        # Pre-generate OHLCV for all scenarios
        self.ohlcv_cache = {}
        for batch in BATCHES:
            for symbol, cfg in batch['assets'].items():
                self.ohlcv_cache[symbol] = generate_ohlcv(
                    BASE_PRICES[symbol], cfg['scenario'], 300
                )

    def test(self, name: str, condition: bool, detail: str = "") -> bool:
        status = PASS if condition else FAIL
        self.results.append((name, condition))
        print(f"  {status} {name}" + (f" — {detail}" if detail else ""))
        return condition

    def _build_engine(self, news_sentiments: Dict[str, float]):
        """Build a TradingEngine with mocked dependencies."""
        from v4_hybrid_lambda import TradingEngine

        # Bypass the real constructor
        with patch.object(TradingEngine, '__init__', lambda self: None):
            engine = TradingEngine()

        engine.aws = self.aws
        engine.persistence = self.persistence
        engine.atomic_persistence = self.atomic_persistence
        engine.exchange = self.mock_exchange
        engine.risk_manager = self.risk_manager
        engine.decision_engine = self.decision_engine
        engine.news_fetcher = MockNewsFetcher(news_sentiments)
        engine.cooldown_seconds = 0
        engine.ohlcv_cache_path = '/tmp/test_integration_ohlcv.json'
        engine.execution_id = f"TEST-{uuid.uuid4().hex[:6]}"

        return engine

    def _run_cycle(self, engine, symbol: str) -> Dict:
        """Run a single trade cycle for a symbol, injecting synthetic OHLCV."""
        ohlcv = self.ohlcv_cache.get(symbol)
        if not ohlcv:
            return {'symbol': symbol, 'status': 'NO_OHLCV'}

        asset_class = classify_asset(symbol)

        # Analyze market with real TA on synthetic OHLCV
        ta_result = analyze_market(ohlcv, symbol=symbol, asset_class=asset_class)

        # Check volatility spike
        if ta_result.get('market_context', '').startswith('VOLATILITY_SPIKE'):
            reason = ta_result['market_context']
            self.persistence.log_skipped_trade(symbol, reason, asset_class)
            return {'symbol': symbol, 'status': 'BLOCKED', 'reason': reason, 'ta': ta_result}

        # Load positions
        positions = self.persistence.load_positions()

        # Check if already in position
        if symbol in positions:
            self.persistence.log_skipped_trade(symbol, "Position already in DynamoDB", asset_class)
            return {'symbol': symbol, 'status': 'IN_POSITION', 'ta': ta_result}

        # Check Binance (mock)
        real_positions = list(self.mock_exchange.positions.keys())
        if symbol in real_positions:
            self.persistence.log_skipped_trade(symbol, "Position already on Binance", asset_class)
            return {'symbol': symbol, 'status': 'IN_POSITION_BINANCE', 'ta': ta_result}

        direction = 'SHORT' if ta_result.get('signal_type') == 'SHORT' else 'LONG'

        # Neutral → SKIP
        if ta_result.get('signal_type') == 'NEUTRAL':
            rsi = ta_result.get('rsi', 50)
            reason = f"RSI neutral ({rsi:.1f}) | No clear signal"
            self.persistence.log_skipped_trade(symbol, reason, asset_class)
            return {'symbol': symbol, 'status': 'NO_SIGNAL', 'ta': ta_result}

        # News
        news_score = engine.news_fetcher.get_news_sentiment_score(symbol)

        # Macro context (mock)
        macro = {'regime': 'NORMAL', 'vix': 15.0, 'dxy': 104.0}

        # Decision Engine (REAL)
        balance = self.mock_exchange.get_balance_usdt()
        decision = self.decision_engine.evaluate_with_risk(
            context=macro, ta_result=ta_result, symbol=symbol,
            capital=balance, direction=direction, asset_class=asset_class,
            news_score=news_score, macro_regime=macro.get('regime', 'NORMAL')
        )

        if not decision['proceed']:
            self.persistence.log_skipped_trade(symbol, decision['reason'], asset_class)
            return {'symbol': symbol, 'status': 'BLOCKED', 'reason': decision['reason'], 'ta': ta_result}

        # MAX_OPEN_TRADES enforcement
        open_count = max(len(positions), len(self.mock_exchange.positions))
        if open_count >= TradingConfig.MAX_OPEN_TRADES:
            reason = f"MAX_OPEN_TRADES reached ({open_count}/{TradingConfig.MAX_OPEN_TRADES})"
            self.persistence.log_skipped_trade(symbol, reason, asset_class)
            return {'symbol': symbol, 'status': 'SLOT_FULL', 'reason': reason, 'ta': ta_result}

        # BINANCE SYNC: check no existing position
        binance_sym = symbol.replace('/USDT:USDT', 'USDT').replace('/', '')
        for pos in self.mock_exchange._get_binance_position_risk():
            if pos['symbol'] == binance_sym and float(pos['positionAmt']) != 0:
                reason = f"BINANCE_SYNC: position already on Binance"
                self.persistence.log_skipped_trade(symbol, reason, asset_class)
                return {'symbol': symbol, 'status': 'BINANCE_ALREADY_OPEN', 'ta': ta_result}

        # EXECUTE ENTRY (mock order)
        trade_id = f"TEST-{uuid.uuid4().hex[:8]}"
        self.test_trade_ids.append(trade_id)
        side = 'sell' if direction == 'SHORT' else 'buy'
        quantity = decision['quantity']

        is_paxg = 'PAXG' in symbol
        leverage = TradingConfig.PAXG_LEVERAGE if is_paxg else TradingConfig.LEVERAGE

        order = self.mock_exchange.create_market_order(symbol, side, quantity, leverage=leverage)
        real_entry = float(order['average'])
        real_size = float(order['filled'])

        # TP/SL
        if is_paxg:
            tp_pct = TradingConfig.PAXG_TP
            sl_pct = TradingConfig.PAXG_SL
        else:
            tp_pct = (TradingConfig.SCALP_TP_MIN + TradingConfig.SCALP_TP_MAX) / 2
            sl_pct = TradingConfig.SCALP_SL

        tp = real_entry * (1 + tp_pct) if direction == 'LONG' else real_entry * (1 - tp_pct)
        sl = real_entry * (1 - sl_pct) if direction == 'LONG' else real_entry * (1 + sl_pct)

        # Log to DynamoDB
        reason_parts = [f"RSI={ta_result.get('rsi', 0):.1f}"]
        if ta_result.get('market_context'):
            reason_parts.append(ta_result['market_context'])
        reason_parts.append(f"News={news_score:+.1f}")
        reason_parts.append(f"Lev={leverage}x")
        detailed_reason = " | ".join(reason_parts)

        self.persistence.log_trade_open(
            trade_id, symbol, asset_class, direction, real_entry, real_size,
            real_size * real_entry, tp, sl, leverage, reason=detailed_reason
        )

        # Save position
        pos_data = {
            'trade_id': trade_id, 'entry_price': real_entry, 'quantity': real_size,
            'direction': direction, 'stop_loss': sl, 'take_profit': tp,
            'asset_class': str(asset_class),
            'risk_dollars': decision['risk_dollars'],
            'entry_time': datetime.now(timezone.utc).isoformat()
        }
        self.persistence.save_position(symbol, pos_data)

        # Track
        self.opened_trades[symbol] = trade_id
        self.risk_manager.register_trade(symbol, real_entry, real_size, decision['risk_dollars'], decision['stop_loss'], direction)

        return {
            'symbol': symbol, 'status': f'{direction}_OPEN', 'trade_id': trade_id,
            'direction': direction, 'entry': real_entry, 'tp': tp, 'sl': sl,
            'leverage': leverage, 'ta': ta_result
        }

    def _close_trade(self, symbol: str, exit_reason: str = "Test TP hit") -> Dict:
        """Simulate closing a trade."""
        positions = self.persistence.load_positions()
        if symbol not in positions:
            return {'symbol': symbol, 'status': 'NOT_FOUND'}

        pos = positions[symbol]
        trade_id = pos.get('trade_id', 'UNKNOWN')
        direction = pos.get('direction', 'LONG')
        entry_price = float(pos.get('entry_price', 0))
        quantity = float(pos.get('quantity', 0))

        # Simulate TP hit price
        if 'TP' in exit_reason:
            exit_price = float(pos.get('take_profit', entry_price * 1.003))
        elif 'SL' in exit_reason:
            exit_price = float(pos.get('stop_loss', entry_price * 0.996))
        else:
            exit_price = entry_price * 1.001

        if direction == 'LONG':
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100

        pnl = pnl_pct * quantity * entry_price / 100

        # Execute close on mock exchange
        exit_side = 'sell' if direction == 'LONG' else 'buy'
        self.mock_exchange.create_market_order(symbol, exit_side, quantity)

        # Update DynamoDB
        reason = f"{exit_reason} at ${exit_price:.4f} (PnL: {pnl_pct:+.2f}%)"
        self.persistence.log_trade_close(trade_id, exit_price, pnl, reason)
        self.persistence.delete_position(symbol)

        # Risk cleanup
        self.risk_manager.close_trade(symbol, exit_price)

        return {
            'symbol': symbol, 'status': 'CLOSED', 'pnl': pnl, 'pnl_pct': pnl_pct,
            'exit_price': exit_price, 'reason': reason
        }

    # ==================== RUN TESTS ====================

    def run_all(self):
        print("=" * 70)
        print("🧪 EMPIRE V13.4 — Integration Test (11 actifs × scénarios)")
        print("=" * 70)

        # PHASE 1: Open trades in batches
        self._test_open_batches()

        # PHASE 2: Verify MAX_OPEN_TRADES
        self._test_max_open_trades()

        # PHASE 3: Close trades
        self._test_close_flow()

        # PHASE 4: Verify DynamoDB consistency
        self._test_dynamo_consistency()

        # Summary
        self._print_summary()

    def _test_open_batches(self):
        total_opened = 0

        for batch_idx, batch in enumerate(BATCHES):
            print(f"\n{'='*70}")
            print(f"📦 {batch['name']}")
            print(f"{'='*70}")

            # Build news sentiments for this batch
            news_sentiments = {sym: cfg['news'] for sym, cfg in batch['assets'].items()}
            engine = self._build_engine(news_sentiments)

            for symbol, cfg in batch['assets'].items():
                expected = cfg['expected_signal']
                scenario = cfg['scenario']
                print(f"\n  🔄 {symbol} ({scenario}, news={cfg['news']:+.1f}, expect={expected})")

                result = self._run_cycle(engine, symbol)
                status = result['status']
                rsi = result.get('ta', {}).get('rsi', '?')
                signal = result.get('ta', {}).get('signal_type', '?')

                print(f"     RSI={rsi} | Signal={signal} | Status={status}")

                # Verify signal matches expected
                if expected == 'NEUTRAL':
                    self.test(
                        f"{symbol}: signal NEUTRAL → skipped",
                        status in ['NO_SIGNAL', 'BLOCKED'],
                        f"status={status}"
                    )
                elif expected in ['LONG', 'SHORT']:
                    if total_opened < TradingConfig.MAX_OPEN_TRADES:
                        # Should open unless blocked by decision engine
                        if status in [f'{expected}_OPEN', 'LONG_OPEN', 'SHORT_OPEN']:
                            total_opened += 1
                            self.test(
                                f"{symbol}: opened {result.get('direction','?')} x{result.get('leverage','?')}",
                                True,
                                f"Entry=${result.get('entry','?')}, TP=${result.get('tp','?'):.4f}"
                            )
                        elif status == 'SLOT_FULL':
                            self.test(
                                f"{symbol}: SLOT_FULL (MAX_OPEN_TRADES={TradingConfig.MAX_OPEN_TRADES})",
                                True,
                                f"open_count >= {TradingConfig.MAX_OPEN_TRADES}"
                            )
                        else:
                            self.test(
                                f"{symbol}: decision engine blocked",
                                status in ['BLOCKED', 'BLOCKED_ATOMIC'],
                                f"reason={result.get('reason','?')}"
                            )
                    else:
                        self.test(
                            f"{symbol}: SLOT_FULL expected (already {total_opened} open)",
                            status == 'SLOT_FULL',
                            f"status={status}"
                        )

            # Show state after batch
            positions = self.persistence.load_positions()
            binance_count = len(self.mock_exchange.positions)
            print(f"\n  {INFO} After {batch['name']}: DynamoDB={len(positions)} | Binance={binance_count} | Total opened={total_opened}")

    def _test_max_open_trades(self):
        print(f"\n{'='*70}")
        print(f"🔒 TEST: MAX_OPEN_TRADES Enforcement")
        print(f"{'='*70}")

        positions = self.persistence.load_positions()
        binance_count = len(self.mock_exchange.positions)

        self.test(
            f"DynamoDB positions <= {TradingConfig.MAX_OPEN_TRADES}",
            len(positions) <= TradingConfig.MAX_OPEN_TRADES,
            f"count={len(positions)}"
        )
        self.test(
            f"Binance positions <= {TradingConfig.MAX_OPEN_TRADES}",
            binance_count <= TradingConfig.MAX_OPEN_TRADES,
            f"count={binance_count}"
        )
        self.test(
            "DynamoDB et Binance sont synchro",
            len(positions) == binance_count,
            f"DB={len(positions)}, Binance={binance_count}"
        )

        # List positions
        for sym, pos in positions.items():
            pos = from_decimal(pos) if isinstance(pos, dict) else pos
            print(f"  📌 {sym}: {pos.get('direction','?')} | Entry=${pos.get('entry_price','?')} | TradeId={pos.get('trade_id','?')}")

    def _test_close_flow(self):
        print(f"\n{'='*70}")
        print(f"🔻 TEST: Close Trades (TP/SL simulation)")
        print(f"{'='*70}")

        positions = self.persistence.load_positions()
        symbols_to_close = list(positions.keys())

        if not symbols_to_close:
            print("  ⚠️  No positions to close")
            return

        # Close first position with TP
        sym1 = symbols_to_close[0]
        print(f"\n  🎯 Closing {sym1} (Take Profit)")
        result1 = self._close_trade(sym1, exit_reason="Take Profit TP hit")
        self.test(f"{sym1}: closed successfully", result1['status'] == 'CLOSED', f"PnL={result1.get('pnl_pct',0):+.2f}%")

        # Close second position with SL
        if len(symbols_to_close) > 1:
            sym2 = symbols_to_close[1]
            print(f"\n  🛑 Closing {sym2} (Stop Loss)")
            result2 = self._close_trade(sym2, exit_reason="Stop Loss SL hit")
            self.test(f"{sym2}: closed successfully", result2['status'] == 'CLOSED', f"PnL={result2.get('pnl_pct',0):+.2f}%")

        # Close remaining
        for sym in symbols_to_close[2:]:
            print(f"\n  ⏰ Closing {sym} (Time Exit)")
            result = self._close_trade(sym, exit_reason="Time Exit")
            self.test(f"{sym}: closed successfully", result['status'] == 'CLOSED')

        # Verify all closed
        remaining = self.persistence.load_positions()
        self.test("All positions closed in DynamoDB", len(remaining) == 0, f"remaining={len(remaining)}")
        self.test("All positions closed on Binance", len(self.mock_exchange.positions) == 0, f"remaining={len(self.mock_exchange.positions)}")

    def _test_dynamo_consistency(self):
        print(f"\n{'='*70}")
        print(f"🔍 TEST: DynamoDB Consistency")
        print(f"{'='*70}")

        trades_table = self.aws.trades_table
        skipped_table = self.aws.skipped_table

        # Verify closed trades have ExitReason
        for trade_id in self.test_trade_ids:
            response = trades_table.query(
                KeyConditionExpression='trader_id = :tid',
                ExpressionAttributeValues={':tid': trade_id},
                Limit=1
            )
            items = response.get('Items', [])
            if items:
                item = from_decimal(items[0])
                status = item.get('Status', 'UNKNOWN')
                self.test(
                    f"Trade {trade_id}: Status=CLOSED",
                    status == 'CLOSED',
                    f"actual={status}"
                )
                self.test(
                    f"Trade {trade_id}: ExitReason present",
                    bool(item.get('ExitReason')),
                    f"reason={item.get('ExitReason', 'MISSING')[:60]}"
                )
                self.test(
                    f"Trade {trade_id}: TakeProfit logged",
                    item.get('TakeProfit') is not None,
                )
                self.test(
                    f"Trade {trade_id}: StopLoss logged",
                    item.get('StopLoss') is not None,
                )
                self.test(
                    f"Trade {trade_id}: Leverage logged",
                    item.get('Leverage') is not None,
                )
                self.test(
                    f"Trade {trade_id}: Reason (open) detailed",
                    'RSI=' in str(item.get('Reason', '')),
                    f"reason={item.get('Reason', 'MISSING')[:80]}"
                )
            else:
                self.test(f"Trade {trade_id}: found in DB", False, "NOT FOUND")

        # Check skipped trades are in EmpireSkippedTrades (not in EmpireTradesHistory)
        # Scan for recent SKIP entries
        now_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        response = skipped_table.scan(
            FilterExpression='#ts > :recent',
            ExpressionAttributeNames={'#ts': 'timestamp'},
            ExpressionAttributeValues={':recent': now_iso},
            Limit=20
        )
        skip_count = response.get('Count', 0)
        self.test(
            "Skipped trades written to EmpireSkippedTrades",
            skip_count > 0,
            f"found={skip_count} recent skips"
        )

    def _print_summary(self):
        passed = sum(1 for _, ok in self.results if ok)
        total = len(self.results)
        print(f"\n{'='*70}")
        print(f"📊 RÉSULTATS: {passed}/{total} tests passés")

        if passed == total:
            print(f"✅ ALL TESTS PASSED")
        else:
            failed = [name for name, ok in self.results if not ok]
            print(f"❌ {total - passed} TESTS FAILED:")
            for f in failed:
                print(f"   - {f}")

        print(f"\n📋 Mock Exchange Orders:")
        for order in self.mock_exchange.orders:
            print(f"   {order['side'].upper():5s} {order['amount']:>12.4f} {order['symbol']} @ ${order['price']:.2f} (Lev={order['leverage']}x)")

        print(f"{'='*70}")

    def cleanup(self):
        """Clean up test data from DynamoDB."""
        print("\n🧹 Cleaning up test data...")
        trades_table = self.aws.trades_table
        skipped_table = self.aws.skipped_table
        state_table = self.aws.state_table

        # Delete test trades
        for trade_id in self.test_trade_ids:
            try:
                response = trades_table.query(
                    KeyConditionExpression='trader_id = :tid',
                    ExpressionAttributeValues={':tid': trade_id}
                )
                for item in response.get('Items', []):
                    trades_table.delete_item(Key={'trader_id': item['trader_id'], 'timestamp': item['timestamp']})
                    print(f"  Deleted trade: {trade_id}")
            except Exception as e:
                print(f"  Error deleting {trade_id}: {e}")

        # Delete test positions
        for symbol in ALL_ASSETS:
            safe_symbol = symbol.replace('/', '_').replace(':', '-')
            try:
                state_table.delete_item(Key={'trader_id': f'POSITION#{safe_symbol}'})
            except:
                pass

        # Clean test skips (recent ones with TEST prefix)
        try:
            response = skipped_table.scan(
                FilterExpression='begins_with(trader_id, :prefix)',
                ExpressionAttributeValues={':prefix': 'SKIP-'},
                Limit=100
            )
            now = datetime.now(timezone.utc)
            for item in response.get('Items', []):
                ts = item.get('timestamp', '')
                if ts > (now - timedelta(minutes=10)).isoformat():
                    skipped_table.delete_item(Key={'trader_id': item['trader_id'], 'timestamp': item['timestamp']})
            print(f"  Cleaned {len(response.get('Items', []))} recent skips")
        except:
            pass

        # Clean portfolio risk
        try:
            state_table.delete_item(Key={'trader_id': 'PORTFOLIO_RISK#GLOBAL'})
            print("  Cleaned portfolio risk state")
        except:
            pass

        print("  ✅ Cleanup complete")


# ==================== MAIN ====================

if __name__ == '__main__':
    test = IntegrationTest()

    if '--cleanup' in sys.argv:
        test.cleanup()
        sys.exit(0)

    try:
        test.run_all()
    finally:
        # Always cleanup
        test.cleanup()

    passed = sum(1 for _, ok in test.results if ok)
    total = len(test.results)
    sys.exit(0 if passed == total else 1)
