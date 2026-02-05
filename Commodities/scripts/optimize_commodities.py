
import sys
import os
import pandas as pd
import numpy as np
import yfinance as yf
from itertools import product

# Add lambda directory to path to import config and strategies
current_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.abspath(os.path.join(current_dir, '../lambda/commodities_trader'))
sys.path.append(lambda_dir)

from strategies import ForexStrategies

def calculate_local_indicators(df, strategy_type):
    # Reusing strategy logic but ensuring we have what we need
    return ForexStrategies.calculate_indicators(df, strategy_type)

def run_optimization():
    print("🚀 Optimization Commodities 2025 Started...\n")
    
    pairs = ['GC=F']
    
    for pair in pairs:
        print(f"--- Optimizing {pair} ---")
        try:
            df_raw = yf.download(pair, start="2024-03-01", end="2024-12-31", interval="1h", progress=False)
        except Exception as e:
            print(f"Skipping {pair}: {e}")
            continue

        if df_raw.empty:
            print(f"No data for {pair}")
            continue

        # Cleanup columns
        if isinstance(df_raw.columns, pd.MultiIndex):
            df_raw.columns = df_raw.columns.get_level_values(0)
        df_raw.columns = [c.lower() for c in df_raw.columns]
        
        # Strategy selection
        if 'GC' in pair:
            strategy = 'TREND_PULLBACK'
            # Params to scan
            rsi_range = [25, 30, 35, 40]
            sl_range = [1.5, 2.0, 2.5]
            tp_range = [3.0, 4.0, 5.0, 6.0]
            param_grid = list(product(rsi_range, sl_range, tp_range))
            param_names = ['rsi', 'sl', 'tp']
        else:
            strategy = 'BOLLINGER_BREAKOUT'
            sl_range = [1.0, 1.5, 2.0, 2.5]
            tp_range = [2.0, 3.0, 4.0, 5.0]
            param_grid = list(product(sl_range, tp_range))
            param_names = ['sl', 'tp']

        # Pre-calc indicators
        df = calculate_local_indicators(df_raw, strategy)
        
        # Convert to list of dicts for faster iteration
        records = df.to_dict('records')
        # We need index access for prev/next
        # records[i] does not give easy access to prev unless we use i-1
        
        best_pnl = -999999
        best_params = None
        best_stats = None

        print(f"Testing {len(param_grid)} combinations...")
        
        for params in param_grid:
            # Unpack params
            if strategy == 'TREND_PULLBACK':
                p_rsi, p_sl, p_tp = params
            else:
                p_sl, p_tp = params
            
            # Simulation
            trades = []
            open_trade = None
            
            for i in range(1, len(records)):
                row = records[i]
                prev = records[i-1]
                
                # Check Exit
                if open_trade:
                    pnl = 0
                    closed = False
                    
                    if open_trade['type'] == 'LONG':
                        if row['low'] <= open_trade['sl']:
                            pnl = open_trade['sl'] - open_trade['entry']
                            closed = True
                        elif row['high'] >= open_trade['tp']:
                            pnl = open_trade['tp'] - open_trade['entry']
                            closed = True
                    else:
                        if row['high'] >= open_trade['sl']:
                            pnl = open_trade['entry'] - open_trade['sl']
                            closed = True
                        elif row['low'] <= open_trade['tp']:
                            pnl = open_trade['entry'] - open_trade['tp']
                            closed = True
                            
                    if closed:
                        trades.append(pnl)
                        open_trade = None
                        
                # Check Entry (only if no position)
                if open_trade is None:
                    # Skip night (simplification of the 22-00 rule, just approximate)
                    # We don't have hour in dict unless we kept it.
                    # Let's assume the impact is uniform or ignore for optimization speed 
                    # (ideally we should check, but timestamps in dict keys might be missing if to_dict('records'))
                    # df index is lost in to_dict('records').
                    # Let's just trust the indicators for now.
                    
                    atr = row.get('ATR', 0)
                    if pd.isna(atr) or atr == 0: continue
                    
                    signal = None
                    entry_price = row['close']
                    
                    if strategy == 'TREND_PULLBACK':
                        sma = row.get('SMA_200')
                        rsi = row.get('RSI')
                        if sma and rsi and row['close'] > sma and rsi < p_rsi and atr > 0.0005:
                            signal = 'LONG'
                            
                    elif strategy == 'BOLLINGER_BREAKOUT':
                        bbu = row.get('BBU')
                        bbl = row.get('BBL')
                        pbbu = prev.get('BBU')
                        pbbl = prev.get('BBL')
                        
                        if bbu and pbbu:
                            if row['close'] > bbu and prev['close'] <= pbbu:
                                signal = 'LONG'
                            elif row['close'] < bbl and prev['close'] >= pbbl:
                                signal = 'SHORT'
                    
                    if signal:
                        sl_dist = atr * p_sl
                        tp_dist = atr * p_tp
                        
                        if signal == 'LONG':
                            sl = entry_price - sl_dist
                            tp = entry_price + tp_dist
                        else:
                            sl = entry_price + sl_dist
                            tp = entry_price - tp_dist
                            
                        open_trade = {'type': signal, 'entry': entry_price, 'sl': sl, 'tp': tp}

            # Evaluate
            if not trades:
                net_pnl = 0
            else:
                net_pnl = sum(trades)
                
            if net_pnl > best_pnl:
                best_pnl = net_pnl
                best_params = params
                best_stats = {
                    'trades': len(trades),
                    'win_rate': len([t for t in trades if t > 0]) / len(trades) * 100 if trades else 0
                }
        
        print(f"🏆 Best Result for {pair}:")
        print(f"   Params: {dict(zip(param_names, best_params))}")
        print(f"   PnL: {best_pnl:.2f}")
        print(f"   Trades: {best_stats['trades']}")
        print(f"   Win Rate: {best_stats['win_rate']:.1f}%")
        print("")

if __name__ == "__main__":
    run_optimization()
