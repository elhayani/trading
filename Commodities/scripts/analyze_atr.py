
import sys
import os
import pandas as pd
import yfinance as yf

# Add lambda directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.abspath(os.path.join(current_dir, '../lambda/commodities_trader'))
sys.path.append(lambda_dir)

from strategies import ForexStrategies

def analyze_atr():
    print("DATA ANALYSIS 2025 - ATR LEVELS")
    pairs = ['GC=F', 'CL=F']
    
    for pair in pairs:
        try:
            df = yf.download(pair, start="2025-01-01", end="2025-12-31", interval="1h", progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]
            
            df = ForexStrategies.calculate_indicators(df, 'TREND_PULLBACK' if 'GC' in pair else 'BOLLINGER_BREAKOUT')
            
            atr = df['ATR'].dropna()
            print(f"\nAsset: {pair}")
            print(f"  Mean ATR: {atr.mean():.4f}")
            print(f"  Max ATR : {atr.max():.4f}")
            print(f"  95% ATR : {atr.quantile(0.95):.4f}")
            print(f"  Rec. Cap (1.5x Mean): {atr.mean() * 1.5:.4f}")
            
        except Exception as e:
            print(f"Error {pair}: {e}")

if __name__ == "__main__":
    analyze_atr()
