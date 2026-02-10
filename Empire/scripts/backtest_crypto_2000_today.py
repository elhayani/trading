
import sys
import os
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import time

# Add path to load market_analysis from lambda
current_dir = os.path.dirname(os.path.abspath(__file__))
# Empire/lambda/v4_trader
lambda_dir = os.path.abspath(os.path.join(current_dir, '../lambda/v4_trader'))
sys.path.append(lambda_dir)

try:
    from market_analysis import analyze_market
except ImportError:
    # Fallback if specific file structure differs
    print("⚠️ Could not import market_analysis. Using simplified internal logic.")
    def analyze_market(ohlcv_list):
        # basic fallback
        return {'indicators': {'rsi': 50, 'atr': 0, 'sma_50': 0}, 'patterns': []}

def fetch_data_yfinance(symbol, start_date="2000-01-01"):
    """
    Downloads data from Yahoo Finance from start_date to today.
    """
    print(f"📥 Downloading Max History for {symbol} (since {start_date})...")
    
    # Yahoo Ticker mapping
    yf_symbol = symbol.replace('/', '-') 
    # e.g., BTC/USDT -> BTC-USD (Yahoo convention usually)
    if yf_symbol.endswith('USDT'):
        yf_symbol = yf_symbol.replace('USDT', 'USD')
        
    try:
        # Fetch daily data for long history (Hourly data on Yahoo is limited to 730 days)
        # The user asked for "since 2000". We must use Daily (1d) timeframe for this duration.
        # Hourly data for 20 years is too huge and not available via free APIs usually.
        interval = "1d" 
        
        df = yf.download(yf_symbol, start=start_date, interval=interval, progress=True)
        
        if df.empty:
            print(f"❌ No data found for {yf_symbol}")
            return []

        # Reset index to get 'Date' as a column
        df = df.reset_index()
        
        # Standardize columns (Yahoo gives Date, Open, High, Low, Close, Adj Close, Volume)
        # We need list of [timestamp, open, high, low, close, volume]
        # Timestamp should be in milliseconds
        
        # Fix for multi-level columns in some yfinance versions
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        data = []
        for index, row in df.iterrows():
            try:
                dt = row['Date']
                timestamp = int(dt.timestamp() * 1000)
                open_ = float(row['Open'])
                high = float(row['High'])
                low = float(row['Low'])
                close = float(row['Close'])
                volume = float(row['Volume'])
                
                # Check for NaNs
                if np.isnan(close): continue
                
                data.append([timestamp, open_, high, low, close, volume])
            except Exception as e:
                continue
                
        print(f"✅ Loaded {len(data)} daily candles for {symbol} (Start: {data[0][0]}, End: {data[-1][0]})")
        return data
        
    except Exception as e:
        print(f"❌ Error downloading {symbol}: {e}")
        return []

def run_long_term_backtest(symbol):
    
    # 1. Fetch Data
    ohlcv = fetch_data_yfinance(symbol, start_date="2010-01-01") # Bitcoin starts ~2010
    
    if not ohlcv:
        return

    print(f"\n🔄 Running V4 Simulation on {symbol} (Daily Timeframe)...")
    
    # 2. Simulation
    capital = 1000.0
    initial_capital = capital
    position = None
    trades = []
    
    # Parameters for Daily Timeframe (adjusted from Hourly)
    # V4 Hybrid adjusted for Daily
    sma_period = 50 
    rsi_period = 14
    
    # We need to buffer data for indicators
    
    for i in range(sma_period, len(ohlcv)):
        # Window for analysis
        # We simulate that we are at the CLOSE of day 'i' making decision for next day OPEN or close of day i
        
        # Slice data up to i
        window = ohlcv[max(0, i-60):i+1] # Need at least 50+ for SMA
        current_candle = window[-1]
        timestamp = current_candle[0]
        date_str = datetime.fromtimestamp(timestamp/1000).strftime('%Y-%m-%d')
        price = current_candle[4] # Close
        
        # Compute simplified indicators locally to avoid complex dependency issues with timeframe mismatch
        # (market_analysis might be tuned for hourly)
        closes = [x[4] for x in window]
        
        # SMA 50
        if len(closes) < 50: continue
        sma_50 = sum(closes[-50:]) / 50
        
        # RSI 14
        deltas = np.diff(closes)
        seed = deltas[:14+1]
        up = seed[seed >= 0].sum()/14
        down = -seed[seed < 0].sum()/14
        rs = up/down if down != 0 else 0
        rsi = 100 - 100/(1+rs)
        
        # Smoothing RSI (Wilder's) - simplified here: standard RSI on last 14
        # Re-calc standard RSI for accuracy
        series_closes = pd.Series(closes)
        delta = series_closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi_series = 100 - (100 / (1 + rs))
        rsi = rsi_series.iloc[-1]
        
        # STRATEGY LOGIC (V4 HYBRID Simplified for Daily)
        
        # Trend Filter
        is_uptrend = price > sma_50
        
        # Entry
        if position is None:
            # Buy if RSI oversold in Uptrend
            # Daily RSI oversold is rare in bull runs, usually 40-50 is "dip"
            if rsi < 45 and is_uptrend:
                # Buy
                qty = capital / price
                position = {
                    'entry_price': price,
                    'qty': qty,
                    'date': date_str,
                    'highest_price': price
                }
                # print(f"🟢 [BUY] {date_str} @ {price:.2f} (RSI: {rsi:.1f})")
                
        # Exit
        elif position:
            # Update Highest Price for Trailing
            if price > position['highest_price']:
                position['highest_price'] = price
                
            # Trailing Stop: 15% from highest (Wide stop for crypto swing)
            trailing_stop = position['highest_price'] * 0.85
            
            # RSI Overbought Exit
            rsi_exit = rsi > 75
            
            # Hard Stop Loss (Fixed 10%)
            stop_loss = position['entry_price'] * 0.90
            
            reason = ""
            if price < trailing_stop:
                reason = "Trailing Stop"
            elif price < stop_loss:
                reason = "Stop Loss"
            elif rsi_exit:
                reason = "RSI Overbought"
                
            if reason:
                # Sell
                revenue = position['qty'] * price
                pnl = revenue - capital
                pnl_pct = (pnl / capital) * 100
                
                capital = revenue
                trades.append({
                    'entry_date': position['date'],
                    'exit_date': date_str,
                    'pnl_pct': pnl_pct,
                    'reason': reason,
                    'profit': pnl
                })
                
                # print(f"🔴 [SELL] {date_str} @ {price:.2f} | PnL: {pnl_pct:+.2f}% | {reason}")
                position = None

    # Final Stats
    total_trades = len(trades)
    if total_trades > 0:
        win_rate = len([t for t in trades if t['profit'] > 0]) / total_trades * 100
        avg_profit = np.mean([t['pnl_pct'] for t in trades])
    else:
        win_rate = 0
        avg_profit = 0
        
    final_perf = ((capital - initial_capital) / initial_capital) * 100
    
    print("\n" + "="*40)
    print(f"📊 REPORT: {symbol} (2014 - Today)")
    print("="*40)
    print(f"Initial Capital : ${initial_capital:.2f}")
    print(f"Final Capital   : ${capital:.2f}")
    print(f"Net Return      : {final_perf:+.2f}%")
    print(f"Total Trades    : {total_trades}")
    print(f"Win Rate        : {win_rate:.1f}%")
    print(f"Avg Trade       : {avg_profit:+.2f}%")
    print("="*40 + "\n")

if __name__ == "__main__":
    print("🚀 STARTING LONG TERM BACKTEST (Since 2000/Inception)")
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    for s in symbols:
        run_long_term_backtest(s)
