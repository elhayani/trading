import sys
import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timedelta, time
import pytz

# --- CONFIGURATION PATHS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../lambda/indices_trader')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../shared')))

try:
    from predictability_index import calculate_predictability_score
except ImportError:
    pass

# --- V5.1 INDICES ENGINE ---
def run_indices_backtest(symbol, strategy='BOLLINGER_BREAKOUT'):
    print(f"\n🎢 BACKTEST V5.1 INDICES: {symbol}")
    
    # 1. Fetch Data (2 Years H1)
    start_date = (datetime.now() - timedelta(days=729)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"📥 Fetching 1h data ({start_date} -> {end_date})...")
    df = yf.download(symbol, start=start_date, end=end_date, interval="1h", progress=False)
    
    if df.empty:
        print("❌ No Data.")
        return

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 2. Indicators (Vectorized)
    print("⚡ Calculating V5.1 Indicators...")
    
    # Trend
    df['SMA_200'] = ta.sma(df['Close'], length=200)
    df['EMA_50'] = ta.ema(df['Close'], length=50)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    
    # Bollinger
    bb = ta.bbands(df['Close'], length=20, std=2.0)
    df = pd.concat([df, bb], axis=1)
    # Rename for clarity if needed, pandas_ta uses BBL_20_2.0 etc.
    # We'll use dynamic column lookup
    
    # RSI
    df['RSI'] = ta.rsi(df['Close'], length=14)
    
    # Predictability (Rolling Approx)
    returns = df['Close'].pct_change()
    rolling_autocorr = returns.rolling(window=50).corr(returns.shift(1))
    df['Pred_Score'] = (rolling_autocorr.fillna(0) + 1) * 50
    
    # 3. Time Filter (US Session Only: 15:30 - 22:00 Paris)
    # YFinance 1h data timestamps are usually UTC or Exchange Time (NY).
    # ^GSPC, ^NDX are US, so timestamps are America/New_York usually, or UTC.
    # Let's assume input is UTC. US Open 9:30 AM ET = 14:30 UTC (Winter) / 13:30 UTC (Summer).
    # To be robust, we look at the Hour in the timestamp.
    # US Session ~ 13h-20h UTC.
    
    capital = 10000.0 # Indices need more capital
    position = None
    trades = []
    
    # Identify BB Cols
    bbu_col = [c for c in df.columns if 'BBU' in c][0]
    bbl_col = [c for c in df.columns if 'BBL' in c][0]
    
    for i in range(200, len(df)):
        curr = df.iloc[i]
        ts = df.index[i]
        
        # TIME FILTER (Target US Session Volume)
        # Simple heuristic: Trade between 14h and 21h (UTC approx)
        if ts.hour < 14 or ts.hour > 21:
            # Force Close at End of Day for Day Trading? 
            # V5.1 Fortress Indices can hold Swing if Trend is Strong.
            # But we prefer entering during active hours.
            can_enter = False
        else:
            can_enter = True
            
        # ENTRY
        if position is None and can_enter:
            # V5.1 Predictability Filter (Lower threshold for Indices: 15)
            if curr['Pred_Score'] < 15:
                continue
                
            # STRATEGY: BOLLINGER BREAKOUT (Follow the Trend)
            if strategy == 'BOLLINGER_BREAKOUT':
                # Long Breakout
                if curr['Close'] > curr[bbu_col]:
                    # Confirm Trend (Price > EMA50)
                    if curr['Close'] > curr['EMA_50']:
                         signal = 'LONG'
                         sl_dist = curr['ATR'] * 2.0
                         tp_dist = curr['ATR'] * 5.0 # Let winners run
                         
                         # Position Sizing
                         risk_amt = capital * 0.02
                         units = risk_amt / sl_dist
                         # Cap leverage to 5x for Indices
                         max_units = (capital * 5) / curr['Close']
                         units = min(units, max_units)
                         
                         position = {
                             'entry': curr['Close'],
                             'units': units,
                             'sl': curr['Close'] - sl_dist,
                             'tp': curr['Close'] + tp_dist,
                             'time': ts
                         }

        # EXIT
        elif position:
            pnl = 0
            reason = ""
            closed = False
            
            # SL/TP
            if curr['Low'] <= position['sl']:
                exit_price = position['sl']
                reason = "SL"
                closed = True
            elif curr['High'] >= position['tp']:
                exit_price = position['tp']
                reason = "TP"
                closed = True
            
            # Trailing Stop V5.1 (Secure profits)
            # If price moves 2x ATR in our favor, move SL to Entry
            if not closed:
                move_up = (curr['Close'] - position['entry']) > (2 * curr['ATR'])
                if move_up and position['sl'] < position['entry']:
                    position['sl'] = position['entry'] # Break Even
                    
            if closed:
                pnl = (exit_price - position['entry']) * position['units']
                capital += pnl
                trades.append({'pnl': pnl, 'reason': reason})
                position = None
                
    # RESULTS
    if trades:
        win_rate = len([t for t in trades if t['pnl'] > 0]) / len(trades) * 100
        pnl_pct = ((capital - 10000)/10000) * 100
        print("-" * 40)
        print(f"✅ RESULT ({len(trades)} trades)")
        print(f"Capital Final: ${capital:.2f} ({pnl_pct:+.2f}%)")
        print(f"Win Rate:      {win_rate:.1f}%")
        print("-" * 40)
    else:
        print("⚠️ No trades.")

if __name__ == "__main__":
    # Nasdaq, S&P 500, Dow Jones
    symbols = ['^NDX', '^GSPC', '^DJI']
    for sym in symbols:
        run_indices_backtest(sym)
