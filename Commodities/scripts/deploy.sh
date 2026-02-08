#!/bin/bash
#
# Commodities Trading - Automatic Deployment Script
# =================================================
#

set -e  # Exit on error

echo "======================================================================"
echo "🛢️  COMMODITIES TRADING AWS DEPLOYMENT"
echo "======================================================================"
echo ""

# Configuration
STACK_NAME="CommoditiesTradingStack"
REGION="eu-west-3"
CDK_DIR="infrastructure/cdk"
ACCOUNT_ID="946179054632"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

# Step 1: Prepare Dependencies Layer
echo "📚 Step 1: Building Commodities Dependency Layer..."
echo "----------------------------------------------------------------------"

LAYER_DIR="lambda/layer_commodities/python"
rm -rf lambda/layer_commodities
mkdir -p $LAYER_DIR

echo "  → Installing yfinance, pandas_ta..."
# Install Linux-compatible wheels for AWS Lambda
pip3 install \
    --platform manylinux2014_x86_64 \
    --target $LAYER_DIR \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    --upgrade \
    --no-deps \
    yfinance requests lxml multitasking beautifulsoup4 frozendict peewee platformdirs

pip3 install \
    --platform manylinux2014_x86_64 \
    --target $LAYER_DIR \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    --upgrade \
    yfinance

# Remove heavy libs provided by AWS Layer
rm -rf $LAYER_DIR/numpy $LAYER_DIR/pandas $LAYER_DIR/dateutil $LAYER_DIR/pytz

# Remove optional/heavy dependencies
rm -rf $LAYER_DIR/numba $LAYER_DIR/llvmlite $LAYER_DIR/scipy

# Cleanup
find $LAYER_DIR -name "__pycache__" -type d -exec rm -rf {} +

echo -e "${GREEN}✅ Layer prepared in lambda/layer_commodities${NC}"
echo ""

# Step 2: Deploy
echo "🚀 Step 2: Deploying to AWS..."
echo "----------------------------------------------------------------------"

cd $CDK_DIR
# Run CDK Deploy
cdk deploy $STACK_NAME --app "python3 app.py" --require-approval never

echo ""
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo ""
