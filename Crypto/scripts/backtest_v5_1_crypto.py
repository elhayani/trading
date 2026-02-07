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
# Ajout des paths pour les modules partagés V5.1
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../lambda/v4_trader')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../shared')))

try:
    from market_analysis import analyze_market
    # V5.1 Modules
    from predictability_index import calculate_predictability_score, get_predictability_adjustment
    from micro_corridors import get_corridor_params, MarketRegime
except ImportError as e:
    print(f"❌ Erreur Import V5.1: {e}")
    sys.exit(1)

# --- SIMULATION MACRO (Mock) ---
# Faute de données historiques DXY/VIX synchronisées, on simule un régime "NEUTRE" par défaut
# ou "RISK_OFF" si le BTC crashe fort.
class MacroSimulation:
    @staticmethod
    def get_mock_regime(btc_perf_24h):
        """
        Simule le régime macro basé sur le proxy BTC.
        Si BTC -5% en 24h -> On assume Risk-Off global.
        """
        if btc_perf_24h < -0.05:
            return {'regime': 'RISK_OFF', 'can_trade': True, 'size_multiplier': 0.5}
        elif btc_perf_24h < -0.10:
            return {'regime': 'DANGER', 'can_trade': False, 'size_multiplier': 0.0}
        else:
            return {'regime': 'NEUTRAL', 'can_trade': True, 'size_multiplier': 1.0}

def fetch_historical_data_s3(symbol, days, offset_days=0):
    """ Récupère les données depuis S3 (Format [timestamp, open, high, low, close, volume]) """
    end_time = datetime.now() - timedelta(days=offset_days)
    start_time = end_time - timedelta(days=days)
    start_year = start_time.year
    end_year = end_time.year
    
    all_ohlcv = []
    bucket_name = "empire-trading-data-paris" # Hardcoded for test
    s3 = boto3.client('s3', region_name='eu-west-3')
    
    safe_symbol = symbol.replace('/', '_')
    print(f"📥 [S3] Chargement {symbol} ({start_year}-{end_year})...")
    
    for y in range(start_year, end_year + 1):
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

def run_backtest_v51(symbol, year=2025):
    """ Backtest V5.1 Fortress Engine """
    print(f"\n🏰 BACKTEST V5.1 FORTRESS: {symbol} ({year})")
    
    # 1. Load Data
    now = datetime.now()
    start_of_year = datetime(year, 1, 1)
    offset_days = (now - datetime(year, 12, 31)).days
    if offset_days < 0: offset_days = 0 # Année en cours
    
    # On charge l'année entière
    ohlcv = fetch_historical_data_s3(symbol, days=365, offset_days=offset_days)
    if not ohlcv:
        print("❌ No Data found.")
        return

    # 2. Simulation Loop
    capital = 1000.0
    initial_capital = capital
    trades = []
    position = None
    
    min_history = 201
    
    # Pre-calculate BTC Correlation if needed (skipped for simplicity in this specialized script)
    
    print(f"🔄 Processing {len(ohlcv)} candles...")
    
    for i in range(min_history, len(ohlcv)):
        window = ohlcv[i-min_history:i+1]
        current_candle = window[-1]
        timestamp = current_candle[0]
        close_price = current_candle[4]
        date_obj = datetime.fromtimestamp(timestamp/1000, tz=timezone.utc)
        
        # --- V5.1 FORTRESS INTELLIGENCE ---
        
        # A. Predictability Index (Calculé sur le window)
        # On reconstitue un DataFrame minimal pour le module
        df_window = pd.DataFrame(window, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        pred_adj = get_predictability_adjustment(df_window)
        pred_score = pred_adj.get('score', 50)
        should_trade_pred = pred_adj.get('should_trade', True)
        
        # B. Micro-Corridors (Time check)
        # On mock l'appel car le module attend l'heure actuelle
        # Ici on doit simuler l'heure de la bougie
        # Le module micro_corridors utilise datetime.now(), donc difficile à backtester directement
        # Sauf si on modifie le module ou on recode la logique ici.
        # Pour ce backtest, on va simplifier : On utilise juste le Predictability Index qui est le coeur de V5.1 Crypto
        
        # C. Macro (Mock Based on Price Action)
        # Si crash brutal récent (-5% en 24h), on passe en RISK_OFF
        price_24h_ago = ohlcv[i-24][4]
        perf_24h = (close_price - price_24h_ago) / price_24h_ago
        macro = MacroSimulation.get_mock_regime(perf_24h)
        
        if not macro['can_trade']:
            continue # KILL SWITCH ACTIVATED
            
        # --- STRATEGY ENGINE (V4 Hybrid Modified) ---
        
        # Tech Analysis
        analysis = analyze_market(window)
        rsi = analysis['indicators']['rsi']
        
        # SIGNAL BUY
        if position is None:
            # Règle V5.1 : Predictability Check (Quarantine)
            if not should_trade_pred:
                # On skip si erratique
                continue
                
            # Signal Technique (RSI < 40 + Confirmations V4)
            if rsi < 40:
                # Position Sizing V5.1 (Compound * Multiplier)
                # Base size = Capital total (simulate Full Risk for backtest purity) -> Or fixed fraction
                base_size_usd = capital # All-in mode backtest standard
                
                # Apply Multipliers
                final_size = base_size_usd * macro['size_multiplier'] * pred_adj.get('size_multiplier', 1.0)
                
                if final_size < 10: continue # Trop petit
                
                amount = final_size / close_price
                position = {
                    'entry': close_price,
                    'amount': amount,
                    'time': date_obj,
                    'pred_score': pred_score
                }
                # print(f"🟢 BUY {date_obj} @ {close_price:.2f} | Score={pred_score} | Size=${final_size:.0f}")

        # SIGNAL SELL
        elif position:
            entry = position['entry']
            
            # Exit Logic (Simple TP/SL for V5 test)
            pnl_pct = (close_price - entry) / entry
            
            # SL dynamique selon volatilité (ou fixe -5% comme V4)
            if pnl_pct < -0.05:
                reason = "STOP_LOSS"
            elif pnl_pct > 0.05:
                reason = "TAKE_PROFIT"
            elif rsi > 70:
                reason = "RSI_EXIT"
            # V5.1 : Si le score de prédictibilité chute DRASTIQUEMENT, on sort ?
            elif pred_score < 20: 
                reason = "PRED_DETRIORATION"
            else:
                reason = None
            
            if reason:
                pnl = (close_price - entry) * position['amount']
                capital += pnl
                trades.append({
                    'pnl': pnl, 
                    'pnl_pct': pnl_pct*100, 
                    'reason': reason,
                    'is_win': pnl > 0
                })
                # print(f"🔴 SELL {date_obj} @ {close_price:.2f} | PnL: {pnl:+.2f}$ ({pnl_pct*100:+.1f}%) | {reason}")
                position = None

    # REPORT
    if not trades:
        print("No trades generated.")
        return

    df_trades = pd.DataFrame(trades)
    win_rate = len(df_trades[df_trades['is_win']])/len(df_trades) * 100
    total_pnl = df_trades['pnl'].sum()
    
    print("-" * 40)
    print(f"RESULTATS V5.1 ({len(trades)} trades)")
    print(f"Capital Final: ${capital:.2f} (Start: $1000)")
    print(f"Performance:   {(capital-1000)/1000*100:+.2f}%")
    print(f"Win Rate:      {win_rate:.1f}%")
    print("-" * 40)

if __name__ == "__main__":
    target_year = 2024
    if len(sys.argv) > 1:
        target_year = int(sys.argv[1])
        
    run_backtest_v51('BTC/USDT', target_year)
    run_backtest_v51('SOL/USDT', target_year)
