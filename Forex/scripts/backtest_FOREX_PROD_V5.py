#!/usr/bin/env python3
"""
V5 PROD FOREX BACKTEST
======================
Based on Production Strategies (Trend Pullback & Bollinger)
Enhanced with V5 Fortress Optimizations:
- Momentum Filter (EMA Strong Trend)
- Reversal Trigger (Candle Confirmation)
- Dynamic Sizing
"""

import pandas as pd
import numpy as np
import yfinance as yf
import pandas_ta as ta
from datetime import datetime

# CONFIGURATION
PAIRS_CONFIG = {
    'EURUSD=X': {'strategy': 'TREND_PULLBACK', 'rsi_oversold': 35, 'risk': 0.02},
    'GBPUSD=X': {'strategy': 'TREND_PULLBACK', 'rsi_oversold': 35, 'risk': 0.02},
    'JPY=X':    {'strategy': 'BOLLINGER_BREAKOUT', 'risk': 0.02} # USDJPY
}

INITIAL_CAPITAL = 1000
LEVERAGE = 30
SPREAD_PCT = 0.00015 # 1.5 pips approx

def fetch_data(symbol, start, end):
    print(f"📥 Fetching {symbol} ({start} -> {end})...")
    df = yf.download(symbol, start=start, end=end, interval="1h", progress=False)
    if df.empty: return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def calculate_indicators(df):
    df = df.copy()
    # Common
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    df['SMA_200'] = ta.sma(df['Close'], length=200)
    df['EMA_50'] = ta.ema(df['Close'], length=50) # Momentum Filter
    df['RSI'] = ta.rsi(df['Close'], length=14)
    
    # Bollinger
    bb = ta.bbands(df['Close'], length=20, std=2.0)
    df = pd.concat([df, bb], axis=1)
    # Rename columns to standard names if needed, pandas_ta usually gives BBL_20_2.0 etc
    # Let's map them dynamically or just use the defaults
    return df

def check_reversal(row, direction):
    """V5 Reversal Trigger: Confirm candle color matches direction"""
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
    
    # Identify BB columns
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
            
            # Check SL/TP
            if position['side'] == 'LONG':
                if curr['Low'] <= position['sl']:
                    exit_price = position['sl']
                    reason = "SL"
                elif curr['High'] >= position['tp']:
                    exit_price = position['tp']
                    reason = "TP"
            else: # SHORT
                if curr['High'] >= position['sl']:
                    exit_price = position['sl']
                    reason = "SL"
                elif curr['Low'] <= position['tp']:
                    exit_price = position['tp']
                    reason = "TP"
            
            if exit_price:
                # PnL Calc
                diff = (exit_price - position['entry']) if position['side'] == 'LONG' else (position['entry'] - exit_price)
                raw_pnl = diff * position['units']
                
                # JPY Adjustment (Quote currency is JPY, need USD)
                if 'JPY' in symbol: raw_pnl /= exit_price
                
                cost = position['units'] * SPREAD_PCT
                if 'JPY' in symbol: cost /= exit_price
                
                net_pnl = raw_pnl - cost
                capital += net_pnl
                
                trades.append({
                    'time': timestamp,
                    'side': position['side'],
                    'entry': position['entry'],
                    'exit': exit_price,
                    'pnl': net_pnl,
                    'pnl_pct': (net_pnl/capital)*100,
                    'reason': reason
                })
                position = None
            continue # Don't re-enter same bar
            
        # 2. ENTRY LOGIC
        signal = None
        
        # --- STRATEGY: TREND PULLBACK (Mean Reversion in Trend) ---
        if strategy == 'TREND_PULLBACK':
            # Trend Filter V5: SMA200 AND EMA50 alignment
            is_bull_trend = (curr['Close'] > curr['SMA_200']) and (curr['EMA_50'] > curr['SMA_200'])
            
            if is_bull_trend:
                # Pullback Entry
                if curr['RSI'] < config['rsi_oversold']:
                    # V5 Fortress: Reversal Trigger
                    if check_reversal(curr, 'LONG'):
                        signal = 'LONG'
                        
        # --- STRATEGY: BOLLINGER BREAKOUT (Volatility Expansion) ---
        elif strategy == 'BOLLINGER_BREAKOUT':
            # Breakout Long
            if curr['Close'] > curr[bbu_col] and prev['Close'] <= prev[bbu_col]:
                # V5: Verify Momentum (EMA50 Slope positive or Price > EMA50)
                if curr['Close'] > curr['EMA_50']:
                    if check_reversal(curr, 'LONG'):
                        signal = 'LONG'
                        
            # Breakout Short
            elif curr['Close'] < curr[bbl_col] and prev['Close'] >= prev[bbl_col]:
                if curr['Close'] < curr['EMA_50']:
                    if check_reversal(curr, 'SHORT'):
                        signal = 'SHORT'
        
        # Execute Trade
        if signal:
            atr = curr['ATR']
            sl_mult = 1.5
            tp_mult = 3.0
            
            price = curr['Close']
            
            if signal == 'LONG':
                sl = price - (atr * sl_mult)
                tp = price + (atr * tp_mult)
                dist = price - sl
            else:
                sl = price + (atr * sl_mult)
                tp = price - (atr * tp_mult)
                dist = sl - price
                
            if dist <= 0: continue
            
            # Sizing
            risk_amt = capital * config['risk']
            units = risk_amt / dist
            
            if 'JPY' in symbol: units = (risk_amt * price) / dist
            
            # Leverage Cap
            max_units = capital * LEVERAGE
            current_lev = units / capital if 'JPY' in symbol else (units * price) / capital
            
            if current_lev > LEVERAGE:
                units *= (LEVERAGE / current_lev)
                
            position = {
                'side': signal,
                'entry': price,
                'sl': sl,
                'tp': tp,
                'units': units
            }
            
    # Final Stats
    wins = [t for t in trades if t['pnl'] > 0]
    wr = (len(wins)/len(trades))*100 if trades else 0
    pnl = capital - INITIAL_CAPITAL
    return {
        'symbol': symbol,
        'final_capital': capital,
        'pnl_abs': pnl,
        'pnl_pct': (pnl/INITIAL_CAPITAL)*100,
        'trades': len(trades),
        'wr': wr
    }

if __name__ == "__main__":
    print("🌍 FOREX PROD V5 BACKTEST (2024-2025)")
    print("-------------------------------------")
    
    total_pnl = 0
    
    for symbol, conf in PAIRS_CONFIG.items():
        try:
            # Adjusted start date to fit 730-day limit (Yahoo limitation for 1h data)
            res = backtest_pair(symbol, conf, "2024-03-01", "2026-02-05")
            
            if res:
                print(f"🔹 {symbol:<10} | PnL: {res['pnl_pct']:+.2f}% (${res['pnl_abs']:.2f}) | WR: {res['wr']:.1f}% | Trades: {res['trades']}")
                total_pnl += res['pnl_abs']
            else:
                print(f"⚠️ No result for {symbol}")
        except Exception as e:
            print(f"❌ Error {symbol}: {e}")
            
    print("-------------------------------------")
    print(f"💰 TOTAL PROFIT: ${total_pnl:.2f}")
