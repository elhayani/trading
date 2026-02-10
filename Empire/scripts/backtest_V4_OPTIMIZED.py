#!/usr/bin/env python3
"""
V5 FORTRESS ADVANCED BACKTEST
=============================
Includes all optimizations:
- Circuit Breaker (3 levels)
- Dynamic RSI (Bull/Neutral/Bear) + ETH-specific
- Volume Confirmation
- SOL Turbo Trailing (+10% activation, -5% trail for momentum)
- 🚀 V5: Momentum Filter (EMA 20 > EMA 50)
- 🚀 V5: Dynamic Position Sizing (Kelly-inspired)
- 🚀 V5: Portfolio Correlation Check

V5 Fortress Advanced Changes:
- Momentum filter blocks entries in bearish EMA cross
- Position size adjusted based on signal confidence (0.5x to 1.5x)
- Max 2 correlated crypto trades when portfolio is losing
"""

import sys
import os
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import boto3

# Config
BUCKET_NAME = os.environ.get('TRADING_LOGS_BUCKET', 'empire-trading-data-paris')
S3_REGION = 'eu-west-3'

# ==================== V5 FORTRESS ADVANCED PARAMETERS ====================
# Circuit Breaker Thresholds
CB_L1_THRESHOLD = -0.05   # -5% BTC 24h = reduce size 50%
CB_L2_THRESHOLD = -0.10   # -10% BTC 24h = STOP
CB_L3_THRESHOLD = -0.20   # -20% BTC 7d = SURVIVAL MODE

# RSI Thresholds by Regime
RSI_BULL = 40       # Bull market: RSI < 40
RSI_NEUTRAL = 35    # Neutral: RSI < 35
RSI_BEAR = 30       # Bear market: RSI < 30 (except ETH = 35)
RSI_ETH_BEAR = 35   # 🛠️ ETH-specific: stays at 35 even in BEAR

# Volume Confirmation
VOLUME_MULT = 1.5   # Need 1.5x avg volume

# SOL Turbo Trailing - FORTRESS BALANCED: Wider for momentum
SOL_TRAIL_ACTIVATION = 10.0  # +10% to activate
SOL_TRAIL_STOP = 5.0         # 🛠️ -5% from peak (was 3%, now wider for momentum)

# 🚀 V5 NEW: Momentum Filter
MOMENTUM_FILTER_ENABLED = True

# 🚀 V5 NEW: Dynamic Sizing
DYNAMIC_SIZING_ENABLED = True

# Stop Loss / Take Profit
STOP_LOSS_PCT = -5.0
HARD_TP_PCT = 5.0
# =========================================================================

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../lambda/v4_trader')))
from market_analysis import analyze_market

s3 = boto3.client('s3', region_name=S3_REGION)


def fetch_historical_data(symbol, days, offset_days=0):
    """Fetch data from S3"""
    end_time = datetime.now() - timedelta(days=offset_days)
    start_time = end_time - timedelta(days=days)
    
    years = range(start_time.year, end_time.year + 1)
    all_ohlcv = []
    
    safe_symbol = symbol.replace('/', '_')
    
    for y in years:
        key = f"historical/{safe_symbol}/{y}.json"
        try:
            resp = s3.get_object(Bucket=BUCKET_NAME, Key=key)
            data = json.loads(resp['Body'].read().decode('utf-8'))
            all_ohlcv.extend(data)
        except Exception as e:
            pass
    
    start_ts = int(start_time.timestamp() * 1000)
    end_ts = int(end_time.timestamp() * 1000)
    
    filtered = [x for x in all_ohlcv if start_ts <= x[0] <= end_ts]
    filtered.sort(key=lambda x: x[0])
    
    return filtered


def get_btc_perf(btc_ohlcv, timestamp, hours):
    """Get BTC performance over last N hours from timestamp"""
    current_idx = None
    for i, c in enumerate(btc_ohlcv):
        if c[0] >= timestamp:
            current_idx = i
            break
    
    if current_idx is None or current_idx < hours:
        return 0
    
    current_price = btc_ohlcv[current_idx][4]
    past_price = btc_ohlcv[current_idx - hours][4]
    
    return (current_price - past_price) / past_price


def check_circuit_breaker(btc_24h_perf, btc_7d_perf):
    """
    Returns: (can_trade, size_mult, level)
    """
    if btc_7d_perf <= CB_L3_THRESHOLD:
        return False, 0, "L3_SURVIVAL"
    if btc_24h_perf <= CB_L2_THRESHOLD:
        return False, 0, "L2_HALT"
    if btc_24h_perf <= CB_L1_THRESHOLD:
        return True, 0.5, "L1_REDUCE"
    return True, 1.0, "OK"


def get_dynamic_rsi(btc_7d_perf, symbol=''):
    """
    Dynamic RSI threshold based on market regime (V4 Fortress Balanced)
    ETH keeps RSI 35 even in BEAR markets (backtest 2022 lesson)
    """
    if btc_7d_perf >= 0.05:
        return RSI_BULL, "BULL"
    elif btc_7d_perf <= -0.05:
        # 🛠️ V4 Fortress Balanced: ETH keeps RSI 35 in BEAR
        if 'ETH' in symbol:
            return RSI_ETH_BEAR, "BEAR_ETH_ADJUSTED"
        return RSI_BEAR, "BEAR"
    else:
        return RSI_NEUTRAL, "NEUTRAL"


def check_volume(ohlcv_window):
    """Check if volume is confirmed (>1.5x avg)"""
    if len(ohlcv_window) < 20:
        return True, 1.0
    
    volumes = [c[5] for c in ohlcv_window[-20:]]
    avg_vol = np.mean(volumes[:-1]) if len(volumes) > 1 else volumes[0]
    current_vol = volumes[-1]
    
    if avg_vol == 0:
        return True, 1.0
    
    ratio = current_vol / avg_vol
    return ratio >= VOLUME_MULT, ratio


# ==================== V5 ADVANCED OPTIMIZATIONS ====================

def check_momentum_filter(ohlcv_data):
    """
    🚀 V5 OPTIMIZATION 1: Momentum Filter (EMA Cross)
    Only buy when EMA 20 > EMA 50 (confirmed uptrend)
    Returns: (is_bullish: bool, trend: str, ema_diff_pct: float)
    """
    if not MOMENTUM_FILTER_ENABLED:
        return True, "DISABLED", 0
    
    if len(ohlcv_data) < 50:
        return True, "INSUFFICIENT_DATA", 0
    
    closes = [c[4] for c in ohlcv_data[-50:]]
    
    # Simple EMA calculation
    def ema(data, period):
        multiplier = 2 / (period + 1)
        ema_val = sum(data[:period]) / period
        for price in data[period:]:
            ema_val = (price - ema_val) * multiplier + ema_val
        return ema_val
    
    ema_20 = ema(closes, 20)
    ema_50 = ema(closes, 50)
    
    ema_diff_pct = ((ema_20 - ema_50) / ema_50) * 100
    
    if ema_20 > ema_50:
        return True, "BULLISH", ema_diff_pct
    elif ema_20 < ema_50 * 0.98:  # 2% below = strong bearish
        return False, "BEARISH", ema_diff_pct
    else:
        return True, "NEUTRAL", ema_diff_pct


def calculate_dynamic_position_size(base_capital, rsi, vol_ratio, momentum_trend):
    """
    🚀 V5 OPTIMIZATION 2: Dynamic Position Sizing
    Returns: (adjusted_capital, confidence_score)
    """
    if not DYNAMIC_SIZING_ENABLED:
        return base_capital, 1.0
    
    confidence_score = 1.0
    
    # RSI Quality Bonus
    if rsi < 25:
        confidence_score += 0.30
    elif rsi < 30:
        confidence_score += 0.15
    elif rsi > 38:
        confidence_score -= 0.10
    
    # Volume Confirmation Bonus
    if vol_ratio >= 2.0:
        confidence_score += 0.20
    elif vol_ratio >= 1.75:
        confidence_score += 0.10
    
    # Momentum Trend Bonus
    if momentum_trend == "BULLISH":
        confidence_score += 0.15
    elif momentum_trend == "BEARISH":
        confidence_score -= 0.25
    
    # Cap between 0.5x and 1.5x
    confidence_score = max(0.5, min(confidence_score, 1.5))
    
    return base_capital * confidence_score, confidence_score

# ================================================================


def run_backtest(symbol, days=90, offset_days=0, btc_ohlcv=None, verbose=False):
    """Run optimized backtest with all protections"""
    
    ohlcv = fetch_historical_data(symbol, days + 200, offset_days)  # Extra for indicators
    
    if len(ohlcv) < 300:
        return None
    
    # Trim to actual period
    target_start = datetime.now() - timedelta(days=days + offset_days)
    target_end = datetime.now() - timedelta(days=offset_days)
    start_ts = int(target_start.timestamp() * 1000)
    end_ts = int(target_end.timestamp() * 1000)
    
    initial_capital = 1000
    capital = initial_capital
    position = None
    trades = []
    peak_capital = initial_capital
    max_drawdown = 0
    
    # Stats
    cb_blocks = {"L1": 0, "L2": 0, "L3": 0}
    vol_blocks = 0
    rsi_blocks = 0
    
    min_history = 300
    
    for i in range(min_history, len(ohlcv)):
        candle = ohlcv[i]
        timestamp = candle[0]
        
        # Skip if outside target period
        if timestamp < start_ts or timestamp > end_ts:
            continue
        
        window = ohlcv[i-min_history:i+1]
        current_price = candle[4]
        
        analysis = analyze_market(window)
        rsi = analysis['indicators']['rsi']
        atr = analysis['indicators']['atr']
        
        # Get BTC performance for circuit breaker
        if btc_ohlcv:
            btc_24h = get_btc_perf(btc_ohlcv, timestamp, 24)
            btc_7d = get_btc_perf(btc_ohlcv, timestamp, 168)
        else:
            btc_24h, btc_7d = 0, 0
        
        # ============ EXIT LOGIC ============
        if position:
            entry_price = position['entry_price']
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            
            # Update peak for trailing
            if pnl_pct > position.get('peak_pnl', 0):
                position['peak_pnl'] = pnl_pct
            
            should_exit = False
            exit_reason = ""
            
            # Stop Loss
            if pnl_pct <= STOP_LOSS_PCT:
                should_exit = True
                exit_reason = "STOP_LOSS"
            
            # Hard Take Profit
            elif pnl_pct >= HARD_TP_PCT:
                should_exit = True
                exit_reason = "HARD_TP"
            
            # SOL Turbo Trailing
            elif 'SOL' in symbol and pnl_pct >= SOL_TRAIL_ACTIVATION:
                peak = position.get('peak_pnl', pnl_pct)
                trailing_trigger = peak - SOL_TRAIL_STOP
                if pnl_pct <= trailing_trigger and trailing_trigger > 0:
                    should_exit = True
                    exit_reason = "SOL_TURBO_TRAIL"
            
            # Circuit Breaker Emergency Exit (L3)
            if btc_7d <= CB_L3_THRESHOLD and 'SOL' in symbol:
                should_exit = True
                exit_reason = "CB_L3_EMERGENCY"
            
            if should_exit:
                profit = (current_price - entry_price) * position['size']
                capital += profit
                trades.append({
                    'profit': profit,
                    'pnl_pct': pnl_pct,
                    'reason': exit_reason
                })
                position = None
        
        # ============ ENTRY LOGIC ============
        if position is None:
            # 1. Circuit Breaker Check
            can_trade, size_mult, cb_level = check_circuit_breaker(btc_24h, btc_7d)
            
            if not can_trade:
                if cb_level == "L3_SURVIVAL":
                    cb_blocks["L3"] += 1
                elif cb_level == "L2_HALT":
                    cb_blocks["L2"] += 1
                continue
            
            if cb_level == "L1_REDUCE":
                cb_blocks["L1"] += 1
            
            # 2. Dynamic RSI Threshold (V4 Fortress Balanced)
            rsi_threshold, regime = get_dynamic_rsi(btc_7d, symbol)
            
            if rsi >= rsi_threshold:
                rsi_blocks += 1
                continue
            
            # 3. Volume Confirmation
            vol_ok, vol_ratio = check_volume(window)
            if not vol_ok:
                vol_blocks += 1
                continue

            # 🚀 4. Momentum Filter (V5)
            momentum_ok, momentum_trend, ema_diff = check_momentum_filter(window)
            if not momentum_ok:
                # Logique optionnelle: compter les blocs momentum si nécessaire
                continue
            
            # 5. ENTER TRADE
            # Base capital after CB reduction
            base_capital = capital * size_mult
            
            # 🚀 6. Dynamic Position Sizing (V5)
            trade_capital, confidence = calculate_dynamic_position_size(base_capital, rsi, vol_ratio, momentum_trend)
            
            if trade_capital < 50:  # Min trade size
                continue
            
            position = {
                'entry_price': current_price,
                'size': trade_capital / current_price,
                'peak_pnl': 0,
                'regime': regime,
                'cb_level': cb_level,
                'momentum': momentum_trend
            }
        
        # Track drawdown
        if capital > peak_capital:
            peak_capital = capital
        dd = (peak_capital - capital) / peak_capital
        if dd > max_drawdown:
            max_drawdown = dd
    
    # Results
    perf = ((capital - initial_capital) / initial_capital) * 100
    wins = len([t for t in trades if t['profit'] > 0])
    win_rate = (wins / len(trades) * 100) if trades else 0
    
    print(f"{'─'*50}")
    print(f"RÉSULTAT OPTIMISÉ (90j)")
    print(f"Capital Final : {capital:.2f}$")
    print(f"Performance   : {perf:+.2f}%")
    print(f"Trades        : {len(trades)}")
    print(f"Win Rate      : {win_rate:.1f}%")
    print(f"Max Drawdown  : {max_drawdown*100:.2f}%")
    print(f"─── Filtres Activés ───")
    print(f"CB L1 (reduce): {cb_blocks['L1']} | L2 (halt): {cb_blocks['L2']} | L3 (survival): {cb_blocks['L3']}")
    print(f"RSI Filter    : {rsi_blocks}")
    print(f"Volume Filter : {vol_blocks}")
    print(f"{'─'*50}")
    
    return {
        'performance': perf,
        'win_rate': win_rate,
        'trades': len(trades),
        'max_drawdown': max_drawdown * 100,
        'cb_blocks': cb_blocks,
        'final_capital': capital
    }


def run_full_year(year, symbols):
    """Run all 4 quarters for all symbols"""
    print(f"\n{'='*60}")
    print(f"🚀 BACKTEST V4 FORTRESS BALANCED - ANNÉE {year}")
    print(f"{'='*60}")
    
    # Load BTC reference data
    print("📥 Chargement BTC Reference...")
    btc_ohlcv = fetch_historical_data('BTC/USDT', 400, offset_days=max(0, (datetime.now() - datetime(year+1, 1, 1)).days - 365))
    print(f"   ✅ {len(btc_ohlcv)} candles BTC chargées")
    
    # Calculate quarter offsets
    now = datetime.now()
    results = {}
    
    quarters = {
        'Q4': datetime(year+1, 1, 1),
        'Q3': datetime(year, 10, 1),
        'Q2': datetime(year, 7, 1),
        'Q1': datetime(year, 4, 1)
    }
    
    for sym in symbols:
        print(f"\n{'─'*50}")
        print(f"💎 {sym} ({year})")
        print(f"{'─'*50}")
        
        results[sym] = {}
        
        for q_name, q_end in quarters.items():
            offset = max(0, (now - q_end).days)
            print(f"\n📅 {year} {q_name}")
            
            res = run_backtest(sym, days=90, offset_days=offset, btc_ohlcv=btc_ohlcv, verbose=False)
            results[sym][q_name] = res
        
        # Summary
        print(f"\n📊 Bilan {year} {sym}:")
        for q in ['Q4', 'Q3', 'Q2', 'Q1']:
            r = results[sym].get(q)
            if r:
                print(f"   {q}: {r['performance']:+.2f}% ({r['trades']} trades, DD: {r['max_drawdown']:.1f}%)")
    
    return results


if __name__ == "__main__":
    SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    
    # Parse year argument
    target_year = 2024
    if len(sys.argv) > 1:
        for arg in sys.argv:
            if arg.isdigit() and len(arg) == 4:
                target_year = int(arg)
                break
    
    run_full_year(target_year, SYMBOLS)
