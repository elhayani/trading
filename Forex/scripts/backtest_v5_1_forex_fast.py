import sys
import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timedelta

# --- CONFIGURATION PATHS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../lambda/forex_trader')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../shared')))

try:
    # V5.1 Modules
    from predictability_index import calculate_predictability_score
except ImportError:
    pass

# --- VECTORIZED BACKTEST ENGINE (FOREX V5.1) ---
def run_forex_backtest(symbol, period_years=2, strategy='TREND_PULLBACK'):
    print(f"\n💶 BACKTEST V5.1 FOREX: {symbol}")
    
    # 1. Fetch Data (Yahoo Logic)
    # 1h data limit is 730 days
    start_date = (datetime.now() - timedelta(days=729)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"📥 Fetching 1h data from YFinance ({start_date} -> {end_date})...")
    df = yf.download(symbol, start=start_date, end=end_date, interval="1h", progress=False)
    
    if df.empty:
        print("❌ No Data.")
        return

    # Flatten MultiIndex if needed
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 2. Indicators (Vectorized)
    print("⚡ Calculating V5.1 Indicators...")
    
    # Trend Filter
    df['SMA_200'] = ta.sma(df['Close'], length=200)
    df['EMA_50'] = ta.ema(df['Close'], length=50) # Momentum
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    
    # RSI
    df['RSI'] = ta.rsi(df['Close'], length=14)
    
    # V5.1 Predictability (Simplified Rolling)
    # Rolling AutoCorr
    returns = df['Close'].pct_change()
    rolling_autocorr = returns.rolling(window=50).corr(returns.shift(1))
    df['Pred_Score'] = (rolling_autocorr.fillna(0) + 1) * 50 # 0-100 approx
    
    # Macro Mock (Random RegExp switching or constant)
    # We assume 'Normal' market mostly
    
    # 3. Signals
    # BUY CONDITION:
    # - Price > SMA200 (Uptrend)
    # - EMA50 > SMA200 (Strong Trend)
    # - RSI < 40 (Pullback)
    # - Pred Score > 30 (Not erratic)
    
    # SELL CONDITION:
    # - SL / TP
    
    capital = 1000.0
    position = None
    trades = []
    
    # Loop for trade management (hard to vectorize fully with state)
    for i in range(200, len(df)):
        curr = df.iloc[i]
        
        # SKIP if Pred Score bad (V5.1 Filter)
        if curr['Pred_Score'] < 25:
            continue
            
        # ENTRY
        if position is None:
            if strategy == 'TREND_PULLBACK':
                # Trend Follow Logic (Best for EURUSD, GBPUSD)
                is_uptrend = (curr['Close'] > curr['SMA_200']) and (curr['EMA_50'] > curr['SMA_200'])
                if is_uptrend and curr['RSI'] < 40:
                    signal = 'LONG'
                    sl_dist = curr['ATR'] * 1.5
                    tp_dist = curr['ATR'] * 3.0
            
            elif strategy == 'BOLLINGER_BREAKOUT':
                # Volatility Breakout Logic (Best for JPY, Gold)
                # Upper Band = SMA20 + 2*STD (We need to calculate it properly)
                # Quick BB calc inline for speed
                sma_20 = df['Close'].rolling(window=20).mean()
                std_20 = df['Close'].rolling(window=20).std()
                upper = sma_20 + (2 * std_20)
                
                # Check current values
                bb_upper = upper.iloc[i]
                
                # Condition: Close breaks Upper (Momentum) + Confirm EMA Slope
                if curr['Close'] > bb_upper and curr['Close'] > curr['EMA_50']:
                    signal = 'LONG'
                    sl_dist = curr['ATR'] * 2.0 # Wider Stop for Breakout
                    tp_dist = curr['ATR'] * 4.0 # Wider TP
                else:
                     signal = None

            if 'signal' in locals() and signal == 'LONG':
                    # Sizing V5 (Compound)
                    risk = capital * 0.02
                    if sl_dist == 0: continue
                    
                    units = risk / sl_dist
                    
                    # JPY adjustment
                    if 'JPY' in symbol:
                        units = (risk * curr['Close']) / sl_dist
                        
                    amount_usd = (units * curr['Close']) if 'JPY' not in symbol else (units / curr['Close']) # Rough approx for exposure
                    
                    position = {
                        'entry': curr['Close'],
                        'units': units,
                        'sl': curr['Close'] - sl_dist,
                        'tp': curr['Close'] + tp_dist,
                        'time': df.index[i]
                    }
                    
        # EXIT
        elif position:
            pnl = 0
            reason = ""
            closed = False
            
            # Check Low/High for SL/TP
            if curr['Low'] <= position['sl']:
                exit_price = position['sl']
                reason = "SL"
                closed = True
            elif curr['High'] >= position['tp']:
                exit_price = position['tp']
                reason = "TP"
                closed = True
            elif curr['RSI'] > 75:
                exit_price = curr['Close']
                reason = "RSI_EXIT"
                closed = True
                
            if closed:
                diff = exit_price - position['entry']
                raw_pnl = diff * position['units']
                
                # JPY Adjustment for PnL
                if 'JPY' in symbol:
                     raw_pnl = raw_pnl / exit_price 
                
                capital += raw_pnl
                trades.append({'pnl': raw_pnl, 'reason': reason})
                position = None
                
    # RESULTS
    if trades:
        win_rate = len([t for t in trades if t['pnl'] > 0]) / len(trades) * 100
        pnl_pct = ((capital - 1000)/1000) * 100
        print("-" * 40)
        print(f"✅ RESULT ({len(trades)} trades)")
        print(f"Capital Final: ${capital:.2f} ({pnl_pct:+.2f}%)")
        print(f"Win Rate:      {win_rate:.1f}%")
        print("-" * 40)
    else:
        print("⚠️ No trades.")

if __name__ == "__main__":
    pairs = ['EURUSD=X', 'GBPUSD=X', 'JPY=X']
    for p in pairs:
        strat = 'TREND_PULLBACK'
        run_forex_backtest(p, strategy=strat)
