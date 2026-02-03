import pandas as pd
import pandas_ta as ta
import numpy as np
import os
from datetime import datetime

# Configuration
INITIAL_CAPITAL = 1000
LEVERAGE = 30
RISK_PER_TRADE = 0.02

# PARAMÈTRES (Optimisés sur 90j, test sur 1 an)
SMA_PERIOD = 200
RSI_THRESHOLD = 35
SL_ATR_MULT = 1.0
TP_ATR_MULT = 3.0

COMMISSION_PER_LOT = 7.0
SPREAD_PIPS = 1.0

def load_data(pair, days=365):
    file_path = os.path.join(os.path.dirname(__file__), f"../data/{pair}_{days}d.csv")
    if not os.path.exists(file_path):
        print(f"❌ Fichier non trouvé: {file_path}")
        return None
    df = pd.read_csv(file_path)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('datetime', inplace=True)
    return df

def calculate_indicators(df):
    df['SMA'] = ta.sma(df['close'], length=SMA_PERIOD)
    df['RSI'] = ta.rsi(df['close'], length=14)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    return df

def run_backtest(pair, df):
    capital = INITIAL_CAPITAL
    trades = []
    position = None
    entry_price = 0
    sl = 0
    tp = 0
    
    print(f"\n🚀 Backtest 1 AN: {pair}")
    
    start_idx = SMA_PERIOD
    
    for i in range(start_idx, len(df)):
        current = df.iloc[i]
        timestamp = df.index[i]
        
        # 1. EXIT
        if position == 'LONG':
            exit_price = None
            reason = ""
            
            if current['low'] <= sl:
                exit_price = sl
                reason = "SL"
            elif current['high'] >= tp:
                exit_price = tp
                reason = "TP"
                
            if exit_price:
                risk_amt = INITIAL_CAPITAL * RISK_PER_TRADE
                dist_sl = entry_price - sl
                units = risk_amt / dist_sl
                max_units = (capital * LEVERAGE) / entry_price
                units = min(units, max_units)
                
                raw_pnl = (exit_price - entry_price) * units
                commission = (units / 100000) * COMMISSION_PER_LOT
                net_pnl = raw_pnl - commission
                
                capital += net_pnl
                trades.append({
                    'type': reason,
                    'pnl': net_pnl,
                    'time': timestamp
                })
                position = None
                
        # 2. ENTRY
        if position is None:
            if current['close'] > current['SMA']: # Trend
                if current['ATR'] > 0.0010: # Vol
                    if current['RSI'] < RSI_THRESHOLD: # Signal
                        entry_price = current['close'] + (SPREAD_PIPS * 0.0001)
                        sl = entry_price - (SL_ATR_MULT * current['ATR'])
                        tp = entry_price + (TP_ATR_MULT * current['ATR'])
                        if (entry_price - sl) > 0:
                            position = 'LONG'

    # Stats
    wins = len([t for t in trades if t['pnl'] > 0])
    losses = len([t for t in trades if t['pnl'] <= 0])
    total = wins + losses
    win_rate = (wins/total * 100) if total > 0 else 0
    pnl_total = capital - INITIAL_CAPITAL
    
    # Max Drawdown
    balance_curve = [INITIAL_CAPITAL]
    curr_bal = INITIAL_CAPITAL
    dd_max = 0
    for t in trades:
        curr_bal += t['pnl']
        balance_curve.append(curr_bal)
        peak = max(balance_curve)
        dd = (peak - curr_bal) / peak * 100
        if dd > dd_max: dd_max = dd

    return {
        'pair': pair,
        'final_capital': capital,
        'pnl_abs': pnl_total,
        'pnl_pct': (pnl_total / INITIAL_CAPITAL) * 100,
        'total_trades': total,
        'win_rate': win_rate,
        'max_dd': dd_max
    }

if __name__ == "__main__":
    pairs = ['EURUSD', 'GBPUSD', 'USDJPY']
    
    print("🌍 RÉSULTATS BACKTEST 1 AN (365 jours)")
    print("=======================================")
    
    total_pnl = 0
    
    for pair in pairs:
        try:
            df = load_data(pair, 365)
            if df is not None:
                df = calculate_indicators(df)
                res = run_backtest(pair, df)
                
                icon = "✅" if res['pnl_abs'] > 0 else "❌"
                print(f"{icon} {pair}: PnL ${res['pnl_abs']:.2f} ({res['pnl_pct']:.2f}%) | WR: {res['win_rate']:.1f}% | Trades: {res['total_trades']} | DD: {res['max_dd']:.2f}%")
                total_pnl += res['pnl_abs']
        except Exception as e:
            print(f"Erreur {pair}: {e}")
            
    print("=======================================")
    print(f"💰 PNL TOTAL: ${total_pnl:.2f}")
