import sys
import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timedelta

# --- CONFIGURATION PATHS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../lambda/commodities_trader')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../shared')))

try:
    from predictability_index import calculate_predictability_score
except ImportError:
    pass

def run_commodities_backtest(symbol, strategy='TREND_PULLBACK'):
    print(f"\n🛢️ BACKTEST V5.1 COMMODITIES: {symbol}")
    
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

    # 2. Indicators V5.1
    print("⚡ Calculating V5.1 Indicators...")
    
    # Trend
    df['SMA_200'] = ta.sma(df['Close'], length=200)
    df['EMA_50'] = ta.ema(df['Close'], length=50)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    
    # Bollinger (For Oil)
    bb = ta.bbands(df['Close'], length=20, std=2.0)
    # Map BB columns dynamically
    bbu_col = [c for c in bb.columns if 'BBU' in c][0]
    bbl_col = [c for c in bb.columns if 'BBL' in c][0]
    df['BBU'] = bb[bbu_col]
    df['BBL'] = bb[bbl_col]
    
    # RSI (For Gold)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    
    # Predictability (Rolling, vectorized approx) for Oil Filter
    returns = df['Close'].pct_change()
    rolling_autocorr = returns.rolling(window=50).corr(returns.shift(1))
    df['Pred_Score'] = (rolling_autocorr.fillna(0) + 1) * 50

    capital = 2000.0 # Commodities need margin
    balance = capital
    position = None
    trades = []
    
    for i in range(200, len(df)):
        curr = df.iloc[i]
        
        # ENTRY
        if position is None:
            # V5.1 Predictability Filter (Critical for Oil)
            # OIL needs score > 25. Gold is safer (> 15).
            min_score = 25 if 'CL=F' in symbol else 15
            if curr['Pred_Score'] < min_score:
                continue
                
            signal = None
            sl_dist = 0
            tp_dist = 0
            
            if strategy == 'TREND_PULLBACK': # GOLD
                # Relaxed Momentum (Price > SMA200 OR EMA50 > SMA200)
                is_uptrend = (curr['Close'] > curr['SMA_200']) 
                # Shallow Dip (RSI < 45)
                if is_uptrend and curr['RSI'] < 45:
                    signal = 'LONG'
                    sl_dist = curr['ATR'] * 3.0 # Wide Stop
                    tp_dist = curr['ATR'] * 3.0 # Conservative TP
                    
            elif strategy == 'BOLLINGER_BREAKOUT': # OIL
                # Breakout Upper Band + Momentum
                if curr['Close'] > curr['BBU']:
                    if curr['Close'] > curr['EMA_50']:
                        signal = 'LONG'
                        sl_dist = curr['ATR'] * 2.0
                        tp_dist = curr['ATR'] * 4.0 # Big Trend Target

            if signal == 'LONG':
                 # Sizing (Risk $200 fixed approx)
                 risk_amt = 200.0
                 if sl_dist == 0: continue
                 units = risk_amt / sl_dist
                 
                 # Cap leverage (Oil/Gold contracts are big)
                 # Simulating micro-contracts or CFDs
                 
                 position = {
                     'entry': curr['Close'],
                     'units': units,
                     'sl': curr['Close'] - sl_dist,
                     'tp': curr['Close'] + tp_dist,
                     'date': df.index[i]
                 }

        # EXIT
        elif position:
            reason = ""
            closed = False
            exit_price = 0
            
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
            # If moved 2x Risk in profit, move SL to Break Even
            if not closed:
                move_up = (curr['Close'] - position['entry']) > (position['entry'] - position['sl']) * 2
                if move_up and position['sl'] < position['entry']:
                    position['sl'] = position['entry']
            
            if closed:
                pnl = (exit_price - position['entry']) * position['units']
                balance += pnl
                trades.append({'pnl': pnl, 'reason': reason})
                position = None
                
    # RESULTS
    if trades:
        win_rate = len([t for t in trades if t['pnl'] > 0]) / len(trades) * 100
        pnl_pct = ((balance - capital)/capital) * 100
        print("-" * 40)
        print(f"✅ RESULT ({len(trades)} trades)")
        print(f"Capital Final: ${balance:.2f} ({pnl_pct:+.2f}%)")
        print(f"Win Rate:      {win_rate:.1f}%")
        print("-" * 40)
    else:
        print("⚠️ No trades.")

if __name__ == "__main__":
    # Gold (Trend Pullback)
    run_commodities_backtest('GC=F', strategy='TREND_PULLBACK')
    
    # Oil (Bollinger Breakout)
    run_commodities_backtest('CL=F', strategy='BOLLINGER_BREAKOUT')
