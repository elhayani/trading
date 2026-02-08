import pandas as pd
import glob
import os
import numpy as np

# Configuration
INITIAL_CAPITAL = 20000.0  # Euros
RISK_PER_TRADE_PERCENT = 0.02 # 2% allocation risk or fixed size concept
# Actually user said "budget de 20000 euros cumulatif".
# Let's assume we allocate capital dynamically or just compound it.
# Simplest approach for "Test 2024 Cumulative":
# - Start with 20k
# - For each trade in chronological order:
#   - Calculate Position Size. Let's say we use fixed 2000 EUR per trade (10% exposure) or risk based?
#   - Let's use Risk Based: Risk 1% of current capital.
#   - Position Size = Risk Amount / (Entry - SL distance %).
#   - If SL not in log, assume fixed allocation e.g. 5% of capital (1000 EUR).
#   - But logs don't guarantee SL info is accurate (some logs have it, some don't).
#   - Alternative: Use fixed allocation of 2,000 EUR per trade. (10% of start capital). 
#     If 2024 was good, we grow.

FIXED_ALLOCATION = 2000.0 # EUR per trade (10% of init capital)

# Load all logs and select latest per symbol
files = glob.glob('backtest_*.log')
latest_files = {}

for f in files:
    # Extract symbol from filename: backtest_Class_Symbol_Timestamp.log
    # Example: backtest_Indices_^NDX_20260208_003508.log
    try:
        parts = f.split('_')
        # Symbol is usually part 2 or 2+3 if contains = or _
        # Robust way: everything between 'backtest_Class_' and '_Timestamp.log'
        # But easier: just use asset class + symbol as key?
        # Actually, let's just parse the timestamp and keep max per symbol string.
        # "backtest_Indices_^NDX_..." -> Symbol "^NDX"
        # "backtest_Crypto_BTC_USDT_..." -> Symbol "BTC_USDT"
        
        # Determine symbol via regex or splitting
        # asset class is index 1.
        asset_class = parts[1]
        timestamp_str = parts[-1].replace('.log', '')
        
        # Symbol is everything between index 2 and -2
        symbol_parts = parts[2:-1] 
        symbol = "_".join(symbol_parts)
        
        key = f"{asset_class}_{symbol}"
        
        if key not in latest_files:
            latest_files[key] = f
        else:
            # Compare timestamps string (YYYYMMDD_HHMMSS can be compared lexically)
            curr_ts = latest_files[key].split('_')[-1].replace('.log', '')
            if timestamp_str > curr_ts:
                latest_files[key] = f
    except:
        continue

print(f"Found {len(files)} logs. Using latest for each symbol:")
for k, v in latest_files.items():
    print(f"  {k}: {v}")

selected_files = list(latest_files.values())
all_trades = []

for f in selected_files:
    try:
        # Read CSV: SYMBOL,TIMESTAMP,TYPE,PRICE,RSI,SMA200,ATR,REASON,PROFIT
        # Note: Some lines might be malformed or empty at end
        df = pd.read_csv(f)
        if df.empty: continue
        df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'])
        all_trades.append(df)
    except Exception as e:
        print(f"Error reading {f}: {e}")

if not all_trades:
    print("No valid trades found in selected logs.")
    exit()

# Combine and Sort
master_df = pd.concat(all_trades, ignore_index=True)
master_df = master_df.sort_values('TIMESTAMP')

# Simulation
current_capital = INITIAL_CAPITAL
equity_curve = []
trade_history = []

active_positions = {} # Symbol -> {EntryPrice, EntryTime, Type}

print(f"Starting Simulation 2024 with {INITIAL_CAPITAL} EUR...")

for index, row in master_df.iterrows():
    symbol = row['SYMBOL']
    ts = row['TIMESTAMP']
    action = row['TYPE']
    price = row['PRICE']
    reason = str(row['REASON'])
    
    # Filter 2024 only (Just in case logs cover more)
    if ts.year != 2024:
        continue
        
    if action in ['BUY', 'LONG', 'SHORT', 'SELL']:
        # Map to standard BUY/SELL
        is_entry = False
        is_exit = False
        direction = 'LONG' # Default
        
        if action in ['BUY', 'LONG']:
            # Check if it's an entry (standard) or exit (short covering? no, bots usually only go Long except Oil/Crypto short)
            # Actually Indices SHORT is possible in some strategies?
            # logs usually show BUY means Open Long, SELL means Close Long.
            # But for Shorting: SHORT means Open Short, BUY means Close Short?
            # Let's check logs context.
            # Indices/Commodities logs usually: BUY -> Open Long. SELL -> Close Long.
            # If Oil strategies use Short: SHORT -> Open Short. 
            # run_test_v2 writes log direction based on signal.
            
            if symbol not in active_positions:
                is_entry = True
                direction = 'LONG'
            else:
                # Existing position
                pos = active_positions[symbol]
                if pos['Type'] == 'SHORT':
                    is_exit = True # Buy to Cover
                else: 
                    # Already Long? Pyramiding or duplicate signal. Ignore duplicates.
                    continue
                    
        elif action in ['SELL', 'SHORT']:
            if action == 'SHORT':
                if symbol not in active_positions:
                    is_entry = True
                    direction = 'SHORT'
                else:
                    # Existing position
                    pos = active_positions[symbol]
                    if pos['Type'] == 'LONG':
                        is_exit = True # Sell to Close
            elif action == 'SELL':
                # Usually Close Long.
                if symbol in active_positions:
                    pos = active_positions[symbol]
                    if pos['Type'] == 'LONG':
                        is_exit = True
                else:
                    # Open Short? Some bots use SELL for open short? 
                    # Standard convention in my bots: SHORT = Open Short. SELL = Close Long.
                    # Exception: Crypto bot might use SELL for Open Short?
                    pass

        if is_entry:
            active_positions[symbol] = {
                'EntryPrice': price,
                'EntryTime': ts,
                'Type': direction,
                'Size': FIXED_ALLOCATION # Simulate 2k bet
            }
            # trade_history.append({'Date': ts, 'Symbol': symbol, 'Action': f"OPEN {direction}", 'Price': price, 'PnL': 0, 'Capital': current_capital})

        elif is_exit:
            pos = active_positions.pop(symbol)
            entry_price = pos['EntryPrice']
            pos_type = pos['Type']
            entry_size = pos['Size']
            
            # Calc PnL
            if pos_type == 'LONG':
                pnl_pct = (price - entry_price) / entry_price
            else: # SHORT
                pnl_pct = (entry_price - price) / entry_price
                
            pnl_eur = entry_size * pnl_pct
            current_capital += pnl_eur
            
            trade_history.append({
                'Date': ts, 
                'Symbol': symbol, 
                'Action': f"CLOSE {pos_type}", 
                'Entry': entry_price, 
                'Exit': price, 
                'PnL %': pnl_pct * 100, 
                'PnL EUR': pnl_eur, 
                'Capital': current_capital
            })

# Generate Report
print("\n=== 📊 2024 CUMULATIVE BACKTEST REPORT ===")
print("------------------------------------------")
print(f"Starting Capital: {INITIAL_CAPITAL} EUR")
print(f"Allocation per Trade: {FIXED_ALLOCATION} EUR (Fixed)")
print("------------------------------------------")

total_trades = len(trade_history)
wins = len([t for t in trade_history if t['PnL EUR'] > 0])
losses = len([t for t in trade_history if t['PnL EUR'] <= 0])
win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
total_pnl = current_capital - INITIAL_CAPITAL
final_return = (total_pnl / INITIAL_CAPITAL) * 100

print(f"Total Trades: {total_trades}")
print(f"Win Rate:     {win_rate:.1f}% ({wins}W / {losses}L)")
print(f"Final Capital: {current_capital:.2f} EUR")
print(f"Total Profit:  {total_pnl:+.2f} EUR")
print(f"Total Return:  {final_return:+.1f}%")
print("------------------------------------------")

# Asset Class Breakdown
print("\nDisclaimer: This simulation assumes a fixed allocation of 2000 EUR per trade across all assets.")
print("This allows fair comparison despite different asset prices (BTC vs EURUSD).\n")

# Detailed Table
print(f"{'DATE':<12} | {'SYMBOL':<10} | {'ACTION':<10} | {'PNL %':<8} | {'PNL EUR':<10} | {'CAPITAL':<10}")
print("-" * 75)
for t in trade_history:
    print(f"{t['Date'].strftime('%Y-%m-%d'):<12} | {t['Symbol']:<10} | {t['Action']:<10} | {t['PnL %']:>7.1f}% | {t['PnL EUR']:>9.2f}€ | {t['Capital']:>9.2f}€")
