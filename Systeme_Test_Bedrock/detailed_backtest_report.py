#!/usr/bin/env python3
"""
Generate detailed backtest report with trade-by-trade analysis
"""
import csv
import os
from datetime import datetime
from collections import defaultdict

INITIAL_CAPITAL = 20000.0

def parse_profit(profit_str):
    """Extract profit value from string"""
    if not profit_str or profit_str.strip() == '':
        return 0.0
    profit_str = profit_str.replace('$', '').replace(',', '').strip()
    try:
        return float(profit_str)
    except:
        return 0.0

def analyze_detailed(filepath, asset_name):
    """Generate detailed trade-by-trade report"""

    print(f"\n{'='*80}")
    print(f"📊 {asset_name.upper()}")
    print(f"{'='*80}")

    trades = []
    entries = {}
    entry_count = 0

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
                    entry_count += 1
                    entries[entry_count] = {
                        'timestamp': timestamp,
                        'price': price,
                        'type': trade_type
                    }

                elif trade_type in ['EXIT', 'SELL'] and ('CLOSED' in reason or 'PNL' in reason):
                    profit = parse_profit(profit_str)
                    if profit != 0:
                        trades.append({
                            'timestamp': timestamp,
                            'exit_price': price,
                            'profit': profit,
                            'reason': reason
                        })

    except Exception as e:
        print(f"Error: {e}")
        return []

    # Display trades
    if not trades:
        print("❌ No completed trades found")
        return []

    print(f"\n📋 Total Trades: {len(trades)}")
    print(f"{'='*80}")

    cumulative = 0
    wins = 0
    losses = 0

    for i, trade in enumerate(trades, 1):
        profit = trade['profit']
        cumulative += profit

        if profit > 0:
            wins += 1
            emoji = "✅"
        else:
            losses += 1
            emoji = "❌"

        print(f"\nTrade #{i} {emoji}")
        print(f"  Date:       {trade['timestamp']}")
        print(f"  Exit Price: ${trade['exit_price']:.4f}")
        print(f"  P&L:        €{profit:+,.2f}")
        print(f"  Cumulative: €{cumulative:+,.2f}")

        # Extract reason details
        reason = trade['reason']
        if 'CLOSED' in reason:
            # Extract number of positions closed
            parts = reason.split('_')
            if len(parts) >= 2:
                num_closed = parts[1]
                print(f"  Details:    Closed {num_closed} position(s)")

    # Summary stats
    print(f"\n{'='*80}")
    print(f"📈 SUMMARY STATISTICS")
    print(f"{'='*80}")
    print(f"Total Trades:     {len(trades)}")
    print(f"Winning Trades:   {wins} ({wins/len(trades)*100:.1f}%)")
    print(f"Losing Trades:    {losses} ({losses/len(trades)*100:.1f}%)")
    print(f"Total P&L:        €{cumulative:+,.2f}")
    print(f"Avg Trade:        €{cumulative/len(trades):+,.2f}")
    print(f"Best Trade:       €{max([t['profit'] for t in trades]):+,.2f}")
    print(f"Worst Trade:      €{min([t['profit'] for t in trades]):+,.2f}")

    return trades

def main():
    print("="*80)
    print("📊 DETAILED BACKTEST REPORT - 2022 Results")
    print("="*80)
    print(f"💶 Initial Capital: €{INITIAL_CAPITAL:,.2f}")

    files = {
        'Forex EURUSD': 'backtest_Forex_EURUSD=X_20260208_213656.log',
        'Indices S&P500': 'backtest_Indices_^GSPC_20260208_213646.log',
        'Commodities Gold': 'backtest_Commodities_GC=F_20260208_213656.log',
        'Crypto BTC': 'backtest_Crypto_BTC-USD_20260208_213650.log'
    }

    all_trades = {}

    for asset_name, filename in files.items():
        if not os.path.exists(filename):
            print(f"\n⚠️  File not found: {filename}")
            continue

        trades = analyze_detailed(filename, asset_name)
        all_trades[asset_name] = trades

    # Portfolio summary
    print(f"\n\n{'='*80}")
    print("💰 PORTFOLIO FINAL SUMMARY")
    print(f"{'='*80}")

    total_profit = 0
    total_trades = 0

    for asset, trades in all_trades.items():
        if trades:
            asset_profit = sum([t['profit'] for t in trades])
            total_profit += asset_profit
            total_trades += len(trades)
            print(f"{asset:20s} : {len(trades):3d} trades, €{asset_profit:+10,.2f}")

    print(f"{'='*80}")
    print(f"{'Total':20s} : {total_trades:3d} trades, €{total_profit:+10,.2f}")
    print(f"\nInitial Capital:  €{INITIAL_CAPITAL:,.2f}")
    print(f"Final Capital:    €{INITIAL_CAPITAL + total_profit:,.2f}")
    print(f"Total ROI:        {(total_profit/INITIAL_CAPITAL*100):+.2f}%")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
