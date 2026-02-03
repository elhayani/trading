import json
import logging
import os
from config import CONFIGURATION
from strategies import ForexStrategies
from data_loader import DataLoader
from news_fetcher import news_fetcher
import uuid
from datetime import datetime

# Configuration Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
            
        # 3. Check Signal
        signal = ForexStrategies.check_signal(pair, df, config)
        
        if signal:
            logger.info(f"🎯 TECHNICAL SIGNAL: {signal}")
            
            # --- 4. AI VALIDATION (Bedrock) ---
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
                    # --- EXECUTION PLACEHOLDER ---
                    # execute_trade(signal)
                else:
                    logger.info(f"🛑 Trade Cancelled by AI")
                
                if ai_decision['decision'] == 'CONFIRM':
                     log_trade_to_dynamo(signal)
            
            except Exception as e:
                logger.error(f"❌ AI Validation Failed: {e}")
                # Fallback: Add signal anyway if AI fails? Or be safe and skip?
                # Let's skip to be safe in v1
                
        else:
            logger.info(f"➡️ No signal for {pair}")
            
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Analysis complete',
            'signals_found': len(results),
            'details': results
        }, default=str)
    }

# AWS Bedrock Client
import boto3
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
dynamodb_client = boto3.resource('dynamodb', region_name='us-east-1')
history_table = dynamodb_client.Table('EmpireTradesHistory')

def log_trade_to_dynamo(signal_data):
    try:
        trade_id = f"FOREX-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.utcnow().isoformat()
        
        item = {
            'TradeId': trade_id,
            'Timestamp': timestamp,
            'AssetClass': 'Forex',
            'Pair': signal_data.get('pair'),
            'Type': signal_data.get('signal'), 
            'Strategy': signal_data.get('strategy'),
            'EntryPrice': str(signal_data.get('entry')), 
            'SL': str(signal_data.get('sl')),
            'TP': str(signal_data.get('tp')),
            'ATR': str(signal_data.get('atr')),
            'AI_Decision': signal_data.get('ai_decision'),
            'AI_Reason': signal_data.get('ai_reason'),
            'Status': 'OPEN'
        }
        
        history_table.put_item(Item=item)
        logger.info(f"✅ Trade logged to EmpireTradesHistory: {trade_id}")
        
    except Exception as e:
        logger.error(f"❌ Failed to log trade to DynamoDB: {e}")

def ask_bedrock(pair, signal_data, news_context):
    """
    Validates the trade with Claude 3 Haiku using Technicals + News
    """
    prompt = f"""
    You are a professional Forex rk manager.
    
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
