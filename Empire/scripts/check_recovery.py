
import yfinance as yf
import pandas as pd
import numpy as np

def calculate_rsi(series, period=14):
    delta = series.diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def check_recovery():
    print("🔍 Analyzing SOL Recovery Status...")
    
    # Fetch SOL-USD data
    # 5 days to cover the drop and potential recovery
    df = yf.download("SOL-USD", period="5d", interval="1h", progress=False)
    
    if df.empty:
        print("❌ Failed to fetch data.")
        return

    # Cleanup headers
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.lower() for c in df.columns]

    # Calculate Indicators
    df['rsi'] = calculate_rsi(df['close'], 14)
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['sma_50'] = df['close'].rolling(window=50).mean()
    
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    current_price = last_row['close']
    current_rsi = last_row['rsi']
    
    # Breakeven target from user provided info
    breakeven = 98.50
    dist_to_be = ((breakeven - current_price) / current_price) * 100
    
    print(f"\n💎 SOL/USD Status:")
    print(f"   Price: ${current_price:.2f}")
    print(f"   RSI (1h): {current_rsi:.2f}")
    print(f"   Target (BE): ${breakeven:.2f} (+{dist_to_be:.2f}%)")
    
    print("\n📉 Recent Price Action (Last 5 hours):")
    print(df[['close', 'rsi']].tail(5))
    
    # Recovery Signals
    print("\n🚦 Signal Check:")
    
    # 1. RSI Recovery
    if current_rsi > 30 and prev_row['rsi'] <= 30:
        print("   ✅ RSI leaving oversold zone (Classic Bounce Signal)")
    elif current_rsi > 40:
        print("   ✅ RSI regaining neutral momentum (>40)")
    else:
        print("   ⚠️ RSI still weak/oversold")
        
    # 2. SMA Reclaim
    if current_price > last_row['sma_20']:
        print("   ✅ Price reclaimed 20h SMA (Short term recovery starting)")
    else:
        print(f"   ❌ Price below 20h SMA (${last_row['sma_20']:.2f}) - Trend still down")
        
    # 3. Double Bottom / Higher Low (Simplified check)
    low_24h = df['low'].tail(24).min()
    if current_price > low_24h * 1.02: # 2% above low
        print(f"   ✅ Bouncing off lows (${low_24h:.2f})")
    else:
        print(f"   ⚠️ At or near 24h lows (${low_24h:.2f}) - Danger zone")

if __name__ == "__main__":
    check_recovery()
