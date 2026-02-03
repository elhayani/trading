
import sys
import os
import pandas as pd
import yfinance as yf
import pandas_ta as ta
import numpy as np

# Add lambda directory to path to import config and strategies
current_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.join(current_dir, '../lambda/indices_trader')
sys.path.append(lambda_dir)

from config import CONFIGURATION, GLOBAL_SETTINGS
from strategies import ForexStrategies  # It's named ForexStrategies but used for Indices

def download_data(ticker):
    """Downloads 1h data for 2024"""
    print(f"⬇️ Downloading data for {ticker} (2024)...")
    try:
        # Download data for 2024 (Starting March due to 730 days limit for 1h data from 2026)
        df = yf.download(ticker, start="2024-03-01", end="2024-12-31", interval="1h", progress=False)
        
        if df.empty:
            print(f"❌ No data found for {ticker}")
            return None
            
        # Handle MultiIndex columns (e.g. ('Close', '^GSPC'))
        if isinstance(df.columns, pd.MultiIndex):
             df.columns = df.columns.get_level_values(0)
             
        # Standardize columns (lowercase)
        df.columns = [str(c).lower() for c in df.columns]
             
        # Rename 'Adj Close' if exists, or just use 'close'
        return df
    except Exception as e:
        print(f"❌ Error downloading {ticker}: {e}")
        return None

def run_backtest(ticker, config, df):
    strategy_type = config['strategy']
    params = config['params']
    
    # Calculate Indicators
    # We use the method from strategies.py to ensure parity with live trading
    df = ForexStrategies.calculate_indicators(df, strategy_type)
    
    capital = 10000 # Starting capital $10,000 for Indices (usually requires more margin)
    balance = capital
    trades = []
    position = None # None or dict
    
    print(f"\n🚀 Running Backtest for {ticker} ({strategy_type})")
    print(f"   Period: {df.index[0]} to {df.index[-1]}")
    print(f"   Initial Capital: ${capital}")
    
    for i in range(201, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        timestamp = df.index[i]
        
        # 1. Manage Open Position
        if position:
            sl = position['sl']
            tp = position['tp']
            entry_price = position['entry']
            units = position['units']
            side = position['side']
            
            pnl = 0
            exit_price = 0
            exit_reason = None
            
            # Check SL/TP
            if side == 'LONG':
                if current['low'] <= sl:
                    exit_price = sl
                    exit_reason = 'SL'
                elif current['high'] >= tp:
                    exit_price = tp
                    exit_reason = 'TP'
            elif side == 'SHORT': # Assuming strategy supports short (Bollinger does)
                if current['high'] >= sl:
                    exit_price = sl
                    exit_reason = 'SL'
                elif current['low'] <= tp:
                    exit_price = tp
                    exit_reason = 'TP'
            
            if exit_reason:
                # Calculate PnL
                if side == 'LONG':
                    pnl = (exit_price - entry_price) * units
                else:
                    pnl = (entry_price - exit_price) * units
                
                balance += pnl
                trades.append({
                    'symbol': ticker,
                    'type': exit_reason,
                    'side': side,
                    'entry': entry_price,
                    'exit': exit_price,
                    'pnl': pnl,
                    'date': timestamp
                })
                position = None
        
        # 2. Check for New Entry
        if position is None:
            # We construct a mini-df for the check_signal function to match its expected input
            # check_signal uses df.iloc[-1] and df.iloc[-2], so we slice up to current i
            # This is slightly inefficient but safe
            slice_df = df.iloc[:i+1]
            
            # Need to mock the 'pair' argument and package params like the lambda expects
            # strategies.py expects 'config' dict with 'params' and 'strategy' keys
            # signal_config = {'params': params, 'strategy': strategy_type}
            # Actually, check_signal signature is: check_signal(pair, df, config)
            # where config is the dict from config.py for that pair.
            
            signal_res = ForexStrategies.check_signal(ticker, slice_df, config)
            
            if signal_res:
                entry_price = signal_res['entry']
                sl = signal_res['sl']
                tp = signal_res['tp']
                signal_side = signal_res['signal'] # 'LONG' or 'SHORT'
                
                # Position Sizing
                risk_amt = balance * GLOBAL_SETTINGS['risk_per_trade']
                dist_to_sl = abs(entry_price - sl)
                
                if dist_to_sl > 0:
                    units = risk_amt / dist_to_sl
                    
                    # Sanity check or margin cap could be added here
                    # For indices, 1 unit is often $1 (CFD) or $20 or $50 depending on contract. 
                    # Assuming CFD logic (1 point = $1) for simplicity as per previous scripts.
                    
                    position = {
                        'entry': entry_price,
                        'sl': sl,
                        'tp': tp,
                        'units': units,
                        'side': signal_side,
                        'date': timestamp
                    }
                    
                    trades.append({
                        'symbol': ticker,
                        'type': 'OPEN',
                        'side': signal_side,
                        'entry': entry_price,
                        'sl': sl,
                        'tp': tp,
                        'date': timestamp
                    })

    # Stats
    wins = len([t for t in trades if t['type'] == 'TP'])
    losses = len([t for t in trades if t['type'] == 'SL'])
    total_trades = wins + losses
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    total_pnl = balance - capital
    
    return {
        'ticker': ticker,
        'final_balance': balance,
        'pnl': total_pnl,
        'trades': total_trades,
        'win_rate': win_rate,
        'history': trades
    }

if __name__ == "__main__":
    print("📈 INDICES BACKTEST 2024")
    print("=========================")
    
    results = []
    
    for ticker, conf in CONFIGURATION.items():
        if not conf['enabled']:
            continue
            
        df = download_data(ticker)
        if df is not None and not df.empty:
            res = run_backtest(ticker, conf, df)
            results.append(res)
            
    print("\n📊 GLOBAL RESULTS (2024)")
    print("=========================")
    total_pnl_all = 0
    
    for res in results:
        print(f"🔹 {res['ticker']}:")
        print(f"   PnL: ${res['pnl']:.2f}")
        print(f"   Trades: {res['trades']}")
        print(f"   Win Rate: {res['win_rate']:.1f}%")
        print(f"   Final Balance: ${res['final_balance']:.2f}")
        total_pnl_all += res['pnl']
        print("-------------------------")
        
    print(f"\n💰 GRAND TOTAL PNL: ${total_pnl_all:.2f}")
