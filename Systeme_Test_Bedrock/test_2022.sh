#!/bin/bash
#
# Backtest 2022 - Year Long Test (1d interval)
# =============================================
# Tests all 4 bots on 2022 data using daily candles
#

set -e

echo "======================================================================"
echo "📊 BACKTEST 2022 - FULL YEAR TEST (365 days)"
echo "======================================================================"
echo ""
echo "⚠️  Note: Using 1d interval (YFinance 1h limit = 730 days)"
echo ""

# Configuration
YEAR=2022
START_DATE="${YEAR}-01-01"
END_DATE="2023-01-01"
DAYS=365

echo "📅 Period: $START_DATE → $END_DATE"
echo "📈 Assets: Forex, Indices, Commodities, Crypto"
echo ""

# Check prerequisites
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found"
    exit 1
fi

echo "✅ Prerequisites OK"
echo ""

# Create results directory
RESULTS_DIR="backtest_results_2022"
mkdir -p $RESULTS_DIR

echo "🧪 Starting backtests (may take 10-15 minutes)..."
echo "----------------------------------------------------------------------"
echo ""

# Forex EURUSD
echo "💱 [1/4] Testing FOREX (EURUSD)..."
python3 run_test_v2.py \
    --asset-class Forex \
    --symbol EURUSD=X \
    --days $DAYS \
    > "${RESULTS_DIR}/forex_eurusd_2022.log" 2>&1 &
PID_FOREX=$!

# Indices S&P 500
echo "📈 [2/4] Testing INDICES (S&P 500)..."
python3 run_test_v2.py \
    --asset-class Indices \
    --symbol ^GSPC \
    --days $DAYS \
    > "${RESULTS_DIR}/indices_sp500_2022.log" 2>&1 &
PID_INDICES=$!

# Commodities Gold
echo "🛢️  [3/4] Testing COMMODITIES (Gold)..."
python3 run_test_v2.py \
    --asset-class Commodities \
    --symbol GC=F \
    --days $DAYS \
    > "${RESULTS_DIR}/commodities_gold_2022.log" 2>&1 &
PID_COMMODITIES=$!

# Crypto Bitcoin
echo "₿  [4/4] Testing CRYPTO (Bitcoin)..."
python3 run_test_v2.py \
    --asset-class Crypto \
    --symbol BTC-USD \
    --days $DAYS \
    > "${RESULTS_DIR}/crypto_btc_2022.log" 2>&1 &
PID_CRYPTO=$!

echo ""
echo "⏳ Backtests running in parallel..."
echo "   → Forex:       PID $PID_FOREX"
echo "   → Indices:     PID $PID_INDICES"
echo "   → Commodities: PID $PID_COMMODITIES"
echo "   → Crypto:      PID $PID_CRYPTO"
echo ""

# Monitor progress
while kill -0 $PID_FOREX 2>/dev/null || kill -0 $PID_INDICES 2>/dev/null || kill -0 $PID_COMMODITIES 2>/dev/null || kill -0 $PID_CRYPTO 2>/dev/null; do
    RUNNING=0
    kill -0 $PID_FOREX 2>/dev/null && RUNNING=$((RUNNING + 1))
    kill -0 $PID_INDICES 2>/dev/null && RUNNING=$((RUNNING + 1))
    kill -0 $PID_COMMODITIES 2>/dev/null && RUNNING=$((RUNNING + 1))
    kill -0 $PID_CRYPTO 2>/dev/null && RUNNING=$((RUNNING + 1))

    echo "⏳ Backtests en cours... $RUNNING processus actifs"
    sleep 5
done

echo ""
echo "======================================================================"
echo "✅ ALL BACKTESTS COMPLETED!"
echo "======================================================================"
echo ""

# Analyze results
echo "📊 RESULTS SUMMARY:"
echo "----------------------------------------------------------------------"
echo ""

for bot in forex_eurusd indices_sp500 commodities_gold crypto_btc; do
    logfile="${RESULTS_DIR}/${bot}_2022.log"

    if [ -f "$logfile" ]; then
        echo "📄 $bot:"

        # Count entries/exits
        ENTRIES=$(grep -c "ENTRY\|BUY\|LONG" "$logfile" 2>/dev/null || echo "0")
        EXITS=$(grep -c "EXIT\|CLOSE\|SELL" "$logfile" 2>/dev/null || echo "0")
        ERRORS=$(grep -c "ERROR\|FAILED" "$logfile" 2>/dev/null || echo "0")

        echo "   Entries: $ENTRIES"
        echo "   Exits:   $EXITS"
        echo "   Errors:  $ERRORS"
        echo ""
    else
        echo "❌ $bot: Log file not found"
        echo ""
    fi
done

echo "----------------------------------------------------------------------"
echo ""
echo "📁 Full logs available in: $RESULTS_DIR/"
echo ""
echo "To view individual logs:"
echo "  tail -100 ${RESULTS_DIR}/forex_eurusd_2022.log"
echo "  tail -100 ${RESULTS_DIR}/indices_sp500_2022.log"
echo "  tail -100 ${RESULTS_DIR}/commodities_gold_2022.log"
echo "  tail -100 ${RESULTS_DIR}/crypto_btc_2022.log"
echo ""
echo "======================================================================"
echo "🎯 BACKTEST 2022 COMPLETE"
echo "======================================================================"
