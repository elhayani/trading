import json
import os
import boto3
import logging
import uuid
import requests
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from market_analysis import analyze_market
from news_fetcher import get_news_context
from exchange_connector import ExchangeConnector

# 🎯 Micro-Corridors (Empire V7 Core)
try:
    from micro_corridors import (
        get_corridor_params, 
        get_current_regime, 
        MarketRegime
    )
    MICRO_CORRIDORS_AVAILABLE = True
except ImportError:
    MICRO_CORRIDORS_AVAILABLE = False

class MacroRegime(Enum):
    BULL_TREND = "BULL_TREND"
    RANGE = "RANGE"
    HIGH_VOL = "HIGH_VOL"
    CRASH = "CRASH"
    ILLIQUID = "ILLIQUID"

# AWS & Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

# Table configuration
EMPIRE_TABLE = os.environ.get('HISTORY_TABLE', 'EmpireTradesHistory') # Unified Table V7
empire_table = dynamodb.Table(EMPIRE_TABLE)

STATE_TABLE = os.environ.get('STATE_TABLE', 'V4TradingState')
state_table = dynamodb.Table(STATE_TABLE)

# --- V8 ATOMIC SLOT MANAGEMENT ---
def sync_slots_with_exchange(real_count):
    """Sync DynamoDB counter with real exchange position count"""
    try:
        state_table.put_item(
            Item={
                'trader_id': 'GLOBAL_LOCK',
                'ActiveSlots': real_count,
                'LastSync': get_paris_time().isoformat()
            }
        )
        logger.info(f"🔄 Slots synced with Exchange: {real_count}")
    except Exception as e:
        logger.error(f"❌ Failed to sync slots: {e}")

def acquire_atomic_slot(max_slots):
    """Try to increment ActiveSlots in DynamoDB atomically"""
    try:
        state_table.update_item(
            Key={'trader_id': 'GLOBAL_LOCK'},
            UpdateExpression="SET ActiveSlots = if_not_exists(ActiveSlots, :zero) + :one",
            ConditionExpression="if_not_exists(ActiveSlots, :zero) < :max",
            ExpressionAttributeValues={
                ':one': 1,
                ':zero': 0,
                ':max': max_slots
            }
        )
        logger.info("🔒 Atomic Slot ACQUIRED")
        return True
    except Exception as e:
        # ConditionalCheckFailedException or others
        logger.warning(f"⏸️ Atomic Slot REJECTED: Slot limit {max_slots} reached or race condition.")
        return False

def release_atomic_slot():
    """Decrement ActiveSlots in DynamoDB atomically"""
    try:
        state_table.update_item(
            Key={'trader_id': 'GLOBAL_LOCK'},
            UpdateExpression="SET ActiveSlots = if_not_exists(ActiveSlots, :zero) - :one",
            ConditionExpression="ActiveSlots > :zero",
            ExpressionAttributeValues={
                ':one': 1,
                ':zero': 0
            }
        )
        logger.info("🔓 Atomic Slot RELEASED")
    except Exception as e:
        logger.error(f"❌ Failed to release slot: {e}")

def get_paris_time():
    """Returns current Paris time (UTC+1)"""
    # Use timezone-aware UTC to fix deprecation warning
    return datetime.now(timezone.utc) + timedelta(hours=1)

# --- SÉCURITÉ DYNAMIQUE EMPIRE V7 ---
def get_max_slots(balance):
    """Allocate 1 slot ($1000 capacity) per $1000 of real balance"""
    if balance < 1000:
        return 1 # Minimum safety
    return int(balance / 1000)

# Asset classification 
COMMODITIES_SYMBOLS = ['PAXG', 'XAG', 'GOLD', 'SILVER', 'USOIL', 'OIL']
FOREX_SYMBOLS = ['EUR', 'GBP', 'AUD', 'JPY', 'CHF', 'CAD']
INDICES_SYMBOLS = ['DEFI', 'NDX', 'GSPC', 'US30', 'SPX']

def classify_asset(symbol):
    """Classify a Binance/Broker symbol into Asset Class."""
    symbol_upper = symbol.upper()
    if any(comm in symbol_upper for comm in COMMODITIES_SYMBOLS): return "Commodities"
    if any(fx in symbol_upper for fx in FOREX_SYMBOLS): return "Forex"
    if any(idx in symbol_upper for idx in INDICES_SYMBOLS): return "Indices"
    return "Crypto"

# --- V8 SAFE EXECUTION ENGINE ---
def execute_trade_safe(exchange, symbol, size, action='buy'):
    """
    🛠️ V8 execution engine with fill verification
    Prevents 'ghost orders' by polling exchange until confirmation.
    Ref: Problem #10
    """
    logger.info(f"🚀 [V8] Executing {action.upper()} for {size} {symbol}...")
    order = exchange.create_market_order(symbol, action, size)
    
    # Wait for real confirmation (approx 10s)
    for i in range(10):
        try:
            status = exchange.fetch_order(order['id'], symbol)
            if status['status'] == 'closed':
                logger.info(f"✅ Order {order['id']} FULLY FILLED")
                return status # Returns the order with average price and amount
            
            logger.info(f"⏳ Order {order['id']} pending ({status['status']})... Check {i+1}/10")
        except Exception as e:
            logger.warning(f"⚠️ fetch_order failed: {e}")
        
        time.sleep(1)
    
    # Final check
    status = exchange.fetch_order(order['id'], symbol)
    if status['status'] == 'closed':
        return status
        
    # Critial Alert: Order exists but status unknown/not-filled
    error_msg = f"❌ CRITICAL: Order {order['id']} not confirmed as filled after 10s! Manual check required."
    logger.error(error_msg)
    raise TimeoutError(error_msg)

# ==================== TRADING CONFIGURATION (EMPIRE V7) ====================
DEFAULT_SYMBOL = os.environ.get('SYMBOL', 'SOL/USDT')

# Risk Management
CAPITAL_PER_TRADE = float(os.environ.get('CAPITAL', '200'))   
MAX_EXPOSURE = int(os.environ.get('MAX_EXPOSURE', '2'))
COOLDOWN_HOURS = float(os.environ.get('COOLDOWN_HOURS', '4'))

# Trading Parameters
RSI_BUY_THRESHOLD = float(os.environ.get('RSI_THRESHOLD', '42'))
RSI_SELL_THRESHOLD = float(os.environ.get('RSI_SELL_THRESHOLD', '78'))
STOP_LOSS_PCT = float(os.environ.get('STOP_LOSS', '-3.5'))
HARD_TP_PCT = float(os.environ.get('HARD_TP', '8.0'))
TRAILING_TP_PCT = float(os.environ.get('TRAILING_TP', '1.5'))

# Filters & Safety
BTC_CRASH_THRESHOLD = float(os.environ.get('BTC_CRASH', '-0.08'))
VIX_MAX_THRESHOLD = float(os.environ.get('VIX_MAX', '30'))
VIX_REDUCE_THRESHOLD = float(os.environ.get('VIX_REDUCE', '25'))

# Risk Guards (V8.3)
MAX_RISK_PER_TRADE_PCT = float(os.environ.get('MAX_RISK_PER_TRADE', '0.02')) # 2% balance
MAX_DAILY_LOSS_PCT = float(os.environ.get('MAX_DAILY_LOSS', '0.05'))        # 5% balance
GLOBAL_DRAWDOWN_LIMIT = float(os.environ.get('MAX_DRAWDOWN', '0.15'))      # 15% drawdown

# Advanced Features
MULTI_TF_ENABLED = os.environ.get('MULTI_TF', 'true').lower() == 'true'
RSI_4H_THRESHOLD = float(os.environ.get('RSI_4H_THRESHOLD', '50'))

# Circuit Breaker (L1: -5%, L2: -10%, L3: -20%)
CIRCUIT_BREAKER_L1 = float(os.environ.get('CB_L1', '-0.05'))
CIRCUIT_BREAKER_L2 = float(os.environ.get('CB_L2', '-0.10'))
CIRCUIT_BREAKER_L3 = float(os.environ.get('CB_L3', '-0.20'))
CB_COOLDOWN_HOURS = float(os.environ.get('CB_COOLDOWN', '48'))

# SOL Specific (Turbo Mode)
SOL_TRAILING_ACTIVATION = float(os.environ.get('SOL_TRAILING_ACT', '6.0'))
SOL_TRAILING_STOP = float(os.environ.get('SOL_TRAILING_STOP', '2.5'))

# Volume Confirmation (Adaptive V7)
VOLUME_CONFIRMATION = float(os.environ.get('VOL_CONFIRM', '1.2'))
VOLUME_CONFIRM_CRYPTO = float(os.environ.get('VOL_CONFIRM_CRYPTO', '1.2'))
VOLUME_CONFIRM_COMMODITIES = float(os.environ.get('VOL_CONFIRM_COMMOD', '0.12'))
VOLUME_CONFIRM_INDICES = float(os.environ.get('VOL_CONFIRM_INDICES', '0.24'))
VOLUME_CONFIRM_FOREX = float(os.environ.get('VOL_CONFIRM_FOREX', '0.6'))

# Trend Following (V7 Hybrid)
TREND_FOLLOWING_ENABLED = os.environ.get('TREND_FOLLOWING', 'true').lower() == 'true'
TREND_RSI_MIN = float(os.environ.get('TREND_RSI_MIN', '55'))
SMA_PERIOD = int(os.environ.get('SMA_PERIOD', '200'))

# Logic Controls
MOMENTUM_FILTER_ENABLED = os.environ.get('MOMENTUM_FILTER', 'true').lower() == 'true'
DYNAMIC_SIZING_ENABLED = os.environ.get('DYNAMIC_SIZING', 'true').lower() == 'true'
CORRELATION_CHECK_ENABLED = os.environ.get('CORRELATION_CHECK', 'true').lower() == 'true'
REVERSAL_TRIGGER_ENABLED = os.environ.get('REVERSAL_TRIGGER', 'true').lower() == 'true'
MAX_CRYPTO_EXPOSURE = int(os.environ.get('MAX_CRYPTO_EXPOSURE', '2'))
# ========================================================

def log_trade_to_empire(trade_id, symbol, action, strategy, entry_price, size, cost, decision, reason, asset_class='Crypto', tp_pct=0, sl_pct=0, execution_info=''):
    """
    🗄️ Persistence Engine (V8): Purely for DynamoDB
    Logs ready-to-save trade data with optimized composite indexing.
    """
    try:
        timestamp = get_paris_time().isoformat()
        item = {
            'TradeId': trade_id,
            'Timestamp': timestamp,
            'PairTimestamp': f"{symbol}#{timestamp}", # 🚀 Composite key for V8.4 GSI
            'AssetClass': asset_class,
            'Pair': symbol,
            'Type': action, 
            'Strategy': strategy,
            'EntryPrice': str(entry_price),
            'Size': str(size),       
            'Cost': str(cost),    
            'Value': str(cost),   
            'SL': str(sl_pct),       
            'TP': str(tp_pct),       
            'ATR': '0',
            'AI_Decision': decision,
            'AI_Reason': reason,
            'Status': 'OPEN',
            'Execution': execution_info
        }
        empire_table.put_item(Item=item)
        logger.info(f"💾 Trade Persistence SUCCESS: {trade_id}")
    except Exception as e:
        logger.error(f"❌ Persistence FAILED for {trade_id}: {e}")

def place_take_profit_safe(exchange, symbol, size, tp_price):
    """Helper to place TP order with error handling"""
    try:
        exchange.create_limit_order(symbol, 'sell', size, tp_price, params={'reduceOnly': True})
        logger.info(f"🎯 LIMIT TP PLACED @ {tp_price}")
        return True
    except Exception as e:
        logger.error(f"⚠️ Failed to place TP: {e}")
        return False

def log_skip_to_empire(symbol, reason, price, asset_class='Crypto'):
    """Log skipped/no-signal events with composite indexing"""
    try:
        timestamp = get_paris_time().isoformat()
        log_id = f"LOG-{uuid.uuid4().hex[:8]}"
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
            'TTL': int((get_paris_time() + timedelta(days=2)).timestamp())
        }
        empire_table.put_item(Item=item)
    except Exception as e:
        logger.error(f"Failed to log skip: {e}")


# ==================== OPTIMIZATION FUNCTIONS ====================

def is_golden_window(timestamp_iso=None):
    """
    🦁 GOLDEN WINDOWS: High Liquidity Zones
    - Europe Open: 07:00 - 10:00 UTC
    - US Open: 13:00 - 16:00 UTC
    Uses timestamp if provided, else current UTC time.
    """
    try:
        if timestamp_iso:
            dt = datetime.fromisoformat(timestamp_iso)
            hour = dt.hour
        else:
            hour = get_paris_time().hour
            
        is_eu = 7 <= hour <= 10
        is_us = 13 <= hour <= 16
        return is_eu or is_us
    except Exception as e:
        logger.error(f"Golden Window check error: {e}")
        return False

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

def calculate_daily_performance():
    """V8.3: Calculate PnL of trades closed today for Risk Management"""
    try:
        # Paris today starting at 00:00
        today_str = get_paris_time().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        
        response = empire_table.query(
            IndexName='Status-index',
            KeyConditionExpression=boto3.dynamodb.conditions.Key('Status').eq('CLOSED'),
            FilterExpression=boto3.dynamodb.conditions.Attr('ExitTime').gte(today_str)
        )
        
        trades = response.get('Items', [])
        daily_pnl = sum(float(t.get('PnL', 0)) for t in trades)
        logger.info(f"📅 Daily Performance: ${daily_pnl:+.2f} ({len(trades)} trades)")
        return daily_pnl
    except Exception as e:
        logger.error(f"Error calculating daily performance: {e}")
        return 0

# --- V8 GLOBAL CONTEXT CACHE (MarketState Class) ---
class MarketState:
    """
    🏛️ Empire V8 Core: Class-based Global State
    Fetches all global data ONCE at startup with retries and fail-safes.
    Ref: Audit 1 #2 & Audit 2 #15
    """
    def __init__(self, exchange):
        logger.info("🧠 Initializing Empire V8 MarketState...")
        self.timestamp = datetime.now(ZoneInfo('Europe/Paris'))
        
        # 1. Balance & Slots (Audit #15)
        self.balance = exchange.get_balance_usdt()
        self.current_trades = exchange.get_open_positions_count()
        self.max_slots = get_max_slots(self.balance)
        
        # 2. VIX with Retry Logic (Audit #2)
        self.vix = self._fetch_vix_with_retry()
        
        # 3. BTC Context (Circuit Breaker + Crash Filter)
        self.btc = self._fetch_btc_context(exchange)
        
        # 4. Golden Window Status
        self.is_golden = self._check_golden_window()
        
        # 5. Market Regime Detection (Audit #V8.6)
        self.regime = self._determine_macro_regime()
        
        # 6. Risk Guards (Audit #V8.3)
        self.daily_pnl = calculate_daily_performance()
        self.daily_pnl_pct = self.daily_pnl / self.balance if self.balance > 0 else 0
        self.risk_blocked = self.daily_pnl_pct <= -MAX_DAILY_LOSS_PCT
        
        if self.risk_blocked:
            logger.critical(f"🛑 RISK BLOCK: Daily Loss {self.daily_pnl_pct:.2%} exceeds limit {MAX_DAILY_LOSS_PCT:.2%}!")
        
        # 7. Adaptive Entry Threshold (Audit #5)
        self.entry_threshold = 65 if self.regime == MacroRegime.BULL_TREND else 80
        
        logger.info(f"✅ V8.6 MarketState Ready | Regime: {self.regime.value} | Threshold: {self.entry_threshold} | VIX: {self.vix['value']:.1f}")

    def _fetch_vix_with_retry(self, retries=3):
        """Fetch VIX with retry logic + DynamoDB Fallback (Audit #4)"""
        for i in range(retries):
            try:
                can_trade, mult, val = check_vix_filter()
                if val > 0:
                    # Update cache
                    state_table.put_item(Item={
                        'trader_id': 'VIX_CACHE',
                        'value': str(val),
                        'timestamp': get_paris_time().isoformat()
                    })
                    return {"can_trade": can_trade, "multiplier": mult, "value": val}
            except Exception as e:
                logger.warning(f"⚠️ VIX Retry {i+1}/{retries} failed: {e}")
                time.sleep(1)
        
        # 🛡️ Audit #4: Fallback to last known value in DynamoDB (60min check)
        try:
            res = state_table.get_item(Key={'trader_id': 'VIX_CACHE'})
            item = res.get('Item')
            if item:
                val = float(item['value'])
                ts = datetime.fromisoformat(item['timestamp'])
                age_mins = (get_paris_time() - ts).total_seconds() / 60
                
                if age_mins < 60:
                    logger.info(f"♻️ VIX Fallback (Fresh: {age_mins:.1f}m): {val}")
                    return {"can_trade": val < 30, "multiplier": 1.0 if val < 20 else 0.5, "value": val}
                else:
                    logger.warning(f"⚠️ VIX Cache too old ({age_mins:.1f}m). Using as non-blocking warning.")
                    return {"can_trade": True, "multiplier": 1.0, "value": val, "warning": "OLD_CACHE"}
        except: pass

        # Fail-safe: Block if VIX fails repeatedly
        logger.error("❌ VIX API failed and no fallback available. SAFETY BLOCK.")
        return {"can_trade": False, "multiplier": 0, "value": 99.0}

    def _fetch_btc_context(self, exchange):
        """Fetch BTC performance data for CB and Crash filters"""
        cb_can_trade, cb_mult, cb_level, btc_24h, btc_7d = check_circuit_breaker(exchange)
        
        # 1h Crash Filter
        btc_ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=5)
        btc_1h_change = 0
        if btc_ohlcv and len(btc_ohlcv) >= 2:
            btc_1h_change = (btc_ohlcv[-1][4] - btc_ohlcv[-2][4]) / btc_ohlcv[-2][4]
            
        return {
            "can_trade": cb_can_trade,
            "multiplier": cb_mult,
            "level": cb_level,
            "24h": btc_24h,
            "7d": btc_7d,
            "1h_change": btc_1h_change
        }

    def _check_golden_window(self):
        """Check if currently in a high-liquidity golden window"""
        hour = self.timestamp.hour
        is_eu = 7 <= hour <= 10
        is_us = 13 <= hour <= 16
        return is_eu or is_us

    def _determine_macro_regime(self):
        """
        🚀 V8.6: Centralized Regime Detection
        Audit #2.2: Every filter looks at the regime.
        """
        # ⚠️ CRASH: Extreme downside
        if self.btc['level'] in ["L3_SURVIVAL", "L2_HALT"] or self.btc['1h_change'] < -0.05:
            return MacroRegime.CRASH
            
        # 🌋 HIGH_VOL: VIX Spike
        if self.vix['value'] > 30:
            return MacroRegime.HIGH_VOL
            
        # 🐃 BULL_TREND: Clear uptrend + low vol
        if self.btc['7d'] > 0.05 and self.btc['24h'] > -0.02 and self.vix['value'] < 22:
            return MacroRegime.BULL_TREND
            
        # 🌑 ILLIQUID: No liquidity window
        if not self.is_golden:
            return MacroRegime.ILLIQUID
            
        # ⚖️ Default: RANGE
        return MacroRegime.RANGE

    def get_dict(self):
        """Return a dictionary version for legacy code compatibility"""
        return {
            "balance": self.balance,
            "current_trades": self.current_trades,
            "max_slots": self.max_slots,
            "cb": self.btc,
            "btc_1h": self.btc["1h_change"],
            "vix": self.vix,
            "is_golden": self.is_golden,
            "regime": self.regime.value, # V8.6
            "entry_threshold": self.entry_threshold
        }

def check_circuit_breaker(exchange):
    """
    🛡️ CIRCUIT BREAKER (Leçon 2022 - FTX/Luna Crash Protection)
    3 niveaux de protection contre les crashs en cascade:
    - L1: BTC -5% 24h -> Réduire taille 50%
    - L2: BTC -10% 24h -> STOP complet 48h
    - L3: BTC -20% 7j -> MODE SURVIE (liquider alts)
    Returns: (can_trade: bool, size_mult: float, level: str, btc_24h: float, btc_7d: float)
    """

    try:
        # Fetch BTC 24h performance
        btc_ohlcv_24h = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=25)
        if len(btc_ohlcv_24h) > 0:
            btc_now = btc_ohlcv_24h[-1][4]
        else:
            btc_now = 0

        if len(btc_ohlcv_24h) >= 25:
            btc_24h_ago = btc_ohlcv_24h[0][4]
            btc_24h_change = (btc_now - btc_24h_ago) / btc_24h_ago
        else:
            btc_24h_change = 0
        
        # Fetch BTC 7d performance
        btc_ohlcv_7d = exchange.fetch_ohlcv('BTC/USDT', '4h', limit=42)  # ~7 days
        if len(btc_ohlcv_7d) >= 42:
            btc_7d_ago = btc_ohlcv_7d[0][4]
            btc_7d_change = (btc_now - btc_7d_ago) / btc_7d_ago
        else:
            btc_7d_change = 0
        
        logger.info(f"📊 Circuit Breaker Check: BTC 24h={btc_24h_change:.2%} | 7d={btc_7d_change:.2%}")
        
        # Level 3: SURVIVAL MODE (BTC -20% in 7 days)
        if btc_7d_change <= CIRCUIT_BREAKER_L3:
            logger.critical(f"🚨🚨🚨 CIRCUIT BREAKER L3 TRIGGERED! BTC {btc_7d_change:.2%} in 7d. SURVIVAL MODE.")
            return False, 0, "L3_SURVIVAL", btc_24h_change, btc_7d_change
        
        # Level 2: FULL STOP (BTC -10% in 24h)
        if btc_24h_change <= CIRCUIT_BREAKER_L2:
            logger.warning(f"🚨🚨 CIRCUIT BREAKER L2 TRIGGERED! BTC {btc_24h_change:.2%} in 24h. Trading HALTED {CB_COOLDOWN_HOURS}h.")
            return False, 0, "L2_HALT", btc_24h_change, btc_7d_change
        
        # Level 1: REDUCE SIZE (BTC -5% in 24h)
        if btc_24h_change <= CIRCUIT_BREAKER_L1:
            logger.warning(f"⚠️ CIRCUIT BREAKER L1 TRIGGERED! BTC {btc_24h_change:.2%} in 24h. Reducing size 50%.")
            return True, 0.5, "L1_REDUCE", btc_24h_change, btc_7d_change
        
        # All clear
        return True, 1.0, "OK", btc_24h_change, btc_7d_change
        
    except Exception as e:
        logger.error(f"Circuit Breaker Error: {e}. Allowing trade by default.")
        return True, 1.0, "ERROR", 0, 0


def get_volume_threshold_for_asset(asset_class):
    """🔥 V7: Get adaptive volume threshold based on asset class"""
    thresholds = {
        'Crypto': VOLUME_CONFIRM_CRYPTO,
        'Commodities': VOLUME_CONFIRM_COMMODITIES,
        'Indices': VOLUME_CONFIRM_INDICES,
        'Forex': VOLUME_CONFIRM_FOREX,
    }
    return thresholds.get(asset_class, VOLUME_CONFIRMATION)


def check_volume_confirmation(ohlcv_data, threshold=None, asset_class='Crypto'):
    """
    🎯 Volume Confirmation Filter (V7 Adaptive)
    Uses per-asset-class thresholds to avoid SKIPPED_LOW_VOLUME on niche assets.
    Returns: (confirmed: bool, vol_ratio: float)
    """
    try:
        if threshold is not None:
            req_threshold = threshold
        else:
            req_threshold = get_volume_threshold_for_asset(asset_class)

        if len(ohlcv_data) < 20:
            return True, 1.0  # Not enough data, allow
        
        volumes = [c[5] for c in ohlcv_data[-20:]]
        avg_vol = sum(volumes[:-1]) / len(volumes[:-1])  # Exclude current
        current_vol = volumes[-1]
        
        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
        
        if vol_ratio >= req_threshold:
            logger.info(f"✅ Volume Confirmed: {vol_ratio:.2f}x average (req {req_threshold}x)")
            return True, vol_ratio
        else:
            logger.info(f"⚠️ Low Volume: {vol_ratio:.2f}x average (need {req_threshold}x)")
            return False, vol_ratio
            
    except Exception as e:
        logger.error(f"Volume check error: {e}")
        return True, 1.0


def calculate_sma(ohlcv_data, period=200):
    """
    📊 V7: Calculate Simple Moving Average
    Used for Trend Following mode
    Returns: SMA value or None if insufficient data
    """
    if not ohlcv_data or len(ohlcv_data) < period:
        return None
    closes = [c[4] for c in ohlcv_data[-period:]]
    return sum(closes) / len(closes)


def get_dynamic_rsi_threshold(circuit_breaker_level, btc_7d_change, symbol=''):
    """
    🎯 Dynamic RSI Threshold based on Market Regime (V4 Fortress Balanced)
    - BULL (BTC +5% 7d): RSI < 40 (current behavior)
    - NEUTRAL: RSI < 35
    - BEAR (BTC -5% 7d): RSI < 30 (stricter) - EXCEPT ETH stays at 35
    Returns: (threshold, regime)
    """
    if btc_7d_change >= 0.05:  # Bull market
        threshold = RSI_BUY_THRESHOLD  # Use configured (40)
        regime = "BULL"
    elif btc_7d_change <= -0.05:  # Bear market
        # 🛠️ V4 Fortress Balanced: ETH keeps RSI 35 even in BEAR (backtest 2022 lesson)
        if 'ETH' in symbol:
            threshold = 35  # ETH: More flexible in bear markets
            regime = "BEAR_ETH_ADJUSTED"
        else:
            threshold = 30  # BTC/SOL: Stricter
            regime = "BEAR"
    else:
        threshold = 35  # Neutral
        regime = "NEUTRAL"
    
    logger.info(f"📊 Market Regime: {regime} | Dynamic RSI Threshold: {threshold} | Symbol: {symbol}")
    return threshold, regime


# ==================== V5 ADVANCED OPTIMIZATIONS ====================

def check_momentum_filter(ohlcv_data, rsi=100):
    """
    🚀 V5 OPTIMIZATION 1: Momentum Filter (EMA Cross)
    Only buy when EMA 20 > EMA 50 (confirmed uptrend)
    Avoids dead cat bounces and bear market rallies
    BYPASS: If RSI < 30 (Deep Value), ignore momentum
    Returns: (is_bullish: bool, trend: str, ema_diff_pct: float)
    """
    if not MOMENTUM_FILTER_ENABLED:
        return True, "DISABLED", 0
    
    # 🦁 Bypass for Deep Value
    if rsi < 30:
        logger.info(f"🦁 Momentum Filter BYPASSED: RSI {rsi:.1f} < 30 (Deep Value)")
        return True, "DEEP_VALUE", 0
    
    try:
        if len(ohlcv_data) < 50:
            return True, "INSUFFICIENT_DATA", 0
        
        closes = [c[4] for c in ohlcv_data[-50:]]
        
        # Simple EMA calculation
        def ema(data, period):
            multiplier = 2 / (period + 1)
            ema_val = sum(data[:period]) / period  # SMA for first period
            for price in data[period:]:
                ema_val = (price - ema_val) * multiplier + ema_val
            return ema_val
        
        ema_20 = ema(closes, 20)
        ema_50 = ema(closes, 50)
        
        ema_diff_pct = ((ema_20 - ema_50) / ema_50) * 100
        
        if ema_20 > ema_50:
            logger.info(f"✅ Momentum BULLISH: EMA20 > EMA50 by {ema_diff_pct:.2f}%")
            return True, "BULLISH", ema_diff_pct
        elif ema_20 < ema_50 * 0.98:  # 2% below = strong bearish
            logger.warning(f"🚫 Momentum BEARISH: EMA20 < EMA50 by {abs(ema_diff_pct):.2f}%")
            return False, "BEARISH", ema_diff_pct
        else:
            logger.info(f"⚠️ Momentum NEUTRAL: EMA crossing zone ({ema_diff_pct:.2f}%)")
            return True, "NEUTRAL", ema_diff_pct
            
    except Exception as e:
        logger.error(f"Momentum filter error: {e}")
        return True, "ERROR", 0


def check_portfolio_correlation(symbol):
    """
    🚀 V5 OPTIMIZATION 2: Portfolio Correlation Check
    Limits exposure when multiple crypto trades are open and losing
    Prevents cascade losses (2022 lesson)
    Returns: (can_trade: bool, reason: str, crypto_exposure: int)
    """
    if not CORRELATION_CHECK_ENABLED:
        return True, "DISABLED", 0
    
    try:
        # Get all open crypto trades using Performance Index
        response = empire_table.query(
            IndexName='Status-index',
            KeyConditionExpression=boto3.dynamodb.conditions.Key('Status').eq('OPEN'),
            FilterExpression=boto3.dynamodb.conditions.Attr('AssetClass').eq('Crypto')
        )
        open_trades = response.get('Items', [])
        crypto_exposure = len(open_trades)
        
        if crypto_exposure >= MAX_CRYPTO_EXPOSURE:
            # Check if portfolio is in loss
            total_unrealized = 0
            for trade in open_trades:
                # Simple check: if any trade is significantly negative
                if trade.get('UnrealizedPnL'):
                    total_unrealized += float(trade.get('UnrealizedPnL', 0))
            
            if total_unrealized < 0:
                logger.warning(f"🚨 CORRELATION BLOCK: {crypto_exposure} crypto trades open, portfolio in loss (${total_unrealized:.2f})")
                return False, f"HIGH_CORRELATION_RISK: {crypto_exposure} trades, PnL ${total_unrealized:.2f}", crypto_exposure
        
        logger.info(f"✅ Correlation OK: {crypto_exposure}/{MAX_CRYPTO_EXPOSURE} crypto trades open")
        return True, "OK", crypto_exposure
        
    except Exception as e:
        logger.error(f"Correlation check error: {e}")
        return True, "ERROR", 0


def calculate_dynamic_position_size(base_capital, final_score, stop_loss_pct, total_balance):
    """
    🚀 V8.5: Proportional Position Sizing
    Size is now directly proportional to the unified signal score.
    Returns: (adjusted_capital: float, confidence_score: float)
    """
    if not DYNAMIC_SIZING_ENABLED:
        return base_capital, 1.0
    
    # 📈 Score-to-Confidence mapping:
    # 70 pts -> 0.5x multiplier (Minimum entry)
    # 85 pts -> 1.0x multiplier (Standard entry)
    # 100 pts -> 1.5x multiplier (Strong conviction)
    
    confidence_score = 0.5 + (final_score - 70) / 30
    confidence_score = max(0.5, min(confidence_score, 1.5))
    
    adjusted_capital = base_capital * confidence_score
    
    # 🛡️ V8.3: Hard Risk Cap (PositionSize * SL% <= Balance * MAX_RISK_PER_TRADE_PCT)
    max_risk_dollars = total_balance * MAX_RISK_PER_TRADE_PCT
    actual_risk_dollars = adjusted_capital * (abs(stop_loss_pct) / 100)
    
    if actual_risk_dollars > max_risk_dollars:
        old_cap = adjusted_capital
        adjusted_capital = max_risk_dollars / (abs(stop_loss_pct) / 100)
        logger.warning(f"🛡️ Risk Cap Applied: ${old_cap:.0f} -> ${adjusted_capital:.0f} (Risk limited to 2% of balance)")
        
    logger.info(f"💰 Unified Dynamic Sizing: Score {final_score} -> {confidence_score:.2f}x | Final: ${adjusted_capital:.0f}")
    
    return adjusted_capital, confidence_score

# ================================================================


def check_vix_filter():
    """
    🔥 OPTIMIZATION 1: VIX Filter
    Don't trade during extreme market fear/volatility
    Uses Yahoo Finance API directly (no yfinance dependency)
    Returns: (can_trade: bool, size_multiplier: float, vix_value: float)
    """
    try:
        # Use Yahoo Finance API directly via requests
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=1d"
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; EmpireV7/1.0)'}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code != 200:
            logger.warning(f"VIX API returned {response.status_code}. Allowing trade by default.")
            return True, 1.0, 0
        
        data = response.json()
        result = data.get('chart', {}).get('result', [])
        if not result:
            return True, 1.0, 0
            
        # Get current VIX from the regular market price
        meta = result[0].get('meta', {})
        current_vix = float(meta.get('regularMarketPrice', 0))
        
        if current_vix <= 0:
            # Fallback to close prices
            indicators = result[0].get('indicators', {}).get('quote', [{}])[0]
            closes = indicators.get('close', [])
            if closes and closes[-1]:
                current_vix = float(closes[-1])
            else:
                return True, 1.0, 0
        
        if current_vix > VIX_MAX_THRESHOLD:
            logger.warning(f"🚨 VIX too high ({current_vix:.1f} > {VIX_MAX_THRESHOLD}). Trading blocked.")
            return False, 0, current_vix
        elif current_vix > VIX_REDUCE_THRESHOLD:
            logger.info(f"⚠️ VIX elevated ({current_vix:.1f} > {VIX_REDUCE_THRESHOLD}). Reducing position size by 50%.")
            return True, 0.5, current_vix
        else:
            logger.info(f"✅ VIX normal ({current_vix:.1f}). Full position size allowed.")
            return True, 1.0, current_vix
            
    except requests.Timeout:
        logger.warning("VIX fetch timeout. Allowing trade by default.")
        return True, 1.0, 0
    except Exception as e:
        logger.error(f"VIX fetch error: {e}. Allowing trade by default.")
        return True, 1.0, 0


def check_multi_timeframe(symbol, exchange, rsi_1h):
    """
    🔥 OPTIMIZATION 2: Multi-Timeframe Confirmation
    Confirm 1h signal with 4h timeframe for stronger signals
    Returns: (signal_strength: str, rsi_4h: float)
    """
    if not MULTI_TF_ENABLED:
        return "NORMAL", 0
        
    try:
        # Fetch 4h data
        ohlcv_4h = exchange.fetch_ohlcv(symbol, '4h', limit=20)
        if not ohlcv_4h or len(ohlcv_4h) < 14:
            return "NORMAL", 0
        
        # Calculate RSI on 4h
        analysis_4h = analyze_market(ohlcv_4h)
        rsi_4h = analysis_4h['indicators']['rsi']
        
        logger.info(f"📊 Multi-TF Analysis | 1h RSI: {rsi_1h:.1f} | 4h RSI: {rsi_4h:.1f}")
        
        # Strong signal: both timeframes oversold
        if rsi_1h < RSI_BUY_THRESHOLD and rsi_4h < RSI_4H_THRESHOLD:
            logger.info(f"🎯 STRONG SIGNAL: Both 1h and 4h RSI oversold!")
            return "STRONG", rsi_4h
        # Weak signal: only 1h oversold, 4h not confirming
        elif rsi_1h < RSI_BUY_THRESHOLD and rsi_4h >= RSI_4H_THRESHOLD:
            logger.info(f"⚠️ WEAK SIGNAL: 1h oversold but 4h ({rsi_4h:.1f}) not confirming. Extra caution needed.")
            return "WEAK", rsi_4h
        else:
            return "NO_SIGNAL", rsi_4h
            
    except Exception as e:
        logger.error(f"Multi-TF error: {e}")
        return "NORMAL", 0



def check_reversal_pattern(ohlcv_data, rsi=100):
    """
    🚀 OPTIMIZATION FINAL: Reversal Trigger
    Only buy if the last candle is GREEN (Close > Open) or Neutral
    Prevents catching falling knives during active crashes.
    EXCEPTION: RSI < 25 (Extreme Oversold) allows catching the knife.
    Returns: (is_reversal: bool, reason: str)
    """
    if not REVERSAL_TRIGGER_ENABLED:
        return True, "DISABLED"
    
    try:
        current_candle = ohlcv_data[-1]
        open_p = current_candle[1]
        close_p = current_candle[4]
        
        # Exception: Extreme Oversold
        if rsi < 25:
            return True, f"EXTREME_OVERSOLD (RSI {rsi:.1f} < 25)"
        
        # Buy only if Green Candle (Bounce started)
        if close_p >= open_p:
            return True, f"GREEN_CANDLE (Close {close_p} >= Open {open_p})"
        
        return False, f"FALLING_KNIFE (Red Candle: {close_p} < {open_p})"
        
    except Exception as e:
        logger.error(f"Reversal check error: {e}")
        return True, "ERROR"  # Fail safe to allow trade if data issue? Or block? Safe to allow mostly.

def calculate_dynamic_trailing(pnl_pct, atr_pct, symbol=''):
    """
    🔥 OPTIMIZATION 3: Dynamic Trailing Stop based on ATR (V4 Fortress Balanced)
    Tighter trailing when in higher profit, wider when profit is small
    SOL: 2.5x ATR for ultra-volatile momentum capture
    Returns: stop_distance_pct
    """
    try:
        if atr_pct <= 0:
            atr_pct = 2.0  # Default 2% if ATR unavailable
        
        # 🛠️ V4 Fortress Balanced: SOL gets wider trailing for momentum runs
        if 'SOL' in symbol and pnl_pct > 10.0:
            # SOL in turbo zone: let profits run with 2.5x ATR trailing
            return 2.5 * atr_pct
        
        if pnl_pct > 3 * atr_pct:
            # Very profitable - tight trailing
            return 1.0 * atr_pct
        elif pnl_pct > 2 * atr_pct:
            # Good profit - medium trailing
            return 1.5 * atr_pct
        elif pnl_pct > atr_pct:
            # Small profit - wider trailing
            return 2.0 * atr_pct
        else:
            # Minimal profit - use standard trailing
            return TRAILING_TP_PCT
            
    except Exception as e:
        return TRAILING_TP_PCT


# ================================================================

def fetch_current_price(symbol, asset_class, exchange=None):
    return float(exchange.fetch_ticker(symbol)['last'])

def ask_bedrock(symbol, rsi, news_context, portfolio_stats, history):
    """Query Bedrock (Claude 3 Haiku) with optimized XML-structured Devil's Advocate Logic"""
    
    last_trade_info = history[0] if history else 'None'
    current_exposure = portfolio_stats.get('current_pair_exposure', 0)
    
    prompt = f"""
Vous êtes l'Analyste de Flux de Nouvelles pour l'Empire V7 (Hybrid Architecture).
LA DÉCISION TECHNIQUE EST DÉJÀ PRISE : Le système a confirmé que {symbol} est statistiquement prêt pour un achat (RSI à {rsi:.1f}).

VOTRE MISSION UNIQUE :
1. Examiner les nouvelles récentes ci-dessous.
2. Déterminer s'il existe une nouvelle CATASTROPHIQUE ou MAJEURE qui invalide ce signal (ex: hack, faillite, décision brutale de la Fed).
3. NE PAS remettre en question le RSI ou les seuils techniques. Le système a déjà validé la probabilité.

CONTEXTE :
- Seuil Dynamique appliqué : {portfolio_stats.get('dynamic_threshold', RSI_BUY_THRESHOLD)}
- RSI Actuel : {rsi:.1f} (C'est mathématiquement VALIDE)

NEWS :
{news_context}

RÈGLE DÉCISIONNELLE :
- CONFIRM : Si les news sont neutres, positives ou simplement du "bruit" habituel.
- CANCEL : Uniquement si une news spécifique contredit directement la survie du trade à court terme.

RÉPONSE JSON : {{ "decision": "CONFIRM" | "CANCEL", "reason": "explication news uniquement" }}
"""
    try:
        response = bedrock.invoke_model(
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
        
        # Extract JSON from response
        if "```json" in completion:
            completion = completion.split("```json")[1].split("```")[0].strip()
        elif "```" in completion:
            completion = completion.split("```")[1].split("```")[0].strip()
        
        # Find JSON object
        start = completion.find('{')
        end = completion.rfind('}') + 1
        if start != -1 and end > start:
            completion = completion[start:end]
        
        return json.loads(completion)
    except Exception as e:
        logger.warning(f"⚠️ Bedrock Error: {e}. Fail-safe: CONFIRM with Low Confidence (Audit #3.3)")
        return {"decision": "CONFIRM", "reason": "AWS_API_TIMEOUT_FALLBACK", "confidence": 0.5}

def close_all_positions(open_trades, current_price, reason, exchange=None):
    """Helper to close all open positions with proper PnL calculation"""
    exit_time = get_paris_time().isoformat()
    total_pnl = 0
    
    for trade in open_trades:
        entry_price = float(trade['EntryPrice'])
        # V6.2: Use position VALUE (Cost) for consistency across all bots
        position_value = float(trade.get('Cost', 0))
        # Calculate P&L as percentage of position value
        pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
        trade_pnl = (pnl_pct / 100) * position_value
        total_pnl += trade_pnl
        
        # 🚀 EXECUTE CLOSE ON EXCHANGE
        if exchange:
            try:
                symbol = trade['Pair']
                size = float(trade['Size'])
                logger.info(f"📉 CLOSING POSITION: {size} {symbol} ({reason})")
                
                # 1. Market Sell (🛠️ V8 SAFE EXECUTION)
                filled_order = execute_trade_safe(exchange, symbol, size, 'sell')
                logger.info(f"📉 Position Closed (Confirmed): {filled_order['id']}")
                
                # 2. Cancel Open Orders (TP/SL)
                exchange.cancel_all_orders(symbol)
                logger.info("✅ Position Closed & Orders Cancelled")
                
                # 🔓 V8: Release Atomic Slot
                release_atomic_slot()
                
            except Exception as close_err:
                logger.error(f"❌ CLOSE EXECUTION FAILED: {close_err}")
                # We still mark as closed in DB to avoid infinite retry loop, but log error
        
        empire_table.update_item(
            Key={'TradeId': trade['TradeId']},
            UpdateExpression="set #st = :s, PnL = :p, ExitPrice = :ep, ExitTime = :et, ExitReason = :er",
            ExpressionAttributeNames={'#st': 'Status'},
            ExpressionAttributeValues={
                ':s': 'CLOSED', 
                ':p': str(round(trade_pnl, 2)), 
                ':ep': str(current_price), 
                ':et': exit_time,
                ':er': reason
            }
        )
    return total_pnl

def manage_exits(symbol, asset_class, exchange=None, memory_cache=None):
    """
    Gestion des sorties (V8.4.1 Optimized Query & Cache)
    """
    try:
        # Performance Index Query for OPEN trades for this symbol DIRECTLY
        response = empire_table.query(
            IndexName='GSI_OpenByPair',
            KeyConditionExpression=(
                boto3.dynamodb.conditions.Key('Status').eq('OPEN') & 
                boto3.dynamodb.conditions.Key('PairTimestamp').begins_with(f"{symbol}#")
            )
        )
        open_trades = response.get('Items', [])
        if not open_trades: 
            return None

        # Calculate weighted average entry price
        total_cost = sum(float(t['EntryPrice']) * float(t.get('Size', 1)) for t in open_trades)
        total_size = sum(float(t.get('Size', 1)) for t in open_trades)
        avg_price = total_cost / total_size if total_size > 0 else 0
        
        current_price = fetch_current_price(symbol, asset_class, exchange)
        if current_price == 0: 
            return None
        
        pnl_pct = ((current_price - avg_price) / avg_price) * 100
        
        logger.info(f"📊 {symbol} | Avg: {avg_price:.2f} | Current: {current_price:.2f} | PnL: {pnl_pct:+.2f}%")

        # ==================== EXIT LOGIC ====================
        
        # Determine Trade-Specific or Global limits
        # V5.1 Micro-Corridors support
        trade_sl_pct = float(open_trades[0].get('SL', 0))
        trade_tp_pct = float(open_trades[0].get('TP', 0))
        
        # Use Dynamic values if set, otherwise Global defaults
        stop_loss_limit = trade_sl_pct if trade_sl_pct != 0 else STOP_LOSS_PCT
        take_profit_limit = trade_tp_pct if trade_tp_pct != 0 else HARD_TP_PCT
        
        # Ensure SL is negative
        if stop_loss_limit > 0: stop_loss_limit = -stop_loss_limit
        
        # 🛑 STOP LOSS CHECK (Priority 1)
        if pnl_pct <= stop_loss_limit:
            logger.warning(f"🛑 STOP LOSS HIT at {pnl_pct:.2f}% (Limit: {stop_loss_limit:.2f}%)! Closing all positions.")
            total_pnl = close_all_positions(open_trades, current_price, "STOP_LOSS", exchange)
            return f"STOP_LOSS_AT_{pnl_pct:.2f}%_PNL_${total_pnl:.2f}"
            
        # 💎 HARD TAKE PROFIT CHECK (Priority 2 - Guaranteed exit)
        if pnl_pct >= take_profit_limit:
            logger.info(f"💎 HARD TAKE PROFIT at {pnl_pct:.2f}% (Limit: {take_profit_limit:.2f}%)! Securing profits.")
            total_pnl = close_all_positions(open_trades, current_price, "HARD_TP", exchange)
            return f"HARD_TP_AT_{pnl_pct:.2f}%_PNL_${total_pnl:.2f}"
            
        # 📈 V8.6: ATR-Based Trailing Stop (Audit #4)
        atr_pct = 0
        cache_key = f"{symbol}_1h"
        if memory_cache is not None and cache_key in memory_cache:
            atr = memory_cache[cache_key]['analysis']['indicators'].get('atr', 0)
            atr_pct = (atr / current_price) * 100 if current_price > 0 else 0

        #  SOL TURBO TRAILING (Priority 2.5)
        if 'SOL' in symbol and pnl_pct >= SOL_TRAILING_ACTIVATION:
            # ... update peak ...
            for trade in open_trades:
                peak_pnl = float(trade.get('PeakPnL', pnl_pct))
                if pnl_pct > peak_pnl:
                    empire_table.update_item(
                        Key={'TradeId': trade['TradeId']},
                        UpdateExpression="set PeakPnL = :p",
                        ExpressionAttributeValues={':p': str(pnl_pct)}
                    )
                    peak_pnl = pnl_pct
                
                # Dynamic Trigger: 2.5x ATR or static fallback
                trail_limit = max(SOL_TRAILING_STOP, atr_pct * 2.5) if atr_pct > 0 else SOL_TRAILING_STOP
                trailing_trigger = peak_pnl - trail_limit
                
                if pnl_pct <= trailing_trigger and trailing_trigger > 0:
                    logger.info(f"🚀 SOL TURBO ATR TRAILING triggered! Peak: +{peak_pnl:.2f}% | Current: +{pnl_pct:.2f}%")
                    total_pnl = close_all_positions(open_trades, current_price, "SOL_ATR_TRAILING", exchange)
                    return f"SOL_ATR_TRAILING_AT_{pnl_pct:.2f}%"

        # 📈 TRAILING STOP CHECK (Priority 3 - RSI confirmation required)
        rsi = None
        if pnl_pct >= TRAILING_TP_PCT:
            # Audit #4: If ATR shows expansion, give more room
            trail_activation = TRAILING_TP_PCT
            if atr_pct > 0.5: trail_activation += (atr_pct * 0.5) 
            
            if pnl_pct >= trail_activation:
                # 🧠 V8.4.1: Use shared cache
                if memory_cache is not None and cache_key in memory_cache and memory_cache[cache_key]:
                    cached = memory_cache[cache_key]
                    rsi = cached["analysis"]['indicators']['rsi']
                else:
                    target_ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=200)
                    if target_ohlcv and len(target_ohlcv) >= 14:
                        analysis = analyze_market(target_ohlcv)
                        rsi = analysis['indicators']['rsi']
                        if memory_cache is not None: memory_cache[cache_key] = {"ohlcv": target_ohlcv, "analysis": analysis}
                
                if rsi and rsi > RSI_SELL_THRESHOLD:
                    logger.info(f"📈 TRAILING TP ACTIVATED (RSI {rsi:.1f} > {RSI_SELL_THRESHOLD}). Closing at {current_price:.2f}")
                    total_pnl = close_all_positions(open_trades, current_price, "TRAILING_TP", exchange)
                    return f"TRAILING_TP_AT_{pnl_pct:.2f}%"

        # 🚀 ATR-BASED TRAILING (Audit #6) - Pure price-based safety
        if pnl_pct >= 1.0: # Only if at least 1% profit
            for trade in open_trades:
                peak_pnl = float(trade.get('PeakPnL', pnl_pct))
                if pnl_pct > peak_pnl:
                    empire_table.update_item(
                        Key={'TradeId': trade['TradeId']},
                        UpdateExpression="set PeakPnL = :p",
                        ExpressionAttributeValues={':p': str(pnl_pct)}
                    )
                    peak_pnl = pnl_pct
                
                # ATR Trailing: If profit drops more than 1.5x ATR from peak
                atr_dist = max(1.0, atr_pct * 1.5) if atr_pct > 0 else 1.5
                if pnl_pct < (peak_pnl - atr_dist):
                    logger.warning(f"📉 ATR TRAILING: Profit dropped {pnl_pct:.2f}% < {peak_pnl:.2f}% - {atr_dist:.1f}%")
                    total_pnl = close_all_positions(open_trades, current_price, "ATR_TRAILING_EXIT", exchange)
                    return f"ATR_TRAILING_AT_{pnl_pct:.2f}%"
        
        # Log status if still held
        rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
        logger.info(f"📊 {symbol} | PnL: {pnl_pct:+.2f}% | RSI: {rsi_str} | Status: HOLD")
    
        return "HOLD"
        
    except Exception as e:
        logger.error(f"Exit Error: {e}")
        return None

def get_portfolio_context(symbol, asset_class='Crypto'):
    """
    Get portfolio context — V8.4: Uses optimized Composite GSI (Status + PairTimestamp)
    Ref: Audit #14 & #V8.4 (Fill/Cost optimization)
    """
    try:
        # 1. Get current OPEN trades for this specific pair DIRECTLY from index
        # 🚀 No FilterExpression needed anymore! Pure PK+SK query.
        response_open = empire_table.query(
            IndexName='GSI_OpenByPair',
            KeyConditionExpression=(
                boto3.dynamodb.conditions.Key('Status').eq('OPEN') & 
                boto3.dynamodb.conditions.Key('PairTimestamp').begins_with(f"{symbol}#")
            )
        )
        open_trades = response_open.get('Items', [])
        
        # 2. Get last CLOSED trade for Cooldown (PK + BeginsWith SK)
        response_closed = empire_table.query(
            IndexName='GSI_OpenByPair',
            KeyConditionExpression=(
                boto3.dynamodb.conditions.Key('Status').eq('CLOSED') & 
                boto3.dynamodb.conditions.Key('PairTimestamp').begins_with(f"{symbol}#")
            ),
            ScanIndexForward=False, # Get latest first
            Limit=1
        )
        last_closed_items = response_closed.get('Items', [])
        last_closed = last_closed_items[0] if last_closed_items else None
        
        # Determine Truly Last Trade
        last_trade = open_trades[0] if open_trades else last_closed
        
        return {"current_pair_exposure": len(open_trades), "last_trade": last_trade}, open_trades
    except Exception as e:
        logger.error(f"Portfolio context error: {e}")
        return {"current_pair_exposure": 0}, []

def lambda_handler(event, context):
    # Determine Context from Event Payload (Priority) or Env
    # Symbols can be a single symbol or a comma-separated list
    symbols_env = os.environ.get('SYMBOLS', DEFAULT_SYMBOL)
    symbols_to_check = event.get('symbols', event.get('symbol', symbols_env)).split(',')
    
    results = []
    
    try:
        # Initialize Exchange with Keys
        api_key = os.environ.get('API_KEY')
        secret = os.environ.get('SECRET_KEY')
        trading_mode = os.environ.get('TRADING_MODE', 'test')
        testnet = (trading_mode == 'test' or trading_mode == 'paper')
        
        exchange = ExchangeConnector('binance', api_key=api_key, secret=secret, testnet=testnet)
        
        # 🔥 V8 GLOBAL CONTEXT (Architecture Context-Aware)
        # We fetch EVERYTHING global once, before the loop
        # V8: Global Market Context
        state = MarketState(exchange)
        g_ctx = state.get_dict()
        
        current_trades = g_ctx['current_trades']
        max_slots = g_ctx['max_slots']
        
        # 🧠 V8.4: In-Memory Execution Cache (Avoid redundant OHLCV/Analysis)
        memory_cache = {}
        
        # 🔄 V8: Sync DynamoDB Lock with Exchange Reality
        sync_slots_with_exchange(current_trades)
        
        for raw_symbol in symbols_to_check:
            symbol = raw_symbol.strip()
            if not symbol: continue
            
            # Dynamic classification (similar to Dashboard API)
            asset_class = classify_asset(symbol)
            logger.info(f"🔍 Processing {symbol} ({asset_class})")
            
            try:
                # 1. GESTION DES SORTIES (Priorité Absolue)
                exit_status = manage_exits(symbol, asset_class, exchange, memory_cache)
                if exit_status and "CLOSED" in exit_status:
                    results.append({"symbol": symbol, "status": "EXIT_SUCCESS", "details": exit_status})
                    current_trades = max(0, current_trades - 1) # Free a slot immediately
                    continue

                # 🚀 V7 DYNAMIC SLOTS CHECK: If full, only manage exits (already done above)
                if current_trades >= max_slots:
                    logger.info(f"⏸️ Slots Full ({current_trades}/{max_slots}). Skipping BUY analysis for {symbol}.")
                    results.append({"symbol": symbol, "status": "SLOTS_FULL", "slots": f"{current_trades}/{max_slots}"})
                    continue

                # 2. 🛡️ CIRCUIT BREAKER CHECK (V8: From Cache)
                if not g_ctx['cb']['can_trade'] or g_ctx.get('risk_blocked'):
                    reason = f"BLOCKED_CB_{g_ctx['cb']['level']}" if not g_ctx['cb']['can_trade'] else "BLOCKED_DAILY_LOSS"
                    if g_ctx['cb']['level'] == "L3_SURVIVAL":
                        logger.critical(f"🚨 SURVIVAL MODE ACTIVE - BTC Crash!")
                    results.append({"symbol": symbol, "status": reason})
                    continue
                
                # 2.5 FILTRE DE CORRÉLATION BTC (V8: From Cache)
                if g_ctx['btc_1h'] < BTC_CRASH_THRESHOLD:
                    logger.warning(f"🚨 BTC CRASH ({g_ctx['btc_1h']:.2%}). Buys blocked.")
                    results.append({"symbol": symbol, "status": "SKIPPED_BTC_CRASH", "btc_change": f"{g_ctx['btc_1h']:.2%}"})
                    continue

                # 3. CONTEXTE (V8: No longer blockers, only scorers)
                portfolio_stats, history = get_portfolio_context(symbol, asset_class)
                hours_since = 999
                if portfolio_stats.get('last_trade'):
                    last_time = datetime.fromisoformat(portfolio_stats['last_trade']['Timestamp'])
                    hours_since = (get_paris_time() - last_time).total_seconds() / 3600

                # 4. ANALYSE & SIGNAL
                # 🧠 V8.4 Persistent Memory Cache (Fetch & Analyze only once per run)
                cache_key = f"{symbol}_1h"
                if cache_key not in memory_cache:
                    ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=200)
                    if not ohlcv or len(ohlcv) < 14:
                        memory_cache[cache_key] = None
                    else:
                        analysis = analyze_market(ohlcv)
                        memory_cache[cache_key] = {
                            "ohlcv": ohlcv,
                            "analysis": analysis
                        }
                
                cached_data = memory_cache.get(cache_key)
                if not cached_data:
                    results.append({"symbol": symbol, "status": "SKIPPED_NO_DATA"})
                    continue
                
                target_ohlcv = cached_data["ohlcv"]
                analysis = cached_data["analysis"]
                rsi = analysis['indicators']['rsi']
                current_price = analysis['current_price']

                # 5. 🎯 DYNAMIC RSI THRESHOLD (V8: Use Cache BTC 7d)
                dynamic_rsi_threshold, market_regime = get_dynamic_rsi_threshold(g_ctx['cb']['level'], g_ctx['cb']['7d'], symbol)
                
                # 🎯 V5.1 Micro-Corridors Override (Time-Based Optimization)
                corridor_risk_mult = 1.0
                corridor_tp_mult = 1.0
                corridor_sl_mult = 1.0
                corridor_name = "Standard"
                
                if MICRO_CORRIDORS_AVAILABLE:
                    c_params = get_corridor_params(symbol)
                    if c_params:
                        p = c_params.get('params', {})
                        corridor_risk_mult = p.get('risk_multiplier', 1.0)
                        corridor_tp_mult = p.get('tp_multiplier', 1.0)
                        corridor_sl_mult = p.get('sl_multiplier', 1.0)
                        corridor_name = c_params.get('name', 'Standard')
                        dynamic_rsi_threshold = p.get('rsi_threshold', dynamic_rsi_threshold)
                        
                # 🦁 GOLDEN WINDOW Check (V8: Use Cache)
                in_golden_window = g_ctx['is_golden']
                
                # 🔥 V7: Adaptive volume threshold per asset class
                required_volume = get_volume_threshold_for_asset(asset_class)
                
                #  Macro Regime Relaxation (Audit #V8.6)
                if g_ctx['regime'] == "BULL_TREND":
                    required_volume *= 0.7 
                    logger.info(f"🐂 BULL REGIME: Relaxing volume to {required_volume:.2f}x")
                    score += 5
                    scoring_details.append("BULL_REGIME_BONUS (+5)")

                if in_golden_window:
                    required_volume = min(required_volume, 1.0)  # More aggressive in golden window
                    dynamic_rsi_threshold = max(dynamic_rsi_threshold, 45) # Allow up to 45
                
                # 📊 V7: Calculate SMA200 for Trend Following
                sma200 = calculate_sma(target_ohlcv, SMA_PERIOD)
                
                # ======================== V8: SCORING PIPELINE ========================
                # 🛠️ V8.2: Integrated Context Scoring (Less Over-Filtering)
                score = 0
                scoring_details = []
                
                # 🛡️ 0. CONTEXT PENALTIES (Size Modulators moved to Score)
                # VIX Penalty
                if not g_ctx['vix']['can_trade']: # If VIX > 30
                    score -= 15
                    scoring_details.append(f"VIX_HIGH_PENALTY (-15) [VIX:{g_ctx['vix']['value']}]")
                elif g_ctx['vix']['value'] > 25:
                    score -= 5
                    scoring_details.append("VIX_NORMALHOOD_PENALTY (-5)")
                
                # Cooldown Penalty
                if hours_since < COOLDOWN_HOURS:
                    score -= 20
                    scoring_details.append(f"COOLDOWN_PENALTY (-20) [{hours_since:.1f}h < {COOLDOWN_HOURS}h]")
                
                # Check Correlation (Early check as scorer)
                correlation_ok, correlation_reason, crypto_exposure = check_portfolio_correlation(symbol)
                if not correlation_ok:
                    score -= 20
                    scoring_details.append(f"CORRELATION_PENALTY (-20) [{correlation_reason}]")

                # 🎯 1. RSI SCORER (Max 40 pts)
                if rsi < dynamic_rsi_threshold:
                    score += 30
                    scoring_details.append(f"RSI_UNDER_LIMIT (+30) [RSI:{rsi:.1f}<{dynamic_rsi_threshold}]")
                    if rsi < 25:
                        score += 10
                        scoring_details.append("EXTREME_OVERSOLD (+10)")
                    elif rsi < 30:
                        score += 5
                        scoring_details.append("STRONG_OVERSOLD (+5)")

                # 📊 2. VOLUME SCORER (Max 20 pts)
                vol_confirmed, vol_ratio = check_volume_confirmation(target_ohlcv, threshold=required_volume, asset_class=asset_class)
                if vol_confirmed:
                    score += 10
                    scoring_details.append(f"VOL_CONFIRMED (+10) [{vol_ratio:.2f}x]")
                    if vol_ratio > required_volume * 1.5:
                        score += 10
                        scoring_details.append("HIGH_VOL_SURGE (+10)")

                # 🚀 3. MOMENTUM SCORER (Max 15 pts)
                momentum_ok, momentum_trend, ema_diff = check_momentum_filter(target_ohlcv, rsi=rsi)
                
                # 📈 5. REVERSAL SCORER (Max 10 pts)
                reversal_ok, reversal_reason = check_reversal_pattern(target_ohlcv, rsi=rsi)

                if momentum_trend == "BULLISH":
                    score += 15
                    scoring_details.append(f"MOMENTUM_OK (+15) [{momentum_trend}]")
                    # 💡 Audit #3: If Trend is strong, ignore reversal candle color (Pullback buy)
                    if g_ctx['regime'] == "BULL_TREND":
                        score += 5
                        scoring_details.append("BULL_REGIME_REVERSAL_EXEMPT (+5)")
                        reversal_ok = True
                
                elif momentum_ok:
                    score += 10
                    scoring_details.append(f"MOMENTUM_NEUTRAL (+10)")
                elif rsi < 28:
                    # Counter-trend dip buying allowed if RSI is low
                    score += 5
                    scoring_details.append("MOMENTUM_FAIL_BUT_RSI_DIP (+5)")

                # 🎯 4. MULTI-TF SCORER (Max 15 pts)
                signal_strength, rsi_4h = check_multi_timeframe(symbol, exchange, rsi)
                if signal_strength == "STRONG":
                    score += 15
                    scoring_details.append(f"MULTI_TF_STRONG (+15) [RSI4H:{rsi_4h:.1f}]")
                elif g_ctx['regime'] == "BULL_TREND":
                    score += 5
                    scoring_details.append("BULL_REGIME_MTF_RELAX (+5)")
                elif signal_strength == "NORMAL" or signal_strength == "WEAK":
                    score += 5
                    scoring_details.append(f"MULTI_TF_CONFRIM (+5)")

                # Final Reversal points
                if reversal_ok and momentum_trend != "BULLISH": # Don't double count if BULLISH
                    score += 10
                    scoring_details.append(f"REVERSAL_OK (+10)")

                # ======================== DECISION ========================
                final_score = min(100, score)
                logger.info(f"⚖️ Final Scoring for {symbol}: {final_score}/100 | Min Req: {g_ctx['entry_threshold']}")

                if final_score >= g_ctx['entry_threshold']:
                    # Final AI confirmation
                    news_symbol = symbol.split('=')[0].split('/')[0]
                    news_ctx = get_news_context(news_symbol)
                    
                    portfolio_stats.update({
                        'signal_strength': signal_strength,
                        'rsi_4h': rsi_4h,
                        'vix': g_ctx['vix']['value'],
                        'dynamic_threshold': dynamic_rsi_threshold,
                        'trading_score': final_score
                    })
                    
                    decision = ask_bedrock(symbol, rsi, news_ctx, portfolio_stats, history)
                    if decision.get('decision') == "CONFIRM":
                        # 🔒 V8: Atomic Slot Acquisition (Last Barrier)
                        if not acquire_atomic_slot(max_slots):
                            results.append({"symbol": symbol, "status": "SKIPPED_SLOT_RACE_LOSS"})
                            continue
                        
                        slot_acquired = True
                        current_trades += 1 # 🔄 Update local counter
                        
                        try:
                            final_size_mult = g_ctx['vix']['multiplier'] * g_ctx['cb']['multiplier'] * corridor_risk_mult
                            base_capital = CAPITAL_PER_TRADE * final_size_mult
                            
                            calc_tp = HARD_TP_PCT * corridor_tp_mult
                            calc_sl = STOP_LOSS_PCT * corridor_sl_mult
                            
                            adjusted_capital, confidence = calculate_dynamic_position_size(
                                base_capital, final_score, calc_sl, g_ctx['balance']
                            )
                            
                            trade_id = f"{asset_class.upper()}-{uuid.uuid4().hex[:8]}"
                            size = round(adjusted_capital / current_price, 4)
                            
                            # 🚀 V8 EXECUTION ENGINE
                            filled = execute_trade_safe(exchange, symbol, size, 'buy')
                            entry_p = float(filled.get('average', current_price))
                            entry_s = float(filled.get('amount', size))
                            
                            # 2. Place Take Profit
                            tp_price = entry_p * (1 + calc_tp/100)
                            place_take_profit_safe(exchange, symbol, entry_s, tp_price)
                            
                            # 3. Persistence
                            log_trade_to_empire(
                                trade_id, symbol, "LONG", f"V8_SCORE_{final_score}_REG_{g_ctx['regime']}",
                                entry_p, entry_s, adjusted_capital, "CONFIRM", 
                                f"Score: {final_score}/100. Regime: {g_ctx['regime']}. {decision.get('reason')}",
                                asset_class, tp_pct=round(calc_tp, 2), sl_pct=round(calc_sl, 2),
                                execution_info=f"EXECUTED_ID_{filled['id']}"
                            )
                            results.append({"symbol": symbol, "status": "TRADE_EXECUTED", "score": final_score})
                            
                        except Exception as exec_err:
                            logger.error(f"❌ CRITICAL EXECUTION ERROR for {symbol}: {exec_err}")
                            if slot_acquired:
                                release_atomic_slot()
                                current_trades -= 1
                            results.append({"symbol": symbol, "status": "EXECUTION_FAILED", "error": str(exec_err)})
                    else:
                        log_skip_to_empire(symbol, f"AI_VETO: {decision.get('reason')}", current_price, asset_class)
                        results.append({"symbol": symbol, "status": "SKIPPED_AI_VETO", "reason": decision.get('reason')})
                # ======================== TREND FOLLOWING (V7 MODE) ========================
                elif TREND_FOLLOWING_ENABLED and sma200 is not None and current_price > sma200 and rsi > TREND_RSI_MIN:
                    logger.info(f"📈 TREND SIGNAL: {symbol} | Price={current_price:.2f} > SMA200={sma200:.2f} | RSI={rsi:.1f}")
                    
                    # �️ V8.5.1: Scoring for Trend Following
                    t_score = 65 # Base score if filters pass
                    t_details = [f"TREND_ON_SMA (+65)"]
                    
                    # Volume bonus
                    vol_confirmed, vol_ratio = check_volume_confirmation(target_ohlcv, threshold=required_volume, asset_class=asset_class)
                    if vol_confirmed:
                        t_score += 15
                        t_details.append(f"VOL_CONFIRMED (+15) [{vol_ratio:.2f}x]")
                    
                    # Momentum bonus
                    momentum_ok, momentum_trend, ema_diff = check_momentum_filter(target_ohlcv, rsi=rsi)
                    if momentum_ok:
                        t_score += 15
                        t_details.append(f"MOMENTUM_OK (+15) [{momentum_trend}]")
                        
                    # RSI bonus
                    if rsi > 60:
                        t_score += 5
                        t_details.append("RSI_STRENGTH (+5)")

                    final_score = min(100, t_score)
                    logger.info(f"⚖️ Trend Scoring for {symbol}: {final_score}/100 | Min Req: {g_ctx['entry_threshold']}")
                    
                    if final_score >= g_ctx['entry_threshold']:
                        # AI confirmation
                        news_symbol = symbol.split('=')[0].split('/')[0]
                        news_ctx = get_news_context(news_symbol)
                        portfolio_stats.update({
                            'signal_strength': "STRONG", 'rsi_4h': 0,
                            'vix': g_ctx['vix']['value'], 'dynamic_threshold': dynamic_rsi_threshold,
                            'trading_score': final_score
                        })
                        
                        decision = ask_bedrock(symbol, rsi, news_ctx, portfolio_stats, history)
                        if decision.get('decision') == "CONFIRM":
                            # 🔒 V8: Atomic Slot Acquisition (Last Barrier)
                            if not acquire_atomic_slot(max_slots):
                                results.append({"symbol": symbol, "status": "SKIPPED_SLOT_RACE_LOSS"})
                                continue

                            slot_acquired = True
                            current_trades += 1 # 🔄 Update local counter
                            
                            try:
                                final_size_mult = g_ctx['vix']['multiplier'] * g_ctx['cb']['multiplier'] * corridor_risk_mult
                                base_capital = CAPITAL_PER_TRADE * final_size_mult
                                
                                calc_tp = HARD_TP_PCT * corridor_tp_mult
                                calc_sl = STOP_LOSS_PCT * corridor_sl_mult
                                
                                adjusted_capital, confidence = calculate_dynamic_position_size(
                                    base_capital, final_score, calc_sl, g_ctx['balance']
                                )
                                
                                trade_id = f"{asset_class.upper()}-{uuid.uuid4().hex[:8]}"
                                size = round(adjusted_capital / current_price, 4)
                                
                                # 🚀 V8 EXECUTION ENGINE
                                filled = execute_trade_safe(exchange, symbol, size, 'buy')
                                entry_p = float(filled.get('average', current_price))
                                entry_s = float(filled.get('amount', size))
                                
                                # 2. Place Take Profit
                                tp_price = entry_p * (1 + calc_tp/100)
                                place_take_profit_safe(exchange, symbol, entry_s, tp_price)
                                
                                # 3. Persistence
                                log_trade_to_empire(
                                    trade_id, symbol, "LONG", f"V8_TREND_{g_ctx['regime']}",
                                    entry_p, entry_s, adjusted_capital, "CONFIRM", 
                                    f"TREND: Price>{sma200:.0f}(SMA200). Score: {final_score}. Regime: {g_ctx['regime']}",
                                    asset_class, tp_pct=round(calc_tp, 2), sl_pct=round(calc_sl, 2),
                                    execution_info=f"EXECUTED_ID_{filled['id']}"
                                )
                                results.append({"symbol": symbol, "status": "TRADE_TREND_EXECUTED", "price": entry_p})
                                
                            except Exception as exec_err:
                                logger.error(f"❌ CRITICAL TREND EXECUTION ERROR: {exec_err}")
                                if slot_acquired:
                                    release_atomic_slot()
                                    current_trades -= 1
                                results.append({"symbol": symbol, "status": "TREND_EXECUTION_FAILED"})
                        else:
                            log_skip_to_empire(symbol, f"TREND_AI_VETO: {decision.get('reason')}", current_price, asset_class)
                            results.append({"symbol": symbol, "status": "SKIPPED_TREND_AI_VETO"})
                    else:
                        log_skip_to_empire(symbol, f"TREND_LOW_SCORE: {final_score}", current_price, asset_class)
                        results.append({"symbol": symbol, "status": "SKIPPED_TREND_LOW_SCORE"})
                
                else:
                    sma_info = f" | SMA200={sma200:.2f}" if sma200 else ""
                    log_skip_to_empire(symbol, f"NO_SIGNAL: RSI={rsi:.1f} > {dynamic_rsi_threshold}{sma_info}", current_price, asset_class)
                    results.append({"symbol": symbol, "status": "IDLE", "rsi": rsi})
                    
            except Exception as item_err:
                logger.error(f"Error processing {symbol}: {item_err}")
                results.append({"symbol": symbol, "status": "ERROR", "msg": str(item_err)})

        return {"status": "SUCCESS", "results": results}
        
    except Exception as e:
        logger.error(f"Global Error: {e}")
        return {"status": "ERROR", "msg": str(e)}


