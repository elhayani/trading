import sys
import os
import ccxt
import pandas as pd
import numpy as np
import time
import json
from datetime import datetime, timedelta, timezone
import boto3

# --- CONFIGURATION PATHS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../lambda/v4_trader')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../shared')))

try:
    from market_analysis import analyze_market
    # V5.1 Modules
    from predictability_index import calculate_predictability_score, get_predictability_adjustment
    from micro_corridors import get_corridor_params, MarketRegime
except ImportError as e:
    print(f"❌ Erreur Import V5.1: {e}")
    # Don't exit, just mock for now if fails
    pass

# --- SIMULATION VECTORISÉE DU PREDICTABILITY INDEX ---
def calculate_rolling_predictability(df, window=50):
    """ Optimisation majeure: Vectorisation Pandas """
    # 1. Autocorrelation (Return vs Return lag 1) -> Rolling corr
    returns = df['close'].pct_change()
    rolling_autocorr = returns.rolling(window=window).corr(returns.shift(1))
    
    # 2. Wick Ratio (Vectorisé)
    body = (df['close'] - df['open']).abs()
    rng = df['high'] - df['low']
    wick_ratio = body / rng
    rolling_wick = wick_ratio.rolling(window=window).mean()
    
    # 3. Trend Fit (R2) - Approx via Correlation Price vs Index
    # R2 = correlation^2 pour linear regression simple
    # On corrèle le prix avec une suite d'entiers (0..n)
    # Pandas rolling corr needs Series vs Series. We can correlate price with time index?
    # Simple approx: Price vs Moving Average deviation? Or just linear slope consistency?
    # Let's focus on Autocorr & Wick for speed, they are key.
    
    # Score composite
    # Autocorr should be positive (trend) -> 0 to 1
    score_autocorr = (rolling_autocorr.fillna(0) + 1) / 2 # -1..1 -> 0..1
    
    # Wick: 1 is no wicks, 0 is all wicks.
    score_wick = rolling_wick.fillna(0.5)
    
    # Global Score (Approx)
    prediction_score = (score_autocorr * 50) + (score_wick * 50)
    
    return prediction_score * 100 # 0-100

def fetch_historical_data_s3(symbol, days, offset_days=0):
    """ Mode S3 """
    end_time = datetime.now() - timedelta(days=offset_days)
    start_time = end_time - timedelta(days=days)
    
    all_ohlcv = []
    bucket_name = "empire-trading-data-paris"
    s3 = boto3.client('s3', region_name='eu-west-3')
    
    safe_symbol = symbol.replace('/', '_')
    print(f"📥 [S3] Chargement optimisé {symbol}...")
    
    for y in range(start_time.year, end_time.year + 1):
        key = f"historical/{safe_symbol}/{y}.json"
        try:
            resp = s3.get_object(Bucket=bucket_name, Key=key)
            data = json.loads(resp['Body'].read().decode('utf-8'))
            all_ohlcv.extend(data)
        except Exception: 
            pass
            
    # Filter
    start_ts = int(start_time.timestamp() * 1000)
    end_ts = int(end_time.timestamp() * 1000)
    filtered = [x for x in all_ohlcv if start_ts <= x[0] <= end_ts]
    filtered.sort(key=lambda x: x[0])
    return filtered

def run_backtest_fast(symbol, year=2023):
    print(f"\n🚀 BACKTEST V5.1 FAST: {symbol} ({year})")
    
    # Load Data
    now = datetime.now()
    offset_days = max(0, (now - datetime(year, 12, 31)).days)
    ohlcv = fetch_historical_data_s3(symbol, days=365, offset_days=offset_days)
    
    if not ohlcv:
        print("❌ No Data.")
        return

    # Convert to DataFrame
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # --- PRÉ-CALCUL INDICATEURS (VECTORISÉ) ---
    print("⚡ Calcul Indicateurs Vectorisés...")
    df['rsi'] = df['close'].diff() # Placeholder RSI (vrai calcul plus bas si lib dispo)
    
    # Ta-Lib / Pandas TA would be better, manual calc here for speed/no-dep
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Predictability (Approximation Vectorisée)
    df['pred_score'] = calculate_rolling_predictability(df)
    
    # --- SIMULATION ---
    capital = 1000.0
    position = None
    trades = []
    
    for i, row in df.iterrows():
        if i < 50: continue
        
        # V5.1 FILTER: PREDICTABILITY
        is_predictable = row['pred_score'] > 25
        
        # SIGNAL BUY (RSI < 40 + Predictable)
        if position is None:
            if row['rsi'] < 40 and is_predictable:
                # Sizing based on Score (Simple logic: Better score = Bigger size)
                # Score 50 -> 1.0x, Score 80 -> 1.2x, Score 30 -> 0.8x
                size_mult = max(0.5, min(1.5, row['pred_score'] / 50))
                
                invest_amount = capital * size_mult
                if invest_amount > capital: invest_amount = capital # Max capital
                
                amount = invest_amount / row['close']
                position = {'entry': row['close'], 'amount': amount, 'time': row['date']}
        
        # SIGNAL SELL
        elif position:
            entry = position['entry']
            curr = row['close']
            pnl_pct = (curr - entry) / entry
            
            should_sell = False
            reason = ""
            
            if pnl_pct < -0.05: # SL -5%
                should_sell = True; reason = "STOP_LOSS"
            elif pnl_pct > 0.05: # TP +5%
                should_sell = True; reason = "TAKE_PROFIT"
            elif row['rsi'] > 70:
                should_sell = True; reason = "RSI_EXIT"
            # V5.1 Exit: Detriorating Score
            elif row['pred_score'] < 15:
                should_sell = True; reason = "PRED_CRASH"
                
            if should_sell:
                pnl = (curr - entry) * position['amount']
                capital += pnl
                trades.append({'pnl_pct': pnl_pct, 'reason': reason})
                position = None

    # STATS
    if trades:
        win_rate = len([t for t in trades if t['pnl_pct'] > 0]) / len(trades) * 100
        print("-" * 40)
        print(f"✅ RÉSULTAT ({len(trades)} trades)")
        print(f"Capital Final: ${capital:.2f} ({((capital-1000)/1000)*100:+.2f}%)")
        print(f"Win Rate:      {win_rate:.1f}%")
        print("-" * 40)
    else:
        print("⚠️ Aucun trade généré (Filtres trop stricts ?)")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        yr = int(sys.argv[1])
        run_backtest_fast('BTC/USDT', yr)
        run_backtest_fast('SOL/USDT', yr)
    else:
        run_backtest_fast('BTC/USDT', 2023)
