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

# ==================== CONFIGURATION ====================
CAPITAL_PER_TRADE = float(os.environ.get('CAPITAL', '100'))  # 200€ total / 2 max positions
STOP_LOSS_PCT = float(os.environ.get('STOP_LOSS', '-3.0'))   # -3% Stop Loss
HARD_TP_PCT = float(os.environ.get('HARD_TP', '4.0'))        # +4% Take Profit  
COOLDOWN_HOURS = float(os.environ.get('COOLDOWN_HOURS', '6')) # 6h between trades per pair
MAX_EXPOSURE = int(os.environ.get('MAX_EXPOSURE', '2'))       # Max 2 trades per pair
DYNAMO_TABLE = os.environ.get('DYNAMO_TABLE', 'EmpireForexHistory')
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

def manage_exits(pair, current_price, asset_class='Forex'):
    """Manage Stop Loss and Take Profit for open positions"""
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
            
            if entry_price == 0:
                continue
            
            # Calculate PnL based on direction
            if trade_type in ['LONG', 'BUY']:
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
            else:  # SHORT/SELL
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
            
            pnl_dollars = (pnl_pct / 100) * size
            
            exit_reason = None
            
            # Check Stop Loss
            if pnl_pct <= STOP_LOSS_PCT:
                exit_reason = "STOP_LOSS"
                logger.warning(f"🛑 STOP LOSS HIT for {pair}: {pnl_pct:.2f}%")
                
            # Check Take Profit
            elif pnl_pct >= HARD_TP_PCT:
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
    
    logger.info("🚀 Forex Trader Started")
    
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
                
                # Ask Bedrock
                ai_decision = ask_bedrock(pair, signal, news_context)
                
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
            log_skip_to_dynamo(pair, "NO_SIGNAL: No technical entry trigger", current_price)
            
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
            'AssetClass': 'Forex',
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
        trade_id = f"FOREX-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.utcnow().isoformat()
        
        entry_price = float(signal_data.get('entry', 0))
        
        # Calculate Size (Forex: units based on capital)
        # For Forex, Size represents notional value in base currency
        size = CAPITAL_PER_TRADE  # $200 notional
        
        item = {
            'TradeId': trade_id,
            'Timestamp': timestamp,
            'AssetClass': 'Forex',
            'Pair': signal_data.get('pair'),
            'Type': signal_data.get('signal'), 
            'Strategy': signal_data.get('strategy'),
            'EntryPrice': str(entry_price), 
            'Size': str(size),
            'Cost': str(CAPITAL_PER_TRADE),
            'Value': str(CAPITAL_PER_TRADE),
            'SL': str(signal_data.get('sl')),
            'TP': str(signal_data.get('tp')),
            'ATR': str(signal_data.get('atr')),
            'AI_Decision': signal_data.get('ai_decision'),
            'AI_Reason': signal_data.get('ai_reason'),
            'Status': 'OPEN'
        }
        
        history_table.put_item(Item=item)
        logger.info(f"✅ Trade logged to {DYNAMO_TABLE}: {trade_id} | Size: ${size}")
        
    except Exception as e:
        logger.error(f"❌ Failed to log trade to DynamoDB: {e}")

def ask_bedrock(pair, signal_data, news_context):
    """
    Validates the trade with Claude 3 Haiku using Technicals + News
    """
    prompt = f"""
    You are a professional Forex Risk Manager.
    
    TRADE PROPOSAL:
    - Pair: {pair}
    - Signal: {signal_data['signal']} ({signal_data['strategy']})
    - Technicals: ATR={signal_data['atr']:.5f}
    
    NEWS CONTEXT:
    {news_context}
    
    TASK: Validate this trade.
    - If news is conflicting (e.g. LONG signal but very BEARISH news), return CANCEL.
    - If news is supportive or neutral, return CONFIRM.
    
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
