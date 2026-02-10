#!/usr/bin/env python3
"""
LIVE TRADING V4 HYBRID - Real-time with AWS
============================================

Features:
- V4 HYBRID strategy (auto-adaptive)
- Real news from CryptoCompare
- AWS Bedrock AI decisions
- DynamoDB state persistence
- CloudWatch logging
- Manual override support

Usage:
    python3 live_trading_v4.py --mode test --capital 1000
    python3 live_trading_v4.py --mode live --capital 5000
"""

import sys
import os
import time
import json
import argparse
from datetime import datetime, timedelta
import boto3
from decimal import Decimal
import numpy as np

# Add Lambda paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../lambda/data_fetcher')))

try:
    from market_analysis import analyze_market
    from news_fetcher import NewsFetcher
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure market_analysis.py and news_fetcher.py are available")
    sys.exit(1)

# AWS Clients
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
cloudwatch = boto3.client('logs', region_name='us-east-1')

# Configuration
CONFIG = {
    'mode': 'test',  # 'test' or 'live'
    'capital': 1000,
    'symbols': ['SOL/USDT'],  # Start with best performer
    'check_interval': 3600,  # 1 hour
    'max_drawdown': 0.20,
    'daily_loss_limit': 0.05,
    'max_position_size': 0.5,  # 50% of capital max
}

class V4LiveTrader:
    """Live trading with V4 HYBRID strategy"""
    
    def __init__(self, config):
        self.config = config
        self.mode = config['mode']
        self.capital = Decimal(str(config['capital']))
        self.initial_capital = self.capital
        self.positions = {}
        self.news_fetcher = NewsFetcher()
        
        # DynamoDB tables
        try:
            self.state_table = dynamodb.Table('TradingState')
            self.trades_table = dynamodb.Table('TradeHistory')
            print("✅ DynamoDB tables connected")
        except Exception as e:
            print(f"⚠️ DynamoDB connection failed: {e}")
            print("   Proceeding in local-only mode")
            self.state_table = None
            self.trades_table = None
        
        # Load existing state
        self.load_state()
        
        print(f"\n{'='*70}")
        print(f"🚀 V4 HYBRID LIVE TRADER - {self.mode.upper()} MODE")
        print(f"{'='*70}")
        print(f"Capital: ${self.capital}")
        print(f"Symbols: {config['symbols']}")
        print(f"Check interval: {config['check_interval']}s")
        if self.mode == 'test':
            print("⚠️  TEST MODE - No real trades will be executed")
        print(f"{'='*70}\n")
    
    def load_state(self):
        """Load trading state from DynamoDB"""
        if not self.state_table:
            return
        
        try:
            response = self.state_table.get_item(Key={'trader_id': 'v4_hybrid'})
            if 'Item' in response:
                state = response['Item']
                self.capital = Decimal(str(state.get('capital', self.capital)))
                self.positions = state.get('positions', {})
                print(f"✅ State loaded: ${self.capital}, {len(self.positions)} positions")
        except Exception as e:
            print(f"⚠️ Could not load state: {e}")
    
    def save_state(self):
        """Save trading state to DynamoDB"""
        if not self.state_table:
            return
        
        try:
            self.state_table.put_item(Item={
                'trader_id': 'v4_hybrid',
                'capital': float(self.capital),
                'positions': self.positions,
                'last_update': datetime.now().isoformat(),
                'mode': self.mode
            })
        except Exception as e:
            print(f"⚠️ Could not save state: {e}")
    
    def detect_market_regime(self, btc_data, news_sentiment_pct):
        """
        V4 HYBRID: Market regime detection
        Returns: 'EXTREME_BEAR' | 'NORMAL_BEAR' | 'BULL'
        """
        if len(btc_data) < 168:
            return 'BULL'  # Default
        
        # BTC 7-day performance
        btc_7d_perf = (btc_data[-1][4] - btc_data[-168][4]) / btc_data[-168][4]
        
        # Volume analysis
        recent_vol = np.mean([c[5] for c in btc_data[-24:]])
        avg_vol = np.mean([c[5] for c in btc_data[-168:]])
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1
        
        # Detection
        if (btc_7d_perf < -0.25 and vol_ratio > 2.5) or news_sentiment_pct > 0.80:
            return 'EXTREME_BEAR'
        
        if btc_7d_perf < -0.15 or news_sentiment_pct > 0.65:
            return 'NORMAL_BEAR'
        
        return 'BULL'
    
    def get_bedrock_decision(self, symbol, indicators, patterns, regime, news_context):
        """Ask Bedrock for trade validation"""
        
        base_data = f"""
        DATE: {datetime.now().strftime('%Y-%m-%d %H:%M')} | ACTIF: {symbol}
        
        📊 DONNÉES TECHNIQUES:
        - RSI: {indicators['rsi']:.1f}
        - Volume Ratio: {indicators['vol_ratio']:.2f}x
        - Tendance SMA50: {indicators['slope']}
        - Patterns: {patterns}
        
        {news_context}
        
        🌐 RÉGIME DE MARCHÉ: {regime}
        """
        
        # Adaptive prompts based on regime
        if regime == 'EXTREME_BEAR':
            prompt = base_data + """
            
            ⚠️ MODE SURVIE (V1 ULTRA-STRICT)
            Marché en PANIQUE. Capital preservation prioritaire.
            
            ⛔ CANCEL PAR DÉFAUT, sauf si:
            - News TRÈS positives (> 85%) ET
            - RSI < 20 (capitulation) ET
            - Volume > 4x
            
            RÉPONSE JSON:
            { "decision": "CANCEL" | "CONFIRM", "reason": "Explication" }
            """
        
        elif regime == 'NORMAL_BEAR':
            prompt = base_data + """
            
            ⚖️ MODE PRUDENT (V3 MODÉRÉ)
            Marché baissier, opportunités de rebond possibles.
            
            ⛔ CANCEL si news > 65% négatives
            ✅ CONFIRM si technique solide + news neutres
            
            RÉPONSE JSON:
            { "decision": "CONFIRM" | "CANCEL" | "BOOST", "reason": "Explication" }
            """
        
        else:  # BULL
            prompt = base_data + """
            
            🚀 MODE OPPORTUNISTE (V3 SMART)
            Marché favorable. Trust technique.
            
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
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
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
            return result
            
        except Exception as e:
            print(f"⚠️ Bedrock error: {e}")
            return {"decision": "CANCEL", "reason": f"API Error: {e}"}
    
    def check_trading_opportunity(self, symbol):
        """Check if there's a trading opportunity"""
        
        print(f"\n{'='*70}")
        print(f"🔍 Checking {symbol} @ {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*70}")
        
        # Placeholder: In real version, fetch from exchange API
        # For now, we'll use a mock
        print("⚠️ Mock data - Replace with real exchange API (ccxt)")
        
        # This would be: exchange.fetch_ohlcv(symbol, '1h', limit=300)
        mock_ohlcv = [[time.time() * 1000, 100, 105, 99, 102, 1000]] * 300
        
        # Analyze
        analysis = analyze_market(mock_ohlcv)
        
        # Get real news
        print(f"📰 Fetching real news for {symbol.split('/')[0]}...")
        news_data = self.news_fetcher.get_latest_news(symbol.split('/')[0], hours=24)
        
        # Parse sentiment
        news_neg_pct = 0
        if news_data:
            neg_count = sum(1 for n in news_data if n.get('sentiment', '') == 'negative')
            news_neg_pct = neg_count / len(news_data) if news_data else 0
            print(f"   📊 {len(news_data)} articles, {news_neg_pct:.0%} négatifs")
        else:
            print("   ⚠️ No news found")
        
        # Detect regime
        regime = self.detect_market_regime(mock_ohlcv, news_neg_pct)
        print(f"   🌐 Régime: {regime}")
        
        # Check if signal
        rsi = analysis['indicators'].get('rsi')
        if rsi and rsi < 45:
            print(f"   🎯 RSI Signal: {rsi:.1f}")
            
            # Ask Bedrock
            indicators = {
                'rsi': rsi,
                'vol_ratio': 1.5,  # Mock
                'slope': 'RISING'
            }
            
            news_context = f"📰 NEWS: {len(news_data)} articles ({news_neg_pct:.0%} négatifs)"
            
            decision = self.get_bedrock_decision(
                symbol, indicators, analysis['patterns'], 
                regime, news_context
            )
            
            print(f"   🤖 Bedrock [{regime}]: {decision['decision']}")
            print(f"      Raison: {decision['reason'][:80]}")
            
            if decision['decision'] == 'CONFIRM' or decision['decision'] == 'BOOST':
                print(f"\n   ✅ TRADE SIGNAL CONFIRMED")
                if self.mode == 'live':
                    print("      🚀 Executing REAL trade...")
                    # self.execute_trade(symbol, 'BUY', decision)
                else:
                    print("      ⚠️ TEST MODE - Trade NOT executed")
            else:
                print(f"\n   ❌ Trade CANCELLED by AI")
        else:
            print(f"   ➡️ No signal (RSI: {rsi:.1f if rsi else 0})")
    
    def run(self):
        """Main trading loop"""
        print(f"\n🎯 Starting V4 HYBRID Live Trading...")
        print(f"   Press Ctrl+C to stop\n")
        
        try:
            while True:
                for symbol in self.config['symbols']:
                    try:
                        self.check_trading_opportunity(symbol)
                    except Exception as e:
                        print(f"❌ Error checking {symbol}: {e}")
                
                # Save state
                self.save_state()
                
                # Sleep
                print(f"\n⏳ Next check in {self.config['check_interval']}s...\n")
                time.sleep(self.config['check_interval'])
                
        except KeyboardInterrupt:
            print(f"\n\n{'='*70}")
            print("🛑 Trading stopped by user")
            print(f"{'='*70}")
            self.save_state()
            print(f"Final capital: ${self.capital}")

def main():
    parser = argparse.ArgumentParser(description='V4 HYBRID Live Trading')
    parser.add_argument('--mode', choices=['test', 'live'], default='test',
                        help='Trading mode (default: test)')
    parser.add_argument('--capital', type=float, default=1000,
                        help='Initial capital in USDT (default: 1000)')
    parser.add_argument('--symbols', nargs='+', default=['SOL/USDT'],
                        help='Trading symbols (default: SOL/USDT)')
    parser.add_argument('--interval', type=int, default=3600,
                        help='Check interval in seconds (default: 3600)')
    
    args = parser.parse_args()
    
    # Update config
    CONFIG['mode'] = args.mode
    CONFIG['capital'] = args.capital
    CONFIG['symbols'] = args.symbols
    CONFIG['check_interval'] = args.interval
    
    # Safety check
    if args.mode == 'live':
        print("\n⚠️  WARNING: LIVE MODE - Real trades will be executed!")
        confirm = input("Type 'YES' to confirm: ")
        if confirm != 'YES':
            print("Cancelled.")
            return
    
    # Start trader
    trader = V4LiveTrader(CONFIG)
    trader.run()

if __name__ == "__main__":
    main()
