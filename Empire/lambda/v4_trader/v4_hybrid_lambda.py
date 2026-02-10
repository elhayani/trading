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
from news_fetcher import get_news_context
from exchange_connector import ExchangeConnector
import macro_context
import micro_corridors as corridors
from models import MarketRegime, AssetClass
from decision_engine import DecisionEngine

# ==================== CONFIGURATION ====================

@dataclass
class TradingConfig:
    """Centralized configuration with validation (Audit #V9.4)"""
    
    # Risk Management & Dynamic Allocation
    capital_pct: float = 0.05             # 5% of balance per trade
    max_slots_calm: int = 5               # Up to 5 slots in calm markets
    max_slots_volatile: int = 2           # Min 2 slots when volatile
    max_risk_per_trade_pct: float = 0.02  # 2%
    max_daily_loss_pct: float = 0.05      # 5%
    max_drawdown_pct: float = 0.15        # 15%
    
    # Dynamic TP/SL Ranges
    target_tp_range: Tuple[float, float] = (4.0, 12.0)  # Min/Max TP
    target_sl_range: Tuple[float, float] = (-2.0, -5.0) # Tight/Wide SL
    
    # Entry/Exit Thresholds
    rsi_buy_threshold: float = 42.0
    rsi_sell_threshold: float = 78.0
    trailing_tp_pct: float = 1.5
    
    # Market Filters
    btc_crash_threshold: float = -0.08
    vix_max: float = 35.0                 # Slightly relaxed for diversification
    vix_reduce: float = 25.0
    
    # Circuit Breakers (Audit #V9.6: Removed unused cooldown/MTF)
    cb_level_1: float = -0.05   # -5%
    cb_level_2: float = -0.10   # -10%
    cb_level_3: float = -0.20   # -20%
    
    # Features (Audit #V9.8: Env-loadable)
    volume_confirmation_enabled: bool = True
    ai_confirmation_enabled: bool = True
    
    # --- Optimizations V10 (Audit #V10.1) ---
    # Confidence weights
    weight_time: float = 0.35
    weight_macro: float = 0.30
    weight_volatility: float = 0.20
    weight_structure: float = 0.15
    
    # Split TP
    tp_split_ratio: float = 0.60  # 60% for first TP, 40% for runner
    runner_enabled: bool = True
    
    # SMA proximity (Audit #V10.4)
    sma_proximity_threshold: float = 0.005 # 0.5% buffer around SMAs
    
    # ATR Multiplier for SL
    atr_sl_mult: float = 2.0
    volatility_adjustment_enabled: bool = True
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables"""
        return cls(
            capital_pct=float(os.getenv('CAPITAL_PCT', '0.05')),
            max_slots_calm=int(os.getenv('MAX_SLOTS_CALM', '5')),
            rsi_buy_threshold=float(os.getenv('RSI_THRESHOLD', '42')),
            volume_confirmation_enabled=os.getenv('VOLUME_CONFIRM', 'true').lower() == 'true',
            ai_confirmation_enabled=os.getenv('AI_CONFIRM', 'true').lower() == 'true',
            tp_split_ratio=float(os.getenv('TP_SPLIT', '0.6')),
            runner_enabled=os.getenv('RUNNER_ENABLE', 'true').lower() == 'true',
            atr_sl_mult=float(os.getenv('ATR_SL_MULT', '2.0'))
        )
    
    def validate(self):
        """Validate configuration constraints"""
        assert 0 < self.capital_pct <= 0.15, "Capital percentage must be 0.1-15%"
        assert 1 <= self.max_slots_volatile <= self.max_slots_calm, "Slot config error"
        assert self.target_tp_range[0] < self.target_tp_range[1], "TP range error"
        assert self.target_sl_range[0] > self.target_sl_range[1], "SL range error" # -2 > -5





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
            
        # Configuration
        self.region = os.getenv('AWS_REGION', 'us-east-1')
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
        self.secretsmanager = boto3.client('secretsmanager', region_name=self.region)
        
        # Tables
        self.trades_table = self.dynamodb.Table(
            os.getenv('HISTORY_TABLE', 'EmpireTradesHistory')
        )
        self.state_table = self.dynamodb.Table(
            os.getenv('STATE_TABLE', 'V4TradingState')
        )
        
        self._initialized = True
    
    def check_kill_switch(self) -> bool:
        """Check if global emergency stop is active"""
        try:
            response = self.state_table.get_item(Key={'trader_id': 'GLOBAL_KILL'})
            item = response.get('Item')
            if item and item.get('enabled') is True:
                logger.critical("🚨 GLOBAL KILL SWITCH DETECTED - ABORTING")
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to check kill switch: {e}")
            return False

    def get_secret(self, secret_name: str) -> Dict:
        """Fetch secret from AWS Secrets Manager with mandatory check in production"""
        if not secret_name:
            if os.getenv('TRADING_MODE') == 'live':
                logger.critical("🚨 PRODUCTION ERROR: SECRET_NAME is mandatory in live mode!")
                raise ValueError("SECRET_NAME missing in live environment")
            return {}
            
        try:
            response = self.secretsmanager.get_secret_value(SecretId=secret_name)
            if 'SecretString' in response:
                return json.loads(response['SecretString'])
            return {}
        except Exception as e:
            logger.error(f"❌ Failed to fetch secret {secret_name}: {e}")
            return {}


# ==================== SLOT MANAGER ====================

class SlotManager:
    """Atomic slot management with TTL-based leak protection (Audit #V9.1)"""
    
    def __init__(self, aws, max_slots: int, execution_id: str):
        self.aws = aws
        self.max_slots = max_slots
        self.execution_id = execution_id
        self.slot_acquired = False
    
    def acquire(self) -> bool:
        """Atomically acquire a trading slot using a counter + heartbeat"""
        try:
            # 1. Atomic Counter Update
            self.aws.state_table.update_item(
                Key={'trader_id': 'GLOBAL_SLOTS'},
                UpdateExpression="SET ActiveSlots = if_not_exists(ActiveSlots, :zero) + :one",
                ConditionExpression="if_not_exists(ActiveSlots, :zero) < :max",
                ExpressionAttributeValues={
                    ':one': 1,
                    ':zero': 0,
                    ':max': self.max_slots
                }
            )
            
            # 2. Register Heartbeat (for future cleanup of orphans)
            ttl = int((datetime.now(timezone.utc) + timedelta(hours=6)).timestamp())
            self.aws.state_table.put_item(Item={
                'trader_id': f"HEARTBEAT#{self.execution_id}",
                'Type': 'SLOT_RESERVATION',
                'TTL': ttl,
                'Timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            self.slot_acquired = True
            logger.info(f"✅ Slot acquired ({self.execution_id})")
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(f"⏸️ All slots occupied ({self.max_slots})")
            else:
                logger.error(f"❌ Slot acquisition error: {e}")
            return False
    
    def release(self):
        """Release acquired slot and cleanup heartbeat"""
        if not self.slot_acquired:
            return
            
        try:
            # 1. Decrement Counter
            self.aws.state_table.update_item(
                Key={'trader_id': 'GLOBAL_SLOTS'},
                UpdateExpression="SET ActiveSlots = ActiveSlots - :one",
                ConditionExpression="ActiveSlots > :zero",
                ExpressionAttributeValues={
                    ':one': 1,
                    ':zero': 0
                }
            )
            
            # 2. Delete Heartbeat
            self.aws.state_table.delete_item(Key={'trader_id': f"HEARTBEAT#{self.execution_id}"})
            
            logger.info(f"🔓 Slot released ({self.execution_id})")
            
        except Exception as e:
            logger.error(f"❌ Slot release failed: {e}")
        finally:
            self.slot_acquired = False
    



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
    
    # Dynamic Targets (Audit #V9.4)
    dynamic_tp_pct: float
    dynamic_sl_pct: float
    
    # Optimization V10
    confidence_score: float = 0.5
    signal_score: float = 0.0
    atr_value: float = 0.0
    sma_50: float = 0.0
    sma_200: float = 0.0
    is_high_liquidity: bool = True
    
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
        """Build complete market context with adaptive logic (Audit #V9.4)"""
        logger.info("🔍 Building adaptive market context...")
        
        # 1. BTC & VIX (Core inputs)
        btc_24h, btc_7d, btc_1h = self._get_btc_performance()
        vix_value, vix_mult = self._get_vix_safe()
        
        # 2. Portfolio state
        balance = self._get_balance_safe()
        open_positions = self._get_open_positions_safe()
        max_slots = self._calculate_max_slots(balance, vix_value)
        
        # 3. Dynamic Targets (Volatility based)
        vix_factor = max(0, min(1, (vix_value - 15) / 20))
        tp_min, tp_max = self.config.target_tp_range
        dyn_tp = tp_min + vix_factor * (tp_max - tp_min)
        sl_wide, sl_tight = self.config.target_sl_range[1], self.config.target_sl_range[0]
        dyn_sl = sl_wide + vix_factor * (sl_tight - sl_wide)
        
        # 4. Circuit breaker & Diversification logic
        cb_mult, cb_level = self._get_circuit_breaker_status(btc_24h, btc_7d)
        is_golden = self._is_golden_window()
        regime = self._determine_regime(btc_24h, btc_7d, btc_1h, vix_value, cb_level)
        daily_pnl, daily_pnl_pct = self._get_daily_performance(balance)
        
        # B. Macro Context (Audit #V10.5: Macro Veto support)
        macro_ctx = macro_context.get_macro_context()
        macro_can_trade = macro_ctx.get('can_trade', True)
        
        diversified_protection = (open_positions >= 2 and daily_pnl_pct > -0.02)
        can_trade = (
            cb_level != "L3_SURVIVAL" and
            (cb_level != "L2_HALT" or diversified_protection) and
            vix_value < self.config.vix_max and
            daily_pnl_pct > -self.config.max_daily_loss_pct and
            macro_can_trade
        )
        risk_blocked = daily_pnl_pct <= -self.config.max_daily_loss_pct

        # 5. Optimization V10: Confidence Score calculation (Level 4: Macro Adjustment)
        # A. Time Edge (Corridor quality)
        current_corridor = corridors.get_current_corridor(self.exchange.symbol if hasattr(self.exchange, 'symbol') else 'BTC/USDT')
        corridor_regime = current_corridor.get('regime') if current_corridor else None
        time_edge = 1.0 if corridor_regime in [corridors.MarketRegime.AGGRESSIVE_BREAKOUT, corridors.MarketRegime.TREND_FOLLOWING] else 0.4
        
        # B. Macro Edge
        macro_edge = 1.0 if macro_ctx.get('regime') == 'RISK_ON' else 0.5 if macro_ctx.get('regime') == 'MIXED' else 0.2
        
        # C. Volatility Edge (Normalized VIX)
        vix_edge = 1.0 - vix_factor 
        
        # D. Structure Edge (Trend alignment)
        ohlcv_1h = self.exchange.fetch_ohlcv('BTC/USDT', '1h', limit=100)
        analysis = analyze_market(ohlcv_1h)
        structure_edge = 1.0 if analysis['indicators']['long_term_trend'] == 'BULLISH' else 0.3
        
        # Raw score (0-1)
        raw_conf = (
            time_edge * self.config.weight_time +
            macro_edge * self.config.weight_macro +
            vix_edge * self.config.weight_volatility +
            structure_edge * self.config.weight_structure
        )
        
        # Incorporate Technical Signal Score (Level 2 impact on Level 4)
        # technical_mult: 0.6 if score 60, 1.0 if score 100
        ta_score = analysis['indicators']['signal_score']
        technical_mult = 0.6 + (max(0, ta_score - 60) / 40) * 0.4 if ta_score >= 60 else 0.5
        
        # Scale to 0.5 to 2.0 range (Level 4)
        scaled_conf = (0.5 + (raw_conf * 1.5)) * technical_mult
        scaled_conf = max(0.5, min(2.0, scaled_conf))
        
        # 6. Build final context
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
            daily_pnl_pct=daily_pnl_pct,
            dynamic_tp_pct=round(dyn_tp, 2),
            dynamic_sl_pct=round(dyn_sl, 2),
            confidence_score=round(scaled_conf, 2),
            signal_score=ta_score,
            atr_value=analysis['indicators']['atr'],
            sma_50=analysis['indicators']['sma_50'],
            sma_200=analysis['indicators']['sma_200'],
            is_high_liquidity=is_golden
        )
        
        logger.info(f"✅ Context: {regime.value} | Conf: {scaled_conf:.2f} | Score: {ta_score}/100 | TP: {dyn_tp:.1f}%")
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
    
    def _calculate_max_slots(self, balance: float, vix: float) -> int:
        """Calculate max slots based on balance & market calm (Audit #V9.4)"""
        # Base slots (1 per $4k budget to keep it conservative but scalable)
        base_slots = max(1, int(balance / 4000))
        
        # Calm market (VIX < 20) -> Allow up to config max (ex: 5)
        if vix < 20:
            return min(base_slots + 2, self.config.max_slots_calm)
        # Volatile market (VIX > 28) -> Restrict slots
        elif vix > 28:
            return min(base_slots, self.config.max_slots_volatile)
        
        return min(base_slots + 1, 3)
    
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
        """Calculate today's PnL (Optimized GSI Query #V9.5)"""
        try:
            today_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            
            # 🛠️ GSI_ExitDate: Status (PK) + ExitDate (SK) 
            response = self.aws.trades_table.query(
                IndexName='GSI_ExitDate',
                KeyConditionExpression=(
                    boto3.dynamodb.conditions.Key('Status').eq('CLOSED') &
                    boto3.dynamodb.conditions.Key('ExitDate').eq(today_date)
                )
            )
            
            trades = response.get('Items', [])
            
            # 🔄 Handle Pagination (Audit #V9.6)
            while 'LastEvaluatedKey' in response:
                response = self.aws.trades_table.query(
                    IndexName='GSI_ExitDate',
                    KeyConditionExpression=(
                        boto3.dynamodb.conditions.Key('Status').eq('CLOSED') &
                        boto3.dynamodb.conditions.Key('ExitDate').eq(today_date)
                    ),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                trades.extend(response.get('Items', []))
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


# ==================== PERSISTENCE ====================


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
        ai_reason: str,
        context: MarketContext
    ):
        """Log new trade opening with full context (Audit #V9.2)"""
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
                'EntryPrice': Decimal(str(round(entry_price, 8))),
                'Size': Decimal(str(round(size, 8))),
                'Cost': Decimal(str(round(capital, 2))),
                'Value': Decimal(str(round(capital, 2))),
                'TP': Decimal(str(round(tp_pct, 2))),
                'SL': Decimal(str(round(sl_pct, 2))),
                'Status': 'OPEN',
                'AI_Decision': ai_decision,
                'AI_Reason': ai_reason,
                'PeakPnL': Decimal('0'),
                'MarketContext': context.to_dict() # 📊 Gold mine for post-trade analysis
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
        """Log trade closure with Anti-Double-Close protection"""
        try:
            exit_time = datetime.now(timezone.utc)
            exit_time_iso = exit_time.isoformat()
            exit_date = exit_time.strftime('%Y-%m-%d')
            
            self.aws.trades_table.update_item(
                Key={'TradeId': trade_id},
                UpdateExpression=(
                    "SET #status = :closed, "
                    "PnL = :pnl, "
                    "ExitPrice = :exit_price, "
                    "ExitTime = :exit_time, "
                    "ExitDate = :exit_date, "
                    "ExitReason = :reason"
                ),
                ConditionExpression="#status = :open", # 🛡️ ANTI-DOUBLE CLOSE
                ExpressionAttributeNames={'#status': 'Status'},
                ExpressionAttributeValues={
                    ':closed': 'CLOSED',
                    ':open': 'OPEN',
                    ':pnl': Decimal(str(round(pnl, 2))),
                    ':exit_price': Decimal(str(round(exit_price, 8))),
                    ':exit_time': exit_time_iso,
                    ':exit_date': exit_date,
                    ':reason': reason
                }
            )
            
            logger.info(f"💾 Trade closed: {trade_id} | PnL: ${pnl:+.2f}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(f"⚠️ Trade {trade_id} already closed or status changed.")
            else:
                logger.error(f"Failed to log trade closure: {e}")
        except Exception as e:
            logger.error(f"Failed to log trade closure: {e}")
    
    def log_skip(
        self,
        symbol: str,
        asset_class: str,
        reason: str,
        price: float,
        context: Optional[MarketContext] = None
    ):
        """Log skipped opportunity with optional context"""
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            log_id = f"SKIP-{int(time.time())}-{uuid.uuid4().hex[:4]}"
            
            item = {
                'TradeId': log_id,
                'Timestamp': timestamp,
                'PairTimestamp': f"{symbol}#{timestamp}",
                'AssetClass': asset_class,
                'Pair': symbol,
                'Status': 'SKIPPED',
                'Type': 'INFO',
                'ExitReason': reason,
                'EntryPrice': Decimal(str(round(price, 8))),
                'TTL': int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
            }
            if context:
                item['MarketContext'] = context.to_dict()
            
            self.aws.trades_table.put_item(Item=item)
            
        except Exception as e:
            logger.warning(f"Failed to log skip: {e}")


# ==================== MAIN TRADING LOGIC ====================

class TradingEngine:
    """Main trading orchestrator"""
    
    def __init__(self, config: TradingConfig, execution_id: str = "local"):
        self.config = config
        self.execution_id = execution_id
        self.aws = AWSClients()
        self.active_slots: Dict[str, SlotManager] = {} # 🛡️ Slot persistence (Audit #V9.5)
        
        # Load credentials (SECURE: Secrets Manager Mandatory in Prod)
        trading_mode = os.environ.get('TRADING_MODE', 'test')
        secret_name = os.environ.get('SECRET_NAME')
        
        if not secret_name and trading_mode == 'live':
            logger.critical("🛑 KILL SWITCH: SECRET_NAME is missing in LIVE mode.")
            raise RuntimeError("Mandatory SECRET_NAME missing")

        api_key = os.environ.get('API_KEY')
        secret = os.environ.get('SECRET_KEY')
        
        if secret_name:
            logger.info(f"🛡️ Loading credentials from Secrets Manager: {secret_name}")
            creds = self.aws.get_secret(secret_name)
            api_key = creds.get('API_KEY', api_key) or creds.get('apiKey', api_key)
            secret = creds.get('SECRET_KEY', secret) or creds.get('secret', secret)
            
        testnet = (trading_mode == 'test' or trading_mode == 'paper')
        
        self.exchange = ExchangeConnector(
            exchange_id='binance',
            api_key=api_key,
            secret=secret,
            testnet=testnet
        )
        self.executor = TradeExecutor(self.exchange, config)
        self.persistence = TradePersistence()
        
        # 🔄 Reconcile slots on startup (Audit #V9.6)
        # Prevents ActiveSlots drift after Lambda restarts or manual adjustments
        self._reconcile_slots()
    
    def _reconcile_slots(self):
        """Synchronize DynamoDB ActiveSlots with actual OPEN trades in database"""
        try:
            logger.info("🔄 Reconciling trading slots...")
            # Query all trades with Status='OPEN' via Index
            response = self.aws.trades_table.query(
                IndexName='GSI_OpenByPair',
                KeyConditionExpression=boto3.dynamodb.conditions.Key('Status').eq('OPEN')
            )
            open_trades = response.get('Items', [])
            
            # Handle pagination for reconciliation
            while 'LastEvaluatedKey' in response:
                response = self.aws.trades_table.query(
                    IndexName='GSI_OpenByPair',
                    KeyConditionExpression=boto3.dynamodb.conditions.Key('Status').eq('OPEN'),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                open_trades.extend(response.get('Items', []))
            
            actual_count = len(open_trades)
            logger.info(f"📊 Found {actual_count} open trades in database.")
            
            # Atomic update to match reality (Audit #V9.7)
            # Using update_item with ConditionExpression could be safer but put_item
            # with LastUpdated is acceptable given the frequency of Lambda execution.
            self.aws.state_table.put_item(Item={
                'trader_id': 'GLOBAL_SLOTS',
                'ActiveSlots': actual_count,
                'LastUpdated': datetime.now(timezone.utc).isoformat(),
                'ReconciledBy': self.execution_id
            })
            logger.info(f"✅ Slots reconciled: {actual_count} active.")
            
        except Exception as e:
            logger.error(f"❌ Slot reconciliation failed: {e}")

    def run_cycle(self, symbol: str):
        """Run single trading cycle with Kill Switch & Observability"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 Empire V9 Cycle: {symbol} | ID: {self.execution_id}")
        logger.info(f"{'='*60}\n")
        
        # 0. Global Kill Switch check (Audit #V9.3)
        if self.aws.check_kill_switch():
            return {"status": "HALTED", "reason": "KILL_SWITCH"}

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
            self.persistence.log_skip(symbol, "crypto", reason, 0, context)
            return {"symbol": symbol, "status": "BLOCKED", "reason": reason}

        # 2b. Symbol-specific Kill Switch (Optimization N°5)
        if self._is_symbol_locked(symbol):
            logger.warning(f"🚫 Symbol {symbol} is LOCKED due to recent poor performance.")
            return {"symbol": symbol, "status": "SYMBOL_LOCKED"}
        
        # 3. Manage exits (Priorité absolue)
        exit_result = self._manage_exits(symbol, context)
        if exit_result:
            return {"symbol": symbol, "status": "EXIT", "result": exit_result}
        
        # 4. Check for entry opportunity
        entry_result = self._evaluate_entry(symbol, context)
        
        return entry_result
    
    def _is_symbol_locked(self, symbol: str) -> bool:
        """Check if a symbol is temporarily locked (Optimization N°5)"""
        try:
            response = self.aws.state_table.get_item(Key={'trader_id': f"LOCK#{symbol}"})
            item = response.get('Item')
            if item:
                expiry = datetime.fromisoformat(item['expiry'])
                if datetime.now(timezone.utc) < expiry:
                    return True
            return False
        except Exception as e:
            logger.warning(f"Failed to check symbol lock: {e}")
            return False
    
    def _lock_symbol(self, symbol: str, hours: int, reason: str):
        """Apply temporary lock to a symbol"""
        expiry = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
        try:
            self.aws.state_table.put_item(Item={
                'trader_id': f"LOCK#{symbol}",
                'expiry': expiry,
                'reason': reason,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            logger.warning(f"🔒 LOCKED {symbol} for {hours}h: {reason}")
        except Exception as e:
            logger.error(f"Failed to lock symbol: {e}")

    def _handle_loss_lock(self, symbol: str, trade: Dict):
        """Analyze loss and lock symbol if conditions met (Optimization N°5)"""
        try:
            context = trade.get('MarketContext', {})
            confidence = float(context.get('confidence_score', 1.0))
            is_low_liq = context.get('is_high_liquidity') is False
            
            # Rule: loss during LOW_LIQUIDITY -> 4h lock
            if is_low_liq:
                self._lock_symbol(symbol, hours=4, reason="LOSS_DURING_LOW_LIQUIDITY")
                return

            # Rule: low confidence loss -> 2h lock
            if confidence < 0.6:
                self._lock_symbol(symbol, hours=2, reason="LOW_CONFIDENCE_LOSS")
        except Exception as e:
            logger.warning(f"Failed to handle loss lock: {e}")

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
            
            # 🔄 Handle Pagination (Audit #V9.6)
            while 'LastEvaluatedKey' in response:
                response = self.aws.trades_table.query(
                    IndexName='GSI_OpenByPair',
                    KeyConditionExpression=(
                        boto3.dynamodb.conditions.Key('Status').eq('OPEN') &
                        boto3.dynamodb.conditions.Key('PairTimestamp').begins_with(f"{symbol}#")
                    ),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                open_trades.extend(response.get('Items', []))
            
            if not open_trades:
                return None
            
            current_price = float(self.exchange.fetch_ticker(symbol)['last'])
            
            # Grouped PnL
            total_cost = sum(float(t['EntryPrice']) * float(t['Size']) for t in open_trades)
            total_size = sum(float(t['Size']) for t in open_trades)
            avg_entry = total_cost / total_size if total_size > 0 else 0
            pnl_pct = ((current_price - avg_entry) / avg_entry) * 100 if avg_entry > 0 else 0
            
            logger.info(f"📊 {symbol} Position: {pnl_pct:+.2f}%")
            
            # Logic: Stop Loss / Take Profit / Trailing (Audit #V9.4)
            # Use stored TP/SL or safe defaults if legacy trade
            sl = float(open_trades[0].get('SL', -3.5))
            tp = float(open_trades[0].get('TP', 8.0))
            
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
        """Helper to close and release slot (Audit #V9.5: Slot Persistence)"""
        symbol = trades[0]['Pair']
        size = sum(float(t['Size']) for t in trades)
        
        try:
            self.executor.close_position(symbol, size, reason)
            
            total_pnl = 0
            for t in trades:
                entry = float(t['EntryPrice'])
                cost = float(t['Cost'])
                pnl = ((exit_price - entry) / entry) * cost
                total_pnl += pnl
                self.persistence.log_trade_close(t['TradeId'], exit_price, pnl, reason)
            
            # Optimization N°5: Symbol-specific Lock
            if total_pnl < 0:
                self._handle_loss_lock(symbol, trades[0])
            
            # ✅ CORRECTION : Récupérer l'instance existante ou release direct
            slot_mgr = self.active_slots.pop(symbol, None)
            if slot_mgr:
                slot_mgr.release()
            else:
                self._release_slot_direct() 
                
            return f"CLOSED_{reason}"
        except Exception as e:
            logger.error(f"Close failure: {e}")
            return f"FAILURE_{reason}"

    def _release_slot_direct(self):
        """Direct fallback release (Audit #V9.5)"""
        try:
            self.aws.state_table.update_item(
                Key={'trader_id': 'GLOBAL_SLOTS'},
                UpdateExpression="SET ActiveSlots = ActiveSlots - :one",
                ConditionExpression="ActiveSlots > :zero",
                ExpressionAttributeValues={':one': 1, ':zero': 0}
            )
            logger.info("🔓 Slot released via direct fallback")
        except Exception as e:
            logger.error(f"❌ Direct slot release failed: {e}")

    def _evaluate_entry(self, symbol: str, context: MarketContext) -> Dict:
        """Evaluate entry (Audit #V10.5: Using DecisionEngine)"""
        
        # 1. Technical Analysis (Data Gathering)
        ta_result = self._check_technical_entry(symbol, context)
        if ta_result['status'] != "SIGNAL":
            return ta_result
            
        # 2. Hierarchical Decision Check (Levels 1-3)
        proceed, reason, size_mult = DecisionEngine.evaluate(context, ta_result, symbol)
        if not proceed:
            return {"symbol": symbol, "status": "DECISION_VETO", "reason": reason}

        # 3. Slot Manager
        slot_manager = SlotManager(self.aws, context.max_slots, self.execution_id)
        if not slot_manager.acquire():
            return {"symbol": symbol, "status": "SKIPPED_SLOTS_FULL"}
        
        self.active_slots[symbol] = slot_manager # Store for possible closure later

        # 3. Dynamic Execution (Audit #V10.2: Guaranteed Release)
        keep_slot = False
        try:
            # A. AI Advisory
            ai_result = self._check_ai_advisory(symbol, ta_result['rsi'])
            if ai_result['decision'] == "CANCEL":
                self.persistence.log_skip(
                    symbol, AssetClass.CRYPTO.value, 
                    f"AI_VETO: {ai_result['reason']}", 
                    ta_result['price'], context
                )
                return {"symbol": symbol, "status": "AI_VETO", "reason": ai_result['reason']}

            # B. Finalize Execution
            result = self._execute_v9_entry(symbol, context, ta_result['price'], ai_result)
            keep_slot = True # ✅ Mark as successfully opened to prevent release
            return result

        except Exception as e:
            logger.error(f"❌ Entry process failed for {symbol}: {e}")
            return {"symbol": symbol, "status": "ERROR", "msg": str(e)}
            
        finally:
            if not keep_slot:
                logger.info(f"🔓 Releasing slot for {symbol} (Entry not completed)")
                slot_manager.release()
                self.active_slots.pop(symbol, None)

    def _check_technical_entry(self, symbol: str, context: MarketContext) -> Dict:
        """Isolated Technical Analysis Entry Check with High Confidence Filters (Audit #V10.4)"""
        ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=100)
        analysis = analyze_market(ohlcv)
        rsi = analysis['indicators']['rsi']
        price = analysis['current_price']
        
        # 1. RSI Extreme Filter
        adaptive_rsi = corridors.get_rsi_threshold_adaptive(symbol, self.config.rsi_buy_threshold)
        logger.info(f"📈 {symbol} Technical: RSI={rsi:.1f} (Target < {adaptive_rsi})")
        
        if rsi >= adaptive_rsi:
            return {"symbol": symbol, "status": "NO_SIGNAL", "rsi": rsi}
        
        # 2. Volume Confirmation
        if self.config.volume_confirmation_enabled and not self._check_volume(ohlcv):
            return {"symbol": symbol, "status": "LOW_VOLUME"}

        # 3. SMA Neutral Zone Filter (Optimization N°4)
        for sma_val in [context.sma_50, context.sma_200]:
            if sma_val > 0:
                dist = abs(price - sma_val) / sma_val
                if dist < self.config.sma_proximity_threshold:
                    logger.warning(f"🚫 Gray Zone Block: Price too close to SMA ({dist:.2%})")
                    return {"symbol": symbol, "status": "SMA_GRAY_ZONE"}
            
        return {"status": "SIGNAL", "rsi": rsi, "price": price, "score": analysis['indicators']['signal_score']}

    def _check_ai_advisory(self, symbol: str, rsi: float) -> Dict:
        """Isolated AI Consultation"""
        if not self.config.ai_confirmation_enabled:
            return {"decision": "CONFIRM", "reason": "AI_DISABLED"}
        
        news_ctx = get_news_context(symbol)
        return self.ask_bedrock(symbol, rsi, news_ctx)

    def ask_bedrock(self, symbol: str, rsi: float, news_context: str) -> Dict:
        """Query Bedrock AI for sentiment confirmation (Audit #V9.5)"""
        prompt = f"""
Vous êtes l'Analyste de Flux de Nouvelles pour l'Empire V9.
LA DÉCISION TECHNIQUE EST DÉJÀ PRISE : {symbol} est prêt (RSI: {rsi:.1f}).
EXAMINEZ LES NEWS : {news_context}
VOTRE MISSION : Détecter toute nouvelle CATASTROPHIQUE.
RÉPONSE JSON : {{ "decision": "CONFIRM" | "CANCEL", "reason": "explication" }}
"""
        try:
            response = self.aws.bedrock.invoke_model(
                modelId="anthropic.claude-3-haiku-20240307-v1:0",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 200,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
                })
            )
            result = json.loads(response['body'].read())
            completion = result['content'][0]['text']
            start = completion.find('{')
            end = completion.rfind('}') + 1
            return json.loads(completion[start:end]) if start != -1 else {"decision": "CONFIRM", "reason": "FORMAT_ERROR"}
        except Exception as e:
            logger.warning(f"⚠️ Bedrock fallback: {e}")
            return {"decision": "CONFIRM", "reason": "AI_API_FALLBACK"}

    def _execute_v9_entry(self, symbol: str, context: MarketContext, entry_price: float, ai: Dict) -> Dict:
        """Isolated Entry Execution with Confidence-Based Sizing (Level 4 Architecture)"""
        
        # 1. Level 4: Macro Adjustment (Confidence Multiplier)
        # size_multiplier results in 0.5x to 2.0x base size
        size_multiplier = context.confidence_score
        
        # Base capital = Account Balance * allocation % * circuit breaker/VIX mult
        base_capital = context.balance * self.config.capital_pct * context.total_multiplier
        
        # Final capital after Level 4 adjustment
        final_capital = base_capital * size_multiplier
        
        # Absolute Risk Cap (L2 protection)
        max_risk = context.balance * self.config.max_risk_per_trade_pct
        potential_loss = final_capital * (abs(context.dynamic_sl_pct) / 100)
        
        if potential_loss > max_risk:
            final_capital = max_risk / (abs(context.dynamic_sl_pct) / 100)
            logger.info(f"🛡️ Size capped by Max Risk (${max_risk:.2f})")

        # 2. Min Position Safeguard (Audit #V10.2)
        market_info = self.exchange.get_market_info(symbol)
        min_cost = market_info.get('min_cost', 5.0) # Default $5 for USDT pairs
        if final_capital < min_cost:
            logger.warning(f"⚠️ Position size too small (${final_capital:.2f} < ${min_cost}). Scaling up to minimum.")
            final_capital = min_cost
        
        size = round(final_capital / entry_price, market_info.get('precision_amount', 4))
        trade_id = f"V10-{uuid.uuid4().hex[:8]}"
        
        # 3. Order Execution
        filled = self.executor.execute_market_order(symbol, 'buy', size)
        real_entry = float(filled.get('average', entry_price))
        real_size = float(filled.get('amount', size))
        
        # 3. Dynamic SL (Optimization N°3)
        # sl = ATR * corridor_sl_mult * volatility_adjustment
        if self.config.volatility_adjustment_enabled and context.atr_value > 0:
            atr_sl_pct = (context.atr_value * self.config.atr_sl_mult) / real_entry * 100
            final_sl = -max(2.0, min(10.0, atr_sl_pct)) # Cap between 2% and 10%
        else:
            final_sl = context.dynamic_sl_pct

        # 4. Split TP / Runner (Optimization N°2)
        if self.config.runner_enabled and context.is_high_liquidity:
            tp_size = round(real_size * self.config.tp_split_ratio, 4)
            runner_size = round(real_size - tp_size, 4)
            
            tp_price = real_entry * (1 + context.dynamic_tp_pct / 100)
            self.executor.place_take_profit_order(symbol, tp_size, tp_price)
            logger.info(f"🏃 Split Runner Activated: {tp_size} for TP, {runner_size} for Runner")
        else:
            tp_price = real_entry * (1 + context.dynamic_tp_pct / 100)
            self.executor.place_take_profit_order(symbol, real_size, tp_price)
        
        # Logging
        self.persistence.log_trade_open(
            trade_id=trade_id, symbol=symbol, asset_class=AssetClass.CRYPTO.value, side="buy",
            entry_price=real_entry, size=real_size, capital=base_capital,
            strategy=f"V10_{context.regime.value}", 
            tp_pct=context.dynamic_tp_pct, sl_pct=final_sl,
            ai_decision=ai['decision'], ai_reason=ai['reason'],
            context=context
        )
        
        return {
            "symbol": symbol, 
            "status": "LONG_OPEN", 
            "id": trade_id, 
            "tp": context.dynamic_tp_pct, 
            "sl": final_sl,
            "confidence": context.confidence_score
        }

    def _check_volume(self, ohlcv: List) -> bool:
        if len(ohlcv) < 20: return True
        current_vol = ohlcv[-1][5]
        avg_vol = sum(c[5] for c in ohlcv[-21:-1]) / 20
        ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
        logger.info(f"📊 Volume Ratio: {ratio:.2f}x")
        return ratio > 1.1


# ==================== LAMBDA HANDLER ====================

def lambda_handler(event, context):
    """V9 Main Entry Point (Audit #V9.3: Observability)"""
    execution_id = f"EXEC-{uuid.uuid4().hex[:6]}"
    logger.info(f"🚀 Execution Start: {execution_id}")
    
    try:
        config = TradingConfig.from_env()
        config.validate()
        
        # Determine symbol(s)
        symbols_env = os.environ.get('SYMBOLS', 'SOL/USDT')
        symbols = event.get('symbols', event.get('symbol', symbols_env)).split(',')
        
        engine = TradingEngine(config, execution_id=execution_id)
        results = []
        
        for s in symbols:
            s = s.strip()
            if not s: continue
            res = engine.run_cycle(s)
            results.append(res)
            
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'SUCCESS', 'results': results, 'execution_id': execution_id})
        }
        
    except Exception as e:
        logger.error(f"Global Failure: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'status': 'ERROR', 'error': str(e)})
        }

