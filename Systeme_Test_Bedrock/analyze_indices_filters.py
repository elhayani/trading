#!/usr/bin/env python3
"""
Analyze why Indices bot is too conservative
"""
import csv
import statistics

def analyze_rsi_distribution(filepath):
    """Analyze RSI values to understand market conditions"""

    rsi_values = []
    wait_count = 0
    trade_count = 0

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)

        for row in reader:
            trade_type = row.get('TYPE', '').strip()
            rsi_str = row.get('RSI', '0')

            try:
                rsi = float(rsi_str)
                if rsi > 0:  # Valid RSI
                    rsi_values.append(rsi)

                    if trade_type == 'WAIT':
                        wait_count += 1
                    elif trade_type in ['BUY', 'LONG']:
                        trade_count += 1
            except:
                pass

    if not rsi_values:
        print("No RSI values found")
        return

    # Statistics
    print("="*80)
    print("📊 RSI ANALYSIS - S&P 500 Backtest")
    print("="*80)
    print(f"\n📈 RSI Statistics:")
    print(f"   Min RSI:     {min(rsi_values):.1f}")
    print(f"   Max RSI:     {max(rsi_values):.1f}")
    print(f"   Moyenne:     {statistics.mean(rsi_values):.1f}")
    print(f"   Médiane:     {statistics.median(rsi_values):.1f}")
    print(f"   Écart-type:  {statistics.stdev(rsi_values):.1f}")

    # Distribution
    print(f"\n📊 Distribution RSI:")
    ranges = [
        (0, 30, "Oversold (<30)"),
        (30, 40, "Weak (30-40)"),
        (40, 50, "Neutral-Low (40-50)"),
        (50, 60, "Neutral-High (50-60)"),
        (60, 70, "Strong (60-70)"),
        (70, 100, "Overbought (>70)")
    ]

    for low, high, label in ranges:
        count = sum(1 for rsi in rsi_values if low <= rsi < high)
        pct = count / len(rsi_values) * 100
        bar = "█" * int(pct / 2)
        print(f"   {label:20s} : {count:3d} ({pct:5.1f}%) {bar}")

    # Current threshold analysis
    print(f"\n🎯 THRESHOLD ANALYSIS:")
    print(f"   Current RSI Threshold: 52")

    below_52 = sum(1 for rsi in rsi_values if rsi <= 52)
    below_55 = sum(1 for rsi in rsi_values if rsi <= 55)
    below_58 = sum(1 for rsi in rsi_values if rsi <= 58)
    below_60 = sum(1 for rsi in rsi_values if rsi <= 60)

    print(f"\n   Opportunities with different thresholds:")
    print(f"   RSI ≤ 52: {below_52:3d} opportunités ({below_52/len(rsi_values)*100:5.1f}%)")
    print(f"   RSI ≤ 55: {below_55:3d} opportunités ({below_55/len(rsi_values)*100:5.1f}%)")
    print(f"   RSI ≤ 58: {below_58:3d} opportunités ({below_58/len(rsi_values)*100:5.1f}%)")
    print(f"   RSI ≤ 60: {below_60:3d} opportunités ({below_60/len(rsi_values)*100:5.1f}%)")

    # Activity summary
    print(f"\n📋 ACTIVITY SUMMARY:")
    print(f"   WAIT signals:  {wait_count}")
    print(f"   Trades taken:  {trade_count}")
    print(f"   Trade rate:    {trade_count/(wait_count+trade_count)*100:.1f}%")

    # Recommendations
    print(f"\n💡 RECOMMENDATIONS:")
    print(f"="*80)

    avg_rsi = statistics.mean(rsi_values)

    if avg_rsi > 55:
        print(f"✅ Market is in BULL MODE (Avg RSI = {avg_rsi:.1f})")
        print(f"   Current threshold (52) is TOO STRICT for bull markets")
        print(f"")
        print(f"   Suggested adjustments:")
        print(f"   • RSI Oversold: 52 → 58 (captures 50%+ opportunities)")
        print(f"   • Alternative:  52 → 60 (captures 70%+ opportunities)")
        print(f"")
        print(f"   Trade-offs:")
        print(f"   • RSI 58: More selective, better quality setups")
        print(f"   • RSI 60: More trades, slightly lower win rate")

    elif avg_rsi < 45:
        print(f"⚠️  Market is in BEAR/CORRECTION MODE (Avg RSI = {avg_rsi:.1f})")
        print(f"   Current threshold (52) is appropriate")
        print(f"   Consider tightening stops instead")

    else:
        print(f"📊 Market is NEUTRAL (Avg RSI = {avg_rsi:.1f})")
        print(f"   Current threshold (52) is balanced")
        print(f"   Consider slight adjustment to 55 for more activity")

    print("="*80)

if __name__ == "__main__":
    filepath = "backtest_Indices_^GSPC_20260208_213646.log"
    analyze_rsi_distribution(filepath)
