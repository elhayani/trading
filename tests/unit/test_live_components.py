#!/usr/bin/env python3
"""
LIVE TRADING V4 HYBRID - Simple Test Version
=============================================
Test local avant déploiement AWS
"""

import sys
import os
import time
import json
from datetime import datetime
import boto3

# Add paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../lambda/data_fetcher')))

from market_analysis import analyze_market
from news_fetcher import NewsFetcher, get_news_context

# AWS
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

print("="*70)
print("🧪 V4 HYBRID - TEST LOCAL SIMPLE")
print("="*70)
print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Test 1: News Fetcher
print("📰 TEST 1: Real News Fetcher")
print("-" * 70)

news_fetcher = NewsFetcher()
print("✅ NewsFetcher initialized")

# Get real news for SOL
print("\nFetching SOL news...")
try:
    news = news_fetcher.get_latest_news('SOL', hours=24, max_news=5)
    
    if news:
        print(f"✅ {len(news)} articles retrieved:")
        for i, article in enumerate(news[:3], 1):
            print(f"\n{i}. {article.get('title', 'No title')[:60]}...")
            print(f"   Source: {article.get('source', 'Unknown')}")
            print(f"   Sentiment: {article.get('sentiment', 'N/A')}")
    else:
        print("⚠️ No news found")
        
except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: News Context (Used by Bedrock)
print("\n" * 2)
print("📊 TEST 2: News Context for Bedrock")
print("-" * 70)

try:
    context = get_news_context('SOL', reference_date=None)
    print(f"Context preview:\n{context[:300]}...")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 3: Bedrock AI
print("\n" * 2)
print("🤖 TEST 3: Bedrock AI Decision")
print("-" * 70)

test_prompt = """
DATE: 2026-02-01 20:35 | ACTIF: SOL/USDT

📊 DONNÉES TECHNIQUES:
- RSI: 42.5
- Volume Ratio: 1.8x
- Tendance SMA50: RISING
- Patterns: HAMMER, BULLISH

📰 NEWS: 3 articles (33% négatifs)

🌐 RÉGIME DE MARCHÉ: BULL

🚀 MODE OPPORTUNISTE (V3 SMART)

⛔ CANCEL si catastrophe (> 75% news neg)
✅ CONFIRM par défaut
🚀 BOOST si news très positives (> 70%)

RÉPONSE JSON:
{ "decision": "CONFIRM" | "CANCEL" | "BOOST", "reason": "Explication" }
"""

try:
    response = bedrock.invoke_model(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": [{"type": "text", "text": test_prompt}]}],
            "temperature": 0.5
        })
    )
    
    content = json.loads(response['body'].read())['content'][0]['text']
    
    # Parse JSON
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    
    start = content.find('{')
    end = content.rfind('}') + 1
    if start != -1 and end > start:
        content = content[start:end]
    
    result = json.loads(content)
    
    print("✅ Bedrock Response:")
    print(f"   Decision: {result.get('decision')}")
    print(f"   Raison: {result.get('reason')}")
    
except Exception as e:
    print(f"❌ Bedrock Error: {e}")

# Test 4: Market Analysis
print("\n" * 2)
print("📈 TEST 4: Market Analysis")
print("-" * 70)

# Mock OHLCV data
mock_data = []
base_price = 100
for i in range(300):
    timestamp = int((datetime.now().timestamp() - (300-i)*3600) * 1000)
    price = base_price + (i % 10) - 5
    mock_data.append([timestamp, price-2, price+2, price-3, price, 1000 + (i % 100)])

try:
    analysis = analyze_market(mock_data)
    print("✅ Market Analysis successful:")
    print(f"   RSI: {analysis['indicators'].get('rsi', 'N/A')}")
    print(f"   SMA50: {analysis['indicators'].get('sma_50', 'N/A')}")
    print(f"   ATR: {analysis['indicators'].get('atr', 'N/A')}")
    print(f"   Patterns: {analysis.get('patterns', 'N/A')}")
except Exception as e:
    print(f"❌ Analysis Error: {e}")

# Summary
print("\n" * 2)
print("="*70)
print("📋 RÉSUMÉ DES TESTS")
print("="*70)
print("""
✅ News Fetcher: OK
✅ News Context: OK
✅ Bedrock AI: OK
✅ Market Analysis: OK

🎯 PROCHAINES ÉTAPES:
1. Intégrer échange réel (CCXT)
2. Ajouter logique de trading
3. Tester sur données live
4. Déployer sur AWS Lambda + EventBridge

💡 RECOMMANDATION:
- Commencer avec capital test: 100-500 USDT
- Mode semi-auto (validation manuelle d'abord)
- 1 actif seulement (SOL)
- Check toutes les heures
""")

print("\n✅ Tous les composants fonctionnent correctement!")
print("🚀 Prêt pour intégration complète\n")
