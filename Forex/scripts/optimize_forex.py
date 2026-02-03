import pandas as pd
import pandas_ta as ta
import numpy as np
import os
import itertools
from tabulate import tabulate

# Configuration de base
INITIAL_CAPITAL = 1000
LEVERAGE = 30
RISK_PER_TRADE = 0.02
COMMISSION_PER_LOT = 7.0
SPREAD_PIPS = 1.0

def load_data(pair):
    file_path = os.path.join(os.path.dirname(__file__), f"../data/{pair}_90d.csv")
    if not os.path.exists(file_path):
        return None
    df = pd.read_csv(file_path)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('datetime', inplace=True)
    return df

def run_backtest_with_params(df, params):
    # Unpack params
    sma_period = params['sma_period']
    rsi_period = 14
    atr_period = 14
    rsi_threshold = params['rsi_threshold']
    sl_mult = params['sl_mult']
    tp_mult = params['tp_mult']
    
    # Check if indicators need recalc (optimization speedup likely negligible here)
    df = df.copy()
    df['SMA'] = ta.sma(df['close'], length=sma_period)
    df['RSI'] = ta.rsi(df['close'], length=rsi_period)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=atr_period)
    
    capital = INITIAL_CAPITAL
    trades = []
    position = None
    entry_price = 0
    sl = 0
    tp = 0
    units = 0
    
    # Skip warmup
    start_idx = max(sma_period, rsi_period, atr_period)
    
    for i in range(start_idx, len(df)):
        current = df.iloc[i]
        timestamp = df.index[i]
        
        # 1. EXIT LOGIC
        if position == 'LONG':
            exit_price = None
            exit_type = None
            
            if current['low'] <= sl:
                exit_price = sl
                exit_type = 'SL'
            elif current['high'] >= tp:
                exit_price = tp
                exit_type = 'TP'
                
            if exit_price:
                raw_pnl = (exit_price - entry_price) * units
                commission = (units / 100000) * COMMISSION_PER_LOT
                net_pnl = raw_pnl - commission
                capital += net_pnl
                trades.append(net_pnl)
                position = None
        
        # 2. ENTRY LOGIC
        if position is None:
            # Trend Check
            if current['close'] > current['SMA']:
                 # Signal Check
                 if current['ATR'] > 0.0010 and current['RSI'] < rsi_threshold:
                    entry_price = current['close'] + (SPREAD_PIPS * 0.0001)
                    sl = entry_price - (sl_mult * current['ATR'])
                    tp = entry_price + (tp_mult * current['ATR'])
                    
                    risk_amt = capital * RISK_PER_TRADE
                    dist_sl = entry_price - sl
                    
                    if dist_sl > 0:
                        units = risk_amt / dist_sl
                        max_units = (capital * LEVERAGE) / entry_price
                        units = min(units, max_units)
                        
                        if units > 0:
                            position = 'LONG'

    # Stats
    total_trades = len(trades)
    wins = len([p for p in trades if p > 0])
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
    final_pnl = capital - INITIAL_CAPITAL
    
    return {
        'params': params,
        'pnl': final_pnl,
        'trades': total_trades,
        'win_rate': win_rate
    }

def optimize(pair):
    print(f"\n🔍 Optimisation pour {pair}...")
    df = load_data(pair)
    if df is None:
        print("Data not found")
        return

    # Grille de paramètres
    param_grid = {
        'sma_period': [50, 200],
        'rsi_threshold': [30, 35, 40, 45, 50],
        'sl_mult': [1.0, 1.5, 2.0],
        'tp_mult': [2.0, 3.0, 4.0]
    }
    
    keys, values = zip(*param_grid.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    results = []
    for combo in combinations:
        res = run_backtest_with_params(df, combo)
        results.append(res)
        
    # Sort by PnL
    results.sort(key=lambda x: x['pnl'], reverse=True)
    
    # Display Top 5
    headers = ["SMA", "RSI <", "SL (ATR)", "TP (ATR)", "Trades", "Win Rate", "PnL ($)"]
    table_data = []
    
    for r in results[:5]:
        p = r['params']
        table_data.append([
            p['sma_period'],
            p['rsi_threshold'],
            p['sl_mult'],
            p['tp_mult'],
            r['trades'],
            f"{r['win_rate']:.1f}%",
            f"${r['pnl']:.2f}"
        ])
        
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    return results[0] # Return best

if __name__ == "__main__":
    pairs = ['GBPUSD', 'EURUSD', 'USDJPY']
    for pair in pairs:
        optimize(pair)
