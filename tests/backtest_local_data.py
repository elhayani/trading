
import os
import pandas as pd
import numpy as np
import glob
from datetime import datetime

# =============================================================================
# 1. INDICATORS & UTILS
# =============================================================================
class Indicators:
    @staticmethod
    def calculate_rsi(series, period=14):
        delta = series.diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        ema_up = up.ewm(com=period-1, adjust=False).mean()
        ema_down = down.ewm(com=period-1, adjust=False).mean()
        rs = ema_up / ema_down
        return 100 - (100 / (1 + rs))

    @staticmethod
    def calculate_atr(df, period=14):
        high = df['high']
        low = df['low']
        close = df['close']
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @staticmethod
    def calculate_sma(series, period):
        return series.rolling(window=period).mean()

    @staticmethod
    def calculate_bollinger_bands(series, period=20, std_dev=2.0):
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        return sma + (std * std_dev), sma - (std * std_dev)

# =============================================================================
# 2. STRATEGIES
# =============================================================================
class ForexStrategy:
    def __init__(self):
        self.params = {
            'rsi_oversold': 30, # Default, can be tuned
            'sl_atr_mult': 1.5,
            'tp_atr_mult': 3.0
        }

    def run(self, df, pair):
        # Calculate Indicators
        df = df.copy()
        df['ATR'] = Indicators.calculate_atr(df)
        df['SMA_200'] = Indicators.calculate_sma(df['close'], 200)
        df['RSI'] = Indicators.calculate_rsi(df['close'], 14)
        
        # Bollinger for USDJPY
        if "JPY" in pair:
            df['BBU'], df['BBL'] = Indicators.calculate_bollinger_bands(df['close'])
            strategy_type = 'BOLLINGER'
        else:
            strategy_type = 'TREND_PULLBACK'

        trades = []
        position = None # {'entry': float, 'sl': float, 'tp': float, 'type': 'LONG'/'SHORT'}

        for i in range(200, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            price = row['close']
            date = row.name

            # 1. Manage Open Position
            if position:
                # Check SL
                if (position['type'] == 'LONG' and price <= position['sl']) or \
                   (position['type'] == 'SHORT' and price >= position['sl']):
                    pnl = (position['sl'] - position['entry']) / position['entry']
                    if position['type'] == 'SHORT': pnl = -pnl
                    trades.append({'date': date, 'type': 'EXIT_SL', 'pnl': pnl, 'reason': 'SL'})
                    position = None
                    continue

                # Check TP
                if (position['type'] == 'LONG' and price >= position['tp']) or \
                   (position['type'] == 'SHORT' and price <= position['tp']):
                    pnl = (position['tp'] - position['entry']) / position['entry']
                    if position['type'] == 'SHORT': pnl = -pnl
                    trades.append({'date': date, 'type': 'EXIT_TP', 'pnl': pnl, 'reason': 'TP'})
                    position = None
                    continue
                
                # Check Time-based limit (optional) or other exits? No, stick to simple for now.
                continue

            # 2. Entry Logic
            if pd.isna(row['ATR']): continue
            
            atr = row['ATR']
            sl_dist = atr * self.params['sl_atr_mult']
            tp_dist = atr * self.params['tp_atr_mult']

            if strategy_type == 'TREND_PULLBACK':
                # LONG only for now usually
                if price > row['SMA_200']: # Trend Bullish
                    if row['RSI'] < 30: # Pullback
                         position = {
                             'entry': price,
                             'sl': price - sl_dist,
                             'tp': price + tp_dist,
                             'type': 'LONG'
                         }
                         trades.append({'date': date, 'type': 'ENTRY_LONG', 'price': price})

            elif strategy_type == 'BOLLINGER':
                 # Breakout Up
                 if price > row['BBU'] and prev['close'] <= prev['BBU']:
                     position = {
                         'entry': price,
                         'sl': price - sl_dist,
                         'tp': price + tp_dist,
                         'type': 'LONG'
                     }
                     trades.append({'date': date, 'type': 'ENTRY_LONG', 'price': price})
                 # Breakout Down
                 elif price < row['BBL'] and prev['close'] >= prev['BBL']:
                     position = {
                         'entry': price,
                         'sl': price + sl_dist,
                         'tp': price - tp_dist,
                         'type': 'SHORT'
                     }
                     trades.append({'date': date, 'type': 'ENTRY_SHORT', 'price': price})

        return trades

class CryptoStrategy:
    def __init__(self):
        self.params = {
            'rsi_buy': 40, # Updated based on user pref
            'rsi_sell': 75,
            'sl_pct': 0.05,
            'tp_pct': 0.05
        }

    def run(self, df, pair=None):
        df = df.copy()
        df['RSI'] = Indicators.calculate_rsi(df['close'], 14)
        df['SMA_50'] = Indicators.calculate_sma(df['close'], 50) # Trend filter
        
        trades = []
        position = None 
        
        # Simulate Capital
        initial_capital = 1000.0
        capital = initial_capital
        
        for i in range(50, len(df)):
            row = df.iloc[i]
            price = row['close']
            date = row.name
            
            if position:
                # Check Exit (SL/TP or RSI Overbought)
                pnl_pct = (price - position['entry']) / position['entry']
                
                # SL
                if pnl_pct <= -self.params['sl_pct']:
                    trades.append({'date': date, 'type': 'EXIT_SL', 'pnl': -self.params['sl_pct'], 'reason': 'SL'})
                    position = None
                    continue
                    
                # TP
                if pnl_pct >= self.params['tp_pct']:
                    trades.append({'date': date, 'type': 'EXIT_TP', 'pnl': self.params['tp_pct'], 'reason': 'TP'})
                    position = None
                    continue
                
                # RSI Overbought Exit
                if row['RSI'] > self.params['rsi_sell']:
                    trades.append({'date': date, 'type': 'EXIT_RSI', 'pnl': pnl_pct, 'reason': 'RSI_HIGH'})
                    position = None
                    continue
            
            else:
                # Entry Logic (V4 Hybrid Simplified: Trend + RSI)
                # We assume "Bull" regime for simplistic backtest
                if row['RSI'] < self.params['rsi_buy']:
                    # Filter: Price > SMA50 (Trend Follow)
                    if price > row['SMA_50']:
                        position = {
                            'entry': price,
                            'type': 'LONG'
                        }
                        trades.append({'date': date, 'type': 'ENTRY_LONG', 'price': price})
                        
        return trades

# =============================================================================
# 3. RUNNER
# =============================================================================
def load_data(filepath):
    """Load CSV data generated by yfinance"""
    try:
        df = pd.read_csv(filepath)
        # Assuming format: timestamp,close,high,low,open,volume
        # Parse timestamp
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        # Rename columns to lowercase just in case
        df.columns = [c.lower() for c in df.columns]
        return df.sort_index()
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def backtest_all():
    data_dir = "/Users/zakaria/Trading/tests/data"
    files = glob.glob(os.path.join(data_dir, "*.csv"))
    
    print(f"\n🚀 STARTING BACKTEST ON LOCAL DATA ({len(files)} files)")
    print(f"📂 Directory: {data_dir}\n")
    print(f"{'FILE':<20} | {'ASSET':<8} | {'DAYS':<5} | {'TRADES':<6} | {'WIN RATE':<8} | {'PnL':<8}")
    print("-" * 80)
    
    for filepath in sorted(files):
        filename = os.path.basename(filepath)
        asset_name = filename.split('_')[0] # BTCUSD, EURUSD
        
        # Identify Type
        if any(x in asset_name for x in ['BTC', 'ETH', 'SOL']):
            asset_type = 'CRYPTO'
            strategy = CryptoStrategy()
        else:
            asset_type = 'FOREX'
            strategy = ForexStrategy()
            
        # Load Data
        df = load_data(filepath)
        if df is None or df.empty:
            continue
            
        days = (df.index[-1] - df.index[0]).days
        
        # Run Strategy
        trades = strategy.run(df, asset_name)
        
        # Calc Stats
        closed_trades = [t for t in trades if 'EXIT' in t['type']]
        num_trades = len(closed_trades)
        
        win_rate = 0.0
        total_pnl = 0.0
        
        if num_trades > 0:
            wins = len([t for t in closed_trades if t['pnl'] > 0])
            win_rate = (wins / num_trades) * 100
            total_pnl = sum([t['pnl'] for t in closed_trades]) * 100 # In %
            
        print(f"{filename:<20} | {asset_type:<8} | {days:<5} | {num_trades:<6} | {win_rate:>6.1f}% | {total_pnl:>+7.1f}%")

if __name__ == "__main__":
    backtest_all()
