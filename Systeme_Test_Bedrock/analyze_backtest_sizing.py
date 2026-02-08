#!/usr/bin/env python3
"""Analyze backtest results to verify position sizing"""

import re

# Parse the backtest log
trades = []
with open('backtest_Indices_^GSPC_20260208_224139.log', 'r') as f:
    lines = f.readlines()[1:]  # Skip header

    for i, line in enumerate(lines):
        parts = line.strip().split(',')
        if len(parts) < 6:
            continue

        timestamp = parts[1]
        trade_type = parts[2]
        price = float(parts[3]) if parts[3] else 0
        reason = parts[7] if len(parts) > 7 else ''
        profit = parts[8] if len(parts) > 8 else ''

        if trade_type == 'BUY' and 'TREND_PULLBACK' in reason:
            # Extract TP and SL
            tp_match = re.search(r'TP:([0-9.]+)', reason)
            sl_match = re.search(r'SL:([0-9.]+)', reason)

            tp = float(tp_match.group(1)) if tp_match else 0
            sl = float(sl_match.group(1)) if sl_match else 0

            trades.append({
                'timestamp': timestamp,
                'entry': price,
                'tp': tp,
                'sl': sl,
                'exit': None,
                'profit': None
            })
        elif trade_type == 'SELL' and profit:
            # Match with last open trade
            exit_price = price
            pnl = profit.strip('$')
            if trades:
                trades[-1]['exit'] = exit_price
                trades[-1]['profit'] = pnl

print("\n📊 ANALYSE DES TRADES V6.2\n")
print("=" * 80)

capital = 10000.0
risk_per_trade = 0.02  # 2%

for i, trade in enumerate(trades, 1):
    print(f"\n🔹 Trade #{i} - {trade['timestamp']}")
    print(f"   Entry:  ${trade['entry']:.2f}")
    print(f"   SL:     ${trade['sl']:.2f}")
    print(f"   TP:     ${trade['tp']:.2f}")

    # Calculate what the position size SHOULD be with risk-based sizing
    sl_distance = abs(trade['entry'] - trade['sl'])
    risk_amount = capital * risk_per_trade  # $200

    expected_quantity = risk_amount / sl_distance
    expected_position_usd = expected_quantity * trade['entry']

    print(f"   SL Distance: ${sl_distance:.2f}")
    print(f"   Risk Amount: ${risk_amount:.2f} (2% of ${capital:.0f})")
    print(f"   Expected Quantity: {expected_quantity:.6f}")
    print(f"   Expected Position: ${expected_position_usd:.2f}")

    if trade['exit']:
        print(f"   Exit:   ${trade['exit']:.2f}")

        # Calculate price move
        price_move_pct = ((trade['exit'] - trade['entry']) / trade['entry']) * 100

        # Calculate expected P&L with proper sizing
        expected_pnl = expected_quantity * (trade['exit'] - trade['entry'])

        # Actual P&L from log
        actual_pnl = float(trade['profit']) if trade['profit'] else 0

        print(f"   Price Move: {price_move_pct:+.2f}%")
        print(f"   Expected P&L: ${expected_pnl:+.2f}")
        print(f"   Actual P&L:   ${actual_pnl:+.2f}")

        # Calculate what size was actually used
        if trade['exit'] != trade['entry']:
            actual_quantity = actual_pnl / (trade['exit'] - trade['entry'])
            actual_position = actual_quantity * trade['entry']
            print(f"   Actual Quantity: {actual_quantity:.6f}")
            print(f"   Actual Position: ${actual_position:.2f}")
            print(f"   ⚠️  SIZING RATIO: {actual_position / expected_position_usd:.1%} of expected")
    else:
        print(f"   Status: OPEN")

print("\n" + "=" * 80)
print("\n🎯 CONCLUSION:")
print("   Si les positions actuelles sont ~10-30% de la taille attendue,")
print("   alors le fix de sizing n'est PAS appliqué correctement.")
