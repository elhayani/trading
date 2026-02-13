"""
🧪 TEST EARLY EXIT: "Early Exit for Opportunity" (75% / Score+)
==============================================================
"""

import os
import sys
import uuid
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# Setup env
os.environ.setdefault('AWS_DEFAULT_REGION', 'eu-west-3')
os.environ.setdefault('HISTORY_TABLE', 'EmpireTradesHistory')
os.environ.setdefault('SKIPPED_TABLE', 'EmpireSkippedTrades')
os.environ.setdefault('STATE_TABLE', 'V4TradingState')
os.environ.setdefault('TRADING_MODE', 'dry_run')

# Local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import TradingConfig
from v4_hybrid_lambda import TradingEngine, AWSClients
from models import AssetClass

def test_early_exit():
    print("🚀 Starting Early Exit Test...")
    
    # Reset Config for test
    TradingConfig.MAX_OPEN_TRADES = 1 # Force slot full easily
    
    # Mock dependencies
    mock_exchange = MagicMock()
    mock_persistence = MagicMock()
    
    # 1. Setup existing weak position
    # Time: 16 min ago (75% of 20min is 15min)
    entry_time = (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()
    weak_pos = {
        'trade_id': 'TEST-WEAK',
        'symbol': 'ETH/USDT:USDT',
        'entry_price': 2500.0,
        'quantity': 0.1,
        'direction': 'LONG',
        'asset_class': 'crypto',
        'score': 70,
        'ai_score': 70,
        'entry_time': entry_time,
        'risk_dollars': 10,
        'stop_loss': 2400.0,
        'take_profit': 2600.0
    }
    
    positions = {'ETH/USDT:USDT': weak_pos}
    mock_persistence.load_positions.return_value = positions
    
    # 2. Mock ticker for weak pos (stagnating: 2501.0 -> +0.04% PnL)
    mock_exchange.fetch_ticker.return_value = {'last': 2501.0}
    
    # 3. Setup strong incoming signal
    new_symbol = 'SOL/USDT:USDT'
    new_ta = {'score': 85, 'rsi': 25, 'price': 100.0, 'signal_type': 'LONG'} # Score delta: +15
    new_decision = {'proceed': True, 'confidence': 0.85, 'quantity': 1.0, 'risk_dollars': 10} # AI Score delta: +15
    
    # Build engine
    with patch('v4_hybrid_lambda.AWSClients'), \
         patch('v4_hybrid_lambda.PersistenceLayer'), \
         patch('v4_hybrid_lambda.ExchangeConnector') as mock_conn:
        
        engine = TradingEngine()
        engine.exchange = mock_exchange
        engine.persistence = mock_persistence
        
        # Mock _close_position to succeed
        engine._close_position = MagicMock(return_value=True)
        
        # Test the early exit check
        print("🔍 Evaluating early exit...")
        result = engine._evaluate_early_exit_for_opportunity(positions, new_symbol, new_ta, new_decision)
        
        if result:
            print("✅ TEST PASSED: Early Exit triggered successfully")
        else:
            print("❌ TEST FAILED: Early Exit did not trigger")

if __name__ == "__main__":
    test_early_exit()
