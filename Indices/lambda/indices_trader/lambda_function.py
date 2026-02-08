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
CAPITAL_PER_TRADE = float(os.environ.get('CAPITAL', '2000')) # Default: 2000 per position (0.5% Risk)
STOP_LOSS_PCT = float(os.environ.get('STOP_LOSS', '-4.0'))   # -4% Stop Loss (Indices are volatile)
HARD_TP_PCT = float(os.environ.get('HARD_TP', '5.0'))        # +5% Take Profit  
COOLDOWN_HOURS = float(os.environ.get('COOLDOWN_HOURS', '2')) # OPTIMIZED V5.8: 2h (Was 4h) for re-entries
MAX_EXPOSURE = int(os.environ.get('MAX_EXPOSURE', '5'))       # OPTIMIZED V5.9: 5 simultaneous trades
DYNAMO_TABLE = os.environ.get('DYNAMO_TABLE', 'EmpireIndicesHistory')
# ========================================================

# AWS Clients
dynamodb_client = boto3.resource('dynamodb')
history_table = dynamodb_client.Table(DYNAMO_TABLE)
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

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
        
        sorted_trades = sorted(all_trades, key=lambda x: x.get('Timestamp', ''), reverse=True)
        last_trade = sorted_trades[0] if sorted_trades else None
        
        return {
            'exposure': len(open_trades),
            'last_trade': last_trade,
            'open_trades': open_trades
        }
    except Exception as e:
        logger.error(f"Portfolio context error: {e}")
        return {'exposure': 0, 'last_trade': None, 'open_trades': []}

def manage_exits(pair, current_price, asset_class='Indices'):
    """
    Manage Stop Loss, Take Profit, and V6.0 Trailing Stop for open positions
    Priority: 1) Stop Loss 2) Trailing Stop 3) Hard Take Profit
    """
    try:
        context = get_portfolio_context(pair)
        open_trades = context.get('open_trades', [])
        
        if not open_trades:
            return None
            
        exit_time = datetime.utcnow().isoformat()
        closed_count = 0
        total_pnl = 0
        
        for trade in open_trades:
            entry_price = float(trade.get('EntryPrice', 0))
            trade_type = trade.get('Type', 'LONG').upper()
            size = float(trade.get('Size', CAPITAL_PER_TRADE))
            current_sl = float(trade.get('SL', entry_price * (1 + STOP_LOSS_PCT/100)))
            
            # Defensive check
            if trade.get('Status') != 'OPEN':
                continue
            
            if entry_price == 0:
                continue
            
            # Calculate PnL based on direction
            if trade_type in ['LONG', 'BUY']:
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
            else:  # SHORT/SELL
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
            
            pnl_dollars = (pnl_pct / 100) * size
            
            exit_reason = None
            
            # Priority 1: Check Stop Loss
            if pnl_pct <= STOP_LOSS_PCT:
                exit_reason = "STOP_LOSS"
                logger.warning(f"🛑 STOP LOSS HIT for {pair}: {pnl_pct:.2f}%")
            
            # Priority 2: V6.0 Trailing Stop Check
            elif TRAILING_STOP_AVAILABLE and pnl_pct > 0:
                peak_price = float(trade.get('PeakPrice', entry_price))
                atr = float(trade.get('ATR', 0)) if trade.get('ATR') else None
                
                trailing_result = check_trailing_stop(
                    entry_price=entry_price,
                    current_price=current_price,
                    trade_type=trade_type,
                    current_sl=current_sl,
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
                    history_table.update_item(
                        Key={'TradeId': trade['TradeId']},
                        UpdateExpression="set SL = :sl",
                        ExpressionAttributeValues={':sl': str(trailing_result['new_sl'])}
                    )
                    logger.info(f"📈 {trailing_result['mode']}: Updated SL to {trailing_result['new_sl']:.5f}")
                
                # Check if trailing stop triggered exit
                if trailing_result['triggered']:
                    exit_reason = f"TRAILING_{trailing_result['mode']}"
                    logger.info(f"📈 TRAILING STOP triggered for {pair}: {pnl_pct:.2f}%")
            
            # Priority 3: Check Hard Take Profit
            if exit_reason is None and pnl_pct >= HARD_TP_PCT:
                exit_reason = "TAKE_PROFIT"
                logger.info(f"💎 TAKE PROFIT HIT for {pair}: {pnl_pct:.2f}%")
            
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
    
    logger.info("🚀 Indices Trader V5.1 Started")
    
    # --- 🏛️ MACRO CONTEXT (Global Check) ---
    macro_data = None
    if MACRO_CONTEXT_AVAILABLE:
        try:
            macro_data = get_macro_context()
            logger.info(f"🏛️ V5.1 MACRO: Regime={macro_data['regime']} | Yield10Y={macro_data['yields']['value']}% | VIX={macro_data['vix']['level']}")
            
            # 🛑 GLOBAL KILL SWITCH (Danger Regime)
            if not macro_data['can_trade']:
                logger.warning(f"🛑 TRADING HALTED by Macro Regime: {macro_data['regime']}")
                return {
                    'statusCode': 200,
                    'body': json.dumps({'message': 'Trading Halted (Macro Condition)', 'regime': macro_data['regime']})
                }
        except Exception as e:
            logger.error(f"❌ Macro Context Failed: {e}")
    
    results = []
    
    for pair, config in CONFIGURATION.items():
        if not config['enabled']:
            continue
            
        logger.info(f"🔍 Analyzing {pair} with {config['strategy']}...")
        
        # 1. Fetch Data
        df = DataLoader.get_latest_data(pair)
        if df is None or len(df) < 201:
            logger.warning(f"⚠️ Not enough data for {pair}")
            continue

        # --- 🛡️ V5.1 PREDICTABILITY CHECK ---
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
                
                # 🚫 QUARANTINE LOGIC (INDICES SPECIFIC)
                # Nasdaq/SPX are noisier than Crypto. We lower the threshold (15 vs 25).
                INDICES_MIN_SCORE = 15
                
                if predictability['score'] < INDICES_MIN_SCORE:
                    # EXCEPTION 1: VIX > 30 (Panic Selling = Opportunity for Indices)
                    if macro_data and macro_data['vix']['value'] > 30:
                        logger.warning(f"⚠️ {pair} Very Erratic ({predictability['score']}) but VIX High -> ALLOWED (Size x0.5)")
                        predictability['multiplier'] = 0.5
                    else:
                        logger.warning(f"🛑 {pair} QUARANTINED (Score {predictability['score']} < {INDICES_MIN_SCORE})")
                        log_skip_to_dynamo(pair, f"QUARANTINE_ERRATIC_{predictability['grade']}", df.iloc[-1]['close'])
                        continue
                
                elif not predictability['should_trade']:
                    # Score between 15 and 25 (Marked ERRATIC by standard module but OK for Indices)
                    logger.info(f"ℹ️ {pair} Low Stability ({predictability['score']}) -> ALLOWED for Indices (Range 15-25)")
                    # Slight penalty for low score
                    predictability['multiplier'] = min(predictability.get('multiplier', 1.0), 0.8)
                    
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
            
        # 3. Manage Exits First (Priority)
        current_price = df.iloc[-1]['close']
        exit_result = manage_exits(pair, current_price)
        if exit_result and "CLOSED" in str(exit_result):
            logger.info(f"📤 Exit executed for {pair}: {exit_result}")
            results.append({'pair': pair, 'action': 'EXIT', 'result': exit_result})
            continue
        
        # 4. Check Cooldown & Exposure
        portfolio = get_portfolio_context(pair)
        
        if portfolio['exposure'] >= MAX_EXPOSURE:
            logger.info(f"⏸️ Max exposure ({MAX_EXPOSURE}) reached for {pair}")
            continue
            
        if portfolio.get('last_trade'):
            last_time = datetime.fromisoformat(portfolio['last_trade']['Timestamp'])
            hours_since = (datetime.utcnow() - last_time).total_seconds() / 3600
            if hours_since < COOLDOWN_HOURS:
                logger.info(f"⏳ Cooldown active for {pair}. {COOLDOWN_HOURS - hours_since:.1f}h remaining.")
                continue
        
        # 5. Check Signal
        signal = ForexStrategies.check_signal(pair, df, config)
        
        if signal:
            logger.info(f"🎯 TECHNICAL SIGNAL: {signal}")
            
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
                    # --- V5.9 SIZING DÉGRESSIF (Risk Management) ---
                    # Si on a déjà 3 positions ou plus, on réduit la taille de 50%
                    current_exposure = portfolio['exposure']
                    trade_allocation = CAPITAL_PER_TRADE
                    
                    if current_exposure >= 3:
                        trade_allocation *= 0.5
                        logger.info(f"⚠️ High Exposure ({current_exposure}): Sizing reduced to ${trade_allocation} (50%)")
                    
                    # Injecter la taille ajustée (Coût en $)
                    signal['cost'] = trade_allocation
                    # Recalculer la quantité en unités (Size = Allocation / Entry Price)
                    entry_p = float(signal.get('entry', df.iloc[-1]['close']))
                    if entry_p > 0:
                        signal['size'] = trade_allocation / entry_p
                    
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
        timestamp = datetime.utcnow().isoformat()
        log_id = f"LOG-{uuid.uuid4().hex[:8]}"
        item = {
            'TradeId': log_id,
            'Timestamp': timestamp,
            'AssetClass': 'Indices',
            'Pair': pair,
            'Status': 'SKIPPED',
            'Type': 'INFO',
            'ExitReason': reason,
            'EntryPrice': str(current_price),
            'TTL': int((datetime.utcnow() + timedelta(days=2)).timestamp())
        }
        history_table.put_item(Item=item)
    except Exception as e:
        logger.error(f"Failed to log skip: {e}")

def log_trade_to_dynamo(signal_data):
    """Log trade to DynamoDB with Size and Cost calculations"""
    try:
        trade_id = f"INDICES-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.utcnow().isoformat()
        
        entry_price = float(signal_data.get('entry', 0))
        size = CAPITAL_PER_TRADE  # Notional value
        
        # --- V5.1: Position Sizing Logique Manquante dans log_trade_to_dynamo du code original ---
        # On va chercher les valeurs passées dans signal_data si available (calculées avant)
        # Sinon fallback sur CAPITAL_PER_TRADE
        cost = float(signal_data.get('cost', CAPITAL_PER_TRADE))
        size_units = float(signal_data.get('size', 0))
        
        item = {
            'TradeId': trade_id,
            'Timestamp': timestamp,
            'AssetClass': 'Indices',
            'Pair': signal_data.get('pair'),
            'Type': signal_data.get('signal'),
            'Strategy': signal_data.get('strategy'),
            'EntryPrice': str(entry_price), 
            'Size': str(size_units),
            'Cost': str(cost),
            'Value': str(cost),
            'SL': str(signal_data.get('sl')),
            'TP': str(signal_data.get('tp')),
            'ATR': str(signal_data.get('atr')),
            'AI_Decision': signal_data.get('ai_decision'),
            'AI_Reason': signal_data.get('ai_reason'),
            'Status': 'OPEN',
            # V5.1 fields
            'Regime': signal_data.get('regime', 'STANDARD'),
            'CompoundMode': str(signal_data.get('compound_mode', False))
        }
        
        history_table.put_item(Item=item)
        logger.info(f"✅ Trade logged to {DYNAMO_TABLE}: {trade_id} | Size: ${size}")
        
    except Exception as e:
        logger.error(f"❌ Failed to log trade to DynamoDB: {e}")

def ask_bedrock(pair, signal_data, news_context, macro_data=None):
    """
    Validates the trade with Claude 3 Haiku using Technicals + News
    """
    # Define strategy-specific instructions
    strategy_instruction = "If news is conflicting (e.g. LONG signal but very BEARISH news), return CANCEL. If news is supportive or neutral, return CONFIRM."
    
    # Custom instruction for Momentum/Breakout (Nasdaq) - Don't block momentum easily
    if 'BOLLINGER_BREAKOUT' in signal_data.get('strategy', ''):
         strategy_instruction = "This is a MOMENTUM trade (High Volatility). Speed is critical. Only CANCEL if the news is EXTREMELY contradictory (e.g. Rate Hike for a Long). If news is just noise or mildly negative, CONFIRM to capture the momentum."

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
    
    # V5.1 Micro Corridor Context Integration (Manquant dans V5 simple)
    corridor_context = ""
    if MICRO_CORRIDORS_AVAILABLE:
        try:
            params = get_adaptive_params(pair)
            corridor_context = f"""
    MARKET TIMING:
    - Corridor: {params.get('corridor_name', 'Default')}
    - Regime: {params.get('regime', 'STANDARD')}
    - Aggressiveness: {params.get('aggressiveness', 'MEDIUM')}
    """
        except Exception: 
            pass

    prompt = f"""
    You are a professional Indices Risk Manager.
    
    TRADE PROPOSAL:
    - Pair: {pair}
    - Signal: {signal_data['signal']} ({signal_data['strategy']})
    - Technicals: ATR={signal_data['atr']:.5f}
    
    NEWS CONTEXT:
    {news_context}
    
    TASK: Validate this trade.
    {corridor_context}
    {macro_context_str}
    {strategy_instruction}
    
    RESPONSE FORMAT JSON: {{ "decision": "CONFIRM" | "CANCEL", "reason": "short explanation" }}
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
