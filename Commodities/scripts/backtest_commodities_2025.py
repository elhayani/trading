
import sys
import os
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# Add lambda directory to path to import config and strategies
current_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.abspath(os.path.join(current_dir, '../lambda/commodities_trader'))
sys.path.append(lambda_dir)

from strategies import ForexStrategies
from config import CONFIGURATION

def run_backtest():
    print("🚀 Backtest Commodities 2025 Started...")
    
    results = {}
    
    for pair, config in CONFIGURATION.items():
        if not config.get('enabled', True):
            continue
            
        print(f"\n🔍 Testing {pair} ({config['strategy']})...")
        
        # 1. Download Data (2025)
        # Using 1h interval for 2025
        # yfinance expects ticker. For GC=F, it works.
        try:
            df = yf.download(pair, start="2025-01-01", end="2025-12-31", interval="1h", progress=False)
        except Exception as e:
            print(f"❌ Failed to download {pair}: {e}")
            continue
            
        if df.empty:
            print(f"⚠️ No data found for {pair}")
            continue
            
        # Cleanup columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        
        # 2. Indicators
        # We reuse the strategy logic to calculate indicators
        df = ForexStrategies.calculate_indicators(df, config['strategy'])
        
        # 3. Simulation Loop
        balance = 10000.0
        equity_curve = [balance]
        trades = []
        open_trade = None
        
        params = config['params']
        strategy_name = config['strategy']
        
        # Need previous row access
        # Convert to records for speed or just iterrows
        # Iterrows is slow, but fine for 1 year 1h (~6000 rows)
        
        rows = list(df.iterrows())
        
        for i in range(1, len(rows)):
            ts, row = rows[i]
            prev_ts, prev_row = rows[i-1]
            
            # Check Exit if Open
            if open_trade:
                # Basic exit logic: Hit TP or SL in this candle?
                # We assume we check Low/High vs SL/TP
                
                # Check for SL Hit
                sl_hit = False
                tp_hit = False
                pnl = 0
                
                if open_trade['type'] == 'LONG':
                    if row['low'] <= open_trade['sl']:
                        sl_hit = True
                        pnl = (open_trade['sl'] - open_trade['entry']) # Loss
                    elif row['high'] >= open_trade['tp']:
                        tp_hit = True
                        pnl = (open_trade['tp'] - open_trade['entry']) # Profit
                else: # SHORT
                    if row['high'] >= open_trade['sl']:
                        sl_hit = True
                        pnl = (open_trade['entry'] - open_trade['sl']) # Loss
                    elif row['low'] <= open_trade['tp']:
                        tp_hit = True
                        pnl = (open_trade['entry'] - open_trade['tp']) # Profit
                
                if sl_hit or tp_hit:
                    # Closing Trade
                    # Adjust PnL for contract size roughly?
                    # For GC (Gold), 1 point = $100? No, let's keep it raw price points for now 
                    # OR we simulation $1 per point for simplicity to test edge.
                    # Or better: Assume 1 unit.
                    
                    trades.append({
                        'entry_time': open_trade['ts'],
                        'exit_time': ts,
                        'type': open_trade['type'],
                        'entry': open_trade['entry'],
                        'exit': open_trade['sl'] if sl_hit else open_trade['tp'],
                        'pnl_points': pnl,
                        'result': 'WIN' if pnl > 0 else 'LOSS'
                    })
                    open_trade = None
            
            # Check Entry if No Open Trade
            if open_trade is None:
                # Time filter (Skip 22:00-00:00)
                if ts.hour >= 22 or ts.hour == 0:
                    continue
                    
                atr = row.get('ATR', 0)
                if pd.isna(atr) or atr == 0: continue
                
                signal = None
                
                if strategy_name == 'TREND_PULLBACK':
                    sma200 = row.get('SMA_200')
                    rsi = row.get('RSI')
                    
                    if sma200 and not pd.isna(sma200) and rsi and not pd.isna(rsi):
                        # Long Condition
                        if row['close'] > sma200 and rsi < params.get('rsi_oversold', 30):
                             if atr > 0.0005: # Min volatility
                                signal = 'LONG'
                                
                elif strategy_name == 'BOLLINGER_BREAKOUT':
                    bbu = row.get('BBU')
                    bbl = row.get('BBL')
                    prev_bbu = prev_row.get('BBU')
                    prev_bbl = prev_row.get('BBL')
                    
                    if bbu and prev_bbu:
                        # Long Breakout
                        if row['close'] > bbu and prev_row['close'] <= prev_bbu:
                            signal = 'LONG'
                        # Short Breakout
                        elif row['close'] < bbl and prev_row['close'] >= prev_bbl:
                            signal = 'SHORT'
                            
                if signal:
                    sl_dist = atr * params['sl_atr_mult']
                    tp_dist = atr * params['tp_atr_mult']
                    
                    if signal == 'LONG':
                        sl = row['close'] - sl_dist
                        tp = row['close'] + tp_dist
                    else:
                        sl = row['close'] + sl_dist
                        tp = row['close'] - tp_dist
                        
                    open_trade = {
                        'ts': ts,
                        'type': signal,
                        'entry': row['close'],
                        'sl': sl,
                        'tp': tp
                    }
                    
        # Analyze Results
        if not trades:
            print("  ➡️ No trades generated.")
        else:
            wins = len([t for t in trades if t['pnl_points'] > 0])
            total = len(trades)
            win_rate = (wins / total) * 100
            total_pnl = sum([t['pnl_points'] for t in trades])
            
            print(f"  📊 Trades: {total}")
            print(f"  ✅ Win Rate: {win_rate:.1f}%")
            print(f"  💰 Net PnL (Points): {total_pnl:.2f}")
            print(f"  📉 Avg Win: {sum([t['pnl_points'] for t in trades if t['pnl_points']>0])/wins if wins else 0:.2f}")
            print(f"  📈 Avg Loss: {sum([t['pnl_points'] for t in trades if t['pnl_points']<=0])/(total-wins) if (total-wins) else 0:.2f}")

if __name__ == "__main__":
    run_backtest()
