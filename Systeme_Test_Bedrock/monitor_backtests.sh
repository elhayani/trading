#!/bin/bash
# Monitor backtests progression

echo "🔍 Monitoring Backtests (2025 - 365 days)..."
echo "================================================"
echo ""

while true; do
    clear
    echo "📊 BACKTEST PROGRESS MONITOR - V6.1 (2025)"
    echo "================================================"
    date
    echo ""

    # Check if processes are running
    echo "🔄 Running Processes:"
    ps aux | grep "run_test_v2.py" | grep -v grep | wc -l | xargs echo "Active backtests:"
    echo ""

    # Check log file sizes (proxy for progress)
    echo "📈 Progress (Log Sizes):"
    if [ -f backtest_forex_2025.log ]; then
        echo "  Forex:       $(wc -l < backtest_forex_2025.log) lines"
    fi
    if [ -f backtest_indices_sp500_2025.log ]; then
        echo "  Indices:     $(wc -l < backtest_indices_sp500_2025.log) lines"
    fi
    if [ -f backtest_commodities_gold_2025.log ]; then
        echo "  Commodities: $(wc -l < backtest_commodities_gold_2025.log) lines"
    fi
    if [ -f backtest_crypto_btc_2025.log ]; then
        echo "  Crypto:      $(wc -l < backtest_crypto_btc_2025.log) lines"
    fi
    echo ""

    # Find generated CSV files
    echo "📁 Generated CSV Files:"
    ls -lh backtest_*_2026*.log 2>/dev/null | tail -4 | awk '{print "  "$9" - "$5}'
    echo ""

    # Check if all done
    RUNNING=$(ps aux | grep "run_test_v2.py" | grep -v grep | wc -l)
    if [ "$RUNNING" -eq 0 ]; then
        echo "✅ ALL BACKTESTS COMPLETED!"
        echo ""
        echo "Results:"
        ls -lh backtest_*_2026*.log 2>/dev/null
        break
    fi

    echo "⏳ Waiting... (Press Ctrl+C to stop monitoring)"
    sleep 10
done
