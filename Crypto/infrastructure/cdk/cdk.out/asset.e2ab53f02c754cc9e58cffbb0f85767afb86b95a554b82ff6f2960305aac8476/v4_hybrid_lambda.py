import json
import os
import boto3
import logging
from datetime import datetime
from market_analysis import analyze_market
from news_fetcher import get_news_context, NewsFetcher
from exchange_connector import ExchangeConnector

# Setup Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS Clients
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
events = boto3.client('events')

# Config
TRADING_MODE = os.environ.get('TRADING_MODE', 'test')
TABLE_NAME = os.environ.get('STATE_TABLE', 'V4TradingState')
HISTORY_TABLE = os.environ.get('HISTORY_TABLE', 'V4TradeHistory')
SYMBOL = os.environ.get('SYMBOL', 'SOL/USDT')

def ask_bedrock(symbol, technical_context, news_context, regime):
    """
    Query Bedrock (Claude 3 Haiku) for trading decision.
    """
    prompt = f"""
    You are an expert Crypto Risk Manager (V4 Hybrid System).
    
    CONTEXT:
    Date: {datetime.now().isoformat()}
    Symbol: {symbol}
    Market Regime: {regime}
    
    TECHNICAL ANALYSIS:
    {technical_context}
    
    NEWS CONTEXT:
    {news_context}
    
    TASK:
    Analyze the above and provide a trading decision.
    
    RULES:
    1. If Regime is EXTREME_BEAR, only buy if capitulation detected (RSI < 25) AND News is Positive.
    2. If Regime is BULL, be aggressive but watch for fakeouts.
    3. If Technicals conflict with News, prioritize Capital Preservation (CANCEL).
    
    OUTPUT FORMAT (JSON ONLY):
    {{
        "decision": "CONFIRM" | "CANCEL",
        "reason": "Short explanation",
        "confidence": 0-100
    }}
    """
    
    try:
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
            })
        )
        
        result = json.loads(response['body'].read())
        completion = result['content'][0]['text']
        
        # Extract JSON from response
        if "```json" in completion:
            completion = completion.split("```json")[1].split("```")[0].strip()
            
        return json.loads(completion)
        
    except Exception as e:
        logger.error(f"Bedrock Error: {e}")
        return {"decision": "CANCEL", "reason": "Bedrock AI Error", "confidence": 0}

def lambda_handler(event, context):
    """
    Main Lambda Handler for V4 Hybrid Logic
    """
    logger.info(f"V4 Hybrid Triggered. Mode: {TRADING_MODE}")
    
    try:
        # 1. Initialize Exchange
        exchange = ExchangeConnector('binance')
        
        # 2. Fetch Data
        btc_ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=168) # 7 days
        target_ohlcv = exchange.fetch_ohlcv(SYMBOL, '1h', limit=100)
        
        # 3. Detect Regime (Simplified for Lambda)
        btc_perf_7d = (btc_ohlcv[-1][4] - btc_ohlcv[0][4]) / btc_ohlcv[0][4]
        regime = "NORMAL"
        if btc_perf_7d < -0.15: regime = "BEAR"
        if btc_perf_7d < -0.30: regime = "EXTREME_BEAR"
        if btc_perf_7d > 0.10: regime = "BULL"
        
        logger.info(f"Market Regime Detected: {regime} (BTC 7d: {btc_perf_7d:.2%})")
        
        # 4. Analyze Target
        analysis = analyze_market(target_ohlcv)
        rsi = analysis['indicators']['rsi']
        
        logger.info(f"Analysis for {SYMBOL}: RSI={rsi:.2f}")
        
        # 5. Check Triggers (Hybrid Logic V1+V3)
        signal = False
        
        # V3 Smart Logic (Default)
        if regime in ['BULL', 'NORMAL']:
            if rsi < 45: # Dip buy
                signal = True
        
        # V1 Strict Logic (Bear)
        elif regime in ['BEAR', 'EXTREME_BEAR']:
            if rsi < 25: # Deep oversold only
                signal = True
                
        if not signal:
            logger.info("No signal generated.")
            return {"status": "NO_SIGNAL"}
            
        # 6. AI Validation
        news_ctx = get_news_context(SYMBOL)
        tech_ctx = f"RSI: {rsi}, Price: {analysis['current_price']}"
        
        ai_decision = ask_bedrock(SYMBOL, tech_ctx, news_ctx, regime)
        logger.info(f"AI Decision: {ai_decision}")
        
        if ai_decision.get("decision") == "CONFIRM":
            # Execute Trade (Placeholder for live execution)
            logger.info(f"TRADE EXECUTED: BUY {SYMBOL}")
            
            # Log to DynamoDB
            # ...
            return {"status": "TRADE_EXECUTED", "details": ai_decision}
        else:
            logger.info("Trade Cancelled by AI.")
            return {"status": "AI_CANCELLED", "reason": ai_decision.get("reason")}
            
    except Exception as e:
        logger.error(f"Lambda Error: {e}")
        return {"status": "ERROR", "error": str(e)}
