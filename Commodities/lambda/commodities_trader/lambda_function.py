import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from config import CONFIGURATION
from strategies import ForexStrategies
from data_loader import DataLoader
from news_fetcher import news_fetcher
import boto3

# Configuration Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ==================== V5.1 MODULES ====================
# Position Sizing Cumulatif (Point 2)
try:
    from position_sizing import calculate_position_size, get_account_balance
    POSITION_SIZING_AVAILABLE = True
except ImportError:
    POSITION_SIZING_AVAILABLE = False
    logger.warning("⚠️ Position Sizing module not available")

# Horloge Biologique (Point 1)
try:
    from trading_windows import get_session_phase, get_session_info
    SESSION_PHASE_AVAILABLE = True
except ImportError:
    SESSION_PHASE_AVAILABLE = False

# Micro-Corridors (pour le prompt Bedrock enrichi - Point 4)
try:
    from micro_corridors import get_adaptive_params, get_corridor_summary
    MICRO_CORRIDORS_AVAILABLE = True
except ImportError:
    MICRO_CORRIDORS_AVAILABLE = False

# 🏛️ V5.1 Macro Context - Hedge Fund Intelligence
try:
    from macro_context import get_macro_context
    MACRO_CONTEXT_AVAILABLE = True
except ImportError:
    MACRO_CONTEXT_AVAILABLE = False

# 🛡️ V5.1 Predictability Index - Anti-Erratic Filter
try:
    from predictability_index import calculate_predictability_score, get_predictability_adjustment
    PREDICTABILITY_INDEX_AVAILABLE = True
except ImportError:
    PREDICTABILITY_INDEX_AVAILABLE = False

# 📈 V6.0 Trailing Stop Module
try:
    import sys
    sys.path.insert(0, '/opt/python/shared/modules')  # Lambda layer path
    from trailing_stop import check_trailing_stop, TrailingStopManager
    TRAILING_STOP_AVAILABLE = True
except ImportError:
    TRAILING_STOP_AVAILABLE = False
    logger.warning("⚠️ Trailing Stop module not available")

# ==================== CONFIGURATION ====================
INITIAL_CAPITAL = float(os.environ.get('INITIAL_CAPITAL', '400'))  # Capital initial total
CAPITAL_PER_TRADE = float(os.environ.get('CAPITAL', '100'))  # Fallback si Position Sizing non dispo
STOP_LOSS_PCT = float(os.environ.get('STOP_LOSS', '-3.0'))   # -3% Stop Loss (Commodities)
HARD_TP_PCT = float(os.environ.get('HARD_TP', '4.0'))        # +4% Take Profit  
COOLDOWN_HOURS = float(os.environ.get('COOLDOWN_HOURS', '6')) # 6h between trades (Gold/Oil move slower)
MAX_EXPOSURE = int(os.environ.get('MAX_EXPOSURE', '2'))       # Max 2 trades per commodity
DYNAMO_TABLE = os.environ.get('DYNAMO_TABLE', 'EmpireCommoditiesHistory')
# ========================================================

# AWS Clients
dynamodb_client = boto3.resource('dynamodb')
history_table = dynamodb_client.Table(DYNAMO_TABLE)
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

def get_paris_time():
    """Returns current Paris time (UTC+1 for winter)"""
    return datetime.utcnow() + timedelta(hours=1)

def get_portfolio_context(pair):
    """Get current exposure and last trade info for cooldown"""
    try:
        response = history_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('Pair').eq(pair) & 
                            boto3.dynamodb.conditions.Attr('Status').eq('OPEN')
        )
        open_trades = response.get('Items', [])
        
        # Get last trade for cooldown check
        all_trades = history_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('Pair').eq(pair)
        ).get('Items', [])
        
        # Filter only actual trades (Status OPEN or CLOSED)
        actual_trades = [t for t in all_trades if t.get('Status') in ['OPEN', 'CLOSED']]
        
        sorted_trades = sorted(actual_trades, key=lambda x: x.get('Timestamp', ''), reverse=True)
        last_trade = sorted_trades[0] if sorted_trades else None
        
        return {
            'exposure': len(open_trades),
            'last_trade': last_trade,
            'open_trades': open_trades
        }
    except Exception as e:
        logger.error(f"Portfolio context error: {e}")
        return {'exposure': 0, 'last_trade': None, 'open_trades': []}

def manage_exits(pair, current_price, asset_class='Commodities'):
    """Manage Stop Loss and Take Profit for open positions"""
    try:
        context = get_portfolio_context(pair)
        open_trades = context.get('open_trades', [])
        
        if not open_trades:
            return None
            
        exit_time = get_paris_time().isoformat()
        closed_count = 0
        total_pnl = 0
        
        for trade in open_trades:
            entry_price = float(trade.get('EntryPrice', 0))
            trade_type = trade.get('Type', 'LONG').upper()
            # V6.2 FIX: Use position VALUE (Cost), not Size (quantity)
            position_value = float(trade.get('Cost', CAPITAL_PER_TRADE))

            if entry_price == 0:
                continue

            # Calculate PnL based on direction
            if trade_type in ['LONG', 'BUY']:
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
            else:  # SHORT/SELL
                pnl_pct = ((entry_price - current_price) / entry_price) * 100

            # V6.2 FIX: Calculate P&L using position VALUE, not quantity
            pnl_dollars = (pnl_pct / 100) * position_value
            
            exit_reason = None
            
            # Check Stored Dynamic SL/TP (Priority)
            stored_sl = float(trade.get('SL', 0))
            stored_tp = float(trade.get('TP', 0))
            
            # --- 📈 V6.0 TRAILING STOP CHECK ---
            if TRAILING_STOP_AVAILABLE and pnl_pct > 0:
                peak_price = float(trade.get('PeakPrice', entry_price))
                atr = float(trade.get('ATR', 0)) if trade.get('ATR') else None
                
                # Use stored SL as current SL if available, else derive from global pct
                if stored_sl == 0:
                    if trade_type in ['LONG', 'BUY']:
                         stored_sl = entry_price * (1 + STOP_LOSS_PCT/100)
                    else:
                         stored_sl = entry_price * (1 - STOP_LOSS_PCT/100) # STOP_LOSS_PCT is negative (-3.0) 
                         # Wait, if STOP_LOSS_PCT is -3.0:
                         # LONG: entry * (1 - 0.03) = 0.97 * entry (Correct)
                         # SHORT: entry * (1 - (-0.03)) = 1.03 * entry (Correct)
                
                trailing_result = check_trailing_stop(
                    entry_price=entry_price,
                    current_price=current_price,
                    trade_type=trade_type,
                    current_sl=stored_sl,
                    asset_class=asset_class,
                    peak_price=peak_price,
                    atr=atr
                )
                
                # Update peak price if changed
                if trailing_result['peak'] != peak_price:
                    history_table.update_item(
                        Key={'TradeId': trade['TradeId']},
                        UpdateExpression="set PeakPrice = :p",
                        ExpressionAttributeValues={':p': str(trailing_result['peak'])}
                    )
                
                # Update SL if trailing moved it
                if trailing_result['new_sl'] is not None:
                    # Update the Stored SL in DynamoDB so next check uses it
                    history_table.update_item(
                        Key={'TradeId': trade['TradeId']},
                        UpdateExpression="set SL = :sl",
                        ExpressionAttributeValues={':sl': str(trailing_result['new_sl'])}
                    )
                    stored_sl = float(trailing_result['new_sl']) # Update local var for next check
                    logger.info(f"📈 {trailing_result['mode']}: Updated SL to {trailing_result['new_sl']:.5f}")
                
                # Check if trailing stop triggered exit
                if trailing_result['triggered']:
                    exit_reason = f"TRAILING_{trailing_result['mode']}"
                    logger.info(f"📈 TRAILING STOP triggered for {pair}: {pnl_pct:.2f}%")

            # Check Dynamic Stop Loss (ATR Based or Updated by Trailing)
            if not exit_reason and stored_sl > 0:
                if trade_type in ['LONG', 'BUY'] and current_price <= stored_sl:
                    exit_reason = "STOP_LOSS_ATR"
                    logger.warning(f"🛑 ATR/TRAILING STOP LOSS HIT for {pair}: {current_price} <= {stored_sl}")
                elif trade_type in ['SHORT', 'SELL'] and current_price >= stored_sl:
                    exit_reason = "STOP_LOSS_ATR"
                    logger.warning(f"🛑 ATR/TRAILING STOP LOSS HIT for {pair}: {current_price} >= {stored_sl}")

            # Check Dynamic Take Profit (ATR Based)
            if not exit_reason and stored_tp > 0:
                if trade_type in ['LONG', 'BUY'] and current_price >= stored_tp:
                    exit_reason = "TAKE_PROFIT_ATR"
                    logger.info(f"💎 ATR TAKE PROFIT HIT for {pair}: {current_price} >= {stored_tp}")
                elif trade_type in ['SHORT', 'SELL'] and current_price <= stored_tp:
                    exit_reason = "TAKE_PROFIT_ATR"
                    logger.info(f"💎 ATR TAKE PROFIT HIT for {pair}: {current_price} <= {stored_tp}")

            # Fallback: Global Safety Nets (Circuit Breakers)
            if not exit_reason:
                if pnl_pct <= STOP_LOSS_PCT: # Default -3% (Safety)
                    # Only use this if Stored SL is 0 (not set).
                    if stored_sl == 0:
                        exit_reason = "STOP_LOSS_HARD"
                        logger.warning(f"🛑 HARD STOP LOSS HIT for {pair}: {pnl_pct:.2f}%")
                
                elif pnl_pct >= HARD_TP_PCT: # Default +4%
                    if stored_tp == 0:
                        exit_reason = "TAKE_PROFIT_HARD"
                        logger.info(f"💎 HARD TAKE PROFIT HIT for {pair}: {pnl_pct:.2f}%")
            
            if exit_reason:
                history_table.update_item(
                    Key={'TradeId': trade['TradeId']},
                    UpdateExpression="set #st = :s, PnL = :p, ExitPrice = :ep, ExitTime = :et, ExitReason = :er",
                    ExpressionAttributeNames={'#st': 'Status'},
                    ExpressionAttributeValues={
                        ':s': 'CLOSED',
                        ':p': str(round(pnl_dollars, 2)),
                        ':ep': str(current_price),
                        ':et': exit_time,
                        ':er': exit_reason
                    }
                )
                closed_count += 1
                total_pnl += pnl_dollars
                
        if closed_count > 0:
            return f"CLOSED_{closed_count}_TRADES_PNL_${total_pnl:.2f}"
            
        return "HOLD"
        
    except Exception as e:
        logger.error(f"Exit management error: {e}")
        return None

def lambda_handler(event, context):
    """
    AWS Lambda Handler pour le trading Forex
    Trigger: EventBridge (Toutes les heures)
    """
    # Fix yfinance cache issue on Lambda (Read-only file system)
    os.environ['YFINANCE_CACHE_DIR'] = '/tmp/yf_cache'
    import yfinance as yf
    try:
        if not os.path.exists('/tmp/yf_cache'):
            os.makedirs('/tmp/yf_cache')
        yf.set_tz_cache_location("/tmp/yf_cache")
    except Exception:
        pass  # Ignore if it fails, it's just cache
    
    logger.info("🚀 Commodities Trader V5.1 Started")
    
    # --- 🏛️ MACRO CONTEXT (Global Check) ---
    macro_data = None
    if MACRO_CONTEXT_AVAILABLE:
        try:
            macro_data = get_macro_context()
            logger.info(f"🏛️ V5.1 MACRO: Regime={macro_data['regime']} | DXY={macro_data['dxy']['value']} | VIX={macro_data['vix']['level']}")
            
            # 🛑 GLOBAL KILL SWITCH
            if not macro_data['can_trade']:
                logger.warning(f"🛑 TRADING HALTED by Macro Regime: {macro_data['regime']}")
                return {
                    'statusCode': 200,
                    'body': json.dumps({'message': 'Trading Halted (Macro Condition)', 'regime': macro_data['regime']})
                }
        except Exception as e:
            logger.error(f"❌ Macro Context Failed: {e}")
    
    # V5.6 FORTRESS: Check for DXY Spike (Kill Switch)
    dxy_kill_switch = False
    if macro_data and macro_data.get('dxy', {}).get('signal') == 'BULLISH_STRONG':
        dxy_kill_switch = True
        logger.warning("🛑 MACRO ALERT: DXY is Pumping (BULLISH_STRONG). enabling Gold Kill-Switch.")

    results = []

    # 🔥 V6.0 FIX: Manage Exits FIRST in separate loop (unconditional)
    # This ensures positions are closed even if pair is disabled/erratic/no data
    logger.info("🚪 Phase 1: Checking exits for all open positions...")
    for pair in CONFIGURATION.keys():
        try:
            # Fetch current price (minimal data needed)
            df = DataLoader.get_latest_data(pair)
            if df is not None and len(df) > 0:
                current_price = df.iloc[-1]['close']
                exit_result = manage_exits(pair, current_price)
                if exit_result and "CLOSED" in str(exit_result):
                    logger.info(f"📤 Exit executed for {pair}: {exit_result}")
                    results.append({'pair': pair, 'action': 'EXIT', 'result': exit_result})
        except Exception as e:
            logger.error(f"❌ Error managing exits for {pair}: {e}")

    # 🎯 Phase 2: Analyze entry signals (conditional on checks)
    logger.info("🎯 Phase 2: Analyzing entry signals...")
    for pair, config in CONFIGURATION.items():
        if not config['enabled']:
            continue

        # V5.6: Apply DXY Kill-Switch for Gold
        if dxy_kill_switch and 'GC=F' in pair:
            logger.info(f"🛑 Skipping {pair} due to DXY Spike (Macro Kill-Switch)")
            continue

        logger.info(f"🔍 Analyzing {pair} with {config['strategy']}...")

        # 1. Fetch Data
        df = DataLoader.get_latest_data(pair)
        if df is None or len(df) < 201:
            logger.warning(f"⚠️ Not enough data for {pair}")
            continue

        # --- 🛡️ V5.1 PREDICTABILITY CHECK (CRITICAL FOR COMMODITIES) ---
        predictability = {'score': 100, 'grade': 'EXCELLENT', 'multiplier': 1.0}
        if PREDICTABILITY_INDEX_AVAILABLE:
            try:
                pred_adj = get_predictability_adjustment(df)
                predictability = {
                    'score': pred_adj.get('score', 50),
                    'grade': pred_adj.get('grade', 'MODERATE'),
                    'multiplier': pred_adj.get('size_multiplier', 1.0),
                    'should_trade': pred_adj.get('should_trade', True)
                }

                logger.info(f"   🛡️ Predictability {pair}: {predictability['grade']} ({predictability['score']}/100)")

                # 🚫 QUARANTINE: Rule is STRICT for Commodities (especially Oil)
                if not predictability['should_trade']:
                    logger.warning(f"🛑 {pair} QUARANTINED (Erratic/Poor Score: {predictability['score']})")
                    log_skip_to_dynamo(pair, f"QUARANTINE_ERRATIC_{predictability['grade']}", df.iloc[-1]['close'])
                    continue

            except Exception as e:
                logger.error(f"Predictability Check Error: {e}")

        # 2. Calculate Indicators
        try:
            df = ForexStrategies.calculate_indicators(df, config['strategy'])

            # Log Technical Analysis details (Like Crypto Bot)
            last_row = df.iloc[-1]
            log_msg = f"   📊 {pair}: Close={last_row['close']:.5f} | ATR={last_row['ATR']:.5f}"

            if 'RSI' in df.columns:
                log_msg += f" | RSI={last_row['RSI']:.2f}"
            if 'SMA_200' in df.columns:
                log_msg += f" | SMA200={last_row['SMA_200']:.5f}"
            if 'BBU' in df.columns:
                log_msg += f" | BB={last_row['BBU']:.5f}/{last_row['BBL']:.5f}"

            logger.info(log_msg)

        except Exception as e:
            logger.error(f"❌ Error indicators {pair}: {e}")
            continue
        
        # 4. Check Cooldown & Exposure
        portfolio = get_portfolio_context(pair)
        
        if portfolio['exposure'] >= MAX_EXPOSURE:
            logger.info(f"⏸️ Max exposure ({MAX_EXPOSURE}) reached for {pair}")
            continue
            
        if portfolio.get('last_trade'):
            last_time = datetime.fromisoformat(portfolio['last_trade']['Timestamp'])
            hours_since = (get_paris_time() - last_time).total_seconds() / 3600
            if hours_since < COOLDOWN_HOURS:
                logger.info(f"⏳ Cooldown active for {pair}. {COOLDOWN_HOURS - hours_since:.1f}h remaining.")
                continue
        
        # 5. Check Signal
        signal = ForexStrategies.check_signal(pair, df, config)
        
        if signal:
            logger.info(f"🎯 TECHNICAL SIGNAL: {signal}")
            
            # --- 💰 V5.1 POSITION SIZING CUMULATIF (Point 2) ---
            # Au lieu d'un montant fixe, on lit le capital actuel et on calcule
            entry = signal['entry']
            sl = signal['sl']
            
            if POSITION_SIZING_AVAILABLE:
                # Calcul dynamique basé sur le capital actuel
                position_info = calculate_position_size(
                    symbol=pair,
                    initial_capital=INITIAL_CAPITAL,
                    dynamo_table=DYNAMO_TABLE,
                    asset_class='Commodities',
                    entry_price=entry,
                    stop_loss=sl
                )
                
                # Utiliser la taille calculée
                position_usd = position_info.get('position_usd', CAPITAL_PER_TRADE)
                risk_multiplier = position_info.get('risk_multiplier', 1.0)
                # Apply Predictability Multiplier (V5.1)
                pred_mult = predictability.get('multiplier', 1.0)
                if pred_mult != 1.0:
                    position_usd *= pred_mult
                    logger.info(f"   📉 Adjusted Size by Predictability ({pred_mult}x): ${position_usd:.2f}")

                # Apply Macro Multiplier (V5.1)
                if macro_data:
                    macro_mult = macro_data.get('size_multiplier', 1.0)
                    if macro_mult != 1.0:
                        position_usd *= macro_mult
                        logger.info(f"   🏛️ Adjusted Size by Macro ({macro_mult}x): ${position_usd:.2f}")

                risk_multiplier = position_info.get('risk_multiplier', 1.0)
                current_capital = position_info.get('current_capital', INITIAL_CAPITAL)
                
                logger.info(f"   💰 COMPOUND SIZING: Capital=${current_capital:.2f} | "
                           f"Position=${position_usd:.2f} | RiskMult={risk_multiplier:.1f}x")
                
                signal['cost'] = position_usd
                signal['capital_at_trade'] = current_capital
                signal['compound_mode'] = True
            else:
                # Fallback: Position sizing classique
                position_usd = config.get('risk_usd', CAPITAL_PER_TRADE)
                signal['cost'] = position_usd
                signal['compound_mode'] = False
            
            # Calculer la taille en unités
            dist = abs(entry - sl)
            if dist > 0:
                pos_size = position_usd / dist
            else:
                pos_size = 0
                
            signal['size'] = round(pos_size, 4)
            signal['risk_usd'] = position_usd  # Pour compatibilité
            
            logger.info(f"   ⚖️ Position Sizing: Cost=${position_usd:.2f} | SL Dist={dist:.2f} | Size={signal['size']}")


            # --- 6. AI VALIDATION (Bedrock) ---
            try:
                # Fetch News Context
                news_context = news_fetcher.get_news_context(pair)
                
                # Ask Bedrock (V5.1 enriched)
                ai_decision = ask_bedrock(pair, signal, news_context, macro_data)
                
                logger.info(f"🤖 BEDROCK DECISION: {ai_decision['decision']} | Reason: {ai_decision['reason']}")
                
                signal['ai_decision'] = ai_decision['decision']
                signal['ai_reason'] = ai_decision['reason']
                signal['news_context'] = news_context
                
                if ai_decision['decision'] == 'CONFIRM':
                    results.append(signal)
                    log_trade_to_dynamo(signal)
                else:
                    logger.info(f"🛑 Trade Cancelled by AI")
                    log_skip_to_dynamo(pair, f"AI_VETO: {ai_decision['reason']}", current_price)

            except Exception as e:
                logger.error(f"❌ AI Validation Failed: {e}")
                # Skip to be safe
                
        else:
            logger.info(f"➡️ No signal for {pair}")
            # Build detailed reason with indicators
            last_row = df.iloc[-1]
            rsi_val = f"RSI={last_row['RSI']:.1f}" if 'RSI' in df.columns else ""
            sma_val = f"SMA200={last_row['SMA_200']:.2f}" if 'SMA_200' in df.columns else ""
            bb_val = f"BB={last_row['BBU']:.2f}/{last_row['BBL']:.2f}" if 'BBU' in df.columns else ""
            detail = " | ".join([x for x in [rsi_val, sma_val, bb_val] if x])
            reason = f"NO_SIGNAL: {detail}" if detail else "NO_SIGNAL: Waiting for entry conditions"
            log_skip_to_dynamo(pair, reason, current_price)
            
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Analysis complete',
            'signals_found': len(results),
            'details': results
        }, default=str)
    }


def log_skip_to_dynamo(pair, reason, current_price):
    """Log skipped/no-signal events for the Reporter"""
    try:
        timestamp = get_paris_time().isoformat()
        log_id = f"LOG-{uuid.uuid4().hex[:8]}"
        item = {
            'TradeId': log_id,
            'Timestamp': timestamp,
            'AssetClass': 'Commodities',
            'Pair': pair,
            'Status': 'SKIPPED',
            'Type': 'INFO',
            'ExitReason': reason,
            'EntryPrice': str(current_price),
            'TTL': int((get_paris_time() + timedelta(days=2)).timestamp())
        }
        history_table.put_item(Item=item)
    except Exception as e:
        logger.error(f"Failed to log skip: {e}")

def log_trade_to_dynamo(signal_data):
    """Log trade to DynamoDB with Size and Cost calculations"""
    try:
        trade_id = f"COMM-{uuid.uuid4().hex[:8]}"
        timestamp = get_paris_time().isoformat()
        
        entry_price = float(signal_data.get('entry', 0))
        size = float(signal_data.get('size', 0))
        cost = float(signal_data.get('cost', CAPITAL_PER_TRADE))
        
        item = {
            'TradeId': trade_id,
            'Timestamp': timestamp,
            'AssetClass': 'Commodities',
            'Pair': signal_data.get('pair'),
            'Type': signal_data.get('signal'),
            'Strategy': signal_data.get('strategy'),
            'EntryPrice': str(entry_price), 
            'Size': str(size),
            'Cost': str(cost),
            'Value': str(cost),
            'SL': str(signal_data.get('sl')),
            'TP': str(signal_data.get('tp')),
            'ATR': str(signal_data.get('atr')),
            'AI_Decision': signal_data.get('ai_decision'),
            'AI_Reason': signal_data.get('ai_reason'),
            'Status': 'OPEN',
            'RiskUSD': str(signal_data.get('risk_usd', 0)),
            'PositionSize': str(size)
        }
        
        history_table.put_item(Item=item)
        logger.info(f"✅ Trade logged to {DYNAMO_TABLE}: {trade_id} | Size: {size} | Cost: ${cost}")
        
    except Exception as e:
        logger.error(f"❌ Failed to log trade to DynamoDB: {e}")

def ask_bedrock(pair, signal_data, news_context, macro_data=None):
    """
    Validates the trade with Claude 3 Haiku using Technicals + News + Corridor Context (V5.1)
    Point 4: Le prompt est enrichi avec les informations du corridor actuel.
    """
    # --- V5.1: Récupérer le contexte du corridor ---
    corridor_context = ""
    regime_instruction = ""
    
    if MICRO_CORRIDORS_AVAILABLE:
        try:
            params = get_adaptive_params(pair)
            corridor_name = params.get('corridor_name', 'Default')
            regime = params.get('regime', 'STANDARD')
            aggressiveness = params.get('aggressiveness', 'MEDIUM')
            risk_mult = params.get('risk_multiplier', 1.0)
            
            corridor_context = f"""
    MARKET TIMING (V5.1 Corridor):
    - Current Corridor: {corridor_name}
    - Market Regime: {regime}
    - Aggressiveness Level: {aggressiveness}
    - Risk Multiplier: {risk_mult}x
    """
            
            # Adapter l'instruction selon le régime
            if regime == 'AGGRESSIVE_BREAKOUT':
                regime_instruction = f"""
    ⚡ HIGH VOLATILITY REGIME (Opening):
    We are in the {corridor_name} zone with HIGH aggressiveness ({aggressiveness}).
    This is a BREAKOUT opportunity. Speed is critical.
    Only CANCEL if news is EXTREMELY contradictory (e.g., major Fed announcement against the trade).
    For normal/mildly negative news → CONFIRM to capture the momentum.
    """
            elif regime == 'TREND_FOLLOWING':
                regime_instruction = f"""
    📈 TREND FOLLOWING REGIME (Core Session):
    We are in {corridor_name} with MEDIUM aggressiveness.
    The trend is established. Favor continuation trades.
    CANCEL only if news clearly reverses the fundamental outlook.
    """
            elif regime in ['CAUTIOUS_REVERSAL', 'LOW_LIQUIDITY']:
                regime_instruction = f"""
    ⚠️ CAUTIOUS REGIME (Closing/Low Liquidity):
    We are in {corridor_name} with LOW aggressiveness ({aggressiveness}).
    Be more selective - CANCEL if there's ANY significant doubt.
    Prefer safety over opportunity.
    """
            else:
                regime_instruction = "Standard validation: CANCEL if news conflicts with the signal."
                
        except Exception as e:
            logger.warning(f"Could not get corridor context: {e}")
    
    if SESSION_PHASE_AVAILABLE:
        try:
            phase = get_session_phase(pair)
            session_name = phase.get('session', 'UNKNOWN')
            phase_name = phase.get('phase', 'UNKNOWN')
            is_tradeable = phase.get('is_tradeable', True)
            
            corridor_context += f"""
    SESSION PHASE: {session_name} ({phase_name})
    Tradeable: {'Yes' if is_tradeable else 'No'}
    """
        except Exception:
            pass
    
        except Exception:
            pass
            
    # --- V5.1 Add Macro Context to Prompt ---
    macro_context_str = ""
    if macro_data:
        macro_context_str = f"""
    MACRO CONTEXT (Hedge Fund View):
    - DXY (Dollar): {macro_data['dxy']['signal']} ({macro_data['dxy']['value']})
    - US 10Y Yield: {macro_data['yields']['signal']} ({macro_data['yields']['value']}%)
    - VIX (Fear): {macro_data['vix']['level']} ({macro_data['vix']['value']})
    - GLOBAL REGIME: {macro_data['regime']}
    """
    
    # Define strategy-specific instructions
    strategy_instruction = "If news is conflicting (e.g. LONG signal but very BEARISH news), return CANCEL. If news is supportive or neutral, return CONFIRM."
    
    # Custom instruction for Momentum/Breakout - Don't block momentum easily
    if 'BOLLINGER_BREAKOUT' in signal_data.get('strategy', ''):
        strategy_instruction = "This is a MOMENTUM trade (High Volatility). Speed is critical. Only CANCEL if the news is EXTREMELY contradictory (e.g. Rate Hike for a Long). If news is just noise or mildly negative, CONFIRM to capture the momentum."

    # Build enriched prompt (Point 4)
    prompt = f"""
    You are a professional Commodities Risk Manager for the Empire V5.1 Trading System.
    
    TRADE PROPOSAL:
    - Pair: {pair}
    - Signal: {signal_data['signal']} ({signal_data['strategy']})
    - Technicals: ATR={signal_data['atr']:.5f}
    - Entry: {signal_data.get('entry', 'N/A')}
    - Stop Loss: {signal_data.get('sl', 'N/A')}
    - Take Profit: {signal_data.get('tp', 'N/A')}
    {corridor_context}
    {macro_context_str}
    
    NEWS CONTEXT:
    {news_context}
    
    REGIME-SPECIFIC GUIDANCE:
    {regime_instruction if regime_instruction else strategy_instruction}
    
    TASK: Validate this trade considering BOTH the news AND the current market timing/regime.
    
    RESPONSE FORMAT (JSON only): {{ "decision": "CONFIRM" | "CANCEL", "reason": "brief explanation mentioning both news and timing" }}
    """
    
    try:
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
                "temperature": 0.0
            })
        )
        content = json.loads(response['body'].read())['content'][0]['text']
        
        # Extract JSON from response
        start = content.find('{')
        end = content.rfind('}') + 1
        if start != -1 and end != -1:
            return json.loads(content[start:end])
            
        return {"decision": "CONFIRM", "reason": "AI response parsing failed, defaulting to confirm"}
        
    except Exception as e:
        logger.error(f"Bedrock Call Error: {e}")
        return {"decision": "CONFIRM", "reason": "Bedrock error"}

# Pour test local
if __name__ == "__main__":
    print(lambda_handler({}, None))
