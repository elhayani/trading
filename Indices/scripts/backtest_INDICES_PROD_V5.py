#!/usr/bin/env python3
"""
V5 PROD INDICES BACKTEST
========================
Fortress Strategy for Indices (S&P 500, Nasdaq, Dow)
- Logic: Trend Pullback (Classic Mean Reversion in Uptrend)
- V5 Optimizations:
  - Momentum Filter: EMA 50 > SMA 200 (Only trade strong trends)
  - Reversal Trigger: Green Candle required (Don't catch falling knives)
  - RSI Threshold: < 40 (Indices drift up, so <30 is too rare)
"""

import pandas as pd
import numpy as np
import yfinance as yf
import pandas_ta as ta
from datetime import datetime

# CONFIGURATION
# Yahoo Symbols for Indices
PAIRS_CONFIG = {
    '^GSPC': {'strategy': 'TREND_PULLBACK', 'rsi_oversold': 40, 'risk': 0.02, 'name': 'S&P 500'},
    '^IXIC': {'strategy': 'TREND_PULLBACK', 'rsi_oversold': 40, 'risk': 0.02, 'name': 'Nasdaq'},
    '^DJI':  {'strategy': 'TREND_PULLBACK', 'rsi_oversold': 40, 'risk': 0.02, 'name': 'Dow Jones'}
}

INITIAL_CAPITAL = 10000 # Indices usually require higher capital for contracts
LEVERAGE = 10 # Lower leverage for indices
SPREAD_PCT = 0.0002 # 2 bps (approx 10pts on NDX, 1pt on SPX)

def fetch_data(symbol, start, end):
    print(f"📥 Fetching {symbol} ({start} -> {end})...")
    df = yf.download(symbol, start=start, end=end, interval="1h", progress=False)
    if df.empty: return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def calculate_indicators(df):
    df = df.copy()
    # Indicators based on Close
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    df['SMA_200'] = ta.sma(df['Close'], length=200)
    df['EMA_50'] = ta.ema(df['Close'], length=50) # Momentum
    df['RSI'] = ta.rsi(df['Close'], length=14)
    return df

def check_reversal(row, direction):
    """V5 Reversal Trigger: Confirm candle color matches direction"""
    open_p = row['Open']
    close_p = row['Close']
    if direction == 'LONG': return close_p > open_p
    # Indices strategy is LONG ONLY for now (safest alpha)
    return False

def backtest_pair(symbol, config, start_date, end_date):
    df = fetch_data(symbol, start_date, end_date)
    if df is None: return None
    
    df = calculate_indicators(df)
    
    capital = INITIAL_CAPITAL
    trades = []
    position = None
    
    for i in range(200, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        timestamp = df.index[i]
        
        # 1. EXIT LOGIC
        if position:
            exit_price = None
            reason = ""
            
            # Check SL/TP
            # LONG ONLY
            if curr['Low'] <= position['sl']:
                exit_price = position['sl']
                reason = "SL"
            elif curr['High'] >= position['tp']:
                exit_price = position['tp']
                reason = "TP"
            
            if exit_price:
                diff = (exit_price - position['entry'])
                # PnL = Diff * Units (assuming CFD logic where 1 unit = $1 per point)
                # For ^GSPC (5000), 1 unit is $5000 notionnal. 
                # If we use units = risk / dist, logic holds.
                
                raw_pnl = diff * position['units']
                cost = (position['units'] * exit_price * SPREAD_PCT)
                net_pnl = raw_pnl - cost
                
                capital += net_pnl
                
                trades.append({
                    'time': timestamp,
                    'side': 'LONG',
                    'entry': position['entry'],
                    'exit': exit_price,
                    'pnl': net_pnl,
                    'reason': reason
                })
                position = None
            continue
            
        # 2. ENTRY LOGIC
        signal = None
        
        # Trend Pullback (Long Only for Indices)
        # Filter 1: Strong Trend (SMA200 < Price AND SMA200 < EMA50)
        is_bull_trend = (curr['Close'] > curr['SMA_200']) and (curr['EMA_50'] > curr['SMA_200'])
        
        if is_bull_trend:
            # Filter 2: RSI Oversold (Pullback)
            if curr['RSI'] < config['rsi_oversold']:
                # Filter 3: V5 Reversal Trigger
                if check_reversal(curr, 'LONG'):
                    signal = 'LONG'
        
        if signal:
            atr = curr['ATR']
            sl_mult = 2.0 # Wider Stop for Indices (noise)
            tp_mult = 4.0 # 1:2 R:R
            
            price = curr['Close']
            sl = price - (atr * sl_mult)
            tp = price + (atr * tp_mult)
            dist = price - sl
            
            if dist <= 0: continue
            
            # Sizing
            risk_amt = capital * config['risk']
            units = risk_amt / dist
            
            # Leverage Cap
            max_units = (capital * LEVERAGE) / price
            units = min(units, max_units)
            
            position = {
                'entry': price,
                'sl': sl,
                'tp': tp,
                'units': units
            }
            
    # Stats
    wins = [t for t in trades if t['pnl'] > 0]
    wr = (len(wins)/len(trades))*100 if trades else 0
    pnl = capital - INITIAL_CAPITAL
    
    return {
        'symbol': symbol,
        'name': config['name'],
        'final_capital': capital,
        'pnl_abs': pnl,
        'pnl_pct': (pnl/INITIAL_CAPITAL)*100,
        'trades': len(trades),
        'wr': wr
    }

if __name__ == "__main__":
    print("📈 INDICES V5 FORTRESS BACKTEST (2024-2025)")
    print("Logic: Trend Pullback + Momentum Filter + Reversal")
    print("------------------------------------------------")
    
    total_pnl = 0
    
    for symbol, conf in PAIRS_CONFIG.items():
        try:
            res = backtest_pair(symbol, conf, "2024-03-01", "2026-02-05")
            if res:
                print(f"🔹 {res['name']:<10} ({symbol}) | PnL: {res['pnl_pct']:+.2f}% (${res['pnl_abs']:.2f}) | WR: {res['wr']:.1f}% | Trades: {res['trades']}")
                total_pnl += res['pnl_abs']
            else:
                print(f"⚠️ No result for {symbol}")
        except Exception as e:
            print(f"❌ Error {symbol}: {e}")
            
    print("------------------------------------------------")
    print(f"💰 TOTAL PROFIT: ${total_pnl:.2f}")
