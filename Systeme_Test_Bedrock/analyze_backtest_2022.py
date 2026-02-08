#!/usr/bin/env python3
"""
Analyze 2022 backtest results with 20000€ cumulative budget
"""
import csv
import os
from datetime import datetime
from collections import defaultdict

INITIAL_CAPITAL = 20000.0
RESULTS_DIR = "backtest_results_2022"

# Risk per trade (as percentage of capital)
RISK_PER_TRADE = 0.01  # 1% risk per trade

def parse_profit(profit_str):
    """Extract profit value from string like '$10.50' or '10.50'"""
    if not profit_str or profit_str.strip() == '':
        return 0.0

    # Remove $ and other characters
    profit_str = profit_str.replace('$', '').replace(',', '').strip()

    try:
        return float(profit_str)
    except:
        return 0.0

def analyze_backtest_file(filepath, asset_name):
    """Analyze a single backtest CSV file"""

    trades = []
    entries = []
    exits = []
    errors = 0

    try:
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)

            for row in reader:
                trade_type = row.get('TYPE', '').strip()
                timestamp = row.get('TIMESTAMP', '')
                price = float(row.get('PRICE', 0))
                reason = row.get('REASON', '')
                profit_str = row.get('PROFIT', '0')

                if trade_type in ['BUY', 'LONG']:
                    entries.append({
                        'timestamp': timestamp,
                        'type': trade_type,
                        'price': price,
                        'reason': reason
                    })

                elif trade_type in ['EXIT', 'SELL'] and 'SELL' not in reason:
                    profit = parse_profit(profit_str)
                    exits.append({
                        'timestamp': timestamp,
                        'price': price,
                        'profit': profit,
                        'reason': reason
                    })

                    if profit != 0:
                        trades.append(profit)

                elif 'ERROR' in reason or 'FAILED' in reason:
                    errors += 1

    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None

    # Calculate statistics
    total_trades = len(trades)
    winning_trades = [t for t in trades if t > 0]
    losing_trades = [t for t in trades if t < 0]

    total_profit = sum(trades) if trades else 0
    win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

    avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else 0

    profit_factor = abs(sum(winning_trades) / sum(losing_trades)) if losing_trades and sum(losing_trades) != 0 else 0

    return {
        'asset': asset_name,
        'entries': len(entries),
        'exits': len(exits),
        'completed_trades': total_trades,
        'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades),
        'win_rate': win_rate,
        'total_profit': total_profit,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'errors': errors
    }

def calculate_portfolio_performance(results, initial_capital):
    """Calculate cumulative portfolio performance"""

    capital = initial_capital
    total_profit = 0

    print("\n" + "="*80)
    print(f"💰 PORTFOLIO SIMULATION - Initial Capital: €{initial_capital:,.2f}")
    print("="*80)

    for result in results:
        if not result:
            continue

        asset = result['asset']
        profit = result['total_profit']

        # Simple approach: add/subtract profit
        capital += profit
        total_profit += profit

        roi = (profit / initial_capital * 100) if initial_capital > 0 else 0

        print(f"\n📊 {asset}:")
        print(f"   Trades: {result['completed_trades']}")
        print(f"   Win Rate: {result['win_rate']:.1f}%")
        print(f"   Total P&L: €{profit:,.2f}")
        print(f"   ROI: {roi:+.2f}%")
        print(f"   Avg Win: €{result['avg_win']:.2f}")
        print(f"   Avg Loss: €{result['avg_loss']:.2f}")
        if result['profit_factor'] > 0:
            print(f"   Profit Factor: {result['profit_factor']:.2f}")

    print("\n" + "="*80)
    print("📈 FINAL RESULTS")
    print("="*80)
    print(f"Initial Capital:  €{initial_capital:,.2f}")
    print(f"Final Capital:    €{capital:,.2f}")
    print(f"Total Profit:     €{total_profit:,.2f}")
    print(f"Total ROI:        {(total_profit/initial_capital*100):+.2f}%")
    print("="*80)

    return capital

def main():
    print("🔍 Analyzing 2022 Backtest Results...")
    print(f"💶 Initial Capital: €{INITIAL_CAPITAL:,.2f}")
    print()

    # Files to analyze (in current directory, not subdirectory)
    files = {
        'Forex EURUSD': 'backtest_Forex_EURUSD=X_20260208_213656.log',
        'Indices S&P500': 'backtest_Indices_^GSPC_20260208_213646.log',
        'Commodities Gold': 'backtest_Commodities_GC=F_20260208_213656.log',
        'Crypto BTC': 'backtest_Crypto_BTC-USD_20260208_213650.log'
    }

    results = []

    for asset_name, filename in files.items():
        filepath = filename  # Files are in current directory

        if not os.path.exists(filepath):
            print(f"⚠️  File not found: {filepath}")
            continue

        print(f"📄 Analyzing {asset_name}...")
        result = analyze_backtest_file(filepath, asset_name)

        if result:
            results.append(result)

    # Calculate portfolio performance
    final_capital = calculate_portfolio_performance(results, INITIAL_CAPITAL)

    print("\n✅ Analysis Complete!")

if __name__ == "__main__":
    main()
