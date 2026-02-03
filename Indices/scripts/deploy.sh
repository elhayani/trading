#!/bin/bash
#
# Indices Trading - Automatic Deployment Script
# =============================================
#

set -e  # Exit on error

echo "======================================================================"
echo "📈 INDICES TRADING AWS DEPLOYMENT"
echo "======================================================================"
echo ""

# Configuration
STACK_NAME="IndicesTradingStack"
REGION="us-east-1"
CDK_DIR="Indices/infrastructure/cdk"
ACCOUNT_ID="946179054632"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

# Step 1: Prepare Dependencies Layer
echo "📚 Step 1: Building Indices Dependency Layer..."
echo "----------------------------------------------------------------------"

LAYER_DIR="Indices/lambda/layer_indices/python"
rm -rf Indices/lambda/layer_indices
mkdir -p $LAYER_DIR

echo "  → Installing yfinance, pandas_ta..."
# Target is python directory inside layer
# We need to install compatible versions if possible, but standard pip usually works for pure python
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

# Note: We use --no-deps above and list deps manually to control exactly what we get, 
# or we can rely on pip resolving. Let's try standard resolve with platform.
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

# Remove optional/heavy dependencies (Numba is 100MB+)
rm -rf $LAYER_DIR/numba $LAYER_DIR/llvmlite $LAYER_DIR/scipy


# Cleanup to reduce size
# find $LAYER_DIR -name "*.dist-info" -type d -exec rm -rf {} +
find $LAYER_DIR -name "__pycache__" -type d -exec rm -rf {} +

echo -e "${GREEN}✅ Layer prepared in Indices/lambda/layer_indices${NC}"
echo ""

# Step 2: Deploy
echo "🚀 Step 2: Deploying to AWS..."
echo "----------------------------------------------------------------------"

cd $CDK_DIR
# Run CDK Deploy with the specific app file
cdk deploy $STACK_NAME --app "python3 app.py" --require-approval never

echo ""
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo ""
