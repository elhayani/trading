import pandas as pd
import pandas_ta as ta
import numpy as np
import os

# Configuration
INITIAL_CAPITAL = 1000
LEVERAGE = 30
RISK_PER_TRADE = 0.02
COMMISSION_PER_LOT = 7.0
SPREAD_PIPS = 1.0

def load_data():
    file_path = os.path.join(os.path.dirname(__file__), "../data/USDJPY_365d.csv")
    if not os.path.exists(file_path):
        print(f"❌ Fichier non trouvé: {file_path}")
        return None
    df = pd.read_csv(file_path)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('datetime', inplace=True)
    return df

def run_strategy(df, strategy_name, params):
    df = df.copy()
    
    # Indicateurs communs
    df['SMA_200'] = ta.sma(df['close'], length=200)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    df['RSI'] = ta.rsi(df['close'], length=14)
    
    # Bollinger
    bb = ta.bbands(df['close'], length=20, std=2.0)
    df = pd.concat([df, bb], axis=1)
    # Debug colonnes
    # print(df.columns)
    
    # Renommage dynamique (car pandas_ta inclut les params dans le nom)
    cols = df.columns
    bbu = [c for c in cols if c.startswith('BBU')][0]
    bbl = [c for c in cols if c.startswith('BBL')][0]
    bbm = [c for c in cols if c.startswith('BBM')][0]
    
    df.rename(columns={bbu: 'BBU', bbl: 'BBL', bbm: 'BBM'}, inplace=True)

    capital = INITIAL_CAPITAL
    trades = []
    position = None # 'LONG', 'SHORT'
    entry_price = 0
    sl = 0
    tp = 0
    
    start_idx = 200
    
    for i in range(start_idx, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        timestamp = df.index[i]
        
        # --- 1. GESTION SORTIE ---
        if position == 'LONG':
            exit_price = None
            if current['low'] <= sl: exit_price = sl
            elif current['high'] >= tp: exit_price = tp
            
            if exit_price:
                pnl = (exit_price - entry_price) * (capital * LEVERAGE / entry_price * RISK_PER_TRADE * 50) # Approx sizing logic corrected below
                # Precise Sizing
                risk_amt = INITIAL_CAPITAL * RISK_PER_TRADE
                dist = entry_price - sl
                if dist > 0:
                    units = risk_amt / dist
                    raw_pnl = (exit_price - entry_price) * units
                    pnl = raw_pnl - ((units/100000)*COMMISSION_PER_LOT)
                    capital += pnl
                    trades.append(pnl)
                    position = None

        elif position == 'SHORT':
            exit_price = None
            if current['high'] >= sl: exit_price = sl
            elif current['low'] <= tp: exit_price = tp
            
            if exit_price:
                risk_amt = INITIAL_CAPITAL * RISK_PER_TRADE
                dist = sl - entry_price
                if dist > 0:
                    units = risk_amt / dist
                    raw_pnl = (entry_price - exit_price) * units # Short PnL
                    pnl = raw_pnl - ((units/100000)*COMMISSION_PER_LOT)
                    capital += pnl
                    trades.append(pnl)
                    position = None

        # --- 2. GESTION ENTRÉE ---
        if position is None:
            signal = None # 'LONG', 'SHORT'
            
            # STRATÉGIE 1: TREND PULLBACK (Long + Short)
            if strategy_name == 'TREND_PULLBACK':
                # Long: Uptrend + Oversold
                if current['close'] > current['SMA_200'] and current['RSI'] < 35:
                    signal = 'LONG'
                # Short: Downtrend + Overbought
                elif current['close'] < current['SMA_200'] and current['RSI'] > 65:
                    signal = 'SHORT'

            # STRATÉGIE 2: BOLLINGER BREAKOUT (Suivi de tendance explosif)
            elif strategy_name == 'BOLLINGER_BREAKOUT':
                # Breakout UP
                if current['close'] > current['BBU'] and prev['close'] <= prev['BBU']:
                     signal = 'LONG'
                # Breakout DOWN
                elif current['close'] < current['BBL'] and prev['close'] >= prev['BBL']:
                     signal = 'SHORT'
            
            # STRATÉGIE 3: MEAN REVERSION (Contre tendance)
            elif strategy_name == 'MEAN_REVERSION':
                 # Buy dip
                 if current['RSI'] < 30: signal = 'LONG'
                 # Sell peak
                 elif current['RSI'] > 70: signal = 'SHORT'

            # --- EXÉCUTION ---
            if signal:
                atr = current['ATR']
                if atr > 0:
                    if signal == 'LONG':
                        entry_price = current['close'] + 0.0001
                        sl = entry_price - (params['sl_atr'] * atr)
                        tp = entry_price + (params['tp_atr'] * atr)
                        if (entry_price - sl) > 0: position = 'LONG'
                    elif signal == 'SHORT':
                        entry_price = current['close'] - 0.0001
                        sl = entry_price + (params['sl_atr'] * atr)
                        tp = entry_price - (params['tp_atr'] * atr)
                        if (sl - entry_price) > 0: position = 'SHORT'

    # Stats
    wins = len([t for t in trades if t > 0])
    total = len(trades)
    wr = (wins/total*100) if total > 0 else 0
    pnl = capital - INITIAL_CAPITAL
    
    return {'strategy': strategy_name, 'pnl': pnl, 'wr': wr, 'trades': total}

if __name__ == "__main__":
    print("🇯🇵 OPTIMISATION SPÉCIALE USDJPY (1 AN)")
    print("=======================================")
    
    df = load_data()
    if df is not None:
        # Params standards pour test
        params = {'sl_atr': 1.5, 'tp_atr': 3.0} 
        
        strats = ['TREND_PULLBACK', 'BOLLINGER_BREAKOUT', 'MEAN_REVERSION']
        
        for s in strats:
            res = run_strategy(df, s, params)
            icon = "✅" if res['pnl'] > 0 else "❌"
            print(f"{icon} {s:20}: PnL ${res['pnl']:8.2f} | WR {res['wr']:4.1f}% | Trades {res['trades']}")
            
        print("\nNote: Trend Pullback inclut maintenant les SHORTS.")
