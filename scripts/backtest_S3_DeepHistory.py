#!/usr/bin/env python3
"""
V5 DEEP HISTORY BACKTEST (S3 DATA)
==================================
Backtest V5 Fortress Strategies on 2010-2023 Data (Daily Resolution)
Fetched from S3 bucket 'empire-trading-data-paris'.

Logic:
- Forex: Trend Pullback (EUR, GBP) / Bollinger Breakout (JPY)
- Indices: Trend Pullback (SPX, NDX)
- Commodities: Relaxed Pullback (Gold), Bollinger Breakout (Oil)

Timeframe: 1d (Daily)
"""

import boto3
import pandas as pd
import pandas_ta as ta
from io import StringIO
import numpy as np

BUCKET_NAME = "empire-trading-data-paris"

# V5 CONFIGURATION (Mapped for Deep History)
ASSETS_CONFIG = {
    # FOREX
    'EURUSD': {'category': 'forex', 'strategy': 'TREND_PULLBACK', 'params': {'rsi_oversold': 40, 'sl_atr': 1.5, 'tp_atr': 3.0}},
    'GBPUSD': {'category': 'forex', 'strategy': 'TREND_PULLBACK', 'params': {'rsi_oversold': 40, 'sl_atr': 1.5, 'tp_atr': 3.0}},
    'JPY':    {'category': 'forex', 'strategy': 'BOLLINGER_BREAKOUT', 'params': {'sl_atr': 1.5, 'tp_atr': 3.0}},
    
    # INDICES
    'GSPC':   {'category': 'indices', 'strategy': 'TREND_PULLBACK', 'params': {'rsi_oversold': 40, 'sl_atr': 2.0, 'tp_atr': 4.0}},
    'IXIC':   {'category': 'indices', 'strategy': 'TREND_PULLBACK', 'params': {'rsi_oversold': 40, 'sl_atr': 2.0, 'tp_atr': 4.0}},
    
    # COMMODITIES
    'GC':     {'category': 'commodities', 'strategy': 'TREND_PULLBACK', 'params': {'rsi_oversold': 45, 'sl_atr': 3.0, 'tp_atr': 3.0, 'relaxed': True}},
    'CL':     {'category': 'commodities', 'strategy': 'BOLLINGER_BREAKOUT', 'params': {'sl_atr': 2.0, 'tp_atr': 4.0}},
    
    # CRYPTO (V5 Fortress)
    'BTC-USD': {'category': 'crypto', 'strategy': 'TREND_PULLBACK', 'params': {'rsi_oversold': 45, 'sl_atr': 2.0, 'tp_atr': 4.0}},
    'ETH-USD': {'category': 'crypto', 'strategy': 'TREND_PULLBACK', 'params': {'rsi_oversold': 45, 'sl_atr': 2.0, 'tp_atr': 5.0}}
}

def load_from_s3(category, symbol):
    s3 = boto3.client('s3')
    key = f"historical/{category}/{symbol}_1d_2010_2023.csv"
    print(f"📥 Loading s3://{BUCKET_NAME}/{key}...")
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        df = pd.read_csv(obj['Body'], index_col=0, parse_dates=True)
        return df
    except Exception as e:
        print(f"❌ Error loading S3: {e}")
        return None

def calculate_indicators(df):
    df = df.copy()
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    df['SMA_200'] = ta.sma(df['close'], length=200)
    df['EMA_50'] = ta.ema(df['close'], length=50) # Momentum
    df['RSI'] = ta.rsi(df['close'], length=14)
    
    # BB
    bb = ta.bbands(df['close'], length=20, std=2.0)
    df = pd.concat([df, bb], axis=1)
    return df

def check_reversal(row, direction):
    # Daily Reversal Trigger
    if direction == 'LONG': return row['close'] > row['open']
    if direction == 'SHORT': return row['close'] < row['open']
    return False

def run_backtest(symbol, config, df):
    df = calculate_indicators(df)
    strategy = config['strategy']
    params = config['params']
    
    capital = 10000
    trades = []
    position = None
    
    # Identify BB Cols
    bbl_col = [c for c in df.columns if 'BBL' in c][0]
    bbu_col = [c for c in df.columns if 'BBU' in c][0]

    for i in range(200, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        ts = df.index[i]
        
        # 1. Manage Exit
        if position:
            exit_price = None
            reason = ""
            
            p_sl = position['sl']
            p_tp = position['tp']
            
            if position['side'] == 'LONG':
                if curr['low'] <= p_sl:
                    exit_price = p_sl
                    reason = "SL"
                elif curr['high'] >= p_tp:
                    exit_price = p_tp
                    reason = "TP"
            else:
                if curr['high'] >= p_sl:
                    exit_price = p_sl
                    reason = "SL"
                elif curr['low'] <= p_tp:
                    exit_price = p_tp
                    reason = "TP"
            
            if exit_price:
                diff = (exit_price - position['entry']) if position['side'] == 'LONG' else (position['entry'] - exit_price)
                norm_diff = diff # Simplified for Deep Backtest (Points PnL)
                pnl = norm_diff * position['units']
                capital += pnl
                trades.append({'pnl': pnl, 'year': ts.year})
                position = None
            continue
            
        # 2. Entry Logic (V5)
        signal = None
        
        if strategy == 'TREND_PULLBACK':
            relaxed = params.get('relaxed', False)
            if relaxed:
                is_bull = curr['close'] > curr['SMA_200']
            else:
                is_bull = (curr['close'] > curr['SMA_200']) and (curr['EMA_50'] > curr['SMA_200'])
            
            if is_bull and curr['RSI'] < params['rsi_oversold']:
                 if check_reversal(curr, 'LONG'):
                     signal = 'LONG'
                     
        elif strategy == 'BOLLINGER_BREAKOUT':
            if curr['close'] > curr[bbu_col] and prev['close'] <= prev[bbu_col]:
                if curr['close'] > curr['EMA_50']:
                    if check_reversal(curr, 'LONG'):
                        signal = 'LONG'
            elif curr['close'] < curr[bbl_col] and prev['close'] >= prev[bbl_col]:
                if curr['close'] < curr['EMA_50']:
                    if check_reversal(curr, 'SHORT'):
                         signal = 'SHORT'

        if signal:
            atr = curr['ATR']
            sl_mult = params['sl_atr']
            tp_mult = params['tp_atr']
            
            entry = curr['close']
            if signal == 'LONG':
                sl = entry - (atr * sl_mult)
                tp = entry + (atr * tp_mult)
                dist = entry - sl
            else:
                sl = entry + (atr * sl_mult)
                tp = entry - (atr * tp_mult)
                dist = sl - entry
            
            if dist <= 0: continue
            
            # Fixed Risk Sizing ($200 per trade)
            risk_amt = 200
            units = risk_amt / dist
            
            position = {
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'units': units,
                'side': signal
            }
            
    # Stats
    wins = len([t for t in trades if t['pnl'] > 0])
    total = len(trades)
    wr = (wins/total)*100 if total else 0

    # Yearly Stats Aggregation
    yearly_pnl = {}
    
    for t in trades:
        # Assuming 'time' was added to trade dict in the loop. 
        # Wait, previous loop didn't add timestamp to trades list. I need to fix that.
        y = t['year']
        if y not in yearly_pnl: yearly_pnl[y] = 0
        yearly_pnl[y] += t['pnl']

    # Convert to PnL % (Fixed capital 10k)
    yearly_res = {y: (val/10000)*100 for y, val in yearly_pnl.items()}
    
    total_pnl = capital - 10000

    return {
        'symbol': symbol,
        'year_stats': yearly_res,
        'pnl_pct': (total_pnl/10000)*100,
        'wr': wr,
        'trades': total
    }

if __name__ == "__main__":
    print("🏛️ EMPIRE DEEP HISTORY YEARLY BREAKDOWN (2010-2023)")
    print("---------------------------------------------------")
    
    # Store all years to create a matrix
    all_years = sorted(list(range(2010, 2024)))
    matrix = {y: {'FOREX': 0, 'INDICES': 0, 'COMMO': 0, 'CRYPTO': 0} for y in all_years}
    
    for symbol, conf in ASSETS_CONFIG.items():
        df = load_from_s3(conf['category'], symbol)
        if df is not None and not df.empty:
            res = run_backtest(symbol, conf, df)
            
            # Add to Matrix
            cat = conf['category'].upper()
            if cat == 'COMMODITIES': cat = 'COMMO'
            
            for y, pnl in res['year_stats'].items():
                if y in matrix:
                    matrix[y][cat] += pnl
            
            # Print individual asset recap? No, too long. Matrix is better.

    print(f"{'YEAR':<6} | {'CRYPTO':<10} | {'INDICES':<10} | {'COMMO':<10} | {'FOREX':<10} | {'TOTAL':<10}")
    print("-" * 65)
    
    total_cumul = 0
    for y in all_years:
        row = matrix[y]
        total = row['CRYPTO'] + row['INDICES'] + row['COMMO'] + row['FOREX']
        total_cumul += total
        print(f"{y:<6} | {row['CRYPTO']:>9.1f}% | {row['INDICES']:>9.1f}% | {row['COMMO']:>9.1f}% | {row['FOREX']:>9.1f}% | {total:>9.1f}%")
        
    print("-" * 65)
    print(f"💰 CUMULATIVE RETURN: {total_cumul:.1f}%")
