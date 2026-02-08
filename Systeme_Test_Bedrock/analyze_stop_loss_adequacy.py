#!/usr/bin/env python3
"""
Analyze if Stop Loss is adequate for higher RSI entries (58 vs 52)
"""
import csv
import statistics

def analyze_sl_adequacy(filepath):
    """
    Analyze ATR and potential drawdown after entry
    """
    print("="*80)
    print("🎯 STOP LOSS ADEQUACY ANALYSIS")
    print("="*80)

    entries = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

        for i, row in enumerate(rows):
            if row['TYPE'] in ['BUY', 'LONG']:
                entry_price = float(row['PRICE'])
                atr = float(row['ATR']) if row['ATR'] and float(row['ATR']) > 0 else 0

                # Look ahead to find lowest price after entry (within next 10 bars)
                max_drawdown = 0
                for j in range(i+1, min(i+11, len(rows))):
                    future_price = float(rows[j]['PRICE'])
                    drawdown_pct = ((future_price - entry_price) / entry_price) * 100
                    if drawdown_pct < max_drawdown:
                        max_drawdown = drawdown_pct

                if atr > 0:
                    atr_pct = (atr / entry_price) * 100
                    entries.append({
                        'price': entry_price,
                        'atr': atr,
                        'atr_pct': atr_pct,
                        'max_drawdown': max_drawdown
                    })

    if not entries:
        print("No valid entries found")
        return

    # Calculate statistics
    atr_values = [e['atr_pct'] for e in entries]
    drawdown_values = [e['max_drawdown'] for e in entries]

    print(f"\n📊 ATR STATISTICS (Current RSI ≤52):")
    print(f"   Average ATR:     {statistics.mean(atr_values):.2f}%")
    print(f"   Min ATR:         {min(atr_values):.2f}%")
    print(f"   Max ATR:         {max(atr_values):.2f}%")
    print(f"   Median ATR:      {statistics.median(atr_values):.2f}%")

    print(f"\n📉 DRAWDOWN AFTER ENTRY (Next 10 bars):")
    print(f"   Average Drawdown: {statistics.mean(drawdown_values):.2f}%")
    print(f"   Worst Drawdown:   {min(drawdown_values):.2f}%")
    print(f"   Best Case:        {max(drawdown_values):.2f}%")

    # Current SL configuration
    sl_atr_mult = 1.4
    fixed_sl_pct = 4.0

    print(f"\n🛡️ CURRENT STOP LOSS CONFIGURATION:")
    print(f"   Method 1 (ATR-based): {sl_atr_mult} × ATR")
    print(f"   Method 2 (Fixed):     -{fixed_sl_pct}%")

    # Calculate actual SL distances
    avg_atr = statistics.mean(atr_values)
    sl_atr_distance = sl_atr_mult * avg_atr
    worst_drawdown = min(drawdown_values)

    print(f"\n🎯 STOP LOSS DISTANCE ANALYSIS:")
    print(f"   ATR-based SL:     -{sl_atr_distance:.2f}%")
    print(f"   Fixed SL:         -{fixed_sl_pct:.2f}%")
    print(f"   Actual SL used:   -{max(sl_atr_distance, fixed_sl_pct):.2f}% (whichever is wider)")
    print(f"   Worst Drawdown:   {worst_drawdown:.2f}%")

    # Calculate buffer
    effective_sl = max(sl_atr_distance, fixed_sl_pct)
    buffer = effective_sl - abs(worst_drawdown)

    print(f"\n📐 SAFETY BUFFER:")
    print(f"   Current Buffer:   {buffer:.2f}%")

    if buffer < 1.0:
        print(f"   Status:           ⚠️  TIGHT (< 1%)")
    elif buffer < 2.0:
        print(f"   Status:           ⚠️  MODERATE (1-2%)")
    else:
        print(f"   Status:           ✅ COMFORTABLE (> 2%)")

    # Recommendations for RSI 58
    print(f"\n" + "="*80)
    print("💡 RECOMMENDATIONS FOR RSI 58")
    print("="*80)

    print(f"\n🔍 Analysis:")
    print(f"   At RSI 52: Worst drawdown = {worst_drawdown:.2f}%")
    print(f"   At RSI 58: Expected worst drawdown ≈ {worst_drawdown * 1.3:.2f}% (+30% estimate)")
    print(f"              Reason: Buying closer to local top")

    # Calculate needed SL for RSI 58
    estimated_worst_dd_58 = worst_drawdown * 1.3
    recommended_sl = abs(estimated_worst_dd_58) + 2.0  # +2% buffer

    print(f"\n🎯 RECOMMENDED ADJUSTMENTS:")
    print(f"   Current Config:")
    print(f"     - sl_atr_mult: 1.4")
    print(f"     - Fixed SL:    -4.0%")
    print(f"     - Effective:   ~{effective_sl:.1f}%")

    if recommended_sl > effective_sl:
        new_sl_atr_mult = recommended_sl / avg_atr
        new_fixed_sl = recommended_sl

        print(f"\n   ⚠️  NEEDS WIDENING:")
        print(f"     Option 1 (ATR-based):")
        print(f"       - sl_atr_mult: 1.4 → {new_sl_atr_mult:.1f}")
        print(f"     Option 2 (Fixed):")
        print(f"       - Fixed SL: -4.0% → -{new_fixed_sl:.1f}%")
        print(f"     Option 3 (Hybrid - RECOMMENDED):")
        print(f"       - sl_atr_mult: 1.4 → 1.8 (reasonable bump)")
        print(f"       - Fixed SL: -4.0% → -5.0%")
    else:
        print(f"\n   ✅ CURRENT SL IS ADEQUATE")
        print(f"      Buffer: {buffer:.2f}% should handle RSI 58 entries")

    # Risk/Reward analysis
    tp_atr_mult = 5.0
    tp_distance = tp_atr_mult * avg_atr

    print(f"\n📊 RISK/REWARD WITH RSI 58:")
    print(f"   Take Profit:  +{tp_distance:.2f}% (5.0 × ATR)")
    print(f"   Stop Loss:    -{recommended_sl:.2f}%")
    print(f"   R/R Ratio:    1:{tp_distance/recommended_sl:.2f}")

    if tp_distance/recommended_sl < 2.0:
        print(f"   Status:       ⚠️  Below 1:2 (consider widening TP)")
    elif tp_distance/recommended_sl < 3.0:
        print(f"   Status:       ✅ Acceptable (1:2 to 1:3)")
    else:
        print(f"   Status:       ✅ Excellent (> 1:3)")

    print("="*80)

if __name__ == "__main__":
    filepath = "backtest_Indices_^GSPC_20260208_213646.log"
    analyze_sl_adequacy(filepath)
