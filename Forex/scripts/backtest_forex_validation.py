import pandas as pd
import pandas_ta as ta
import numpy as np
import os
from datetime import datetime, timedelta

# Configuration
INITIAL_CAPITAL = 1000
LEVERAGE = 30
COMMISSION_PER_LOT = 7.0
SPREAD_PIPS = 1.0

def load_data(pair, days=700):
    file_path = os.path.join(os.path.dirname(__file__), f"../data/{pair}_{days}d.csv")
    if not os.path.exists(file_path):
        return None
    df = pd.read_csv(file_path)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('datetime', inplace=True)
    return df

def run_strategy(df, strategy, params):
    df = df.copy()
    
    # Indicateurs
    if strategy == 'TREND_PULLBACK':
        df['SMA'] = ta.sma(df['close'], length=200)
        df['RSI'] = ta.rsi(df['close'], length=14)
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    elif strategy == 'BOLLINGER_BREAKOUT':
        bb = ta.bbands(df['close'], length=20, std=2.0)
        df = pd.concat([df, bb], axis=1)
        cols = df.columns
        bbu = [c for c in cols if c.startswith('BBU')][0]
        bbl = [c for c in cols if c.startswith('BBL')][0]
        df.rename(columns={bbu: 'BBU', bbl: 'BBL'}, inplace=True)
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)

    capital = INITIAL_CAPITAL
    trades = []
    position = None 
    entry_price = 0
    sl = 0
    tp = 0
    
    start_idx = 200
    
    for i in range(start_idx, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        
        # --- EXIT ---
        if position:
            exit_price = None
            if position == 'LONG':
                if current['low'] <= sl: exit_price = sl
                elif current['high'] >= tp: exit_price = tp
            elif position == 'SHORT':
                if current['high'] >= sl: exit_price = sl
                elif current['low'] <= tp: exit_price = tp
            
            if exit_price:
                risk_amt = capital * 0.02
                dist = abs(entry_price - sl)
                if dist > 0:
                    units = risk_amt / dist
                    raw_pnl = (exit_price - entry_price) * units if position == 'LONG' else (entry_price - exit_price) * units
                    pnl = raw_pnl - ((units/100000)*COMMISSION_PER_LOT)
                    capital += pnl
                    trades.append(pnl)
                    position = None

        # --- ENTRY ---
        if position is None:
            signal = None
            
            if strategy == 'TREND_PULLBACK':
                # Long Only for EURUSD/GBPUSD as approved
                if current['close'] > current['SMA']:
                    if current['RSI'] < 35: # Optimized Param
                         signal = 'LONG'

            elif strategy == 'BOLLINGER_BREAKOUT':
                # Up and Down
                if current['close'] > current['BBU'] and prev['close'] <= prev['BBU']:
                    signal = 'LONG'
                elif current['close'] < current['BBL'] and prev['close'] >= prev['BBL']:
                    signal = 'SHORT'
            
            if signal:
                atr = current['ATR']
                if atr > 0:
                    sl_mult = params['sl']
                    tp_mult = params['tp']
                    
                    if signal == 'LONG':
                        entry_price = current['close'] + 0.0001
                        sl = entry_price - (sl_mult * atr)
                        tp = entry_price + (tp_mult * atr)
                        if (entry_price - sl) > 0: position = 'LONG'
                    elif signal == 'SHORT':
                        entry_price = current['close'] - 0.0001
                        sl = entry_price + (sl_mult * atr)
                        tp = entry_price - (tp_mult * atr)
                        if (sl - entry_price) > 0: position = 'SHORT'

    pnl_total = capital - INITIAL_CAPITAL
    return pnl_total

if __name__ == "__main__":
    print("🛡️ VALIDATION OUT-OF-SAMPLE (Crash Test Année Précédente)")
    print("=========================================================")
    
    pairs_config = [
        {'pair': 'EURUSD', 'strat': 'TREND_PULLBACK', 'params': {'sl': 1.0, 'tp': 3.0}},
        {'pair': 'GBPUSD', 'strat': 'TREND_PULLBACK', 'params': {'sl': 1.0, 'tp': 3.0}},
        {'pair': 'USDJPY', 'strat': 'BOLLINGER_BREAKOUT', 'params': {'sl': 1.5, 'tp': 3.0}}
    ]

    for cfg in pairs_config:
        df = load_data(cfg['pair'], 700)
        if df is None: continue
        
        # Split Data
        mid_point = len(df) // 2
        df_old = df.iloc[:mid_point]  # Année N-1 (Test)
        df_recent = df.iloc[mid_point:] # Année N (Validation)
        
        print(f"\n🔹 {cfg['pair']} ({cfg['strat']})")
        
        # Test Année N (Confirm)
        pnl_recent = run_strategy(df_recent, cfg['strat'], cfg['params'])
        icon_n = "✅" if pnl_recent > 0 else "❌"
        print(f"   📅 Année N (Récents): {icon_n} ${pnl_recent:.2f}")

        # Test Année N-1 (Crash Test)
        pnl_old = run_strategy(df_old, cfg['strat'], cfg['params'])
        icon_old = "✅" if pnl_old > 0 else "❌"
        print(f"   📅 Année N-1 (Passé): {icon_old} ${pnl_old:.2f}")
        
        if pnl_old > 0 and pnl_recent > 0:
            print(f"   🏆 ROBUSTE ! (Gagnant sur 2 ans)")
        elif pnl_recent > 0 and pnl_old < 0:
             print(f"   ⚠️ RISQUE (Optimisé sur l'année récente seulement)")
        else:
             print(f"   💀 ÉCHEC (Instable)")

    print("\n=========================================================")
