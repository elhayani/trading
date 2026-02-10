#!/bin/bash
set -e

echo "👑 DEPLOYING EMPIRE DASHBOARD INFRASTRUCTURE"
echo "=========================================="
echo ""

# Step 1: Build Lambda Layer with CCXT
echo "📦 Step 1/2: Building Lambda Layer (CCXT)..."
cd "$(dirname "$0")"
if [ -f "build_layer.sh" ]; then
    ./build_layer.sh
else
    echo "⚠️  build_layer.sh not found, skipping layer build"
fi

# Step 2: Deploy CDK Stack
echo ""
echo "🚀 Step 2/2: Deploying CDK Stack..."
cd ../infrastructure/cdk

# Install requirements if needed (assuming global/shared venv or similar, but for now just relying on env)
# pip install -r requirements.txt

cdk deploy EmpireDashboardStack --app "python3 app.py" --require-approval never

echo ""
echo "✅ Empire Dashboard Deployed!"
echo ""
echo "💡 New Features:"
echo "   ✅ Unified Binance Account (Crypto, Forex, Indices, Commodities)"
echo "   ✅ Real-time balance & margin detection"
echo "   ✅ Trade filters (Bot, Month, Status)"
echo "   ✅ Panic switches for all systems"
