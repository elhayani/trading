#!/bin/bash
# V4 HYBRID - Dashboard Pro Fix

# Configuration
REGION="us-east-1"
FUNCTION_NAME="V4HybridLiveTrader"

echo "======================================================================"
echo "🎯 V4 HYBRID TRADING BOT - DASHBOARD (FIXED)"
echo "======================================================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 1. Lambda Status
echo -e "${BLUE}📊 LAMBDA STATUS:${NC}"
LAMBDA_DATA=$(aws lambda get-function --function-name $FUNCTION_NAME --region $REGION --output json 2>/dev/null)
STATE=$(echo $LAMBDA_DATA | jq -r '.Configuration.State' 2>/dev/null)
UPDATED=$(echo $LAMBDA_DATA | jq -r '.Configuration.LastModified' 2>/dev/null)

if [ "$STATE" == "Active" ]; then
    echo -e "  Status: ${GREEN}✅ Active${NC}"
else
    echo -e "  Status: ${YELLOW}⚠️ $STATE${NC}"
fi
echo "  Last Updated: $UPDATED"
echo ""

# 2. EventBridge Status
echo -e "${BLUE}⏰ EVENTBRIDGE CRON:${NC}"
RULE_DATA=$(aws events describe-rule --name V4HybridHourlyCron --region $REGION --output json 2>/dev/null)
RULE_STATE=$(echo $RULE_DATA | jq -r '.State' 2>/dev/null)
if [ "$RULE_STATE" == "ENABLED" ]; then
    echo -e "  Status: ${GREEN}✅ Enabled${NC}"
else
    echo -e "  Status: ${YELLOW}⚠️ Disabled${NC}"
fi
echo ""

# 3. DynamoDB State (Récupération propre)
echo -e "${BLUE}💾 DYNAMODB STATE:${NC}"
STATE_JSON=$(aws dynamodb get-item --table-name V4TradingState --key '{"trader_id": {"S": "v4_hybrid"}}' --region $REGION --output json 2>/dev/null)

if [ -n "$STATE_JSON" ] && [ "$STATE_JSON" != "{}" ]; then
    LAST_CHECK=$(echo $STATE_JSON | jq -r '.Item.last_check.S' 2>/dev/null)
    MODE=$(echo $STATE_JSON | jq -r '.Item.mode.S' 2>/dev/null)
    echo "  Last Check: $LAST_CHECK"
    echo "  Mode: $MODE"
else
    echo -e "  ${YELLOW}⚠️ No state found in DynamoDB. Run a manual trigger!${NC}"
fi
echo ""

# 4. Recent Activity (2h)
echo -e "${BLUE}📝 RECENT ACTIVITY (Last 2h):${NC}"
# On compte les requêtes START dans les logs
INVOCATIONS=$(aws logs filter-log-events --log-group-name /aws/lambda/$FUNCTION_NAME --start-time $(($(date +%s) - 7200))000 --filter-pattern "START" --region $REGION --output json 2>/dev/null | jq '.events | length')

echo "  Invocations: $INVOCATIONS"
echo "======================================================================"