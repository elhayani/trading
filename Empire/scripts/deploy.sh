#!/bin/bash
#
# V4 HYBRID - Automatic Deployment Script
# ========================================
#

set -e  # Exit on error

echo "======================================================================"
echo "🚀 V4 HYBRID AWS DEPLOYMENT"
echo "======================================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
STACK_NAME="V4TradingStack"
REGION="eu-west-3"
CDK_DIR="infrastructure/cdk"

# Step 1: Prerequisites
echo "📋 Step 1: Checking Prerequisites..."
echo "----------------------------------------------------------------------"

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI not found${NC}"
    echo "Install: brew install awscli"
    exit 1
fi
echo -e "${GREEN}✅ AWS CLI${NC}"

# Check CDK
if ! command -v cdk &> /dev/null; then
    echo -e "${RED}❌ CDK not found${NC}"
    echo "Install: npm install -g aws-cdk"
    exit 1
fi
echo -e "${GREEN}✅ CDK${NC}"

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ AWS credentials not configured${NC}"
    echo "Run: aws configure"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${GREEN}✅ AWS Account: $ACCOUNT_ID${NC}"

echo ""

# Step 2: Prepare Lambda Code
echo "📦 Step 2: Preparing Lambda Code..."
echo "----------------------------------------------------------------------"

# Empire/lambda/v4_trader already contains the source code.
# We no longer need to copy from crypto_trader.

echo -e "${GREEN}✅ Lambda code ready in Empire/lambda/v4_trader${NC}"
echo ""

# Step 2.1: Prepare Dependencies Layer
echo "📚 Step 2.1: Building Dependency Layer..."
echo "----------------------------------------------------------------------"

LAYER_DIR="lambda/layer/python"
rm -rf lambda/layer
mkdir -p $LAYER_DIR

echo "  → Installing CCXT & YFinance..."
# Install using manylinux2014_x86_64 for AWS Lambda compatibility
pip3 install \
    --platform manylinux2014_x86_64 \
    --target $LAYER_DIR \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    --upgrade \
    ccxt yfinance requests pandas numpy

# Optimize CCXT size: Keep only essential files if possible, but don't break imports
echo "  → Optimizing CCXT size..."
# find $LAYER_DIR/ccxt -maxdepth 1 -type f -name "*.py" ! -name "binance.py" ! -name "__init__.py" -delete
if [ -d "$LAYER_DIR/ccxt/async_support" ]; then
    rm -rf $LAYER_DIR/ccxt/async_support
fi

# Cleanup heavy libs (keeping pandas/numpy)
rm -rf $LAYER_DIR/scipy $LAYER_DIR/docutils $LAYER_DIR/boto3 $LAYER_DIR/botocore
# Cleanup non-essential heavy libs
rm -rf $LAYER_DIR/numba $LAYER_DIR/llvmlite

# Cleanup cache/dist info to save space
find $LAYER_DIR -name "__pycache__" -type d -exec rm -rf {} +
# find $LAYER_DIR -name "*.dist-info" -type d -exec rm -rf {} +

echo -e "${GREEN}✅ Layer prepared in lambda/layer${NC}"
echo ""

# Step 3: Update CDK App with Account ID
echo "⚙️  Step 3: Configuring CDK App..."
echo "----------------------------------------------------------------------"

# Update account in app.py
sed -i.bak "s/YOUR_ACCOUNT/$ACCOUNT_ID/" $CDK_DIR/app.py
echo -e "${GREEN}✅ Account ID updated: $ACCOUNT_ID${NC}"
echo ""

# Step 4: CDK Bootstrap (if needed)
echo "🔧 Step 4: CDK Bootstrap..."
echo "----------------------------------------------------------------------"

if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION &> /dev/null; then
    echo "  → Bootstrapping CDK..."
    cdk bootstrap aws://$ACCOUNT_ID/$REGION --app "python3 $CDK_DIR/app.py"
    echo -e "${GREEN}✅ CDK Bootstrapped${NC}"
else
    echo -e "${YELLOW}⚠️  CDK already bootstrapped${NC}"
fi
echo ""

# Step 5: CDK Synth (validate)
echo "🔍 Step 5: Validating CDK Stack..."
echo "----------------------------------------------------------------------"

cd $CDK_DIR
cdk synth --app "python3 app.py" > /dev/null
echo -e "${GREEN}✅ Stack validated${NC}"
echo ""

# Step 6: Deploy
echo "🚀 Step 6: Deploying to AWS..."
echo "----------------------------------------------------------------------"
echo -e "${YELLOW}⚠️  This will create AWS resources (Lambda, DynamoDB, EventBridge)${NC}"
echo ""

# Automated deployment - no confirmation prompt
echo "Deploying... (this may take 2-3 minutes)"
cdk deploy $STACK_NAME --app "python3 app.py" --require-approval never

echo ""
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo ""

# Step 7: Post-deployment verification
echo "🔎 Step 7: Verifying Deployment..."
echo "----------------------------------------------------------------------"

# Check Lambda
LAMBDA_NAME=$(aws lambda list-functions --query "Functions[?contains(FunctionName, 'V4Hybrid')].FunctionName" --output text | head -1)
if [ -n "$LAMBDA_NAME" ]; then
    echo -e "${GREEN}✅ Lambda created: $LAMBDA_NAME${NC}"
else
    echo -e "${RED}❌ Lambda not found${NC}"
fi

# Check DynamoDB Tables
STATE_TABLE=$(aws dynamodb list-tables --query "TableNames[?contains(@, 'V4TradingState')]" --output text)
if [ -n "$STATE_TABLE" ]; then
    echo -e "${GREEN}✅ DynamoDB State Table: $STATE_TABLE${NC}"
else
    echo -e "${RED}❌ State table not found${NC}"
fi

# Check EventBridge Rule
RULE=$(aws events list-rules --name-prefix V4Hybrid --query "Rules[0].Name" --output text)
if [ -n "$RULE" ] && [ "$RULE" != "None" ]; then
    echo -e "${GREEN}✅ EventBridge Rule: $RULE${NC}"
else
    echo -e "${RED}❌ EventBridge rule not found${NC}"
fi

echo ""

# Step 8: Test Manual Trigger
echo "🧪 Step 8: Testing Lambda..."
echo "----------------------------------------------------------------------"

# Optional manual test - commented out for automation
# read -p "Run manual test of Lambda? (yes/no): " test_confirm
test_confirm="no"

if [ "$test_confirm" == "yes" ]; then
    echo "  → Invoking Lambda..."
    
    aws lambda invoke \
        --function-name $LAMBDA_NAME \
        --payload '{"test": true}' \
        /tmp/lambda_response.json \
        --log-type Tail \
        --query 'LogResult' \
        --output text | base64 -d
    
    echo ""
    echo "Response:"
    cat /tmp/lambda_response.json | python3 -m json.tool
    echo ""
    echo -e "${GREEN}✅ Lambda test complete${NC}"
fi

echo ""

# Summary
echo "======================================================================"
echo "✅ DEPLOYMENT SUCCESSFUL!"
echo "======================================================================"
echo ""
echo "📋 Resources Created:"
echo "  - Lambda: $LAMBDA_NAME"
echo "  - DynamoDB: $STATE_TABLE"
echo "  - EventBridge: $RULE (runs hourly)"
echo ""
echo "🎯 Next Steps:"
echo "  1. Monitor CloudWatch Logs:"
echo "     aws logs tail /aws/lambda/$LAMBDA_NAME --follow"
echo ""
echo "  2. Check DynamoDB State:"
echo "     aws dynamodb scan --table-name $STATE_TABLE"
echo ""
echo "  3. View EventBridge Schedule:"
echo "     aws events describe-rule --name $RULE"
echo ""
echo "  4. To change to LIVE mode:"
echo "     aws lambda update-function-configuration \\"
echo "       --function-name $LAMBDA_NAME \\"
echo "       --environment Variables={TRADING_MODE=live}"
echo ""
echo "⚠️  Currently in TEST MODE - no real trades will be executed"
echo ""
echo "📖 Full guide: DEPLOYMENT_GUIDE.md"
echo "======================================================================"
