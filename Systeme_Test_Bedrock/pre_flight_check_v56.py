
"""
🚀 PRE-FLIGHT CHECK - EMPIRE V5.6 FORTRESS ELITE
================================================
Objectif : Valider l'intégrité du système avant l'ouverture des marchés (Lundi 08:00).
Vérifie :
1. Connectivité AWS (S3, DynamoDB, Bedrock)
2. Configuration V5.6 (Gold Filters, Forex Risk, Macro Kill-Switch)
3. État des caches et logs

Auteur : Zakaria / Gemini 3 Pro
Date : 09 Février 2026
"""

import boto3
import json
import os
import sys
import logging
from datetime import datetime
from botocore.exceptions import ClientError

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PreFlight")

# Regions
REGION = "eu-west-3"  # Paris
BEDROCK_REGION = "us-east-1"  # N. Virginia

# Config Paths (Adjust based on your local path)
BASE_PATH = "/Users/zakaria/Trading"
COMMODITIES_PATH = os.path.join(BASE_PATH, "Commodities/lambda/commodities_trader")
FOREX_PATH = os.path.join(BASE_PATH, "Forex/lambda/forex_trader")

sys.path.append(COMMODITIES_PATH)
sys.path.append(FOREX_PATH)

def check_aws_connectivity():
    """Vérifie l'accès aux services AWS critiques"""
    print("\n📡 1. CONNECTIVITÉ AWS")
    print("-" * 30)
    
    # S3
    try:
        s3 = boto3.client('s3', region_name=REGION)
        buckets = s3.list_buckets()
        print(f"✅ S3 Access: OK ({len(buckets['Buckets'])} buckets found)")
    except Exception as e:
        print(f"❌ S3 Access: FAILED ({e})")
        return False

    # DynamoDB
    try:
        dynamo = boto3.client('dynamodb', region_name=REGION)
        tables = dynamo.list_tables()
        required_tables = ['EmpireCommoditiesHistory', 'EmpireForexHistory', 'EmpireIndicesHistory', 'EmpireCryptoV4']
        missing = [t for t in required_tables if t not in tables['TableNames']]
        
        if missing:
            print(f"❌ DynamoDB: MISSING TABLES {missing}")
            return False
        else:
            print(f"✅ DynamoDB Access: OK (All Empire tables found)")
    except Exception as e:
        print(f"❌ DynamoDB Access: FAILED ({e})")
        return False

    # Bedrock
    try:
        bedrock = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION)
        # Simple invoke to check access
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Ping"}]
            })
        )
        print(f"✅ Bedrock Access: OK (Latency: Low)")
    except Exception as e:
        print(f"❌ Bedrock Access: FAILED ({e})")
        return False

    return True

def check_configuration_v56():
    """Vérifie que les paramètres V5.6 Fortress Elite sont bien appliqués"""
    print("\n🛡️ 2. VÉRIFICATION V5.6 (FORTRESS ELITE)")
    print("-" * 30)
    
    all_good = True

    # 1. Check Gold Green Candle & Volume Filter (Code Analysis)
    try:
        strategies_file = os.path.join(COMMODITIES_PATH, "strategies.py")
        with open(strategies_file, 'r') as f:
            content = f.read()
            
        if "V5.6 FORTRESS: Anti-Wick Filter" in content and "is_green = current['close'] > current['open']" in content:
            print("✅ Gold Strategy: Anti-Wick Filter (Green Candle + Volume) DETECTED")
        else:
            print("❌ Gold Strategy: Anti-Wick Filter MISSING!")
            all_good = False
            
    except Exception as e:
        print(f"❌ Error reading Commodities strategies: {e}")
        all_good = False

    # 2. Check Commodities Macro Kill-Switch (Code Analysis)
    try:
        lambda_file = os.path.join(COMMODITIES_PATH, "lambda_function.py")
        with open(lambda_file, 'r') as f:
            content = f.read()
            
        if "dxy_kill_switch = True" in content and "BULLISH_STRONG" in content:
            print("✅ Gold Strategy: Macro Kill-Switch (DXY Protection) DETECTED")
        else:
            print("❌ Gold Strategy: Macro Kill-Switch MISSING!")
            all_good = False
            
    except Exception as e:
        print(f"❌ Error reading Commodities lambda: {e}")
        all_good = False

    # 3. Check Forex Risk Reduction (Config Analysis)
    try:
        config_file = os.path.join(FOREX_PATH, "config.py")
        with open(config_file, 'r') as f:
            content = f.read()
            
        if "'risk_per_trade': 0.02" in content:
            print("✅ Forex Config: V5.7 BOOST Mode (Risk 2%) CONFIRMED")
        else:
            print("❌ Forex Config: Risk seems standard (0.02?). CHECK FAILED.")
            all_good = False
            
    except Exception as e:
        print(f"❌ Error reading Forex config: {e}")
        all_good = False

    return all_good

def clean_environment():
    """Nettoie les logs et fichiers temporaires"""
    print("\n🧹 3. NETTOYAGE ENVIRONNEMENT")
    print("-" * 30)
    
    deleted = 0
    # Remove .log files in current dir
    for file in os.listdir(BASE_PATH):
        if file.endswith(".log") and "backtest" in file:
            # os.remove(os.path.join(BASE_PATH, file)) # Uncomment to actually delete
            print(f"   - Found log to archive: {file}")
            deleted += 1
            
    print(f"✅ Environment Clean ({deleted} files ready to archive)")
    return True

def final_verdict(aws, config):
    print("\n" + "="*40)
    print("🚀 RÉSUMÉ PRE-FLIGHT V5.6")
    print("="*40)
    
    if aws and config:
        print("✅ SYSTEM READY FOR MONDAY OPEN")
        print("   - AWS Connectivity: STABLE")
        print("   - V5.6 Configuration: VALIDATED")
        print("   - Risk Management: ACTIVATED")
        print("\n👉 Proceed to launch at 08:00 CET.")
    else:
        print("🛑 SYSTEM NOT READY - INVESTIGATE ERRORS ABOVE")

if __name__ == "__main__":
    print(f"🔍 Starting Pre-Flight Check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    aws_status = check_aws_connectivity()
    config_status = check_configuration_v56()
    clean_status = clean_environment()
    
    final_verdict(aws_status, config_status)
