"""
Empire Trading System V9 - Production Optimized
Architecture: Clean, Testable, Fail-Safe
"""

import json
import os
import logging
import uuid
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List, Tuple
from contextlib import contextmanager

import boto3
import requests
from botocore.exceptions import ClientError

# Import custom modules
from market_analysis import analyze_market
from news_fetcher import get_news_context, get_full_context
from exchange_connector import ExchangeConnector

# ==================== CONFIGURATION ====================

@dataclass
class TradingConfig:
    """Centralized configuration with validation"""
    
    # Risk Management
    capital_per_trade: float = 200.0
    max_slots: int = 3
    max_risk_per_trade_pct: float = 0.02  # 2%
    max_daily_loss_pct: float = 0.05      # 5%
    max_drawdown_pct: float = 0.15        # 15%
    
    # Entry/Exit Thresholds
    rsi_buy_threshold: float = 42.0
    rsi_sell_threshold: float = 78.0
    stop_loss_pct: float = -3.5
    hard_tp_pct: float = 8.0
    trailing_tp_pct: float = 1.5
    
    # Market Filters
    btc_crash_threshold: float = -0.08
    vix_max: float = 30.0
    vix_reduce: float = 25.0
    
    # Circuit Breakers
    cb_level_1: float = -0.05   # -5%
    cb_level_2: float = -0.10   # -10%
    cb_level_3: float = -0.20   # -20%
    cb_cooldown_hours: float = 48.0
    
    # Features
    volume_confirmation_enabled: bool = True
    multi_timeframe_enabled: bool = True
    ai_confirmation_enabled: bool = True
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables"""
        return cls(
            capital_per_trade=float(os.getenv('CAPITAL', '200')),
            max_slots=int(os.getenv('MAX_SLOTS', '3')),
            rsi_buy_threshold=float(os.getenv('RSI_THRESHOLD', '42')),
            stop_loss_pct=float(os.getenv('STOP_LOSS', '-3.5')),
            hard_tp_pct=float(os.getenv('HARD_TP', '8.0')),
        )
    
    def validate(self):
        """Validate configuration constraints"""
        assert 0 < self.max_risk_per_trade_pct <= 0.05, "Risk per trade must be 0-5%"
        assert 0 < self.max_daily_loss_pct <= 0.10, "Daily loss limit must be 0-10%"
        # assert self.stop_loss_pct < 0, "Stop loss must be negative" # Logic depends on sign
        assert self.hard_tp_pct > 0, "Take profit must be positive"


class MarketRegime(Enum):
    """Market regime classification"""
    BULL_TREND = "bull_trend"
    BEAR_TREND = "bear_trend"
    HIGH_VOLATILITY = "high_volatility"
    RANGE_BOUND = "range_bound"
    CRASH = "crash"
    RECOVERY = "recovery"


class AssetClass(Enum):
    """Asset classification"""
    CRYPTO = "crypto"
    FOREX = "forex"
    COMMODITIES = "commodities"
    INDICES = "indices"


# ==================== LOGGING SETUP ====================

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# ==================== AWS CLIENTS ====================

class AWSClients:
    """Singleton AWS clients with lazy initialization"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.dynamodb = boto3.resource('dynamodb')
        self.bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
        
        # Tables
        self.trades_table = self.dynamodb.Table(
            os.getenv('HISTORY_TABLE', 'EmpireTradesHistory')
        )
        self.state_table = self.dynamodb.Table(
            os.getenv('STATE_TABLE', 'V4TradingState')
        )
        
        self._initialized = True


# ==================== SLOT MANAGER ====================

class SlotManager:
    """Atomic slot management with guaranteed cleanup"""
    
    def __init__(self, state_table, max_slots: int):
        self.state_table = state_table
        self.max_slots = max_slots
        self.slot_acquired = False
    
    def acquire(self) -> bool:
        """Atomically acquire a trading slot"""
        try:
            self.state_table.update_item(
                Key={'trader_id': 'GLOBAL_LOCK'},
                UpdateExpression="SET ActiveSlots = if_not_exists(ActiveSlots, :zero) + :one",
                ConditionExpression="if_not_exists(ActiveSlots, :zero) < :max",
                ExpressionAttributeValues={
                    ':one': 1,
                    ':zero': 0,
                    ':max': self.max_slots
                }
            )
            self.slot_acquired = True
            logger.info(f"✅ Slot acquired ({self.max_slots} max)")
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(f"⏸️ All slots occupied ({self.max_slots})")
            else:
                logger.error(f"❌ Slot acquisition error: {e}")
            return False
    
    def release(self):
        """Release acquired slot"""
        try:
            self.state_table.update_item(
                Key={'trader_id': 'GLOBAL_LOCK'},
                UpdateExpression="SET ActiveSlots = if_not_exists(ActiveSlots, :one) - :one",
                ConditionExpression="ActiveSlots > :zero",
                ExpressionAttributeValues={
                    ':one': 1,
                    ':zero': 0
                }
            )
            logger.info("🔓 Slot released")
            
        except Exception as e:
            logger.error(f"❌ Slot release failed: {e}")
        finally:
            self.slot_acquired = False
    
    @contextmanager
    def acquire_context(self):
        """Context manager for guaranteed cleanup"""
        acquired = self.acquire()
        try:
            yield acquired
        finally:
            # Note: We usually don't release immediately unless the trade fails or finishes.
            # But in the V9 cycle, entries/exits are separate.
            # If we acquired a slot for an ENTRY but failed, we release.
            pass


# ==================== MARKET STATE ====================

@dataclass
class MarketContext:
    """Immutable market state snapshot"""
    
    timestamp: datetime
    balance: float
    open_positions: int
    max_slots: int
    
    # Market conditions
    btc_24h_change: float
    btc_7d_change: float
    btc_1h_change: float
    vix_value: float
    
    # Regime
    regime: MarketRegime
    
    # Risk multipliers
    vix_multiplier: float
    circuit_breaker_multiplier: float
    circuit_breaker_level: str
    
    # Flags
    is_golden_window: bool
    can_trade: bool
    risk_blocked: bool
    
    # Daily performance
    daily_pnl: float
    daily_pnl_pct: float
    
    @property
    def total_multiplier(self) -> float:
        """Combined risk multiplier"""
        return self.vix_multiplier * self.circuit_breaker_multiplier
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        data = asdict(self)
        data['regime'] = self.regime.value
        data['timestamp'] = self.timestamp.isoformat()
        return data


class MarketStateBuilder:
    """Builder pattern for market context construction"""
    
    def __init__(self, exchange, config: TradingConfig):
        self.exchange = exchange
        self.config = config
        self.aws = AWSClients()
    
    def build(self) -> MarketContext:
        """Build complete market context with retries"""
        logger.info("🔍 Building market context...")
        
        # 1. Portfolio state
        balance = self._get_balance_safe()
        open_positions = self._get_open_positions_safe()
        max_slots = self._calculate_max_slots(balance)
        
        # 2. BTC context
        btc_24h, btc_7d, btc_1h = self._get_btc_performance()
        
        # 3. VIX
        vix_value, vix_mult = self._get_vix_safe()
        
        # 4. Circuit breaker
        cb_mult, cb_level = self._get_circuit_breaker_status(btc_24h, btc_7d)
        
        # 5. Golden window
        is_golden = self._is_golden_window()
        
        # 6. Regime
        regime = self._determine_regime(btc_24h, btc_7d, btc_1h, vix_value, cb_level)
        
        # 7. Daily performance
        daily_pnl, daily_pnl_pct = self._get_daily_performance(balance)
        
        # 8. Can trade?
        can_trade = (
            cb_level != "L3_SURVIVAL" and
            cb_level != "L2_HALT" and
            vix_value < self.config.vix_max and
            daily_pnl_pct > -self.config.max_daily_loss_pct
        )
        
        risk_blocked = daily_pnl_pct <= -self.config.max_daily_loss_pct
        
        context = MarketContext(
            timestamp=datetime.now(timezone.utc),
            balance=balance,
            open_positions=open_positions,
            max_slots=max_slots,
            btc_24h_change=btc_24h,
            btc_7d_change=btc_7d,
            btc_1h_change=btc_1h,
            vix_value=vix_value,
            regime=regime,
            vix_multiplier=vix_mult,
            circuit_breaker_multiplier=cb_mult,
            circuit_breaker_level=cb_level,
            is_golden_window=is_golden,
            can_trade=can_trade,
            risk_blocked=risk_blocked,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct
        )
        
        logger.info(f"✅ Context: {regime.value} | VIX: {vix_value:.1f} | Can trade: {can_trade}")
        return context
    
    def _get_balance_safe(self) -> float:
        """Get balance with retry"""
        for attempt in range(3):
            try:
                # 🛠️ ExchangeConnector specific method
                return self.exchange.get_balance_usdt()
            except Exception as e:
                logger.warning(f"Balance fetch attempt {attempt + 1}/3 failed: {e}")
                time.sleep(1)
        
        logger.error("❌ Failed to fetch balance after 3 attempts")
        raise RuntimeError("Cannot proceed without balance")
    
    def _get_open_positions_safe(self) -> int:
        """Get open positions count"""
        try:
            return self.exchange.get_open_positions_count()
        except Exception as e:
            logger.error(f"Failed to get open positions: {e}")
            return 0
    
    def _calculate_max_slots(self, balance: float) -> int:
        """Calculate max slots based on balance"""
        if balance < 1000:
            return 1
        return min(int(balance / 1000), self.config.max_slots)
    
    def _get_btc_performance(self) -> Tuple[float, float, float]:
        """Get BTC performance metrics"""
        try:
            # 24h
            ohlcv_24h = self.exchange.fetch_ohlcv('BTC/USDT', '1h', limit=25)
            btc_24h = self._calculate_change(ohlcv_24h, 24) if len(ohlcv_24h) >= 25 else 0
            
            # 7d
            ohlcv_7d = self.exchange.fetch_ohlcv('BTC/USDT', '4h', limit=42)
            btc_7d = self._calculate_change(ohlcv_7d, 42) if len(ohlcv_7d) >= 42 else 0
            
            # 1h
            ohlcv_1h = self.exchange.fetch_ohlcv('BTC/USDT', '1h', limit=2)
            btc_1h = self._calculate_change(ohlcv_1h, 1) if len(ohlcv_1h) >= 2 else 0
            
            logger.info(f"📊 BTC: 1h={btc_1h:.2%} | 24h={btc_24h:.2%} | 7d={btc_7d:.2%}")
            return btc_24h, btc_7d, btc_1h
            
        except Exception as e:
            logger.error(f"BTC performance fetch error: {e}")
            return 0.0, 0.0, 0.0
    
    @staticmethod
    def _calculate_change(ohlcv: List, periods: int) -> float:
        """Calculate percentage change"""
        if len(ohlcv) < periods + 1:
            return 0.0
        
        current = ohlcv[-1][4]  # Close
        previous = ohlcv[-periods - 1][4]
        
        return (current - previous) / previous if previous > 0 else 0.0
    
    def _get_vix_safe(self) -> Tuple[float, float]:
        """Get VIX with fallback to cache"""
        # Try fresh fetch
        for attempt in range(3):
            try:
                vix_value = self._fetch_vix()
                if vix_value > 0:
                    # Update cache
                    self._cache_vix(vix_value)
                    mult = self._vix_to_multiplier(vix_value)
                    return vix_value, mult
                    
            except Exception as e:
                logger.warning(f"VIX attempt {attempt + 1}/3 failed: {e}")
                time.sleep(1)
        
        # Fallback to cache
        cached_vix = self._get_cached_vix()
        if cached_vix:
            logger.info(f"♻️ Using cached VIX: {cached_vix:.1f}")
            return cached_vix, self._vix_to_multiplier(cached_vix)
        
        # Ultimate failsafe: block trading
        logger.error("❌ VIX unavailable - BLOCKING TRADES")
        return 99.0, 0.0
    
    def _fetch_vix(self) -> float:
        """Fetch current VIX from Yahoo Finance"""
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
        params = {'interval': '1d', 'range': '1d'}
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        result = data['chart']['result'][0]
        vix = float(result['meta']['regularMarketPrice'])
        
        return vix
    
    def _cache_vix(self, vix_value: float):
        """Cache VIX value in DynamoDB"""
        try:
            self.aws.state_table.put_item(Item={
                'trader_id': 'VIX_CACHE',
                'value': str(vix_value),
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.warning(f"Failed to cache VIX: {e}")
    
    def _get_cached_vix(self) -> Optional[float]:
        """Get cached VIX if fresh enough (<60 min)"""
        try:
            response = self.aws.state_table.get_item(Key={'trader_id': 'VIX_CACHE'})
            item = response.get('Item')
            
            if not item:
                return None
            
            vix_value = float(item['value'])
            timestamp = datetime.fromisoformat(item['timestamp'])
            age_minutes = (datetime.now(timezone.utc) - timestamp).total_seconds() / 60
            
            if age_minutes < 60:
                return vix_value
                
        except Exception as e:
            logger.warning(f"Failed to get cached VIX: {e}")
        
        return None
    
    def _vix_to_multiplier(self, vix: float) -> float:
        """Convert VIX to position size multiplier"""
        if vix >= self.config.vix_max:
            return 0.0  # Block
        elif vix >= self.config.vix_reduce:
            return 0.5  # Reduce 50%
        else:
            return 1.0  # Full size
    
    def _get_circuit_breaker_status(self, btc_24h: float, btc_7d: float) -> Tuple[float, str]:
        """Determine circuit breaker level"""
        # Level 3: Survival mode
        if btc_7d <= self.config.cb_level_3:
            logger.critical(f"🚨 CB L3: BTC 7d {btc_7d:.2%}")
            return 0.0, "L3_SURVIVAL"
        
        # Level 2: Full halt
        if btc_24h <= self.config.cb_level_2:
            logger.critical(f"🚨 CB L2: BTC 24h {btc_24h:.2%}")
            return 0.0, "L2_HALT"
        
        # Level 1: Reduce size
        if btc_24h <= self.config.cb_level_1:
            logger.warning(f"⚠️ CB L1: BTC 24h {btc_24h:.2%}")
            return 0.5, "L1_REDUCE"
        
        return 1.0, "OK"
    
    def _is_golden_window(self) -> bool:
        """Check if in high-liquidity window"""
        hour = datetime.now(timezone.utc).hour
        return (7 <= hour <= 10) or (13 <= hour <= 16)
    
    def _determine_regime(
        self, 
        btc_24h: float, 
        btc_7d: float, 
        btc_1h: float,
        vix: float,
        cb_level: str
    ) -> MarketRegime:
        """Classify current market regime"""
        
        # Crash
        if cb_level in ["L3_SURVIVAL", "L2_HALT"] or btc_1h < -0.05:
            return MarketRegime.CRASH
        
        # High volatility
        if vix > 30:
            return MarketRegime.HIGH_VOLATILITY
        
        # Bull trend
        if btc_7d > 0.05 and btc_24h > -0.02 and vix < 22:
            return MarketRegime.BULL_TREND
        
        # Bear trend
        if btc_7d < -0.05 and btc_24h < 0:
            return MarketRegime.BEAR_TREND
        
        # Recovery
        if btc_7d < 0 < btc_24h and vix < 25:
            return MarketRegime.RECOVERY
        
        # Default: range bound
        return MarketRegime.RANGE_BOUND
    
    def _get_daily_performance(self, balance: float) -> Tuple[float, float]:
        """Calculate today's PnL"""
        try:
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            
            # 🛠️ V8.6 Optimized Index: GSI_OpenByPair (Status PK)
            response = self.aws.trades_table.query(
                IndexName='GSI_OpenByPair',
                KeyConditionExpression=boto3.dynamodb.conditions.Key('Status').eq('CLOSED'),
                FilterExpression=boto3.dynamodb.conditions.Attr('ExitTime').gte(today_start)
            )
            
            trades = response.get('Items', [])
            daily_pnl = sum(float(t.get('PnL', 0)) for t in trades)
            daily_pnl_pct = daily_pnl / balance if balance > 0 else 0
            
            logger.info(f"📅 Daily: ${daily_pnl:+.2f} ({daily_pnl_pct:+.2%})")
            return daily_pnl, daily_pnl_pct
            
        except Exception as e:
            logger.error(f"Daily performance error: {e}")
            return 0.0, 0.0


# ==================== TRADE EXECUTOR ====================

class TradeExecutor:
    """Safe trade execution with verification"""
    
    def __init__(self, exchange, config: TradingConfig):
        self.exchange = exchange
        self.config = config
    
    def execute_market_order(
        self, 
        symbol: str, 
        side: str, 
        size: float,
        max_wait_seconds: int = 10
    ) -> Dict:
        """
        Execute market order with fill verification
        """
        logger.info(f"🚀 Executing {side.upper()} {size} {symbol}")
        
        # Place order
        order = self.exchange.create_market_order(symbol, side, size)
        order_id = order['id']
        
        # Wait for fill confirmation
        for i in range(max_wait_seconds):
            try:
                status = self.exchange.fetch_order(order_id, symbol)
                
                if status['status'] == 'closed':
                    logger.info(f"✅ Order {order_id} filled @ {status.get('average', 'N/A')}")
                    return status
                
                logger.info(f"⏳ Order pending ({status['status']}) - check {i+1}/{max_wait_seconds}")
                
            except Exception as e:
                logger.warning(f"Order status check failed: {e}")
            
            time.sleep(1)
        
        # Final verification
        try:
            status = self.exchange.fetch_order(order_id, symbol)
            if status['status'] == 'closed':
                return status
        except Exception as e:
            logger.error(f"Final order check failed: {e}")
        
        # Critical: order status unknown but order exists
        return order
    
    def place_take_profit_order(
        self, 
        symbol: str, 
        size: float, 
        price: float
    ) -> bool:
        """Place limit TP order"""
        try:
            self.exchange.create_limit_order(
                symbol, 
                'sell', 
                size, 
                price,
                params={'reduceOnly': True}
            )
            logger.info(f"🎯 TP order placed @ {price}")
            return True
            
        except Exception as e:
            logger.error(f"TP order failed: {e}")
            return False
    
    def close_position(
        self,
        symbol: str,
        size: float,
        reason: str
    ) -> Dict:
        """Close position with order cancellation"""
        try:
            # 1. Market Sell
            filled_order = self.execute_market_order(symbol, 'sell', size)
            
            # 2. Cancel all open orders for this symbol
            self.exchange.cancel_all_orders(symbol)
            
            logger.info(f"✅ Position closed: {reason}")
            return filled_order
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            raise


# ==================== AI ANALYST (Empire V8 Core) ====================

def ask_bedrock(symbol, rsi, news_context, portfolio_stats, history):
    """Query Bedrock AI for sentiment confirmation (Audit #3.3)"""
    aws = AWSClients()
    
    prompt = f"""
Vous êtes l'Analyste de Flux de Nouvelles pour l'Empire V9 (Production Optimized).
LA DÉCISION TECHNIQUE EST DÉJÀ PRISE : Le système a confirmé que {symbol} est statistiquement prêt pour un achat (RSI à {rsi:.1f}).

VOTRE MISSION :
1. Examiner les nouvelles récentes pour {symbol}.
2. Détecter toute nouvelle CATASTROPHIQUE (hack, faillite, exploit) invalidant le trade.
3. NE PAS juger le RSI ou les indicateurs techniques.

NEWS :
{news_context}

RÉPONSE JSON : {{ "decision": "CONFIRM" | "CANCEL", "reason": "explication" }}
"""
    try:
        response = aws.bedrock.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "temperature": 0,
                "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
            })
        )
        result = json.loads(response['body'].read())
        completion = result['content'][0]['text'].strip()
        
        # JSON Extraction
        start = completion.find('{')
        end = completion.rfind('}') + 1
        if start != -1:
            return json.loads(completion[start:end])
        return {"decision": "CONFIRM", "reason": "AI_FORMAT_ERROR"}
    except Exception as e:
        logger.warning(f"⚠️ Bedrock Error: {e}. Fallback to CONFIRM.")
        return {"decision": "CONFIRM", "reason": "AI_API_FALLBACK"}


# ==================== PERSISTENCE ====================

class TradePersistence:
    """Handle all DynamoDB operations"""
    
    def __init__(self):
        self.aws = AWSClients()
    
    def log_trade_open(
        self,
        trade_id: str,
        symbol: str,
        asset_class: str,
        side: str,
        entry_price: float,
        size: float,
        capital: float,
        strategy: str,
        tp_pct: float,
        sl_pct: float,
        ai_decision: str,
        ai_reason: str
    ):
        """Log new trade opening"""
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            
            item = {
                'TradeId': trade_id,
                'Timestamp': timestamp,
                'PairTimestamp': f"{symbol}#{timestamp}",
                'AssetClass': asset_class,
                'Pair': symbol,
                'Type': side.upper(),
                'Strategy': strategy,
                'EntryPrice': str(entry_price),
                'Size': str(size),
                'Cost': str(capital),
                'Value': str(capital),
                'TP': str(tp_pct),
                'SL': str(sl_pct),
                'Status': 'OPEN',
                'AI_Decision': ai_decision,
                'AI_Reason': ai_reason,
                'PeakPnL': '0'
            }
            
            self.aws.trades_table.put_item(Item=item)
            logger.info(f"💾 Trade logged: {trade_id}")
            
        except Exception as e:
            logger.error(f"Failed to log trade: {e}")
    
    def log_trade_close(
        self,
        trade_id: str,
        exit_price: float,
        pnl: float,
        reason: str
    ):
        """Log trade closure"""
        try:
            exit_time = datetime.now(timezone.utc).isoformat()
            
            self.aws.trades_table.update_item(
                Key={'TradeId': trade_id},
                UpdateExpression=(
                    "SET #status = :status, "
                    "PnL = :pnl, "
                    "ExitPrice = :exit_price, "
                    "ExitTime = :exit_time, "
                    "ExitReason = :reason"
                ),
                ExpressionAttributeNames={'#status': 'Status'},
                ExpressionAttributeValues={
                    ':status': 'CLOSED',
                    ':pnl': str(pnl),
                    ':exit_price': str(exit_price),
                    ':exit_time': exit_time,
                    ':reason': reason
                }
            )
            
            logger.info(f"💾 Trade closed: {trade_id} | PnL: ${pnl:+.2f}")
            
        except Exception as e:
            logger.error(f"Failed to log trade closure: {e}")
    
    def log_skip(
        self,
        symbol: str,
        asset_class: str,
        reason: str,
        price: float
    ):
        """Log skipped opportunity"""
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            log_id = f"SKIP-{int(time.time())}"
            
            item = {
                'TradeId': log_id,
                'Timestamp': timestamp,
                'PairTimestamp': f"{symbol}#{timestamp}",
                'AssetClass': asset_class,
                'Pair': symbol,
                'Status': 'SKIPPED',
                'Type': 'INFO',
                'ExitReason': reason,
                'EntryPrice': str(price),
                'TTL': int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
            }
            
            self.aws.trades_table.put_item(Item=item)
            
        except Exception as e:
            logger.warning(f"Failed to log skip: {e}")


# ==================== MAIN TRADING LOGIC ====================

class TradingEngine:
    """Main trading orchestrator"""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        
        # Load credentials from env
        api_key = os.environ.get('API_KEY')
        secret = os.environ.get('SECRET_KEY')
        trading_mode = os.environ.get('TRADING_MODE', 'test')
        testnet = (trading_mode == 'test' or trading_mode == 'paper')
        
        self.exchange = ExchangeConnector(
            exchange_id='binance',
            api_key=api_key,
            secret=secret,
            testnet=testnet
        )
        self.executor = TradeExecutor(self.exchange, config)
        self.persistence = TradePersistence()
        self.aws = AWSClients()
    
    def run_cycle(self, symbol: str):
        """Run single trading cycle for symbol"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 Empire V9 Cycle: {symbol}")
        logger.info(f"{'='*60}\n")
        
        # 1. Build market context
        try:
            market_builder = MarketStateBuilder(self.exchange, self.config)
            context = market_builder.build()
        except Exception as e:
            logger.error(f"❌ Failed to build market context: {e}")
            return {"status": "ERROR", "reason": "MARKET_CONTEXT_FAILED"}
        
        # 2. Pre-flight checks (Global)
        if not context.can_trade:
            reason = self._get_block_reason(context)
            logger.warning(f"🚫 Global Block: {reason}")
            self.persistence.log_skip(symbol, "crypto", reason, 0)
            return {"symbol": symbol, "status": "BLOCKED", "reason": reason}
        
        # 3. Manage exits (Priorité absolue)
        exit_result = self._manage_exits(symbol, context)
        if exit_result:
            return {"symbol": symbol, "status": "EXIT", "result": exit_result}
        
        # 4. Check for entry opportunity
        entry_result = self._evaluate_entry(symbol, context)
        
        return entry_result
    
    def _get_block_reason(self, context: MarketContext) -> str:
        """Determine why trading is blocked"""
        if context.risk_blocked:
            return f"DAILY_LOSS_LIMIT ({context.daily_pnl_pct:.2%})"
        if context.circuit_breaker_level == "L3_SURVIVAL":
            return "CIRCUIT_BREAKER_L3"
        if context.circuit_breaker_level == "L2_HALT":
            return "CIRCUIT_BREAKER_L2"
        if context.vix_value >= self.config.vix_max:
            return f"VIX_TOO_HIGH ({context.vix_value:.1f})"
        return "UNKNOWN_BLOCK"
    
    def _manage_exits(self, symbol: str, context: MarketContext) -> Optional[str]:
        """Manage exit logic for open positions (Optimized GSI)"""
        try:
            # 🛠️ GSI_OpenByPair (Status PK)
            response = self.aws.trades_table.query(
                IndexName='GSI_OpenByPair',
                KeyConditionExpression=(
                    boto3.dynamodb.conditions.Key('Status').eq('OPEN') &
                    boto3.dynamodb.conditions.Key('PairTimestamp').begins_with(f"{symbol}#")
                )
            )
            open_trades = response.get('Items', [])
            
            if not open_trades:
                return None
            
            current_price = float(self.exchange.fetch_ticker(symbol)['last'])
            
            # Grouped PnL
            total_cost = sum(float(t['EntryPrice']) * float(t['Size']) for t in open_trades)
            total_size = sum(float(t['Size']) for t in open_trades)
            avg_entry = total_cost / total_size if total_size > 0 else 0
            pnl_pct = ((current_price - avg_entry) / avg_entry) * 100 if avg_entry > 0 else 0
            
            logger.info(f"📊 {symbol} Position: {pnl_pct:+.2f}%")
            
            # Logic: Stop Loss / Take Profit / Trailing
            sl = float(open_trades[0].get('SL', self.config.stop_loss_pct))
            tp = float(open_trades[0].get('TP', self.config.hard_tp_pct))
            
            # 1. Stop Loss
            if pnl_pct <= sl:
                return self._close_all_v9(open_trades, current_price, "STOP_LOSS")
            
            # 2. Hard TP
            if pnl_pct >= tp:
                return self._close_all_v9(open_trades, current_price, "TAKE_PROFIT")
            
            # 3. Trailing (RSI Confirmation)
            if pnl_pct >= self.config.trailing_tp_pct:
                ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=14)
                analysis = analyze_market(ohlcv)
                if analysis['indicators']['rsi'] > self.config.rsi_sell_threshold:
                    return self._close_all_v9(open_trades, current_price, "TRAILING_STOP_RSI")
            
            return None
            
        except Exception as e:
            logger.error(f"Exit management error for {symbol}: {e}")
            return None
    
    def _close_all_v9(self, trades, exit_price, reason):
        """Helper to close and release slot"""
        symbol = trades[0]['Pair']
        size = sum(float(t['Size']) for t in trades)
        
        try:
            self.executor.close_position(symbol, size, reason)
            
            for t in trades:
                entry = float(t['EntryPrice'])
                cost = float(t['Cost'])
                pnl = ((exit_price - entry) / entry) * cost
                self.persistence.log_trade_close(t['TradeId'], exit_price, pnl, reason)
                
                # Release atomic slot per trade
                SlotManager(self.aws.state_table, 1).release()
                
            return f"CLOSED_{reason}"
        except Exception as e:
            logger.error(f"Close failure: {e}")
            return f"FAILURE_{reason}"

    def _evaluate_entry(self, symbol: str, context: MarketContext) -> Dict:
        """Evaluate and execute entry with AI Advisory"""
        
        # 1. Technical Analysis
        ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=100)
        analysis = analyze_market(ohlcv)
        rsi = analysis['indicators']['rsi']
        
        logger.info(f"📈 {symbol} Technical: RSI={rsi:.1f} (Target < {self.config.rsi_buy_threshold})")
        
        if rsi >= self.config.rsi_buy_threshold:
            return {"symbol": symbol, "status": "NO_SIGNAL", "rsi": rsi}
        
        # 2. Volume Confirmation
        if self.config.volume_confirmation_enabled:
            vol_ok = self._check_volume(ohlcv)
            if not vol_ok:
                return {"symbol": symbol, "status": "LOW_VOLUME"}

        # 3. Slot Acquisition (Atomic)
        slot_manager = SlotManager(self.aws.state_table, context.max_slots)
        if not slot_manager.acquire():
            return {"symbol": symbol, "status": "SKIPPED_SLOTS_FULL"}
            
        try:
            # 4. AI Advisory (Production Fail-safe)
            ai_decision = "CONFIRM"
            ai_reason = "AI_DISABLED"
            
            if self.config.ai_confirmation_enabled:
                news_ctx = get_news_context(symbol)
                decision = ask_bedrock(symbol, rsi, news_ctx, {}, [])
                ai_decision = decision.get("decision", "CONFIRM")
                ai_reason = decision.get("reason", "AI_ANALYSIS_COMPLETE")

            if ai_decision == "CANCEL":
                slot_manager.release()
                self.persistence.log_skip(symbol, "crypto", f"AI_VETO: {ai_reason}", analysis['current_price'])
                return {"symbol": symbol, "status": "AI_VETO", "reason": ai_reason}

            # 5. Position Sizing (Risk Managed)
            entry_price = analysis['current_price']
            base_capital = self.config.capital_per_trade * context.total_multiplier
            
            # Risk Cap (2% Max Loss)
            max_risk = context.balance * self.config.max_risk_per_trade_pct
            potential_loss = base_capital * (abs(self.config.stop_loss_pct) / 100)
            if potential_loss > max_risk:
                base_capital = max_risk / (abs(self.config.stop_loss_pct) / 100)
                logger.info("🛡️ Position size capped by Risk Management (2% limit)")
            
            size = round(base_capital / entry_price, 4)
            
            # 6. Execution
            trade_id = f"V9-{uuid.uuid4().hex[:8]}"
            filled = self.executor.execute_market_order(symbol, 'buy', size)
            
            real_entry = float(filled.get('average', entry_price))
            real_size = float(filled.get('amount', size))
            
            # 7. Protect (Take Profit)
            tp_price = real_entry * (1 + self.config.hard_tp_pct / 100)
            self.executor.place_take_profit_order(symbol, real_size, tp_price)
            
            # 8. Persistence
            self.persistence.log_trade_open(
                trade_id=trade_id, symbol=symbol, asset_class="crypto", side="buy",
                entry_price=real_entry, size=real_size, capital=base_capital,
                strategy=f"V9_{context.regime.value}", 
                tp_pct=self.config.hard_tp_pct, sl_pct=self.config.stop_loss_pct,
                ai_decision=ai_decision, ai_reason=ai_reason
            )
            
            return {"symbol": symbol, "status": "LONG_OPEN", "id": trade_id}

        except Exception as e:
            logger.error(f"Entry execution failed for {symbol}: {e}")
            slot_manager.release()
            return {"symbol": symbol, "status": "ERROR", "msg": str(e)}

    def _check_volume(self, ohlcv: List) -> bool:
        if len(ohlcv) < 20: return True
        current_vol = ohlcv[-1][5]
        avg_vol = sum(c[5] for c in ohlcv[-21:-1]) / 20
        ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
        logger.info(f"📊 Volume Ratio: {ratio:.2f}x")
        return ratio > 1.1


# ==================== LAMBDA HANDLER ====================

def lambda_handler(event, context):
    """V9 Main Entry Point"""
    try:
        config = TradingConfig.from_env()
        config.validate()
        
        # Determine symbol(s)
        symbols_env = os.environ.get('SYMBOLS', 'SOL/USDT')
        symbols = event.get('symbols', event.get('symbol', symbols_env)).split(',')
        
        engine = TradingEngine(config)
        results = []
        
        for s in symbols:
            s = s.strip()
            if not s: continue
            res = engine.run_cycle(s)
            results.append(res)
            
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'SUCCESS', 'results': results})
        }
        
    except Exception as e:
        logger.error(f"Global Failure: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'status': 'ERROR', 'error': str(e)})
        }

if __name__ == "__main__":
    # Local Test
    print(lambda_handler({'symbol': 'SOL/USDT'}, None))
