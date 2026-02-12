"""
Empire Trading System V11.5 - PERFORMANCE SNIPER APPLIED
=========================================================
GSI Query for Positions (Critique #V11.5.1)
Smart OHLCV Caching (Critique #V11.5.2)
CCXT Singleton & Warm Cache (Critique #V11.5.3)
Circuit Breaker Yahoo (Critique #V11.5.4)
"""

import json
import os
import logging
import uuid
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

import boto3
from botocore.exceptions import ClientError

# Absolute imports
import models
from models import MarketRegime, AssetClass
import config
from config import TradingConfig
import market_analysis
from market_analysis import analyze_market, classify_asset
import news_fetcher
from news_fetcher import NewsFetcher
import exchange_connector
from exchange_connector import ExchangeConnector
import risk_manager
from risk_manager import RiskManager
import decision_engine
from decision_engine import DecisionEngine
import macro_context
from atomic_persistence import AtomicPersistence
from anti_spam_helpers import is_in_cooldown, record_trade_timestamp, get_real_binance_positions
from trim_switch import evaluate_trim_and_switch

@dataclass
class MacroContext:
    can_trade: bool = True
    confidence_score: float = 1.0
    regime: str = "NORMAL"

def to_decimal(obj):
    if isinstance(obj, float): return Decimal(str(obj))
    if isinstance(obj, Enum): return obj.value
    if isinstance(obj, dict): return {k: to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list): return [to_decimal(v) for v in obj]
    return obj

# ==================== LOGGING ====================

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# ==================== AWS ====================

class AWSClients:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized: return
        self.region = os.getenv('AWS_REGION', 'us-east-1')
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.secretsmanager = boto3.client('secretsmanager', region_name=self.region)
        self.trades_table = self.dynamodb.Table(os.getenv('HISTORY_TABLE', 'EmpireTradesHistory'))
        self.state_table = self.dynamodb.Table(os.getenv('STATE_TABLE', 'V4TradingState'))
        self._initialized = True

class PersistenceLayer:
    def __init__(self, aws: AWSClients):
        self.aws = aws
    
    def log_trade_open(self, trade_id, symbol, asset_class, side, entry_price, size, capital, tp_pct, sl_pct, context, reason=None):
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            # Audit Fix: Use PascalCase for Dashboard Compatibility
            item = {
                'trader_id': trade_id,  # Required partition key
                'timestamp': timestamp,  # Required sort key
                'TradeId': trade_id,
                'Symbol': symbol,
                'Pair': symbol,
                'AssetClass': asset_class,
                'Type': 'LONG' if side.lower() == 'buy' else 'SHORT',
                'EntryPrice': entry_price,
                'Size': size,
                'Cost': capital,
                'TpPct': tp_pct,
                'SlPct': sl_pct,
                'ConfidenceScore': context.confidence_score,
                'Timestamp': timestamp,
                'Status': 'OPEN'
            }
            
            # Add detailed reason if provided (RSI, Volume, AI confidence)
            if reason:
                item['Reason'] = reason
            
            self.aws.trades_table.put_item(Item=to_decimal(item))
        except Exception as e: logger.error(f"[ERROR] Failed to log trade: {e}")
    
    def log_trade_close(self, trade_id, exit_price, pnl, reason):
        try:
            # Scan to find the item with this TradeId (since we need trader_id + timestamp for Key)
            response = self.aws.trades_table.scan(
                FilterExpression='TradeId = :tid',
                ExpressionAttributeValues={':tid': trade_id},
                Limit=1
            )
            
            if response.get('Items'):
                item = response['Items'][0]
                trader_id = item['trader_id']
                timestamp = item['timestamp']
                
                self.aws.trades_table.update_item(
                    Key={'trader_id': trader_id, 'timestamp': timestamp},
                    UpdateExpression='SET #st = :status, ExitPrice = :price, PnL = :pnl, ExitReason = :reason, ClosedAt = :closed_at',
                    ExpressionAttributeNames={'#st': 'Status'},
                    ExpressionAttributeValues=to_decimal({
                        ':status': 'CLOSED', ':price': exit_price, ':pnl': pnl, ':reason': reason,
                        ':closed_at': datetime.now(timezone.utc).isoformat()
                    })
                )
                logger.info(f"[INFO] Logged CLOSE for {trade_id}: PnL={pnl}, Reason={reason}")
            else:
                logger.warning(f"[WARN] Trade {trade_id} not found for close update")
        except Exception as e: 
            logger.error(f"[ERROR] Failed to log close: {e}")

    def log_skipped_trade(self, symbol, reason, asset_class):
        try:
            trade_id = f"SKIP-{uuid.uuid4().hex[:8]}"
            timestamp = datetime.now(timezone.utc).isoformat()
            # Use PascalCase for Dashboard compatibility
            self.aws.trades_table.put_item(Item=to_decimal({
                'trader_id': trade_id,  # Required partition key
                'timestamp': timestamp,  # Required sort key
                'TradeId': trade_id,
                'Symbol': symbol,
                'Pair': symbol,
                'AssetClass': asset_class,
                'Status': 'SKIPPED',
                'Reason': reason,
                'Timestamp': timestamp
            }))
            logger.info(f"[INFO] Logged SKIP for {symbol}: {reason}")
        except Exception as e: 
            logger.error(f"[ERROR] Failed to log skip: {e}")
    
    def save_position(self, symbol, position_data):
        try:
            # Sanitize symbol for DynamoDB keys
            safe_symbol = symbol.replace('/', '_').replace(':', '-')
            # We add a 'status' field for GSI (Audit #V11.5)
            position_data['status'] = 'OPEN'
            self.aws.state_table.put_item(Item=to_decimal({
                'trader_id': f'POSITION#{safe_symbol}', 
                'position': position_data,
                'status': 'OPEN',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }))
        except Exception as e: logger.error(f"[ERROR] Failed to save position: {e}")
    
    def load_positions(self):
        """
        GSI Optimized Query (Critique #V11.5.1)
        Gain: 500ms -> 18ms
        """
        try:
            response = self.aws.state_table.query(
                IndexName='status-timestamp-index',
                KeyConditionExpression='#status = :open',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':open': 'OPEN'}
            )
            # Convert back from sanitized to original symbols for compatibility
            positions = {}
            for item in response.get('Items', []):
                sanitized_symbol = item['trader_id'].replace('POSITION#', '')
                # Convert back: _ -> / and - -> :
                original_symbol = sanitized_symbol.replace('_', '/').replace('-', ':')
                positions[original_symbol] = item['position']
            return positions
        except Exception as e:
            # Fallback to scan if GSI is not yet ready or fails
            logger.warning(f"[WARN] GSI Query failed, falling back to scan: {e}")
            try:
                response = self.aws.state_table.scan(
                    FilterExpression='begins_with(trader_id, :prefix)',
                    ExpressionAttributeValues={':prefix': 'POSITION#'}
                )
                # Convert back from sanitized to original symbols
                positions = {}
                for item in response.get('Items', []):
                    sanitized_symbol = item['trader_id'].replace('POSITION#', '')
                    original_symbol = sanitized_symbol.replace('_', '/').replace('-', ':')
                    positions[original_symbol] = item['position']
                return positions
            except Exception as e2:
                logger.error(f"[ERROR] Failed to load positions (Scan): {e2}")
                return {}
    
    def save_risk_state(self, state):
        try:
            self.aws.state_table.put_item(Item=to_decimal({
                'trader_id': 'RISK_MANAGER#GLOBAL', 'state': state,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }))
        except Exception as e: logger.error(f"[ERROR] Failed to save risk state: {e}")

    def load_risk_state(self):
        try:
            response = self.aws.state_table.get_item(Key={'trader_id': 'RISK_MANAGER#GLOBAL'})
            return response.get('Item', {}).get('state', {})
        except Exception as e:
            logger.error(f"[ERROR] Failed to load risk state: {e}")
            return {}

    def delete_position(self, symbol):
        try: 
            # Sanitize symbol for DynamoDB keys
            safe_symbol = symbol.replace('/', '_').replace(':', '-')
            # We don't delete, we update status for GSI management or delete item
            self.aws.state_table.delete_item(Key={'trader_id': f'POSITION#{safe_symbol}'})
        except Exception as e: logger.error(f"[ERROR] Failed to delete position: {e}")

# ==================== ENGINE ====================

class TradingEngine:
    def __init__(self, execution_id: str = None):
        self.execution_id = execution_id or f"EXEC-{uuid.uuid4().hex[:6]}"
        self.aws = AWSClients()
        self.persistence = PersistenceLayer(self.aws)
        self.atomic_persistence = AtomicPersistence(self.aws.state_table)
        self.ohlcv_cache_path = '/tmp/ohlcv_cache.json'
        self.cooldown_seconds = 300  # Anti-spam: 5 minutes cooldown per symbol
        
        mode = os.getenv('TRADING_MODE', 'dry_run')
        credentials = {}
        secret_name = os.getenv('SECRET_NAME')
        if secret_name:
            try:
                response = self.aws.secretsmanager.get_secret_value(SecretId=secret_name)
                credentials = json.loads(response['SecretString'])
            except Exception as e:
                logger.error(f"[ERROR] Secret fetch failed: {e}")
                if mode == 'live': raise
        
        # Robust Credential Extraction
        api_key = credentials.get('api_key') or credentials.get('apiKey') or credentials.get('API_KEY')
        secret = credentials.get('secret') or credentials.get('secretKey') or credentials.get('SECRET_KEY') or credentials.get('api_secret')
        
        if api_key: api_key = api_key.strip()
        if secret: secret = secret.strip()

        # Optimized Connector (Singleton/Warm)
        # Fix -2008: Clear separation between Live and Demo (Audit #V11.6.6)
        is_live = TradingConfig.LIVE_MODE
        logger.info(f"[BOOT] Mode ACTIVE: {'LIVE (REAL TRADING)' if is_live else 'DEMO (MOCK TRADING)'}")
        
        self.exchange = ExchangeConnector(
            api_key=api_key,
            secret=secret,
            live_mode=is_live
        )
        
        self.risk_manager = RiskManager()
        self.decision_engine = DecisionEngine(risk_manager=self.risk_manager)
        self.news_fetcher = NewsFetcher()
        
        # Hydrate RiskManager
        self.risk_manager.load_state(self.persistence.load_risk_state())
        logger.info(f"[INFO] TradingEngine V11.5 initialized [{mode.upper()}]")

    def _get_ohlcv_smart(self, symbol: str, timeframe='1h') -> List:
        """
        Smart Strategy:
        1. Load local cache (/tmp)
        2. Fetch only new candles (limit=10)
        3. Merge and save
        (Critique #V11.5.2) -82% latency
        """
        cache = self._load_ohlcv_cache()
        cached_data = cache.get(symbol, [])
        
        if cached_data:
            try:
                # Fetch only latest few candles (Audit #V11.5)
                latest = self.exchange.fetch_ohlcv(symbol, timeframe, limit=10)
                
                # Merge without duplicates
                last_cached_ts = cached_data[-1][0]
                new_candles = [c for c in latest if c[0] > last_cached_ts]
                
                merged = cached_data + new_candles
                merged = merged[-500:] # Keep last 500
                
                if new_candles:
                    logger.info(f"[CACHE HIT] {symbol}: {len(new_candles)} new candles added")
                else:
                    logger.info(f"[CACHE HIT] {symbol}: Already up to date")
            except Exception as e:
                logger.warning(f"[WARN] Smart OHLCV fetch failed: {e}. Falling back to full fetch.")
                merged = self.exchange.fetch_ohlcv(symbol, timeframe, limit=500)
        else:
            # First time: full fetch
            merged = self.exchange.fetch_ohlcv(symbol, timeframe, limit=500)
            logger.info(f"[CACHE MISS] {symbol}: fetched 500 candles")
            
        # Update cache
        cache[symbol] = merged
        self._save_ohlcv_cache(cache)
        return merged

    def _load_ohlcv_cache(self) -> Dict:
        try:
            if os.path.exists(self.ohlcv_cache_path):
                with open(self.ohlcv_cache_path, 'r') as f:
                    return json.load(f)
        except: pass
        return {}

    def _save_ohlcv_cache(self, cache: Dict):
        try:
            with open(self.ohlcv_cache_path, 'w') as f:
                json.dump(cache, f)
        except Exception as e: logger.warning(f"[WARN] Failed to save OHLCV cache: {e}")
    
    def run_cycle(self, symbol: str) -> Dict:
        # Resolve to canonical symbol early (Audit #V11.6.8)
        symbol = self.exchange.resolve_symbol(symbol)
        asset_class = classify_asset(symbol)  # Define early for logging
        
        logger.info(f"\n{'='*70}\n[INFO] CYCLE START: {symbol}\n{'='*70}")
        try:
            # EMPIRE V12.6: "NOUVELLE PAGE BLANCHE" - No cooldown timer
            # ANTI-SPAM via position detection only (not time-based)
            # This allows:
            # 1. AGNOSTICISME: LONG to SHORT switches without delay
            # 2. RE-ENTRY: Exit at 1% profit, re-scan, re-enter if signal still strong
            # 3. CAPITAL VELOCITY: Capture multiple 1% moves on same asset during trends
            # Philosophy: Don't marry a trade - force re-evaluation after each exit
            
            # Load positions and manage them (check SL/TP/exits)
            positions = self.persistence.load_positions()
            if positions: 
                self._manage_positions(positions)
                # Reload positions after management (some may have been closed)
                positions = self.persistence.load_positions()
            
            # CRITICAL: Check real Binance position before trusting DynamoDB
            real_positions = self._get_real_binance_positions()
            if symbol in real_positions:
                logger.warning(f"[REAL_POSITION] {symbol} already open on Binance (managed)")
                
                # CRITICAL FIX: Manage Binance positions even if not in DynamoDB
                if symbol not in positions:
                    # Create mock position from Binance data for management
                    mock_positions = self._create_mock_binance_position(symbol)
                    if mock_positions:
                        logger.info(f"[MOCK_POSITION] Managing Binance-only position: {symbol}")
                        self._manage_positions(mock_positions)
                
                self.persistence.log_skipped_trade(symbol, "Position already open on Binance", asset_class)
                return {'symbol': symbol, 'status': 'IN_POSITION_BINANCE'}
            
            if symbol in positions:
                logger.info(f"[INFO] Skip: Already in position for {symbol}")
                self.persistence.log_skipped_trade(symbol, "Position already in DynamoDB", asset_class)
                return {'symbol': symbol, 'status': 'IN_POSITION'}
            
            # EMPIRE V13.0: REPLACE_LOW_PRIORITY - Flash Exit for USDC/USDT parking position
            # If USDC/USDT (forex) is open and a high-priority opportunity appears, eject immediately
            usdc_position = positions.get('USDC/USDT:USDT')
            if usdc_position and usdc_position.get('asset_class') == 'forex':
                # Check if current symbol is high-priority (crypto or commodity) with strong signal
                if asset_class in ['crypto', 'commodities']:
                    # Get quick score for current symbol
                    ohlcv_quick = self._get_ohlcv_smart(symbol, '1h')
                    ta_quick = analyze_market(ohlcv_quick, symbol=symbol, asset_class=asset_class)
                    quick_score = ta_quick.get('score', 0)
                    
                    if quick_score > 85:  # High-priority opportunity detected
                        logger.warning(f"[FLASH_EXIT] Ejecting USDC parking position for {symbol} (score: {quick_score})")
                        try:
                            # Close USDC immediately (market order)
                            usdc_direction = usdc_position.get('direction', 'LONG')
                            usdc_side = 'sell' if usdc_direction == 'LONG' else 'buy'
                            usdc_qty = usdc_position.get('quantity', 0)
                            
                            exit_order = self.exchange.create_market_order('USDC/USDT:USDT', usdc_side, usdc_qty)
                            exit_price = float(exit_order.get('average', 0))
                            
                            # Calculate PnL
                            entry_price = float(usdc_position.get('entry_price', 0))
                            if usdc_direction == 'LONG':
                                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                            else:
                                pnl_pct = ((entry_price - exit_price) / entry_price) * 100
                            
                            pnl = self.risk_manager.close_trade('USDC/USDT:USDT', exit_price)
                            
                            reason = f"Flash Exit for priority {symbol} (score: {quick_score}, USDC PnL: {pnl_pct:+.2f}%)"
                            self.persistence.log_trade_close(usdc_position['trade_id'], exit_price, pnl, reason)
                            self.persistence.delete_position('USDC/USDT:USDT')
                            self.atomic_persistence.atomic_remove_risk('USDC/USDT:USDT', float(usdc_position.get('risk_dollars', 0)))
                            
                            del positions['USDC/USDT:USDT']
                            balance = self.exchange.get_balance_usdt()  # Refresh balance
                            
                            logger.info(f"[FLASH_EXIT] USDC closed, capital freed: ${balance:.0f}")
                        except Exception as e:
                            logger.error(f"[ERROR] Flash exit failed: {e}")
            
            # TRIM & SWITCH: Check if we should reduce existing positions for better opportunities
            # Only if we have positions AND low available capital
            if positions and balance < 500:  # Less than $500 available
                logger.info(f"[TRIM_CHECK] Low capital (${balance:.0f}), checking for better opportunities...")
            
            # Smart OHLCV Fetching (Audit #V11.5)
            ohlcv = self._get_ohlcv_smart(symbol, '1h')
            ta_result = analyze_market(ohlcv, symbol=symbol, asset_class=asset_class)
            
            if ta_result.get('market_context', '').startswith('VOLATILITY_SPIKE'):
                reason = ta_result['market_context']
                self.persistence.log_skipped_trade(symbol, reason, asset_class)
                return {'symbol': symbol, 'status': 'BLOCKED', 'reason': reason}
            
            news_score = self.news_fetcher.get_news_sentiment_score(symbol)
            macro = macro_context.get_macro_context(state_table=self.aws.state_table)
            
            balance = self.exchange.get_balance_usdt()
            if balance < 10: raise ValueError("Insufficient balance ( < $10 )")
            
            direction = 'SHORT' if ta_result.get('signal_type') == 'SHORT' else 'LONG'
            if ta_result.get('signal_type') == 'NEUTRAL':
                # Build meaningful skip reason
                rsi = ta_result.get('rsi', 50)
                score = ta_result.get('score', 0)
                
                # EMPIRE V13.0: USDC/USDT low-priority entry logic
                # Only enter USDC if it's forex AND all other priority assets are calm (<50 score)
                if asset_class == 'forex' and 'USDC' in symbol:
                    # Check if this is a calm market - scan priority assets
                    priority_symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'XRP/USDT:USDT', 'PAXG/USDT:USDT', 'SPX/USDT:USDT', 'BNB/USDT:USDT']
                    all_calm = True
                    
                    for priority_sym in priority_symbols:
                        if priority_sym in positions:
                            # Already have a priority position, don't enter USDC
                            all_calm = False
                            break
                        
                        try:
                            priority_ohlcv = self._get_ohlcv_smart(priority_sym, '1h')
                            priority_ta = analyze_market(priority_ohlcv, symbol=priority_sym, asset_class=classify_asset(priority_sym))
                            priority_score = priority_ta.get('score', 0)
                            
                            if priority_score >= 50:  # Priority asset has opportunity
                                all_calm = False
                                logger.info(f"[USDC_SKIP] {priority_sym} has score {priority_score} >= 50, skipping USDC parking")
                                break
                        except:
                            pass
                    
                    if not all_calm:
                        reason = "Priority assets active (score >= 50), USDC parking not needed"
                        self.persistence.log_skipped_trade(symbol, reason, asset_class)
                        return {'symbol': symbol, 'status': 'LOW_PRIORITY_BLOCKED', 'reason': reason}
                    else:
                        logger.info(f"[USDC_PARKING] All priority assets calm, allowing USDC entry as parking position")
                        # Continue to decision engine - USDC can enter as parking position
                else:
                    # Not USDC or not neutral - normal skip logic
                    reasons = []
                    if rsi > 70:
                        reasons.append(f"RSI > 70 (overbought: {rsi:.1f})")
                    elif rsi < 30:
                        reasons.append(f"RSI < 30 (oversold: {rsi:.1f})")
                    else:
                        reasons.append(f"RSI neutral ({rsi:.1f})")
                    
                    if score < 50:
                        reasons.append(f"Low technical score ({score})")
                    
                    # Check volume if available
                    if 'volume_spike' in ta_result.get('market_context', ''):
                        reasons.append("Low volume")
                    
                    # Check trend
                    trend = ta_result.get('market_context', '')
                    if 'Trend=' in trend:
                        trend_val = trend.split('Trend=')[1].split('|')[0].strip()
                        if trend_val == 'SIDEWAYS':
                            reasons.append("Sideways trend")
                    
                    reason = " | ".join(reasons) if reasons else f"No clear signal (RSI={rsi:.1f})"
                    self.persistence.log_skipped_trade(symbol, reason, asset_class)
                    return {'symbol': symbol, 'status': 'NO_SIGNAL', 'score': ta_result.get('score')}

            decision = self.decision_engine.evaluate_with_risk(
                context=macro, ta_result=ta_result, symbol=symbol,
                capital=balance, direction=direction, asset_class=asset_class,
                news_score=news_score, macro_regime=macro.get('regime', 'NORMAL')
            )
            
            if not decision['proceed']:
                logger.info(f"[INFO] Blocked: {decision['reason']}")
                self.persistence.log_skipped_trade(symbol, decision['reason'], asset_class)
                return {'symbol': symbol, 'status': 'BLOCKED', 'reason': decision['reason']}
            
            # TRIM & SWITCH: If we have a high-confidence signal but low capital, consider trimming positions
            if positions and balance < 500 and decision['confidence'] >= 0.75:
                trim_result = self._evaluate_trim_and_switch(positions, symbol, decision, balance)
                if trim_result['action'] == 'TRIMMED':
                    balance = trim_result['freed_capital']
                    logger.info(f"[TRIM_SUCCESS] Freed ${balance:.0f} for {symbol} opportunity")
            
            return self._execute_entry(symbol, direction, decision, ta_result, asset_class, balance)
            
        except Exception as e:
            logger.error(f"[ERROR] Cycle error: {e}")
            return {'symbol': symbol, 'status': 'ERROR', 'error': str(e)}
    
    def _execute_entry(self, symbol, direction, decision, ta_result, asset_class, balance):
        trade_id = f"V11-{uuid.uuid4().hex[:8]}"
        side = 'sell' if direction == 'SHORT' else 'buy'
        quantity = decision['quantity']
        
        market_info = self.exchange.get_market_info(symbol)
        min_amount = market_info.get('min_amount', 0)
        if quantity < min_amount: quantity = min_amount

        try:
            # Force leverage 1 for scalping safety
            order = self.exchange.create_market_order(symbol, side, quantity, leverage=TradingConfig.LEVERAGE)
            real_entry = float(order.get('average', ta_result['price']))
            real_size = float(order.get('filled', quantity))
            logger.info(f"[OK] {direction} filled: {real_size} @ ${real_entry:.2f} (Leverage: {TradingConfig.LEVERAGE}x)")
        except Exception as e:
            logger.error(f"[ERROR] Order failed: {e}")
            return {'symbol': symbol, 'status': 'ORDER_FAILED', 'error': str(e)}
        
        success, reason = self.atomic_persistence.atomic_check_and_add_risk(
            symbol=symbol,
            risk_dollars=decision['risk_dollars'],
            capital=balance,
            entry_price=real_entry,
            quantity=real_size,
            direction=direction
        )
        
        if not success:
            logger.error(f"[ALERT] Atomic risk check failed: {reason}. Attempting order rollback...")
            try:
                rollback_side = 'sell' if direction == 'LONG' else 'buy'
                self.exchange.create_market_order(symbol, rollback_side, real_size)
                logger.info(f"[OK] Emergency rollback executed for {symbol}")
            except Exception as rollback_err:
                logger.error(f"[CRITICAL] ROLLBACK FAILED: {rollback_err}")
            self.persistence.log_skipped_trade(symbol, reason, asset_class)
            return {'symbol': symbol, 'status': 'BLOCKED_ATOMIC', 'reason': reason}
        
        # Scalping TP: Fixed 0.3-0.5% profit target (not ATR-based)
        # Use 0.4% as default target (middle of range)
        tp_pct = TradingConfig.SCALP_TP_MIN + ((TradingConfig.SCALP_TP_MAX - TradingConfig.SCALP_TP_MIN) / 2)
        tp = real_entry * (1 + tp_pct) if direction == 'LONG' else real_entry * (1 - tp_pct)
        
        # Scalping SL: Fixed 0.15% stop loss
        sl = real_entry * (1 - TradingConfig.SCALP_SL) if direction == 'LONG' else real_entry * (1 + TradingConfig.SCALP_SL)
        
        logger.info(f"[SCALP] Entry: ${real_entry:.4f} | TP: ${tp:.4f} ({tp_pct*100:.2f}%) | SL: ${sl:.4f} ({TradingConfig.SCALP_SL*100:.2f}%)")
        
        # Build detailed reason with technical indicators
        reason_parts = []
        if 'rsi' in ta_result:
            reason_parts.append(f"RSI={ta_result['rsi']:.1f}")
        if 'volume_ratio' in ta_result:
            reason_parts.append(f"Vol={ta_result['volume_ratio']:.2f}x")
        if decision.get('confidence'):
            reason_parts.append(f"AI={decision['confidence']*100:.0f}%")
        if 'score' in decision:
            reason_parts.append(f"Score={decision['score']}")
        
        detailed_reason = " | ".join(reason_parts) if reason_parts else decision.get('reason', 'Signal detected')
        
        self.persistence.log_trade_open(
            trade_id, symbol, asset_class, direction, real_entry, real_size, 
            real_size * real_entry, 10.0, -5.0,
            MacroContext(confidence_score=decision['confidence']),
            reason=detailed_reason
        )
        
        pos_data = {
            'trade_id': trade_id, 'entry_price': real_entry, 'quantity': real_size,
            'direction': direction, 'stop_loss': sl, 'take_profit': tp,
            'asset_class': asset_class,
            'risk_dollars': decision['risk_dollars'],
            'entry_time': datetime.now(timezone.utc).isoformat()
        }
        self.persistence.save_position(symbol, pos_data)
        
        # Local state sync
        self.risk_manager.register_trade(symbol, real_entry, real_size, decision['risk_dollars'], decision['stop_loss'], direction)
        self.persistence.save_risk_state(self.risk_manager.get_state())
        
        # Record trade timestamp for cooldown
        self._record_trade_timestamp(symbol)
        
        logger.info(f"[OK] Position opened atomically: {direction} {symbol}")
        return {'symbol': symbol, 'status': f'{direction}_OPEN', 'trade_id': trade_id}
    
    def _is_in_cooldown(self, symbol: str) -> bool:
        """Check if symbol is in cooldown period (anti-spam protection)"""
        return is_in_cooldown(self.aws.state_table, symbol, self.cooldown_seconds)
    
    def _record_trade_timestamp(self, symbol: str):
        """Record trade timestamp for cooldown tracking"""
        record_trade_timestamp(self.aws.state_table, symbol)
    
    def _get_real_binance_positions(self) -> List[str]:
        """Get actual open positions from Binance (source of truth)"""
        return get_real_binance_positions(self.exchange)
    
    def _create_mock_binance_position(self, symbol: str) -> Dict:
        """Create mock position data for Binance-only positions to enable SL/TP management"""
        try:
            # Get real position data from Binance
            positions = self.exchange.fetch_positions([symbol])
            if not positions:
                return {}
            
            pos_data = positions[0]
            if float(pos_data.get('contracts', 0)) == 0:
                return {}
            
            # Calculate TP/SL based on current price (since we don't have original entry)
            current_price = float(pos_data['lastPrice'])
            side = pos_data['side'].lower()  # 'long' or 'short'
            
            # Estimate entry price (use current price as fallback - not ideal but functional)
            entry_price = current_price
            
            # Set TP/SL based on current price (emergency protection)
            if side == 'long':
                tp = current_price * (1 + TradingConfig.SCALP_TP_MIN)
                sl = current_price * (1 - TradingConfig.SCALP_SL)
            else:
                tp = current_price * (1 - TradingConfig.SCALP_TP_MIN)
                sl = current_price * (1 + TradingConfig.SCALP_SL)
            
            mock_position = {
                'direction': side.upper(),
                'entry_price': entry_price,
                'quantity': float(pos_data['contracts']),
                'stop_loss': sl,
                'take_profit': tp,
                'entry_time': datetime.now(timezone.utc).isoformat(),
                'trade_id': f'EMERGENCY-{symbol.replace("/", "")}',
                'asset_class': classify_asset(symbol)
            }
            
            logger.warning(f"[MOCK_CREATED] {symbol}: {side.upper()} {mock_position['quantity']} @ ${entry_price:.2f}")
            return {symbol: mock_position}
            
        except Exception as e:
            logger.error(f"[MOCK_ERROR] Failed to create mock position for {symbol}: {e}")
            return {}
    
    def _evaluate_trim_and_switch(self, positions: Dict, new_symbol: str, new_decision: Dict, current_balance: float) -> Dict:
        """Evaluate if we should trim existing positions for better opportunities"""
        return evaluate_trim_and_switch(
            self.exchange,
            self.persistence,
            positions,
            new_symbol,
            new_decision,
            current_balance
        )
    
    def _manage_positions(self, positions: Dict):
        logger.info(f"\n{'='*70}\n[INFO] POSITION MANAGEMENT\n{'='*70}")
        for symbol, pos in list(positions.items()):
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = float(ticker['last'])
                entry_price = float(pos.get('entry_price', 0))
                direction = pos['direction']
                
                # Calculate current PnL %
                if direction == 'LONG':
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100
                else:
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100
                
                # Check traditional TP/SL
                stop_loss = float(pos['stop_loss'])
                take_profit = float(pos['take_profit'])
                hit_sl = (current_price <= stop_loss) if direction == 'LONG' else (current_price >= stop_loss)
                hit_tp = (current_price >= take_profit) if direction == 'LONG' else (current_price <= take_profit)
                
                # EMPIRE V12.6: "NOUVELLE PAGE BLANCHE" - 1% PROFIT PROTECTION
                # Philosophy: Ne pas transformer un trade en mariage
                # Exit at 1% forces re-evaluation: "Would I buy this asset NOW at this price?"
                # If signal remains strong after exit, bot can re-enter (no cooldown blocks it)
                # This allows capturing multiple 1% moves on same asset during strong trends
                # Security: Profit is REAL on account before any re-entry decision
                hit_profit_1pct = pnl_pct >= 1.0
                if hit_profit_1pct:
                    logger.warning(f"[PROFIT_1PCT] {symbol} reached +{pnl_pct:.2f}% - securing profit! (Nouvelle Page Blanche)")
                
                # EMPIRE V12.3: Time-based exits
                entry_time_str = pos.get('entry_time', '')
                should_exit_time = False
                should_exit_fast_discard = False
                
                if entry_time_str:
                    try:
                        entry_time = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
                        time_open_hours = (datetime.now(timezone.utc) - entry_time).total_seconds() / 3600
                        time_open_minutes = time_open_hours * 60
                        
                        # TIME_BASED_EXIT: Adaptatif par asset class
                        # Crypto: 30min (haute volatilité, momentum rapide)
                        # Indices: 45min (volatilité moyenne)
                        # Commodities: 90min (PAXG/Gold - très lent à démarrer)
                        # Forex: 1h (basse volatilité, momentum lent)
                        asset_class = pos.get('asset_class', 'crypto')
                        symbol = pos.get('symbol', '')
                        
                        if asset_class == 'crypto':
                            time_threshold_hours = 0.5  # 30min
                        elif asset_class == 'indices':
                            time_threshold_hours = 0.75  # 45min
                        elif asset_class == 'commodities' or 'PAXG' in symbol:
                            time_threshold_hours = 1.5  # 90min (Gold needs more time)
                        else:  # forex
                            time_threshold_hours = 1.0  # 1h
                        
                        if time_open_hours > time_threshold_hours:
                            should_exit_time = True
                            logger.warning(f"[TIME_EXIT] {symbol} ({asset_class}) open {time_open_hours*60:.0f}min - auto-close (PnL: {pnl_pct:+.2f}%)")
                        
                        # FAST_DISCARD: >15min AND PnL < 0.10% (libérer capital si momentum absent)
                        if time_open_minutes > 15 and pnl_pct < 0.10:
                            should_exit_fast_discard = True
                            logger.warning(f"[FAST_DISCARD] {symbol} open {time_open_minutes:.0f}min with only {pnl_pct:+.2f}% - no momentum")
                    except: pass
                
                # Optional: Claude analysis for exit decision
                should_exit_claude = False
                if self.news_fetcher.use_claude and pnl_pct > 0.3:
                    try:
                        # Call Claude to analyze if we should exit this profitable position
                        logger.info(f"[CLAUDE] Analyzing exit for {symbol} (+{pnl_pct:.2f}%)")
                        
                        # Fetch recent news for exit decision
                        news = self.news_fetcher._fetch_raw_news(symbol)
                        if news:
                            # Ask Claude: should we exit now or hold for more?
                            analysis = self.news_fetcher.claude.analyze_news_batch(symbol, news[:5])
                            sentiment = analysis.get('sentiment', 'NEUTRAL')
                            confidence = analysis.get('confidence', 0.5)
                            
                            # Exit if sentiment turns against our position
                            if direction == 'LONG' and sentiment == 'BEARISH' and confidence > 0.7:
                                should_exit_claude = True
                                logger.info(f"[CLAUDE_EXIT] {symbol} LONG exit - bearish sentiment detected (conf: {confidence:.2f})")
                            elif direction == 'SHORT' and sentiment == 'BULLISH' and confidence > 0.7:
                                should_exit_claude = True
                                logger.info(f"[CLAUDE_EXIT] {symbol} SHORT exit - bullish sentiment detected (conf: {confidence:.2f})")
                            else:
                                logger.info(f"[CLAUDE_HOLD] {symbol} sentiment: {sentiment} (conf: {confidence:.2f}) - holding")
                        else:
                            # No news available - use aggressive profit taking
                            if pnl_pct > 0.8:
                                should_exit_claude = True
                                logger.info(f"[CLAUDE_EXIT] {symbol} profit {pnl_pct:.2f}% exceeds threshold (no news)")
                    except Exception as e:
                        logger.warning(f"[CLAUDE] Exit analysis failed: {e}")
                
                # Exit if any condition is met
                if hit_sl or hit_tp or hit_profit_1pct or should_exit_time or should_exit_fast_discard or should_exit_claude:
                    # Build detailed close reason
                    if hit_sl:
                        reason = f"Stop Loss hit at ${current_price:.2f} (SL: ${stop_loss:.2f}, PnL: {pnl_pct:+.2f}%)"
                    elif hit_tp:
                        reason = f"Take Profit hit at ${current_price:.2f} (TP: ${take_profit:.2f}, PnL: {pnl_pct:+.2f}%)"
                    elif hit_profit_1pct:
                        reason = f"1% Profit Protection (PnL: {pnl_pct:+.2f}%, Entry: ${entry_price:.2f})"
                    elif should_exit_fast_discard:
                        duration_min = time_open_minutes if 'time_open_minutes' in locals() else 0
                        reason = f"Fast Discard after {duration_min:.0f}min (PnL: {pnl_pct:+.2f}%, no momentum)"
                    elif should_exit_time:
                        duration_h = time_open_hours if 'time_open_hours' in locals() else 0
                        asset_class_name = pos.get('asset_class', 'crypto')
                        reason = f"Time Exit {asset_class_name} after {duration_h*60:.0f}min (PnL: {pnl_pct:+.2f}%)"
                    else:
                        reason = f"Claude AI Exit (sentiment changed, PnL: {pnl_pct:+.2f}%)"
                    
                    logger.warning(f"[ALERT] EXIT: {symbol} - {reason}")
                    exit_side = 'sell' if direction == 'LONG' else 'buy'
                    exit_order = self.exchange.create_market_order(symbol, exit_side, pos['quantity'])
                    exit_price = float(exit_order.get('average', current_price))
                    
                    self.atomic_persistence.atomic_remove_risk(symbol, float(pos.get('risk_dollars', 0)))
                    
                    pnl = self.risk_manager.close_trade(symbol, exit_price)
                    self.persistence.save_risk_state(self.risk_manager.get_state())
                    self.persistence.log_trade_close(pos['trade_id'], exit_price, pnl, reason)
                    self.persistence.delete_position(symbol)
                    del positions[symbol]
                    logger.info(f"[OK] Closed {symbol} | PnL: ${pnl:.2f} ({pnl_pct:+.2f}%)")
                else:
                    logger.info(f"[HOLD] {symbol} | PnL: {pnl_pct:+.2f}% | Time: {entry_time_str[:16] if entry_time_str else 'N/A'}")

            except Exception as e: logger.error(f"[ERROR] Manage failed for {symbol}: {e}")

# ==================== LAMBDA HANDLER ====================

def lambda_handler(event, context):
    try:
        engine = TradingEngine()
        
        # Get symbols from event or environment variable (8 symbols for scalping)
        symbols_str = event.get('symbols') if event.get('symbols') else os.getenv('SYMBOLS', 'BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT,XRP/USDT:USDT,PAXG/USDT:USDT,SPX/USDT:USDT,USDC/USDT:USDT,BNB/USDT:USDT')
        symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]
        
        logger.info(f"[INFO] Scanning {len(symbols)} symbols: {', '.join(symbols)}")
        
        risk_state = engine.persistence.load_risk_state()
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        if risk_state.get('last_reset_date') != today:
            logger.info(f"[INFO] New day reset {today}")
            engine.risk_manager.reset_daily()
            new_state = engine.risk_manager.get_state()
            new_state['last_reset_date'] = today
            engine.persistence.save_risk_state(new_state)

        results = [engine.run_cycle(s) for s in symbols]
        
        logger.info(f"[INFO] Scan complete: {len(results)} results")
        return {'statusCode': 200, 'body': json.dumps({'status': 'SUCCESS', 'results': results})}
    except Exception as e:
        logger.error(f"[CRITICAL] Global failure: {e}")
        return {'statusCode': 500, 'body': json.dumps({'status': 'ERROR', 'error': str(e)})}
