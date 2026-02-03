import pandas as pd
import pandas_ta as ta
import numpy as np
import os
from datetime import datetime

# Configuration
INITIAL_CAPITAL = 1000
LEVERAGE = 30
RISK_PER_TRADE = 0.02  # 2% du capital par trade
COMMISSION_PER_LOT = 7.0  # $7 par round turn lot (standard ECN)
SPREAD_PIPS = 1.0  # 1 pip de spread moyen

def load_data(pair):
    """Charge les données CSV locales"""
    file_path = os.path.join(os.path.dirname(__file__), f"../data/{pair}_90d.csv")
    if not os.path.exists(file_path):
        print(f"❌ Fichier non trouvé: {file_path}")
        return None
    
    df = pd.read_csv(file_path)
    # Conversion timestamp ms -> datetime
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('datetime', inplace=True)
    return df

def calculate_indicators(df):
    """Calcule les indicateurs techniques"""
    # SMA 50 pour la tendance
    df['SMA_50'] = ta.sma(df['close'], length=50)
    
    # RSI 14 pour les entrées
    df['RSI'] = ta.rsi(df['close'], length=14)
    
    # ATR 14 pour la volatilité et SL/TP
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    return df

def run_backtest(pair, df):
    """Exécute le backtest sur une paire"""
    capital = INITIAL_CAPITAL
    balance_history = [capital]
    trades = []
    
    position = None  # None, 'LONG', 'SHORT'
    entry_price = 0
    sl = 0
    tp = 0
    lot_size = 0
    
    print(f"\n🚀 Démarrage Backtest: {pair}")
    print(f"   Capital Init: ${capital}, Levier: {LEVERAGE}x")
    
    for i in range(50, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        timestamp = df.index[i]
        
        # 1. GESTION DES POSITIONS OUVERTES
        if position == 'LONG':
            # Check SL
            if current['low'] <= sl:
                exit_price = sl
                pnl = (exit_price - entry_price) * lot_size * 100000 # Standard lot const
                # Apply leverage/margin logic simplified for PnL
                # PnL = (Price Diff) * Units
                units = (capital * RISK_PER_TRADE * LEVERAGE) / current['close'] # Simple sizing logic fix later
                
                # Correct sizing: Risk Amount / Distance to SL
                risk_amount = capital * RISK_PER_TRADE
                sl_distance_pips = (entry_price - sl)
                if sl_distance_pips <= 0: continue
                
                pip_value = 10 # Standard $10/pip pro lot
                # Calculation is tricky without exact pip value per pair, assuming USD quote currency (EURUSD, GBPUSD)
                
                # Simplified PnL calculation
                raw_pnl = (exit_price - entry_price) * units 
                commission = (units / 100000) * COMMISSION_PER_LOT
                net_pnl = raw_pnl - commission
                
                capital += net_pnl
                trades.append({
                    'type': 'SL',
                    'entry': entry_price,
                    'exit': exit_price,
                    'pnl': net_pnl,
                    'time': timestamp
                })
                position = None
                
            # Check TP
            elif current['high'] >= tp:
                exit_price = tp
                raw_pnl = (exit_price - entry_price) * units
                commission = (units / 100000) * COMMISSION_PER_LOT
                net_pnl = raw_pnl - commission
                
                capital += net_pnl
                trades.append({
                    'type': 'TP',
                    'entry': entry_price,
                    'exit': exit_price,
                    'pnl': net_pnl,
                    'time': timestamp
                })
                position = None
                
        # 2. LOGIQUE D'ENTRÉE (STRATÉGIE)
        if position is None:
            # Filtre Tendance: Prix > SMA 50
            is_uptrend = current['close'] > current['SMA_50']
            
            # Filtre Volatilité: ATR suffisant (ex: > 10 pips)
            # Pour EURUSD 0.0010
            min_volatility = 0.0010 
            is_volatile = current['ATR'] > min_volatility
            
            # Signal: Pullback (RSI < 40 en tendance haussière) - Ajusté à 40 pour plus de trades
            is_oversold = current['RSI'] < 45 
            
            if is_uptrend and is_volatile and is_oversold:
                # ENTRY LONG
                entry_price = current['close'] + (SPREAD_PIPS * 0.0001)
                atr = current['ATR']
                
                # SL & TP dynamiques based on ATR
                sl = entry_price - (1.5 * atr)
                tp = entry_price + (3.0 * atr) # Ratio 1:2
                
                # Position Sizing
                risk_per_trade = capital * RISK_PER_TRADE
                dist_to_sl = entry_price - sl
                
                if dist_to_sl > 0:
                    units = risk_per_trade / dist_to_sl
                    
                    # Cap par levier max
                    max_units = (capital * LEVERAGE) / entry_price
                    units = min(units, max_units)
                    
                    if units > 0:
                        position = 'LONG'
                        trades.append({
                            'type': 'OPEN_LONG',
                            'entry': entry_price,
                            'sl': sl,
                            'tp': tp,
                            'time': timestamp
                        })
    
    # Clôturer position restante à la fin
    
    # Stats
    wins = len([t for t in trades if t['type'] == 'TP'])
    losses = len([t for t in trades if t['type'] == 'SL'])
    total = wins + losses
    win_rate = (wins/total * 100) if total > 0 else 0
    pnl_total = capital - INITIAL_CAPITAL
    return {
        'pair': pair,
        'final_capital': capital,
        'pnl_abs': pnl_total,
        'pnl_pct': (pnl_total / INITIAL_CAPITAL) * 100,
        'total_trades': total,
        'win_rate': win_rate
    }

if __name__ == "__main__":
    pairs = ['EURUSD', 'GBPUSD', 'USDJPY']
    results = []
    
    print("🌍 DÉMARRAGE BACKTEST FOREX STRATEGY V1")
    print("=======================================")
    
    for pair in pairs:
        try:
            df = load_data(pair)
            if df is not None:
                df = calculate_indicators(df)
                res = run_backtest(pair, df)
                results.append(res)
        except Exception as e:
            print(f"Erreur sur {pair}: {e}")
            
    print("\n📊 RÉSULTATS GLOBAUX")
    print("=======================================")
    total_pnl = 0
    
    for r in results:
        print(f"🔹 {r['pair']}: {r['pnl_pct']:.2f}% | Trades: {r['total_trades']} | WR: {r['win_rate']:.1f}% | PnL: ${r['pnl_abs']:.2f}")
        total_pnl += r['pnl_abs']
        
    print("=======================================")
    print(f"💰 PNL TOTAL: ${total_pnl:.2f}")
    if total_pnl > 0:
        print("✅ STRATÉGIE GAGNANTE")
    else:
        print("❌ STRATÉGIE PERDANTE - Optimisation requise")
