"""
Empire Trading System V13.2 - 11 ACTIFS BINANCE VALIDATED
=========================================================
Pump/News: DOGE (30min) - Momentum pur, news-driven
Tech L1: AVAX (30min) - Volatilité "High Tech"
Oracle: LINK (30min) - Décorrélation (matière première crypto)
Leaders: BTC, ETH, SOL, XRP, BNB (30min) - Noyau dur
RWA: PAXG (90min) - Or/Commodity
Indices: SPX (45min) - S&P 500
Parking: USDC (60min) - Trésorerie (Priorité Basse)

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
from datetime import datetime, timezone, timedelta
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
import exchange_connector
from exchange_connector import ExchangeConnector
import risk_manager
from risk_manager import RiskManager
import decision_engine
from decision_engine import DecisionEngine
import macro_context
import claude_analyzer
from claude_analyzer import ClaudeNewsAnalyzer
from atomic_persistence import AtomicPersistence
from anti_spam_helpers import is_in_cooldown, record_trade_timestamp, get_real_binance_positions

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

def from_decimal(obj):
    if isinstance(obj, Decimal): return float(obj)
    if isinstance(obj, dict): return {k: from_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list): return [from_decimal(v) for v in obj]
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
        self.skipped_table = self.dynamodb.Table(os.getenv('SKIPPED_TABLE', 'EmpireSkippedTrades'))
        self.state_table = self.dynamodb.Table(os.getenv('STATE_TABLE', 'V4TradingState'))
        self._initialized = True

    @staticmethod
    def get_secret(secret_name):
        """Fetch secret from AWS Secrets Manager"""
        clients = AWSClients()
        try:
            response = clients.secretsmanager.get_secret_value(SecretId=secret_name)
            return json.loads(response['SecretString'])
        except Exception as e:
            logger.error(f"[ERROR] Failed to fetch secret {secret_name}: {e}")
            return {}

class PersistenceLayer:
    def __init__(self, aws: AWSClients, api_key: str = None, secret: str = None):
        self.aws = aws
        self.api_key = api_key
        self.secret = secret
    
    def log_trade_open(self, trade_id, symbol, asset_class, direction, entry_price, size, cost, tp_price, sl_price, leverage, reason=None):
        try:
            ts_ms = int(time.time() * 1000)
            iso_ts = datetime.now(timezone.utc).isoformat()
            item = {
                'trade_id': trade_id,        # FIX: Partition Key (HASH)
                'timestamp': ts_ms,          # FIX: RANGE Key (Number/N)
                'trader_id': trade_id,        # Legacy compatibility
                'Symbol': symbol,
                'Pair': symbol,
                'AssetClass': asset_class,
                'Type': direction,
                'EntryPrice': entry_price,
                'Size': size,
                'Cost': cost,
                'TakeProfit': tp_price,
                'StopLoss': sl_price,
                'Leverage': leverage,
                'iso_timestamp': iso_ts,
                'Status': 'OPEN'
            }
            if reason:
                item['Reason'] = reason
            
            self.aws.trades_table.put_item(Item=to_decimal(item))
            logger.info(f"[DB] OPEN logged: {symbol} {direction} x{leverage} | Entry=${entry_price:.4f} | TP=${tp_price:.4f} | SL=${sl_price:.4f}")
        except Exception as e: logger.error(f"[ERROR] Failed to log trade: {e}")
    
    def log_trade_close(self, trade_id, exit_price, pnl, reason):
        try:
            # Query by partition key (trade_id) - O(1)
            response = self.aws.trades_table.query(
                KeyConditionExpression='trade_id = :tid',
                ExpressionAttributeValues={':tid': trade_id},
                Limit=1
            )
            
            if response.get('Items'):
                item = response['Items'][0]
                tid = item['trade_id']
                ts = item['timestamp']
                
                self.aws.trades_table.update_item(
                    Key={'trade_id': tid, 'timestamp': ts},
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
            ts_ms = int(time.time() * 1000)
            iso_ts = datetime.now(timezone.utc).isoformat()
            
            # TTL: auto-delete after 7 days (epoch seconds)
            ttl = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
            
            self.aws.skipped_table.put_item(Item=to_decimal({
                'trade_id': trade_id,        # FIX: Partition Key (HASH)
                'timestamp': ts_ms,          # FIX: RANGE Key (Number/N)
                'trader_id': trade_id,        # Legacy compatibility
                'Symbol': symbol,
                'Pair': symbol,
                'AssetClass': asset_class,
                'Status': 'SKIPPED',
                'Reason': reason,
                'ttl': ttl,
                'iso_timestamp': iso_ts       # ISO string for dashboard time rendering
            }))
            logger.info(f"[INFO] Logged SKIP for {symbol}: {reason}")
        except Exception as e: 
            logger.error(f"[ERROR] Failed to log skip: {e}")
    
    def save_position(self, symbol: str, position_data: Dict):
        """🏛️ EMPIRE V16.3: Positions saved to DynamoDB (Memory)"""
        try:
            safe_symbol = symbol.replace('/', '_').replace(':', '-')
            trader_id = f'POSITION#{safe_symbol}'
            
            item = {
                'trader_id': trader_id,
                'symbol': symbol,
                'status': 'OPEN',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                **position_data
            }
            # Handle decimals for DynamoDB
            self.aws.state_table.put_item(Item=to_decimal(item))
            logger.info(f"[DB] Position {symbol} saved to DynamoDB memory")
        except Exception as e:
            logger.error(f"[ERROR] Failed to save position to DB: {e}")
    
    def load_positions(self):
        """
        🏛️ EMPIRE V16.3: Load positions from DynamoDB (Memory)
        Source of truth for bot state to reduce API spam.
        """
        try:
            # Query the GSI for OPEN positions
            response = self.aws.state_table.query(
                IndexName='status-timestamp-index',
                KeyConditionExpression='#status = :open',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':open': 'OPEN'}
            )
            
            items = response.get('Items', [])
            positions = {}
            for item in items:
                pos = from_decimal(item)
                symbol = pos.get('symbol')
                if symbol:
                    positions[symbol] = pos
            
            logger.debug(f"[DB] Loaded {len(positions)} positions from memory")
            return positions
            
        except Exception as e:
            logger.error(f"[DB_ERROR] Failed to load positions from memory: {e}")
            # Fallback (optional) removed as per user request to avoid Binance calls
            return {}
    
    def save_risk_state(self, state):
        """ EMPIRE V16: Risk state managed in memory only"""
        # Risk state is now managed in memory, no DynamoDB storage needed
        logger.info(f"[MEMORY] Risk state updated: {len(state)} rules")
        pass

    def load_risk_state(self):
        """ EMPIRE V16: Risk state managed in memory only"""
        # Return default risk state from memory
        return {
            'max_open_trades': getattr(TradingConfig, 'MAX_OPEN_TRADES', 4),
            'max_loss_per_trade': getattr(TradingConfig, 'MAX_LOSS_PER_TRADE', 0.02),
            'max_daily_loss': getattr(TradingConfig, 'MAX_DAILY_LOSS', 0.05)
        }

    def delete_position(self, symbol):
        """🏛️ EMPIRE V16.3: Mark position as CLOSED in DynamoDB memory"""
        try:
            safe_symbol = symbol.replace('/', '_').replace(':', '-')
            trader_id = f'POSITION#{safe_symbol}'
            
            # Query for the open position
            response = self.aws.state_table.query(
                KeyConditionExpression='trader_id = :tid',
                FilterExpression='#status = :open',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':tid': trader_id, ':open': 'OPEN'}
            )
            
            if response.get('Items'):
                item = response['Items'][0]
                timestamp = item['timestamp']
                
                self.aws.state_table.update_item(
                    Key={'trader_id': trader_id, 'timestamp': timestamp},
                    UpdateExpression='SET #status = :closed, closed_at = :now',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={
                        ':closed': 'CLOSED',
                        ':now': datetime.now(timezone.utc).isoformat()
                    }
                )
                logger.info(f"[DB] Position {symbol} marked as CLOSED in memory")
            else:
                logger.debug(f"[DB] No open position found in memory for {symbol}")
        except Exception as e:
            logger.error(f"[DB_ERROR] Failed to update position in memory: {e}")

# ==================== ENGINE ====================

class TradingEngine:
    def __init__(self, execution_id: str = None):
        self.execution_id = execution_id or f"EXEC-{uuid.uuid4().hex[:6]}"
        self.aws = AWSClients()
        self.persistence = PersistenceLayer(self.aws)
        # 🏛️ EMPIRE V16: No more atomic persistence needed (Binance API is source of truth)
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

        # Update persistence with real credentials early
        self.persistence.api_key = api_key
        self.persistence.secret = secret

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
        self.claude = ClaudeNewsAnalyzer()
        
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
    
    def get_compound_capital(self, base_capital: float) -> float:
        """
        V16.0 Compound Capital Calculation.
        
        Calculates current trading capital by adding realized PnL from closed trades.
        This allows gains from each trade to compound into the next position.
        
        Args:
            base_capital: Starting capital from environment/config
            
        Returns:
            Compound capital (base + realized PnL), never below base_capital
        """
        if not TradingConfig.USE_COMPOUND:
            return base_capital
        
        try:
            # Query closed trades from last 24 hours using index
            from datetime import datetime, timezone, timedelta
            cutoff_time = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)
            
            response = self.aws.trades_table.query(
                IndexName='status-timestamp-index',
                KeyConditionExpression='#status = :closed AND #ts > :cutoff',
                ExpressionAttributeNames={
                    '#status': 'Status',
                    '#ts': 'timestamp'
                },
                ExpressionAttributeValues={
                    ':closed': 'CLOSED',
                    ':cutoff': cutoff_time
                },
                ScanIndexForward=False,
                Limit=100
            )
            
            # Sum all realized PnL
            total_pnl = 0.0
            for item in response.get('Items', []):
                pnl = item.get('PnL', 0)
                if pnl:
                    total_pnl += float(pnl)
            
            compound_capital = base_capital + total_pnl
            
            # Log compound effect
            if total_pnl != 0:
                logger.info(f"[COMPOUND] Base: ${base_capital:.2f} + PnL(24h): ${total_pnl:+.2f} = ${compound_capital:.2f}")
            
            # Never go below base capital (protect against negative PnL reducing capital)
            return max(base_capital, compound_capital)
            
        except Exception as e:
            logger.error(f"[COMPOUND_ERROR] Failed to calculate compound capital: {e}")
            return base_capital
    
    def run_cycle(self, symbol: str, scanner_data: Dict = None, positions: Dict = None) -> Dict:
        # 🛡️ SECURITY: Kill Switch
        if getattr(TradingConfig, 'EMERGENCY_STOP', False):
            logger.critical("🚨 EMERGENCY STOP ACTIVATED in config")
            return {'symbol': symbol, 'status': 'STOPPED', 'reason': 'EMERGENCY_STOP'}

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
            
            # 🏛️ EMPIRE V16: Gestion intelligente des positions (Optimisation Vitesse)
            manage_done = False
            if positions is None:
                positions = self.persistence.load_positions()
                if positions: 
                    self._manage_positions(positions)
                    positions = self.persistence.load_positions()
                manage_done = True
            
            # Si le symbole est déjà ouvert, on le gère spécifiquement s'il n'a pas été géré plus haut
            if symbol in positions:
                if not manage_done:
                    # Gérer uniquement cette position pour gagner du temps
                    self._manage_positions({symbol: positions[symbol]})
                    # Vérification rapide si elle est toujours là
                    if self._get_binance_position_detail(symbol):
                        logger.warning(f"[REAL_POSITION] {symbol} already open/managed")
                        return {'symbol': symbol, 'status': 'SKIP_OPEN', 'reason': 'Already open'}
                    else:
                        # Clôturée par management ! On peut ré-entrer (Nouvelle Page Blanche)
                        del positions[symbol]
            
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
                            
                            del positions['USDC/USDT:USDT']
                            balance = self.exchange.get_balance_usdt()  # Refresh balance
                            
                            logger.info(f"[FLASH_EXIT] USDC closed, capital freed: ${balance:.0f}")
                        except Exception as e:
                            logger.error(f"[ERROR] Flash exit failed: {e}")
            
            # Get balance early (needed for trim check and later logic)
            balance = self.exchange.get_balance_usdt()
            if balance < 10: raise ValueError("Insufficient balance ( < $10 )")
            
            # Scaling automatique selon le capital
            scaling = TradingConfig.get_scaling_config(balance)
            TradingConfig.MIN_VOLUME_24H = scaling['min_volume']
            TradingConfig.MAX_OPEN_TRADES = scaling['max_trades']
            TradingConfig.LEVERAGE = scaling['leverage']
            logger.info(f"[SCALING] {scaling['note']} | Capital: ${balance:,.0f} | Eligible: {scaling['eligible']}")
            
            # TRIM & SWITCH: Check if we should reduce existing positions for better opportunities
            # Only if we have positions AND low available capital
            if positions and balance < 500:  # Less than $500 available
                logger.info(f"[TRIM_CHECK] Low capital (${balance:.0f}), checking for better opportunities...")
            
            # 1. Pré-filtre de mobilité (25 bougies légères)
            ohlcv_light = self.exchange.fetch_ohlcv_1min(symbol, limit=25)
            
            if len(ohlcv_light) < 25:
                self.persistence.log_skipped_trade(symbol, "INSUFFICIENT_1MIN_DATA", asset_class)
                return {'symbol': symbol, 'status': 'SKIPPED', 'reason': 'INSUFFICIENT_1MIN_DATA'}
            
            # ❌ MOBILITY CHECK SUPPRIMÉ - Le scanner fait déjà ce travail!
            # Si le symbole arrive ici, c'est qu'il a déjà passé le mobility check en Phase 4
            # Le trading_engine fait 100% confiance au scanner pour la mobilité
            
            # ❌ SUPPRIMÉ: Le scanner a déjà fait l'analyse momentum!
            # Pas de double calcul - utilisation directe des données du scanner
            
            # ✅ V16: Utiliser 100% les données du scanner (pas de re-analysis)
            if scanner_data:
                # Données fournies par le scanner (mode optimal)
                ta_result = {
                    'signal_type': scanner_data['direction'],
                    'score': scanner_data['elite_score'],
                    'price': scanner_data['current_price'],
                    'atr': scanner_data['atr'],
                    'tp_price': scanner_data['tp_price'],
                    'sl_price': scanner_data['sl_price'],
                    'volume_ratio': scanner_data['vol_ratio'],
                    'volume_24h_usdt': scanner_data.get('volume_24h', 0),
                    'blocked': False,
                    'scanner_validated': True
                }
                signal_type = scanner_data['direction']
                # Skip NEUTRAL check - scanner already validated
            else:
                # Fallback: ne devrait jamais arriver en V16
                raise ValueError("Scanner data required for V16 momentum strategy")
            
            # ✅ V16: Plus de vérification NEUTRAL - scanner a déjà validé

            # 🚀 OPTIMIZATION: Utiliser le volume du scanner si disponible (évite 1 API call)
            if scanner_data and scanner_data.get('volume_24h_usdt'):
                volume_24h = scanner_data['volume_24h_usdt']
                self.risk_manager.set_current_volume_24h(volume_24h)
                ta_result['volume_24h_usdt'] = volume_24h
            else:
                # Fallback API seulement si nécessaire
                try:
                    ticker_stats = self.exchange.fetch_binance_ticker_stats(symbol)
                    volume_24h = ticker_stats.get('volume_24h', 0)
                    self.risk_manager.set_current_volume_24h(volume_24h)
                    ta_result['volume_24h_usdt'] = volume_24h
                except:
                    volume_24h = 0
            
            news_score = 0
            
            import macro_context
            macro = macro_context.get_macro_context(state_table=self.aws.state_table)
            
            # V16: Calculate compound capital properly
            compound_capital = self.get_compound_capital(balance) if TradingConfig.USE_COMPOUND else None

            decision = self.decision_engine.evaluate_with_risk(
                context=macro, ta_result=ta_result, symbol=symbol,
                capital=balance, direction=signal_type, asset_class=asset_class,
                news_score=news_score, macro_regime=macro.get('regime', 'NORMAL'),
                compound_capital=compound_capital
            )
            
            if not decision['proceed']:
                logger.info(f"[INFO] Blocked: {decision['reason']}")
                self.persistence.log_skipped_trade(symbol, decision['reason'], asset_class)
                return {'symbol': symbol, 'status': 'BLOCKED', 'reason': decision['reason']}
            
            # 🏛️ EMPIRE V16: MAX_OPEN_TRADES enforcement (Binance API only)
            open_count = len(positions)  # positions vient déjà de Binance API
            if open_count >= TradingConfig.MAX_OPEN_TRADES:
                reason = f"MAX_OPEN_TRADES reached ({open_count}/{TradingConfig.MAX_OPEN_TRADES})"
                logger.warning(f"[SLOT_FULL] {reason}")
                self.persistence.log_skipped_trade(symbol, reason, asset_class)
                return {'symbol': symbol, 'status': 'SLOT_FULL', 'reason': reason}

            # 🏛️ EMPIRE V16.8: Claude Veto moved to Scanner (pick_best_trades)
            # market_veto() is deprecated - all AI arbitrage happens in Scanner Phase 3
            
            return self._execute_entry(symbol, signal_type, decision, ta_result, asset_class, balance)
            
        except Exception as e:
            logger.error(f"[ERROR] Cycle error: {e}")
            return {'symbol': symbol, 'status': 'ERROR', 'error': str(e)}
    
    def _execute_entry(self, symbol, direction, decision, ta_result, asset_class, balance):
        # BINANCE SYNC: Verify no existing position before opening (source of truth)
        binance_pos = self._get_binance_position_detail(symbol)
        if binance_pos:
            reason = f"BINANCE_SYNC: Position already exists on Binance ({binance_pos['side']} {binance_pos['quantity']} @ ${binance_pos['entry_price']:.2f})"
            logger.warning(f"[BINANCE_BLOCK] {symbol} — {reason}")
            self.persistence.log_skipped_trade(symbol, reason, asset_class)
            return {'symbol': symbol, 'status': 'BINANCE_ALREADY_OPEN', 'reason': reason}
        
        trade_id = f"V11-{uuid.uuid4().hex[:8]}"
        side = 'sell' if direction == 'SHORT' else 'buy'
        quantity = decision['quantity']
        
        market_info = self.exchange.get_market_info(symbol)
        min_amount = market_info.get('min_amount', 0)
        if quantity < min_amount: quantity = min_amount

        # Utiliser le levier adaptatif depuis decision engine
        adaptive_leverage = decision.get('leverage', TradingConfig.LEVERAGE)
        
        # 🏛️ EMPIRE V16: Levier et mode marge gérés directement par create_market_order
        try:
            order = self.exchange.create_market_order(symbol, side, quantity, leverage=adaptive_leverage)
            real_entry = float(order.get('average', ta_result['price']))
            real_size = float(order.get('filled', quantity))
            logger.info(f"[OK] {direction} filled: {real_size} @ ${real_entry:.2f} (Leverage: {adaptive_leverage}x)")
        except Exception as e:
            logger.error(f"[ERROR] Order failed: {e}")
            return {'symbol': symbol, 'status': 'ORDER_FAILED', 'error': str(e)}
        
        # Risk dollars calculation (simuler ce que faisait atomic_persistence)
        risk_dollars = decision.get('risk_dollars', 0.0)
        
        # Utiliser les TP/SL de analyze_momentum
        # 🏛️ EMPIRE V16.7.3: Clean TP/SL recalculation (Conflit ATR vs Fixe)
        atr = float(ta_result.get('atr', 0))
        
        # TP: max(ATR * Multiplier, MIN_TP_PCT)
        tp_dist_atr = atr * TradingConfig.TP_MULTIPLIER
        tp_dist_min = real_entry * TradingConfig.MIN_TP_PCT
        final_tp_dist = max(tp_dist_atr, tp_dist_min)
        tp_pct = final_tp_dist / real_entry
        
        # SL: max(ATR * Multiplier, MIN_SL_PCT) - Asymétrie EMPIRE V16.7.5
        sl_multiplier = TradingConfig.SL_MULTIPLIER if direction == 'LONG' else getattr(TradingConfig, 'SHORT_SL_MULTIPLIER', 0.7)
        sl_min_pct = TradingConfig.MIN_SL_PCT if direction == 'LONG' else getattr(TradingConfig, 'SHORT_SL_PCT', 0.0030)
        
        sl_dist_atr = atr * sl_multiplier
        sl_dist_min = real_entry * sl_min_pct
        final_sl_dist = max(sl_dist_atr, sl_dist_min)
        sl_pct = final_sl_dist / real_entry
        
        # Arrondi selon la précision du marché (Hardware Rules)
        market = self.exchange.get_market_info(symbol)
        # 🛡️ SECURITE: Utiliser tickSize si disponible, sinon fallback precision
        tick_size = market.get('precision', {}).get('price')
        
        def round_step(price, step):
            if not step: return round(price, 8)
            if step >= 1: return round(price / step) * step
            return round(price / step) * step

        if direction == 'LONG':
            tp = round_step(real_entry * (1 + tp_pct), tick_size)
            sl = round_step(real_entry * (1 - sl_pct), tick_size)
        else:
            tp = round_step(real_entry * (1 - tp_pct), tick_size)
            sl = round_step(real_entry * (1 + sl_pct), tick_size)

        # Sécurité ultime: ne jamais avoir un prix <= 0
        tp = max(tp, 0.00000001)
        sl = max(sl, 0.00000001)

        # Logging avec pourcentages réels post-arrondi
        tp_pct_final = abs(tp - real_entry) / real_entry
        sl_pct_final = abs(sl - real_entry) / real_entry
        logger.info(f"[MOMENTUM] Entry: ${real_entry:.4f} | TP: ${tp:.4f} ({tp_pct_final*100:.2f}%) | SL: ${sl:.4f} ({sl_pct_final*100:.2f}%) | TickSize: {tick_size}")
        
        # Build detailed reason with technical indicators
        reason_parts = []
        if 'rsi' in ta_result:
            reason_parts.append(f"RSI={ta_result['rsi']:.1f}")
        if ta_result.get('market_context'):
            reason_parts.append(ta_result['market_context'])
        if decision.get('confidence'):
            reason_parts.append(f"AI={decision['confidence']*100:.0f}%")
        if 'score' in ta_result:
            reason_parts.append(f"Score={ta_result['score']}")
        reason_parts.append(f"Lev={adaptive_leverage}x")
        
        detailed_reason = " | ".join(reason_parts) if reason_parts else decision.get('reason', 'Signal detected')
        
        self.persistence.log_trade_open(
            trade_id, symbol, asset_class, direction, real_entry, real_size,
            real_size * real_entry, tp, sl, adaptive_leverage,
            reason=detailed_reason
        )
        
        pos_data = {
            'trade_id': trade_id, 'entry_price': real_entry, 'quantity': real_size,
            'direction': direction, 'stop_loss': sl, 'take_profit': tp,
            'asset_class': asset_class,
            'risk_dollars': decision['risk_dollars'],
            'leverage': adaptive_leverage,
            'entry_time': datetime.now(timezone.utc).isoformat()
        }
        self.persistence.save_position(symbol, pos_data)
        
        # Local state sync
        self.risk_manager.register_trade(symbol, real_entry, real_size, decision['risk_dollars'], decision['stop_loss'], direction)
        self.persistence.save_risk_state(self.risk_manager.get_state())
        
        # 🏛️ EMPIRE V16: Placement immédiat des ordres GTC (Hardware Safety)
        try:
            self.exchange.create_sl_tp_orders(symbol, direction, real_size, sl, tp)
            logger.info(f"[GTC] SL/TP orders placed for {symbol}")
        except Exception as gtc_err:
            logger.error(f"[GTC_ERROR] Failed to place SL/TP for {symbol}: {gtc_err}")

        logger.info(f"[OK] Position opened and secured: {direction} {symbol}")
        return {
            'symbol': symbol, 
            'status': f'{direction}_OPEN', 
            'trade_id': trade_id,
            'tp_price': tp,
            'sl_price': sl
        }
    
    def _is_in_cooldown(self, symbol: str) -> bool:
        """Check if symbol is in cooldown period (anti-spam protection)"""
        return is_in_cooldown(self.aws.state_table, symbol, self.cooldown_seconds)
    
    def _record_trade_timestamp(self, symbol: str):
        """Record trade timestamp for cooldown tracking"""
        record_trade_timestamp(self.aws.state_table, symbol)
    
    def _get_real_binance_positions(self) -> List[str]:
        """Get actual open positions from Binance (source of truth)"""
        return get_real_binance_positions(self.exchange)
    
    def _get_binance_position_detail(self, symbol: str) -> Optional[Dict]:
        """Get real position detail from Binance for a specific symbol. Returns None if no position."""
        try:
            ccxt_ex = self.exchange.exchange if hasattr(self.exchange, 'exchange') else self.exchange
            # Explicit parameter for speed and reliability (Audit #V16.4)
            binance_sym = symbol.replace('/USDT:USDT', 'USDT').replace('/', '')
            positions = ccxt_ex.fapiPrivateV2GetPositionRisk({'symbol': binance_sym})
            
            if not positions:
                return None
                
            # Response can be list or single dict
            pos = positions[0] if isinstance(positions, list) else positions
            
            qty = abs(float(pos.get('positionAmt', 0)))
            if qty > 0:
                return {
                    'quantity': qty,
                    'side': 'LONG' if float(pos['positionAmt']) > 0 else 'SHORT',
                    'entry_price': float(pos.get('entryPrice', 0)),
                    'unrealized_pnl': float(pos.get('unRealizedProfit', 0)),
                    'mark_price': float(pos.get('markPrice', 0)),
                    'leverage': int(pos.get('leverage', 1))
                }
            return None
        except Exception as e:
            logger.error(f"[BINANCE_SYNC] Failed to get position detail for {symbol}: {e}")
            return None
    
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
    
        
    def _manage_positions(self, positions: Dict):
        logger.info(f"\n{'='*70}\n[INFO] POSITION MANAGEMENT\n{'='*70}")
        for symbol, pos in list(positions.items()):
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = float(ticker['last'])
                entry_price = float(pos.get('entry_price', 0))
                direction = pos['direction']
                
                # Calculate current PnL % (ensure all values are float to avoid Decimal errors)
                current_price = float(current_price)
                entry_price = float(entry_price)
                
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
                        
                        # 🏛️ EMPIRE V16.1: Fast exit pour trades qui stagnent (frais de transaction)
                        if time_open_minutes >= TradingConfig.FAST_EXIT_MINUTES and abs(pnl_pct) < TradingConfig.FAST_EXIT_PNL_THRESHOLD * 100:
                            logger.warning(f"[FAST_EXIT] {symbol} flat after {time_open_minutes:.0f}min (PnL: {pnl_pct:+.2f}% < {TradingConfig.FAST_EXIT_PNL_THRESHOLD*100:.1f}%)")
                            should_exit_fast_discard = True
                            exit_reason = f"FAST_EXIT_{time_open_minutes:.0f}min_flat"
                        
                        # V16: MAX_HOLD_CANDLES enforcement (10 minutes = 10 candles)
                        if time_open_minutes >= TradingConfig.MAX_HOLD_CANDLES:
                            logger.warning(f"[MAX_HOLD] {symbol} held for {time_open_minutes:.1f}min (max: {TradingConfig.MAX_HOLD_CANDLES}min)")
                            should_exit_time = True
                            exit_reason = f"MAX_HOLD_{time_open_minutes:.0f}min"
                        
                        # TIME_BASED_EXIT: Adaptatif par asset class (V13.4 - Levier x2/x4)
                        # Crypto (x2): 20min - Scalping rapide, momentum pur
                        # Indices (x2): 30min - Suivi de tendance
                        # Commodities/PAXG (x4): 90min - Rebond structurel, or lent
                        # Forex/Parking (x2): 60min - Stabilité
                        asset_class = pos.get('asset_class', 'crypto')
                        symbol_key = symbol if isinstance(symbol, str) else pos.get('symbol', '')
                        
                        # Crypto: 20min (x2 = scalping rapide)
                        if asset_class == 'crypto':
                            time_threshold_hours = 1/3  # 20min
                        # Indices: 30min (x2 = suivi tendance)
                        elif asset_class == 'indices':
                            time_threshold_hours = 0.5  # 30min
                        # Commodities (PAXG x4): 90min (or = rebond structurel)
                        elif asset_class == 'commodities' or 'PAXG' in symbol_key:
                            time_threshold_hours = 1.5  # 90min
                        # Forex (USDC): 60min (parking)
                        else:  # forex
                            time_threshold_hours = 1.0  # 60min
                        
                        if time_open_hours > time_threshold_hours:
                            should_exit_time = True
                            logger.warning(f"[TIME_EXIT] {symbol} ({asset_class}) open {time_open_hours*60:.0f}min - auto-close (PnL: {pnl_pct:+.2f}%)")
                        
                        # FAST_DISCARD: >10min AND PnL < 0.10% (libérer capital si momentum absent)
                        if time_open_minutes > 10 and pnl_pct < 0.10:
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
                    
                    pnl = self.risk_manager.close_trade(symbol, exit_price)
                    self.persistence.save_risk_state(self.risk_manager.get_state())
                    self.persistence.log_trade_close(pos['trade_id'], exit_price, pnl, reason)
                    self.persistence.delete_position(symbol)
                    del positions[symbol]
                    logger.info(f"[OK] Closed {symbol} | PnL: ${pnl:.2f} ({pnl_pct:+.2f}%)")
                    
                    # 📊 MONITORING: CloudWatch Metrics
                    try:
                        import boto3
                        cw = boto3.client('cloudwatch', region_name=os.getenv('AWS_REGION', 'ap-northeast-1'))
                        cw.put_metric_data(
                            Namespace='EmpireTrading',
                            MetricData=[
                                {
                                    'MetricName': 'TradePnLPercent',
                                    'Dimensions': [{'Name': 'Symbol', 'Value': symbol}],
                                    'Value': float(pnl_pct),
                                    'Unit': 'Percent'
                                },
                                {
                                    'MetricName': 'TradePnLUSD',
                                    'Value': float(pnl),
                                    'Unit': 'None'
                                }
                            ]
                        )
                    except Exception as cw_err:
                        logger.warning(f"[CW_ERROR] Failed to log metrics: {cw_err}")
                else:
                    logger.info(f"[HOLD] {symbol} | PnL: {pnl_pct:+.2f}% | Time: {entry_time_str[:16] if entry_time_str else 'N/A'}")

            except Exception as e: logger.error(f"[ERROR] Manage failed for {symbol}: {e}")

    async def execute_trade_websocket(self, symbol: str, side: str, quantity: float, price: float) -> Optional[Dict]:
        """🏛️ EMPIRE V16.2: Wrapper pour l'exécuteur WebSocket"""
        try:
            from websocket_executor import WebSocketExecutor
            executor = WebSocketExecutor(demo_mode=not TradingConfig.LIVE_MODE)
            
            # Map side (LONG/SHORT -> BUY/SELL)
            ws_side = 'BUY' if side == 'LONG' else 'SELL'
            
            # Utiliser Decimal pour la précision
            from decimal import Decimal
            d_quantity = Decimal(str(quantity))
            
            result = await executor.execute_market_order(symbol, ws_side, float(d_quantity))
            return result
        except Exception as e:
            logger.error(f"[WS_EXEC_WRAPPER_ERROR] {e}")
            return None

# ==================== LAMBDA HANDLER ====================

def lambda_handler(event, context):
    try:
        engine = TradingEngine()
        
        # Get symbols from event or environment variable
        symbols_str = event.get('symbols') if event.get('symbols') else os.getenv('SYMBOLS', '')
        if not symbols_str:
            # Si aucun symbole fourni, récupérer tous les symboles disponibles
            try:
                import requests
                # Use correct base URL for exchangeInfo
                base_url = "https://fapi.binance.com" if TradingConfig.LIVE_MODE else "https://demo-api.binance.com"
                response = requests.get(f"{base_url}/fapi/v1/exchangeInfo", timeout=5)
                response.raise_for_status()
                data = response.json()
                
                symbols = []
                for symbol_info in data['symbols']:
                    if (symbol_info['status'] == 'TRADING' and 
                        symbol_info['contractType'] == 'PERPETUAL' and
                        symbol_info['quoteAsset'] == 'USDT'):
                        symbols.append(f"{symbol_info['symbol']}/USDT:USDT")
                
                logger.info(f"[INFO] Dynamically loaded {len(symbols)} symbols from Binance API")
                
            except Exception as e:
                logger.error(f"[ERROR] Failed to load symbols from API: {e}")
                symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT']  # Minimal fallback
        else:
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
