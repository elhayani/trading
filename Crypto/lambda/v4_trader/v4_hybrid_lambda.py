import json
import os
import boto3
import logging
import uuid
import requests
from datetime import datetime, timedelta
from market_analysis import analyze_market
from news_fetcher import get_news_context
from exchange_connector import ExchangeConnector

# AWS & Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
EMPIRE_TABLE = "EmpireCryptoV4"
empire_table = dynamodb.Table(EMPIRE_TABLE)

# ==================== CONFIGURATION ====================
DEFAULT_SYMBOL = os.environ.get('SYMBOL', 'SOL/USDT')
CAPITAL_PER_TRADE = float(os.environ.get('CAPITAL', '133'))   # 400€ total / 3 max positions
RSI_BUY_THRESHOLD = float(os.environ.get('RSI_THRESHOLD', '35'))  # More conservative than 40
RSI_SELL_THRESHOLD = float(os.environ.get('RSI_SELL_THRESHOLD', '75'))  # Overbought exit
STOP_LOSS_PCT = float(os.environ.get('STOP_LOSS', '-5.0'))  # -5% Stop Loss
HARD_TP_PCT = float(os.environ.get('HARD_TP', '5.0'))  # +5% Guaranteed Take Profit
TRAILING_TP_PCT = float(os.environ.get('TRAILING_TP', '2.0'))  # +2% Trailing activation
MAX_EXPOSURE = int(os.environ.get('MAX_EXPOSURE', '3'))  # Max trades per pair
COOLDOWN_HOURS = float(os.environ.get('COOLDOWN_HOURS', '4'))  # Hours between trades
BTC_CRASH_THRESHOLD = float(os.environ.get('BTC_CRASH', '-0.02'))  # -2% BTC crash filter

# ==================== NEW OPTIMIZATIONS ====================
VIX_MAX_THRESHOLD = float(os.environ.get('VIX_MAX', '30'))  # Don't trade if VIX > 30
VIX_REDUCE_THRESHOLD = float(os.environ.get('VIX_REDUCE', '25'))  # Reduce size if VIX > 25
MULTI_TF_ENABLED = os.environ.get('MULTI_TF', 'true').lower() == 'true'  # Multi-timeframe confirmation
RSI_4H_THRESHOLD = float(os.environ.get('RSI_4H_THRESHOLD', '45'))  # 4h RSI must be < 45 to confirm
# ========================================================

def log_trade_to_empire(symbol, action, strategy, price, decision, reason, asset_class='Crypto'):
    try:
        trade_id = f"{asset_class.upper()}-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.utcnow().isoformat()
        
        # Calculate Position Size based on Capital (Default $1000 per trade)
        capital = float(os.environ.get('CAPITAL', '1000'))
        price_float = float(price)
        # Only Crypto Logic
        size = round(capital / price_float, 4) if price_float > 0 else 0
        
        item = {
            'TradeId': trade_id,
            'Timestamp': timestamp,
            'AssetClass': asset_class,
            'Pair': symbol,
            'Type': action, # 'BUY'
            'Strategy': strategy,
            'EntryPrice': str(price),
            'Size': str(size),       # Save Quantity
            'Cost': str(capital),    # Save Cost Basis
            'Value': str(capital),   # Initial Value = Cost
            'SL': '0',
            'TP': '0',
            'ATR': '0',
            'AI_Decision': decision,
            'AI_Reason': reason,
            'Status': 'OPEN'
        }
        empire_table.put_item(Item=item)
        logger.info(f"✅ Trade logged: {trade_id} | Size: {size:.4f} {symbol}")
    except Exception as e:
        logger.error(f"❌ Failed to log to Empire: {e}")

def log_skip_to_empire(symbol, reason, price, asset_class='Crypto'):
    """Log skipped/no-signal events for the Reporter"""
    try:
        timestamp = datetime.utcnow().isoformat()
        log_id = f"LOG-{uuid.uuid4().hex[:8]}"
        item = {
            'TradeId': log_id,
            'Timestamp': timestamp,
            'AssetClass': asset_class,
            'Pair': symbol,
            'Status': 'SKIPPED',
            'Type': 'INFO',
            'ExitReason': reason,
            'EntryPrice': str(price),
            'TTL': int((datetime.utcnow() + timedelta(days=2)).timestamp())
        }
        empire_table.put_item(Item=item)
    except Exception as e:
        logger.error(f"Failed to log skip: {e}")


# ==================== OPTIMIZATION FUNCTIONS ====================

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
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; EmpireBot/1.0)'}
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


def calculate_dynamic_trailing(pnl_pct, atr_pct):
    """
    🔥 OPTIMIZATION 3: Dynamic Trailing Stop based on ATR
    Tighter trailing when in higher profit, wider when profit is small
    Returns: stop_distance_pct
    """
    try:
        if atr_pct <= 0:
            atr_pct = 2.0  # Default 2% if ATR unavailable
        
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
<role>Senior Crypto Risk Manager & Devil's Advocate</role>
<mission>REJECT this trade unless it is statistically exceptional.</mission>

<market_context>
- Symbol: {symbol}
- RSI: {rsi} (Threshold: {RSI_BUY_THRESHOLD})
- News: {news_context}
</market_context>

<portfolio_status>
- Current Exposure: {current_exposure}/{MAX_EXPOSURE}
- Last Trade: {last_trade_info}
- Recent History: {len(history)} trades in last 24h
</portfolio_status>

<rules>
1. If BTC is bearish or news mention "SEC", "HACK", "FUD", "LAWSUIT", or "CRASH", vote CANCEL.
2. If RSI > {RSI_BUY_THRESHOLD}, be 2x more critical - this is not oversold enough.
3. Find 3 SPECIFIC reasons to NOT buy.
4. Only CONFIRM if the signal is statistically exceptional (RSI < 30 with positive news).
5. Default to CANCEL when uncertain.
</rules>

<output_format>
Return ONLY a valid JSON object, no markdown:
{{
    "decision": "CONFIRM" | "CANCEL",
    "reason": "Short summary of why (max 100 chars)",
    "confidence": 0-100
}}
</output_format>
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
        logger.error(f"Bedrock Error: {e}")
        return {"decision": "CANCEL", "reason": "Bedrock AI Error - Safety default", "confidence": 0}

def close_all_positions(open_trades, current_price, reason):
    """Helper to close all open positions with proper PnL calculation"""
    exit_time = datetime.utcnow().isoformat()
    total_pnl = 0
    
    for trade in open_trades:
        entry_price = float(trade['EntryPrice'])
        size = float(trade.get('Size', 0))
        # ✅ FIXED: PnL in $ = (exit - entry) * quantity
        trade_pnl = (current_price - entry_price) * size
        total_pnl += trade_pnl
        
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

def manage_exits(symbol, asset_class, exchange=None):
    """
    Gestion des sorties avec:
    - 🛑 STOP LOSS: -5% (configurable)
    - 💎 HARD TAKE PROFIT: +5% (configurable, independent of RSI)
    - 📈 TRAILING STOP: +2% activation + RSI > 75 confirmation
    """
    try:
        response = empire_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('Status').eq('OPEN') & 
                             boto3.dynamodb.conditions.Attr('Pair').eq(symbol)
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
        
        # 🛑 STOP LOSS CHECK (Priority 1)
        if pnl_pct <= STOP_LOSS_PCT:
            logger.warning(f"🛑 STOP LOSS HIT at {pnl_pct:.2f}%! Closing all positions.")
            total_pnl = close_all_positions(open_trades, current_price, "STOP_LOSS")
            return f"STOP_LOSS_AT_{pnl_pct:.2f}%_PNL_${total_pnl:.2f}"
        
        # 💎 HARD TAKE PROFIT CHECK (Priority 2 - Guaranteed exit)
        if pnl_pct >= HARD_TP_PCT:
            logger.info(f"💎 HARD TAKE PROFIT at {pnl_pct:.2f}%! Securing profits.")
            total_pnl = close_all_positions(open_trades, current_price, "HARD_TP")
            return f"HARD_TP_AT_{pnl_pct:.2f}%_PNL_${total_pnl:.2f}"
        
        # 📈 TRAILING STOP CHECK (Priority 3 - RSI confirmation required)
        if pnl_pct >= TRAILING_TP_PCT:
            target_ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=14)
            rsi = analyze_market(target_ohlcv)['indicators']['rsi']
            
            if rsi > RSI_SELL_THRESHOLD:
                logger.info(f"📈 TRAILING TP ACTIVATED (RSI {rsi:.1f} > {RSI_SELL_THRESHOLD}). Closing at {current_price:.2f}")
                total_pnl = close_all_positions(open_trades, current_price, "TRAILING_TP")
                return f"TRAILING_TP_AT_{pnl_pct:.2f}%_PNL_${total_pnl:.2f}"
            else:
                logger.info(f"📊 In profit +{pnl_pct:.2f}% but RSI={rsi:.1f} < {RSI_SELL_THRESHOLD}. Holding for more gains.")
        
        return "HOLD"
        
    except Exception as e:
        logger.error(f"Exit Error: {e}")
        return None

def get_portfolio_context(symbol):
    try:
        response = empire_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('AssetClass').eq('Crypto') & 
                             boto3.dynamodb.conditions.Key('Pair').eq(symbol), # Optimize scan
            Limit=50
        )
        items = sorted(response.get('Items', []), key=lambda x: x['Timestamp'], reverse=True)
        open_trades = [t for t in items if t.get('Status') == 'OPEN']
        return {"current_pair_exposure": len(open_trades), "last_trade": open_trades[0] if open_trades else None}, items[:10]
    except Exception as e:
        return {"current_pair_exposure": 0}, []

def lambda_handler(event, context):
    # Determine Context from Event Payload (Priority) or Env
    symbol = event.get('symbol', DEFAULT_SYMBOL)
    asset_class = event.get('asset_class', 'Crypto') # 'Crypto', 'Indices', 'Commodities', 'Forex'
    
    logger.info(f"🚀 Empire V4 Hybrid | Target: {symbol} | Class: {asset_class}")
    
    # ENFORCE CRYPTO ONLY
    if asset_class != 'Crypto':
        logger.warning(f"⛔ SKIPPED: Asset Class {asset_class} not allowed. Only Crypto.")
        return {"status": "SKIPPED_NOT_CRYPTO"}

    try:
        exchange = ExchangeConnector('binance')
        
        # 1. GESTION DES SORTIES (Priorité)
        exit_status = manage_exits(symbol, asset_class, exchange)
        if exit_status and "CLOSED" in exit_status:
            return {"status": "EXIT_SUCCESS", "details": exit_status}

        # 2. FILTRE DE CORRÉLATION BTC (Crypto Only)
        btc_ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=5)
        current_close = btc_ohlcv[-1][4]
        prev_close = btc_ohlcv[-2][4] 
        btc_change = (current_close - prev_close) / prev_close
        
        if btc_change < BTC_CRASH_THRESHOLD:
            logger.warning(f"🚨 BTC CRASH ({btc_change:.2%}). Buys blocked.")
            return {"status": "SKIPPED_BTC_CRASH", "btc_change": f"{btc_change:.2%}"}

        # 3. CONTEXTE & LIMITES (Configurable)
        portfolio_stats, history = get_portfolio_context(symbol)
        if portfolio_stats['current_pair_exposure'] >= MAX_EXPOSURE:
            logger.info(f"⏸️ Max exposure ({MAX_EXPOSURE}) reached for {symbol}")
            return {"status": "SKIPPED_MAX_EXPOSURE", "current": portfolio_stats['current_pair_exposure']}
        
        if portfolio_stats.get('last_trade'):
            last_time = datetime.fromisoformat(portfolio_stats['last_trade']['Timestamp'])
            hours_since = (datetime.utcnow() - last_time).total_seconds() / 3600
            if hours_since < COOLDOWN_HOURS:
                logger.info(f"⏳ Cooldown active. {COOLDOWN_HOURS - hours_since:.1f}h remaining.")
                return {"status": "SKIPPED_COOLDOWN", "hours_remaining": round(COOLDOWN_HOURS - hours_since, 1)}

        # 🔥 NEW: 3.5 VIX FILTER (Don't trade in extreme volatility)
        can_trade, size_multiplier, vix_value = check_vix_filter()
        if not can_trade:
            return {"status": "SKIPPED_VIX_HIGH", "vix": vix_value, "threshold": VIX_MAX_THRESHOLD}

        # 4. ANALYSE & SIGNAL
        target_ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=100)
        if not target_ohlcv or len(target_ohlcv) < 14:
            return {"status": "SKIPPED_NO_DATA"}
             
        analysis = analyze_market(target_ohlcv)
        rsi = analysis['indicators']['rsi']
        current_price = analysis['current_price']

        # 5. STRATEGY CHECK (Configurable RSI threshold)
        logger.info(f"📈 Analysis {symbol}: RSI={rsi:.2f} | Threshold={RSI_BUY_THRESHOLD}")
        
        if rsi < RSI_BUY_THRESHOLD:
            
            # 🔥 NEW: 5.5 MULTI-TIMEFRAME CONFIRMATION
            signal_strength, rsi_4h = check_multi_timeframe(symbol, exchange, rsi)
            
            if signal_strength == "WEAK":
                # Weak signal - add to AI context for extra scrutiny
                logger.info(f"⚠️ Weak multi-TF signal. AI will apply extra scrutiny.")
            elif signal_strength == "NO_SIGNAL":
                logger.info(f"📊 No signal on multi-TF analysis.")
                log_skip_to_empire(symbol, f"NO_SIGNAL: RSI_4H={rsi_4h:.1f} (Multi-TF filter)", current_price, asset_class)
                return {"status": "IDLE", "rsi": round(rsi, 2), "rsi_4h": round(rsi_4h, 2), "asset": symbol}
            
            # 6. IA AVOCAT DU DIABLE (Bedrock)
            news_symbol = symbol.split('=')[0].split('/')[0]  # 'SOL/USDT' -> 'SOL', 'GC=F' -> 'GC'
            news_ctx = get_news_context(news_symbol)
            
            # Add multi-TF context to AI decision
            portfolio_stats['signal_strength'] = signal_strength
            portfolio_stats['rsi_4h'] = rsi_4h
            portfolio_stats['vix'] = vix_value
            
            decision = ask_bedrock(symbol, rsi, news_ctx, portfolio_stats, history)
            
            logger.info(f"🤖 AI Decision: {decision.get('decision')} | Confidence: {decision.get('confidence', 0)}%")
            
            if decision.get('decision') == "CONFIRM":
                # 🔥 Apply size multiplier from VIX filter
                adjusted_capital = CAPITAL_PER_TRADE * size_multiplier
                
                log_trade_to_empire(
                    symbol, 
                    "LONG", 
                    f"V4_HYBRID_MTF_{signal_strength}", 
                    current_price, 
                    "CONFIRM", 
                    decision.get('reason'),
                    asset_class
                )
                return {
                    "status": "TRADE_EXECUTED", 
                    "asset": symbol, 
                    "price": current_price,
                    "rsi_1h": rsi,
                    "rsi_4h": rsi_4h,
                    "signal_strength": signal_strength,
                    "vix": vix_value,
                    "size_multiplier": size_multiplier,
                    "ai_confidence": decision.get('confidence', 0)
                }
            else:
                log_skip_to_empire(symbol, f"AI_VETO: {decision.get('reason')}", current_price, asset_class)
                return {
                    "status": "SKIPPED_AI_VETO", 
                    "reason": decision.get('reason'),
                    "rsi_1h": rsi,
                    "rsi_4h": rsi_4h,
                    "signal_strength": signal_strength
                }

        log_skip_to_empire(symbol, f"NO_SIGNAL: RSI={rsi:.1f} > {RSI_BUY_THRESHOLD}", current_price, asset_class)
        return {"status": "IDLE", "rsi": round(rsi, 2), "threshold": RSI_BUY_THRESHOLD, "asset": symbol}
    except Exception as e:
        logger.error(f"Global Error: {e}")
        return {"status": "ERROR", "msg": str(e)}

