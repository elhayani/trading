#!/bin/bash
#
# Empire V6.1 - Project Cleanup Script
# =====================================
# Nettoie les fichiers temporaires tout en préservant les fichiers importants
#

set -e

echo "======================================================================"
echo "🧹 EMPIRE V6.1 PROJECT CLEANUP"
echo "======================================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
TOTAL_REMOVED=0
TOTAL_SIZE=0

echo "📋 Step 1: Analyzing files to clean..."
echo "----------------------------------------------------------------------"

# Find and count files
LOG_COUNT=$(find . -type f -name "*.log" ! -name "*v61*" ! -name "*V6_1*" | wc -l | xargs)
PYC_COUNT=$(find . -type f -name "*.pyc" | wc -l | xargs)
PYCACHE_COUNT=$(find . -type d -name "__pycache__" | wc -l | xargs)
BAK_COUNT=$(find . -type f -name "*.bak" | wc -l | xargs)
DS_COUNT=$(find . -type f -name ".DS_Store" | wc -l | xargs)

echo "  → Old logs (non-V6.1): $LOG_COUNT files"
echo "  → Python cache (.pyc): $PYC_COUNT files"
echo "  → __pycache__ dirs: $PYCACHE_COUNT directories"
echo "  → Backup files (.bak): $BAK_COUNT files"
echo "  → .DS_Store: $DS_COUNT files"
echo ""

echo "⚠️  Files that will be PRESERVED:"
echo "  ✅ V6.1 backtest logs (backtest_*_v61_*.log)"
echo "  ✅ Documentation (*.md files)"
echo "  ✅ Source code (*.py, *.sh, *.json)"
echo "  ✅ Lambda ZIPs in lambda/ directories"
echo "  ✅ Configuration files"
echo ""

read -p "Continue with cleanup? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cleanup cancelled"
    exit 1
fi

echo ""
echo "🗑️  Step 2: Removing temporary files..."
echo "----------------------------------------------------------------------"

# 1. Remove old log files (keep V6.1 logs)
echo "  → Cleaning old backtest logs..."
find . -type f -name "backtest_*.log" ! -name "*v61*" ! -name "*V6_1*" -delete 2>/dev/null || true
find . -type f -name "*_deploy.log" -delete 2>/dev/null || true
REMOVED=$((LOG_COUNT))
TOTAL_REMOVED=$((TOTAL_REMOVED + REMOVED))
echo -e "${GREEN}    ✓ Removed $REMOVED log files${NC}"

# 2. Remove Python cache
echo "  → Cleaning Python cache..."
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
REMOVED=$((PYC_COUNT + PYCACHE_COUNT))
TOTAL_REMOVED=$((TOTAL_REMOVED + REMOVED))
echo -e "${GREEN}    ✓ Removed $REMOVED cache files/dirs${NC}"

# 3. Remove backup files
echo "  → Cleaning backup files..."
find . -type f -name "*.bak" -delete 2>/dev/null || true
REMOVED=$BAK_COUNT
TOTAL_REMOVED=$((TOTAL_REMOVED + REMOVED))
echo -e "${GREEN}    ✓ Removed $REMOVED backup files${NC}"

# 4. Remove .DS_Store
echo "  → Cleaning .DS_Store..."
find . -type f -name ".DS_Store" -delete 2>/dev/null || true
REMOVED=$DS_COUNT
TOTAL_REMOVED=$((TOTAL_REMOVED + REMOVED))
echo -e "${GREEN}    ✓ Removed $REMOVED .DS_Store files${NC}"

# 5. Clean CDK outputs (except current assets)
echo "  → Cleaning CDK outputs..."
CDK_CLEANED=0
for bot in Forex Indices Commodities Crypto; do
    if [ -d "$bot/infrastructure/cdk/cdk.out" ]; then
        # Keep manifest.json and tree.json, remove old assets
        find "$bot/infrastructure/cdk/cdk.out" -type d -name "asset.*" -mtime +7 -exec rm -rf {} + 2>/dev/null || true
        find "$bot/infrastructure/cdk/cdk.out/.cache" -type f -mtime +7 -delete 2>/dev/null || true
        CDK_CLEANED=$((CDK_CLEANED + 1))
    fi
done
echo -e "${GREEN}    ✓ Cleaned CDK outputs for $CDK_CLEANED bots${NC}"

# 6. Clean old Lambda ZIPs (keep current ones in lambda/ dirs)
echo "  → Cleaning old Lambda ZIPs..."
ZIP_CLEANED=0
# Remove ZIPs in root directories (deployment artifacts)
find ./Forex ./Indices ./Commodities ./Crypto -maxdepth 1 -type f -name "*.zip" -delete 2>/dev/null || true
# Remove old ZIPs in scripts/
find ./Crypto/scripts -type f -name "*.zip" -delete 2>/dev/null || true
ZIP_CLEANED=$?
echo -e "${GREEN}    ✓ Cleaned old ZIP files${NC}"

# 7. Clean temporary test data
echo "  → Cleaning temporary test data..."
find ./Systeme_Test_Bedrock -type f -name "backtest_*.log" ! -name "*v61*" ! -name "*V6_1*" -delete 2>/dev/null || true
echo -e "${GREEN}    ✓ Cleaned test data${NC}"

# 8. Clean lambda layer duplicates (keep only current)
echo "  → Cleaning duplicate lambda layers..."
for bot in Forex Indices Commodities Crypto; do
    # Remove nested duplicate lambda directories (e.g., Forex/Forex/lambda)
    if [ -d "$bot/$bot/lambda" ]; then
        rm -rf "$bot/$bot" 2>/dev/null || true
        echo -e "${GREEN}    ✓ Removed duplicate layer in $bot${NC}"
    fi
done

echo ""
echo "======================================================================"
echo "✅ CLEANUP COMPLETE!"
echo "======================================================================"
echo ""
echo "📊 Summary:"
echo "  → Total files/directories removed: $TOTAL_REMOVED"
echo ""
echo "📁 Project Structure (cleaned):"
du -sh . 2>/dev/null || echo "  [Size calculation unavailable]"
echo ""
echo "🔍 Verification:"
echo "  → Remaining __pycache__: $(find . -type d -name "__pycache__" | wc -l | xargs)"
echo "  → Remaining .pyc files: $(find . -type f -name "*.pyc" | wc -l | xargs)"
echo "  → Remaining old logs: $(find . -type f -name "*.log" ! -name "*v61*" | wc -l | xargs)"
echo "  → V6.1 logs preserved: $(find . -type f -name "*v61*.log" | wc -l | xargs)"
echo ""
echo -e "${GREEN}✅ Project is clean and ready!${NC}"
echo ""
