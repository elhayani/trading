#!/bin/bash
# 🏛️ EMPIRE V16.7.8 - Vérification Déploiement
# Script de validation avant mise en production

set -e

echo "=========================================="
echo "🏛️ EMPIRE V16.7.8 - AUDIT DE DÉPLOIEMENT"
echo "=========================================="
echo ""

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

# 1. Vérifier LIVE_MODE dans config.py
echo "1️⃣  Vérification LIVE_MODE dans config.py..."
if grep -q "LIVE_MODE = True" Empire/lambda/v4_trader/config.py; then
    echo -e "${GREEN}✅ LIVE_MODE = True (Production)${NC}"
else
    echo -e "${RED}❌ LIVE_MODE = False (Demo/Testnet)${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 2. Vérifier que les fichiers obsolètes sont supprimés
echo "2️⃣  Vérification suppression code mort..."
OBSOLETE_FILES=(
    "Empire/lambda/v4_trader/websocket_executor.py"
    "Empire/lambda/v4_trader/websocket_manager.py"
    "Empire/lambda/v4_trader/claude_analyzer.py"
    "Empire/lambda/v4_trader/lambda1_scanner_websocket.py"
    "Empire/lambda/v4_trader/lambda2_closer_websocket.py"
)

for file in "${OBSOLETE_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${RED}❌ Fichier obsolète trouvé: $file${NC}"
        ERRORS=$((ERRORS + 1))
    else
        echo -e "${GREEN}✅ Supprimé: $(basename $file)${NC}"
    fi
done
echo ""

# 3. Vérifier atomic persistence fix
echo "3️⃣  Vérification Atomic Persistence fix..."
if grep -q "V16.7.8 FIX: Single atomic operation" Empire/lambda/v4_trader/atomic_persistence.py; then
    echo -e "${GREEN}✅ Atomic persistence race condition fixée${NC}"
else
    echo -e "${RED}❌ Atomic persistence fix manquant${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 4. Vérifier leverage degradation alerts
echo "4️⃣  Vérification Leverage Degradation Alerts..."
if grep -q "LEVERAGE_DEGRADED" Empire/lambda/v4_trader/risk_manager.py; then
    echo -e "${GREEN}✅ Leverage degradation alerts présentes${NC}"
else
    echo -e "${RED}❌ Leverage degradation alerts manquantes${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 5. Vérifier error handling avec fail fast
echo "5️⃣  Vérification Error Handling (Fail Fast)..."
if grep -q "consecutive_errors" Empire/lambda/v4_trader/lambda2_closer.py; then
    echo -e "${GREEN}✅ Error handling avec compteur d'erreurs consécutives${NC}"
else
    echo -e "${RED}❌ Error handling fail fast manquant${NC}"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# 6. Vérifier BTC Compass initialization
echo "6️⃣  Vérification BTC Compass initialization..."
if grep -q "analyze_btc_trend" Empire/lambda/v4_trader/lambda1_scanner.py && \
   grep -q "analyze_btc_trend" Empire/lambda/v4_trader/lambda2_closer.py; then
    echo -e "${GREEN}✅ BTC Compass initialisé dans Scanner et Closer${NC}"
else
    echo -e "${YELLOW}⚠️  BTC Compass initialization incomplète${NC}"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# 7. Vérifier cache limits
echo "7️⃣  Vérification Cache Limits..."
if grep -q "self.btc_history\[-100:\]" Empire/lambda/v4_trader/btc_compass.py && \
   grep -q "future_events\[:20\]" Empire/lambda/v4_trader/macro_context.py; then
    echo -e "${GREEN}✅ Cache limits en place (BTC: 100, Events: 20)${NC}"
else
    echo -e "${YELLOW}⚠️  Cache limits manquants ou modifiés${NC}"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# 8. Vérifier AWS Lambda LIVE_MODE (si AWS CLI disponible)
echo "8️⃣  Vérification AWS Lambda LIVE_MODE..."
if command -v aws &> /dev/null; then
    REGION="ap-northeast-1"
    FUNCTIONS=("Lambda1Scanner" "Lambda2Closer")
    
    for func in "${FUNCTIONS[@]}"; do
        LIVE_MODE=$(aws lambda get-function-configuration \
            --function-name "$func" \
            --region "$REGION" \
            --query 'Environment.Variables.LIVE_MODE' \
            --output text 2>/dev/null || echo "NOT_FOUND")
        
        if [ "$LIVE_MODE" == "True" ] || [ "$LIVE_MODE" == "true" ]; then
            echo -e "${GREEN}✅ $func: LIVE_MODE = True${NC}"
        elif [ "$LIVE_MODE" == "NOT_FOUND" ] || [ "$LIVE_MODE" == "None" ]; then
            echo -e "${YELLOW}⚠️  $func: LIVE_MODE non défini (utilise config.py)${NC}"
            WARNINGS=$((WARNINGS + 1))
        else
            echo -e "${RED}❌ $func: LIVE_MODE = $LIVE_MODE (devrait être True)${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    done
else
    echo -e "${YELLOW}⚠️  AWS CLI non disponible, impossible de vérifier Lambda${NC}"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# 9. Vérifier structure DynamoDB
echo "9️⃣  Vérification DynamoDB State Table..."
if command -v aws &> /dev/null; then
    TABLE_NAME="V4TradingState"
    TABLE_STATUS=$(aws dynamodb describe-table \
        --table-name "$TABLE_NAME" \
        --region "ap-northeast-1" \
        --query 'Table.TableStatus' \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [ "$TABLE_STATUS" == "ACTIVE" ]; then
        echo -e "${GREEN}✅ DynamoDB Table: $TABLE_NAME (ACTIVE)${NC}"
    else
        echo -e "${RED}❌ DynamoDB Table: $TABLE_NAME ($TABLE_STATUS)${NC}"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${YELLOW}⚠️  AWS CLI non disponible${NC}"
fi
echo ""

# 10. Résumé
echo "=========================================="
echo "📊 RÉSUMÉ DE L'AUDIT"
echo "=========================================="
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ TOUS LES TESTS PASSÉS${NC}"
    echo -e "${GREEN}🚀 Prêt pour déploiement en production${NC}"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠️  $WARNINGS avertissement(s)${NC}"
    echo -e "${YELLOW}🟡 Déploiement possible avec surveillance${NC}"
    exit 0
else
    echo -e "${RED}❌ $ERRORS erreur(s) critique(s)${NC}"
    echo -e "${YELLOW}⚠️  $WARNINGS avertissement(s)${NC}"
    echo -e "${RED}🛑 NE PAS DÉPLOYER - Corriger les erreurs d'abord${NC}"
    exit 1
fi
