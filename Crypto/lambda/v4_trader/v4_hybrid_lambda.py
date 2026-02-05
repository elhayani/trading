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
RSI_BUY_THRESHOLD = float(os.environ.get('RSI_THRESHOLD', '40'))  # Increased to 40 (AI Validated)
RSI_SELL_THRESHOLD = float(os.environ.get('RSI_SELL_THRESHOLD', '75'))  # Overbought exit
STOP_LOSS_PCT = float(os.environ.get('STOP_LOSS', '-5.0'))  # -5% Stop Loss
HARD_TP_PCT = float(os.environ.get('HARD_TP', '5.0'))  # +5% Guaranteed Take Profit
TRAILING_TP_PCT = float(os.environ.get('TRAILING_TP', '2.0'))  # +2% Trailing activation
MAX_EXPOSURE = int(os.environ.get('MAX_EXPOSURE', '3'))  # Max trades per pair
COOLDOWN_HOURS = float(os.environ.get('COOLDOWN_HOURS', '4'))  # Hours between trades
BTC_CRASH_THRESHOLD = float(os.environ.get('BTC_CRASH', '-0.07'))  # -7% BTC crash filter (V4 Fortress Balanced)

# ==================== NEW OPTIMIZATIONS ====================
VIX_MAX_THRESHOLD = float(os.environ.get('VIX_MAX', '30'))  # Don't trade if VIX > 30
VIX_REDUCE_THRESHOLD = float(os.environ.get('VIX_REDUCE', '25'))  # Reduce size if VIX > 25
MULTI_TF_ENABLED = os.environ.get('MULTI_TF', 'true').lower() == 'true'  # Multi-timeframe confirmation
RSI_4H_THRESHOLD = float(os.environ.get('RSI_4H_THRESHOLD', '45'))  # 4h RSI must be < 45 to confirm

# 🔥 CIRCUIT BREAKER (Leçon 2022 - Protection Anti-Crash à 3 Niveaux)
CIRCUIT_BREAKER_L1 = float(os.environ.get('CB_L1', '-0.05'))  # -5% BTC 24h = Reduce size 50%
CIRCUIT_BREAKER_L2 = float(os.environ.get('CB_L2', '-0.10'))  # -10% BTC 24h = FULL STOP 48h
CIRCUIT_BREAKER_L3 = float(os.environ.get('CB_L3', '-0.20'))  # -20% BTC 7d = SURVIVAL MODE
CB_COOLDOWN_HOURS = float(os.environ.get('CB_COOLDOWN', '48'))  # Hours of trading pause after L2

# 🎯 SOL TURBO MODE (Capture Volatilité 2025)
SOL_TRAILING_ACTIVATION = float(os.environ.get('SOL_TRAILING_ACT', '10.0'))  # +10% = activate trailing
SOL_TRAILING_STOP = float(os.environ.get('SOL_TRAILING_STOP', '3.0'))  # -3% trailing from peak
VOLUME_CONFIRMATION = float(os.environ.get('VOL_CONFIRM', '1.5'))  # Volume must be > 1.5x avg

# 🚀 V5 ADVANCED OPTIMIZATIONS
MOMENTUM_FILTER_ENABLED = os.environ.get('MOMENTUM_FILTER', 'true').lower() == 'true'
DYNAMIC_SIZING_ENABLED = os.environ.get('DYNAMIC_SIZING', 'true').lower() == 'true'
CORRELATION_CHECK_ENABLED = os.environ.get('CORRELATION_CHECK', 'true').lower() == 'true'
REVERSAL_TRIGGER_ENABLED = os.environ.get('REVERSAL_TRIGGER', 'true').lower() == 'true' # 🟢 NEW: Green Candle Check
MAX_CRYPTO_EXPOSURE = int(os.environ.get('MAX_CRYPTO_EXPOSURE', '2'))  # Max crypto trades when correlated
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
        if len(btc_ohlcv_24h) >= 25:
            btc_now = btc_ohlcv_24h[-1][4]
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


def check_volume_confirmation(ohlcv_data):
    """
    🎯 Volume Confirmation Filter (SOL Turbo Mode)
    Only buy if current volume > 1.5x average (avoid false signals in low liquidity)
    Returns: (confirmed: bool, vol_ratio: float)
    """
    try:
        if len(ohlcv_data) < 20:
            return True, 1.0  # Not enough data, allow
        
        volumes = [c[5] for c in ohlcv_data[-20:]]
        avg_vol = sum(volumes[:-1]) / len(volumes[:-1])  # Exclude current
        current_vol = volumes[-1]
        
        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
        
        if vol_ratio >= VOLUME_CONFIRMATION:
            logger.info(f"✅ Volume Confirmed: {vol_ratio:.2f}x average")
            return True, vol_ratio
        else:
            logger.info(f"⚠️ Low Volume: {vol_ratio:.2f}x average (need {VOLUME_CONFIRMATION}x)")
            return False, vol_ratio
            
    except Exception as e:
        logger.error(f"Volume check error: {e}")
        return True, 1.0


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

def check_momentum_filter(ohlcv_data):
    """
    🚀 V5 OPTIMIZATION 1: Momentum Filter (EMA Cross)
    Only buy when EMA 20 > EMA 50 (confirmed uptrend)
    Avoids dead cat bounces and bear market rallies
    Returns: (is_bullish: bool, trend: str, ema_diff_pct: float)
    """
    if not MOMENTUM_FILTER_ENABLED:
        return True, "DISABLED", 0
    
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
        # Get all open crypto trades
        response = empire_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('Status').eq('OPEN') & 
                           boto3.dynamodb.conditions.Attr('AssetClass').eq('Crypto')
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


def calculate_dynamic_position_size(base_capital, rsi, signal_strength, vol_ratio, momentum_trend):
    """
    🚀 V5 OPTIMIZATION 3: Dynamic Position Sizing
    Increases size on high-confidence signals, reduces on weak signals
    Based on simplified Kelly Criterion
    Returns: (adjusted_capital: float, confidence_score: float)
    """
    if not DYNAMIC_SIZING_ENABLED:
        return base_capital, 1.0
    
    confidence_score = 1.0
    
    # RSI Quality Bonus
    if rsi < 25:
        confidence_score += 0.30  # Extreme oversold = strong signal
        logger.info(f"🎯 RSI Bonus +30%: Extreme oversold ({rsi:.1f})")
    elif rsi < 30:
        confidence_score += 0.15
        logger.info(f"🎯 RSI Bonus +15%: Very oversold ({rsi:.1f})")
    elif rsi > 38:
        confidence_score -= 0.10  # Near threshold = weaker signal
    
    # Volume Confirmation Bonus
    if vol_ratio >= 2.0:
        confidence_score += 0.20
        logger.info(f"🎯 Volume Bonus +20%: Strong volume ({vol_ratio:.1f}x)")
    elif vol_ratio >= 1.75:
        confidence_score += 0.10
    
    # Multi-TF Signal Strength Bonus
    if signal_strength == "STRONG":
        confidence_score += 0.25
        logger.info(f"🎯 Multi-TF Bonus +25%: STRONG signal")
    elif signal_strength == "WEAK":
        confidence_score -= 0.15
    
    # Momentum Trend Bonus
    if momentum_trend == "BULLISH":
        confidence_score += 0.15
        logger.info(f"🎯 Momentum Bonus +15%: BULLISH trend")
    elif momentum_trend == "BEARISH":
        confidence_score -= 0.25  # Strong penalty for counter-trend
    
    # Cap between 0.5x and 1.5x
    confidence_score = max(0.5, min(confidence_score, 1.5))
    
    adjusted_capital = base_capital * confidence_score
    logger.info(f"💰 Dynamic Sizing: {base_capital:.0f}$ × {confidence_score:.2f} = {adjusted_capital:.0f}$")
    
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



def check_reversal_pattern(ohlcv_data):
    """
    🚀 OPTIMIZATION FINAL: Reversal Trigger
    Only buy if the last candle is GREEN (Close > Open) or Neutral
    Prevents catching falling knives during active crashes.
    Returns: (is_reversal: bool, reason: str)
    """
    if not REVERSAL_TRIGGER_ENABLED:
        return True, "DISABLED"
    
    try:
        current_candle = ohlcv_data[-1]
        open_p = current_candle[1]
        close_p = current_candle[4]
        
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
        
        # � SOL TURBO TRAILING (Priority 2.5 - For high-momentum SOL trades)
        if 'SOL' in symbol and pnl_pct >= SOL_TRAILING_ACTIVATION:
            # Track peak profit and apply trailing stop
            # Store peak in trade metadata if not exists
            for trade in open_trades:
                peak_pnl = float(trade.get('PeakPnL', pnl_pct))
                if pnl_pct > peak_pnl:
                    # Update peak
                    empire_table.update_item(
                        Key={'TradeId': trade['TradeId']},
                        UpdateExpression="set PeakPnL = :p",
                        ExpressionAttributeValues={':p': str(pnl_pct)}
                    )
                    peak_pnl = pnl_pct
                
                # Check if we've fallen from peak by trailing amount
                trailing_trigger = peak_pnl - SOL_TRAILING_STOP
                if pnl_pct <= trailing_trigger and trailing_trigger > 0:
                    logger.info(f"🚀 SOL TURBO TRAILING triggered! Peak: +{peak_pnl:.2f}% | Current: +{pnl_pct:.2f}%")
                    total_pnl = close_all_positions(open_trades, current_price, "SOL_TURBO_TRAILING")
                    return f"SOL_TURBO_TRAILING_AT_{pnl_pct:.2f}%_PNL_${total_pnl:.2f}"
            
            logger.info(f"🚀 SOL in Turbo Zone +{pnl_pct:.2f}%. Trailing active, riding the wave...")
        
        # �📈 TRAILING STOP CHECK (Priority 3 - RSI confirmation required)
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

        # 2. 🛡️ CIRCUIT BREAKER CHECK (Leçon 2022 - 3 niveaux)
        cb_can_trade, cb_size_mult, cb_level, btc_24h, btc_7d = check_circuit_breaker(exchange)
        
        if not cb_can_trade:
            if cb_level == "L3_SURVIVAL":
                # TODO: Implement auto-liquidation of SOL positions in survival mode
                logger.critical(f"🚨 SURVIVAL MODE - Consider liquidating risky positions!")
            return {
                "status": f"BLOCKED_CIRCUIT_BREAKER_{cb_level}", 
                "btc_24h": f"{btc_24h:.2%}",
                "btc_7d": f"{btc_7d:.2%}"
            }
        
        # 2.5 FILTRE DE CORRÉLATION BTC (Crash horaire)
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

        # 5. 🎯 DYNAMIC RSI THRESHOLD (based on market regime) - V4 Fortress Balanced
        dynamic_rsi_threshold, market_regime = get_dynamic_rsi_threshold(cb_level, btc_7d, symbol)
        logger.info(f"📈 Analysis {symbol}: RSI={rsi:.2f} | Dynamic Threshold={dynamic_rsi_threshold} ({market_regime})")
        
        if rsi < dynamic_rsi_threshold:
            
            # 5.1 VOLUME CONFIRMATION (SOL Turbo Mode)
            vol_confirmed, vol_ratio = check_volume_confirmation(target_ohlcv)
            if not vol_confirmed:
                log_skip_to_empire(symbol, f"LOW_VOLUME: {vol_ratio:.2f}x (need {VOLUME_CONFIRMATION}x)", current_price, asset_class)
                return {"status": "SKIPPED_LOW_VOLUME", "vol_ratio": round(vol_ratio, 2), "rsi": round(rsi, 2)}
            
            # 5.2 🚀 REVERSAL TRIGGER (Final Optimization)
            reversal_ok, reversal_reason = check_reversal_pattern(target_ohlcv)
            if not reversal_ok:
                logger.info(f"🔪 Falling Knife blocked: {reversal_reason}")
                return {"status": "SKIPPED_FALLING_KNIFE", "reason": reversal_reason, "rsi": round(rsi, 2)}
            
            # 5.5 MULTI-TIMEFRAME CONFIRMATION
            signal_strength, rsi_4h = check_multi_timeframe(symbol, exchange, rsi)
            
            if signal_strength == "WEAK":
                # Weak signal - add to AI context for extra scrutiny
                logger.info(f"⚠️ Weak multi-TF signal. AI will apply extra scrutiny.")
            elif signal_strength == "NO_SIGNAL":
                logger.info(f"📊 No signal on multi-TF analysis.")
                log_skip_to_empire(symbol, f"NO_SIGNAL: RSI_4H={rsi_4h:.1f} (Multi-TF filter)", current_price, asset_class)
                return {"status": "IDLE", "rsi": round(rsi, 2), "rsi_4h": round(rsi_4h, 2), "asset": symbol}
            
            # 5.6 🚀 MOMENTUM FILTER (V5 Optimization)
            momentum_ok, momentum_trend, ema_diff = check_momentum_filter(target_ohlcv)
            if not momentum_ok:
                log_skip_to_empire(symbol, f"BEARISH_MOMENTUM: EMA diff {ema_diff:.2f}%", current_price, asset_class)
                return {"status": "SKIPPED_BEARISH_MOMENTUM", "ema_diff": round(ema_diff, 2), "rsi": round(rsi, 2)}
            
            # 5.7 🚀 CORRELATION CHECK (V5 Optimization)
            correlation_ok, correlation_reason, crypto_exposure = check_portfolio_correlation(symbol)
            if not correlation_ok:
                log_skip_to_empire(symbol, correlation_reason, current_price, asset_class)
                return {"status": "SKIPPED_CORRELATION_RISK", "exposure": crypto_exposure, "reason": correlation_reason}
            
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
                # 🔥 Apply size multiplier from VIX AND Circuit Breaker
                final_size_mult = size_multiplier * cb_size_mult
                base_capital = CAPITAL_PER_TRADE * final_size_mult
                
                # 🚀 V5: Dynamic Position Sizing based on signal quality
                adjusted_capital, confidence = calculate_dynamic_position_size(
                    base_capital, rsi, signal_strength, vol_ratio, momentum_trend
                )
                
                logger.info(f"💰 Final Trade Size: {adjusted_capital:.2f}$ (VIX: {size_multiplier}, CB: {cb_size_mult}, Confidence: {confidence:.2f})")
                
                # Add V5 context to trade log
                portfolio_stats['momentum_trend'] = momentum_trend
                portfolio_stats['confidence_score'] = confidence
                portfolio_stats['crypto_exposure'] = crypto_exposure
                
                log_trade_to_empire(
                    symbol, 
                    "LONG", 
                    f"V5_FORTRESS_{signal_strength}_{momentum_trend}",
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

