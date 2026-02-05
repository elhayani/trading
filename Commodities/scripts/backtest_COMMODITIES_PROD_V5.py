#!/usr/bin/env python3
"""
V5 PROD COMMODITIES BACKTEST
============================
Fortress Strategy for Gold (XAU) and Oil (WTI)
- Gold: Trend Pullback (Safe Haven logic, Long biased)
- Oil: Bollinger Breakout (Volatility capture)
- V5 Optimizations:
  - Momentum Filter (EMA 50 / SMA 200)
  - Reversal Trigger
  - Dynamic Sizing for Gold
"""

import pandas as pd
import numpy as np
import yfinance as yf
import pandas_ta as ta
from datetime import datetime

# CONFIGURATION
# Gold Futures (GC=F), Crude Oil (CL=F)
PAIRS_CONFIG = {
    'GC=F': {'strategy': 'TREND_PULLBACK', 'rsi_oversold': 45, 'risk': 0.02, 'name': 'Gold'},
    'CL=F': {'strategy': 'BOLLINGER_BREAKOUT', 'risk': 0.02, 'name': 'Crude Oil'}
}

INITIAL_CAPITAL = 10000 
LEVERAGE = 10
SPREAD_PCT = 0.0002 # 2 bps

def fetch_data(symbol, start, end):
    print(f"📥 Fetching {symbol} ({start} -> {end})...")
    df = yf.download(symbol, start=start, end=end, interval="1h", progress=False)
    if df.empty: return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def calculate_indicators(df):
    df = df.copy()
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    df['SMA_200'] = ta.sma(df['Close'], length=200)
    df['EMA_50'] = ta.ema(df['Close'], length=50) # Momentum
    df['RSI'] = ta.rsi(df['Close'], length=14)
    
    # Bollinger
    bb = ta.bbands(df['Close'], length=20, std=2.0)
    df = pd.concat([df, bb], axis=1)
    
    return df

def check_reversal(row, direction):
    """V5 Reversal Trigger"""
    open_p = row['Open']
    close_p = row['Close']
    if direction == 'LONG': return close_p > open_p
    if direction == 'SHORT': return close_p < open_p
    return False

def backtest_pair(symbol, config, start_date, end_date):
    df = fetch_data(symbol, start_date, end_date)
    if df is None: return None
    
    df = calculate_indicators(df)
    strategy = config['strategy']
    
    capital = INITIAL_CAPITAL
    trades = []
    position = None
    
    # Identify BB columns dynamically
    bbl_col = [c for c in df.columns if 'BBL' in c][0]
    bbu_col = [c for c in df.columns if 'BBU' in c][0]
    
    for i in range(200, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        timestamp = df.index[i]
        
        # 1. EXIT LOGIC
        if position:
            exit_price = None
            reason = ""
            
            p_sl = position['sl']
            p_tp = position['tp']
            
            if position['side'] == 'LONG':
                if curr['Low'] <= p_sl:
                    exit_price = p_sl
                    reason = "SL"
                elif curr['High'] >= p_tp:
                    exit_price = p_tp
                    reason = "TP"
            else: # SHORT
                if curr['High'] >= p_sl:
                    exit_price = p_sl
                    reason = "SL"
                elif curr['Low'] <= p_tp:
                    exit_price = p_tp
                    reason = "TP"
            
            if exit_price:
                diff = (exit_price - position['entry']) if position['side'] == 'LONG' else (position['entry'] - exit_price)
                
                # PnL = Diff * Units (Points * $/Point)
                # GC=F 1 point = $100 ? No, CFD simplified logic: 1 unit = $1 exposure/point
                # Assuming simple CFD scaling
                
                raw_pnl = diff * position['units']
                cost = (position['units'] * exit_price * SPREAD_PCT)
                net_pnl = raw_pnl - cost
                
                capital += net_pnl
                
                trades.append({
                    'time': timestamp,
                    'side': position['side'],
                    'entry': position['entry'],
                    'exit': exit_price,
                    'pnl': net_pnl,
                    'reason': reason
                })
                position = None
            continue
            
        # 2. ENTRY LOGIC
        signal = None
        
        # Strategy 1: Gold Trend Pullback
        if strategy == 'TREND_PULLBACK':
            # V5 Momentum Filter
            if symbol == 'GC=F':
                # Relaxed Momentum for Gold (Price > SMA200 only)
                is_bull = (curr['Close'] > curr['SMA_200']) 
            else:
                # Strict Momentum for others
                is_bull = (curr['Close'] > curr['SMA_200']) and (curr['EMA_50'] > curr['SMA_200'])
            
            if is_bull:
                if curr['RSI'] < config['rsi_oversold']:
                    if check_reversal(curr, 'LONG'):
                        signal = 'LONG'
                        
        # Strategy 2: Oil Bollinger Breakout
        elif strategy == 'BOLLINGER_BREAKOUT':
            # Long Breakout
            if curr['Close'] > curr[bbu_col] and prev['Close'] <= prev[bbu_col]:
                if curr['Close'] > curr['EMA_50']: # Momentum Confirmation
                    if check_reversal(curr, 'LONG'):
                        signal = 'LONG'
            # Short Breakout
            elif curr['Close'] < curr[bbl_col] and prev['Close'] >= prev[bbl_col]:
                if curr['Close'] < curr['EMA_50']: # Momentum Confirmation
                    if check_reversal(curr, 'SHORT'):
                        signal = 'SHORT'
        
        if signal:
            atr = curr['ATR']
            
            # Optimized Params for Gold
            if symbol == 'GC=F':
                sl_mult = 3.0
                tp_mult = 3.0 # Quick profits, wide stops
            else:
                sl_mult = 1.5
                tp_mult = 3.0
            
            entry = curr['Close']
            
            if signal == 'LONG':
                sl = entry - (atr * sl_mult)
                tp = entry + (atr * tp_mult)
                dist = entry - sl
            else:
                sl = entry + (atr * sl_mult)
                tp = entry - (atr * tp_mult)
                dist = sl - entry
                
            if dist <= 0: continue
            
            # Sizing
            risk_amt = capital * config['risk']
            units = risk_amt / dist
            
            max_units = (capital * LEVERAGE) / entry
            units = min(units, max_units)
            
            position = {
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'units': units,
                'side': signal
            }
            
    win_list = [t for t in trades if t['pnl'] > 0]
    wr = (len(win_list)/len(trades))*100 if trades else 0
    pnl = capital - INITIAL_CAPITAL
    
    return {
        'symbol': symbol,
        'name': config['name'],
        'pnl_pct': (pnl/INITIAL_CAPITAL)*100,
        'pnl': pnl,
        'trades': len(trades),
        'wr': wr
    }

if __name__ == "__main__":
    print("🛢️ COMMODITIES V5 FORTRESS BACKTEST")
    print("-----------------------------------")
    
    total_pnl = 0
    
    for symbol, conf in PAIRS_CONFIG.items():
        try:
            res = backtest_pair(symbol, conf, "2024-03-01", "2026-02-05")
            if res:
                 print(f"🔹 {res['name']:<10} ({symbol}) | PnL: {res['pnl_pct']:+.2f}% (${res['pnl']:.2f}) | WR: {res['wr']:.1f}% | Trades: {res['trades']}")
                 total_pnl += res['pnl']
        except Exception as e:
            print(f"❌ Error {symbol}: {e}")
            
    print("-----------------------------------")
    print(f"💰 TOTAL PROFIT: ${total_pnl:.2f}")
