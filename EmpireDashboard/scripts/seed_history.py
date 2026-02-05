
import boto3
import uuid
import random
from datetime import datetime, timedelta
from decimal import Decimal

# Configuration
TABLE_NAME = "EmpireTradesHistory"
REGION = "eu-west-3"

# Client
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

def generate_trades():
    trades = []
    
    # Start Date: Jan 1st 2024
    current_date = datetime(2024, 1, 1)
    end_date = datetime.now()
    
    # 1. INDICES (Based on Backtest Results: ~+4500$ over 2 years)
    # Approx 80 trades total
    
    balance = 0
    
    while current_date < end_date:
        # Advance time by random 1-5 days
        current_date += timedelta(days=random.randint(1, 5))
        if current_date > end_date: break
        
        # Randomly choose an asset to trade
        r = random.random()
        
        trade = None
        
        # 40% Chance Indices Trade
        if r < 0.4:
            is_nasdaq = random.random() > 0.5
            if is_nasdaq:
                pair = "^NDX"
                strategy = "BOLLINGER_BREAKOUT"
                # Nasdaq: 40% win rate but high R:R
                outcome = "WIN" if random.random() < 0.40 else "LOSS"
                pnl = random.randint(300, 800) if outcome == "WIN" else random.randint(-250, -150)
            else:
                pair = "^GSPC"
                strategy = "TREND_PULLBACK"
                # SP500: 60% win rate low R:R
                outcome = "WIN" if random.random() < 0.60 else "LOSS"
                pnl = random.randint(100, 200) if outcome == "WIN" else random.randint(-120, -80)

            trade = {
                'AssetClass': 'Indices',
                'Pair': pair,
                'Strategy': strategy,
                'Type': 'LONG' if random.random() > 0.4 else 'SHORT',
                'PnL': pnl,
                'AI_Decision': 'CONFIRM',
                'AI_Reason': f"Momentum detected on {pair} with supportive macro news.",
                'EntryPrice': str(random.randint(15000, 20000)),
                'Status': 'CLOSED'
            }

        # 30% Chance Forex Trade (EURUSD/USDJPY)
        elif r < 0.7:
            pair = "EURUSD" if random.random() > 0.5 else "USDJPY"
            strategy = "TREND_FOLLOWING"
            outcome = "WIN" if random.random() < 0.45 else "LOSS"
            pnl = random.randint(50, 150) if outcome == "WIN" else random.randint(-80, -40)
            
            trade = {
                'AssetClass': 'Forex',
                'Pair': pair,
                'Strategy': strategy,
                'Type': 'LONG',
                'PnL': pnl,
                'AI_Decision': 'CONFIRM',
                'AI_Reason': "Dollar weakness confirmed by latest CPI data.",
                'EntryPrice': str(random.uniform(1.05, 1.15) if pair == 'EURUSD' else random.randint(140, 155)),
                'Status': 'CLOSED'
            }
            
        # 30% Chance Crypto Trade (SOL/BTC)
        else:
            pair = "SOL/USDT"
            strategy = "V4_HYBRID"
            outcome = "WIN" if random.random() < 0.35 else "LOSS" # Lower win rate, big wins
            pnl = random.randint(200, 1000) if outcome == "WIN" else random.randint(-300, -100)
            
            trade = {
                'AssetClass': 'Crypto',
                'Pair': pair,
                'Strategy': strategy,
                'Type': 'BUY',
                'PnL': pnl,
                'AI_Decision': 'CONFIRM',
                'AI_Reason': "Bullish divergence on 4H RSI with on-chain volume spike.",
                'EntryPrice': str(random.randint(80, 200)),
                'Status': 'CLOSED'
            }

        # Common Fields
        trade['TradeId'] = f"HIST-{uuid.uuid4().hex[:8]}"
        trade['Timestamp'] = current_date.isoformat()
        
        trades.append(trade)

    return trades

def seed_db():
    print(f"🌱 Seeding {TABLE_NAME} with historical data...")
    trades = generate_trades()
    
    with table.batch_writer() as batch:
        for t in trades:
            # Convert float PnL to Decimal/String
            t['PnL'] = Decimal(str(t['PnL']))
            batch.put_item(Item=t)
            
    print(f"✅ Successfully injected {len(trades)} trades.")
    
    # Calculate Total PnL
    total = sum(t['PnL'] for t in trades)
    print(f"💰 Simulated Total PnL: ${total}")

if __name__ == "__main__":
    seed_db()
