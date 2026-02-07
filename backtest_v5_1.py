#!/usr/bin/env python3
"""
🌍 EMPIRE V5.1 - GLOBAL BACKTEST 2025 (Micro-Corridors Edition)
==============================================================
Ce script simule l'année 2025 heure par heure pour les 3 classes d'actifs :
- Indices (Nasdaq, S&P 500)
- Commodities (Gold, Oil)
- Forex (EURUSD, GBPUSD)

Il utilise les VRAIS modules V5.1 modifiés pour accepter le temps simulé.
"""

import sys
import os
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from datetime import datetime, timedelta
import numpy as np

# Ajouter les chemins des modules partagés
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'shared')))

try:
    from micro_corridors import get_adaptive_params, check_volume_veto
    from trading_windows import get_session_phase
    print("✅ Modules V5.1 chargés avec succès")
except ImportError as e:
    print(f"❌ Erreur d'import modules V5.1: {e}")
    sys.exit(1)

# ==================== CONFIGURATION ====================
# Période de backtest (2022 - Tentative)
backtest_start = "2022-01-01"
backtest_end = "2022-12-31"
initial_capital = 10000.0

ASSETS = {
    # INDICES
    '^NDX': {'class': 'Indices', 'strategy': 'MOMENTUM_BREAKOUT'},
    '^GSPC': {'class': 'Indices', 'strategy': 'MOMENTUM_BREAKOUT'},
    
    # COMMODITIES
    'GC=F': {'class': 'Commodities', 'strategy': 'TREND_PULLBACK'},
    'CL=F': {'class': 'Commodities', 'strategy': 'VOLATILITY_BREAKOUT'},
    
    # FOREX
    'EURUSD=X': {'class': 'Forex', 'strategy': 'TREND_PULLBACK'},
    'GBPUSD=X': {'class': 'Forex', 'strategy': 'TREND_PULLBACK'}
}

# Paramètres de base (avant adaptation V5.1)
BASE_PARAMS = {
    'Indices': {'tp': 0.03, 'sl': 0.015, 'rsi_buy': 40, 'rsi_sell': 60},
    'Commodities': {'tp': 0.025, 'sl': 0.012, 'rsi_buy': 35, 'rsi_sell': 65},
    'Forex': {'tp': 0.015, 'sl': 0.007, 'rsi_buy': 30, 'rsi_sell': 70}
}

def fetch_data(symbol, start, end):
    print(f"📥 Téléchargement {symbol}...")
    df = yf.download(symbol, start=start, end=end, interval="1h", progress=False)
    if df.empty: return None
    
    # Aplatir MultiIndex si nécessaire
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    return df

def calculate_indicators(df):
    df = df.copy()
    # ATR
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    # SMA 200 (Trend)
    df['SMA_200'] = ta.sma(df['Close'], length=200)
    # SMA 50 (Trend Strict V5.1)
    df['SMA_50'] = ta.sma(df['Close'], length=50)
    # RSI
    df['RSI'] = ta.rsi(df['Close'], length=14)
    # Volume SMA (pour Veto)
    df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
    
    # Bollinger Bands (pour Breakout)
    bb = ta.bbands(df['Close'], length=20, std=2.0)
    # pandas_ta retourne les colonnes dans l'ordre: BBL, BBM, BBU, BBB, BBP
    # Mais le nommage peut varier.
    if bb is not None and not bb.empty:
        df['BBL'] = bb.iloc[:, 0] # Lower
        df['BBU'] = bb.iloc[:, 2] # Upper
    else:
        df['BBL'] = df['Close']
        df['BBU'] = df['Close']
    
    return df

def run_backtest():
    global_capital = initial_capital
    portfolio_history = []
    total_trades = 0
    wins = 0
    
    print("\n🚀 Démarrage du Backtest V5.1 (2025)...")
    print(f"Capital Initial: ${global_capital:.2f}\n")
    
    results = {}
    
    for symbol, config in ASSETS.items():
        print(f"🔎 Analyse {symbol} ({config['class']})...")
        
        df = fetch_data(symbol, backtest_start, backtest_end)
        if df is None: continue
        
        df = calculate_indicators(df)
        
        asset_trades = []
        position = None
        asset_class = config['class']
        base = BASE_PARAMS[asset_class]
        
        # Parcourir les bougies
        for i in range(200, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            timestamp = df.index[i]
            
            # --- V5.1 MAGIC: Time Simulation ---
            # Convertir timestamp en datetime aware (UTC -> Paris) est géré dans le module via simulated_time str
            sim_time_str = str(timestamp)
            
            # 1. Adaptative Parameters
            adaptive = get_adaptive_params(symbol, simulated_time=sim_time_str)
            
            # Paramètres finaux
            current_tp_pct = base['tp'] * adaptive['tp_multiplier']
            current_sl_pct = base['sl'] * adaptive['sl_multiplier']
            current_risk_mult = adaptive['risk_multiplier']
            current_rsi_buy = adaptive['rsi_threshold'] 
            
            # Vérifier phase
            phase_info = get_session_phase(symbol, simulated_time=sim_time_str)
            if not phase_info['is_tradeable']:
                pass
                
            # --- GESTION POSITION ---
            if position:
                exit_price = None
                pnl = 0
                reason = ""
                
                # Check SL/TP
                if position['side'] == 'LONG':
                    if curr['Low'] <= position['sl']:
                        exit_price = position['sl']
                        reason = "SL"
                    elif curr['High'] >= position['tp']:
                        exit_price = position['tp']
                        reason = "TP"
                elif position['side'] == 'SHORT':
                    if curr['High'] >= position['sl']:
                        exit_price = position['sl']
                        reason = "SL"
                    elif curr['Low'] <= position['tp']:
                        exit_price = position['tp']
                        reason = "TP"
                
                if exit_price:
                    # Calcul PnL
                    diff = (exit_price - position['entry']) if position['side'] == 'LONG' else (position['entry'] - exit_price)
                    pnl_raw = diff * position['size']
                    # Spread cost (approx 0.02%)
                    cost = position['size'] * exit_price * 0.0002
                    net_pnl = pnl_raw - cost
                    
                    global_capital += net_pnl
                    total_trades += 1
                    if net_pnl > 0: wins += 1
                    
                    asset_trades.append({
                        'date': timestamp,
                        'type': 'EXIT',
                        'pnl': net_pnl,
                        'reason': reason,
                        'capital': global_capital,
                        'corridor': adaptive['corridor_name']
                    })
                    position = None
                continue
                
            # --- ENTREE ---
            # Filtre Volume V5.1 (Désactivé pour Commodities V4)
            if config['class'] != 'Commodities':
                if 'Vol_SMA' in curr and not pd.isna(curr['Vol_SMA']):
                     vol_check = check_volume_veto(symbol, curr['Volume'], curr['Vol_SMA'], simulated_time=sim_time_str)
                     if vol_check['veto']:
                         continue
            
            # Pas d'entrée si phase DEAD (Sauf si V4 ignore ça ? Gardons le pour éviter la nuit)
            if phase_info['phase'] == 'DEAD':
                continue
                
            signal = None
            
            # Stratégies simplifiées pour le backtest
            if config['strategy'] == 'TREND_PULLBACK':
                # Long: SMA200 < Close et RSI < Threshold
                if curr['Close'] > curr['SMA_200'] and curr['RSI'] < current_rsi_buy:
                    signal = 'LONG'
                # Short: SMA200 > Close et RSI > (100 - Threshold)
                elif curr['Close'] < curr['SMA_200'] and curr['RSI'] > (100 - current_rsi_buy):
                    signal = 'SHORT'
                    
            elif config['strategy'] == 'MOMENTUM_BREAKOUT':
                # Breakout BB Sup (Long Only pour Indices)
                if adaptive['aggressiveness'] in ['HIGH', 'MEDIUM']:
                    if curr['Close'] > curr['BBU'] and curr['Close'] > curr['SMA_200']:
                        signal = 'LONG'
                        
            elif config['strategy'] == 'VOLATILITY_BREAKOUT': # Oil V4 (Rollback)
                 # V4 SIMPLE: Breakout pur sans SMA50 ni Volume
                 if curr['Close'] > curr['BBU']:
                     signal = 'LONG'
                 elif curr['Close'] < curr['BBL']:
                     signal = 'SHORT'
            
            if signal:
                price = curr['Close']
                dist_sl = price * current_sl_pct
                
                # Sizing Cumulatif V5.1 (Gardé car gestion du risque globale)
                risk_amt = global_capital * 0.01 * current_risk_mult
                
                # Force RiskV4 pour Commodities (standard)
                if config['class'] == 'Commodities':
                     risk_amt = global_capital * 0.01 * 1.0 # Risque fixe 1%
                
                if dist_sl > 0:
                    size = risk_amt / dist_sl
                else:
                    size = 0
                
                trade_value = size * price
                if trade_value > global_capital * 0.5: 
                    size = (global_capital * 0.5) / price
                    
                position = {
                    'entry': price,
                    'sl': price - dist_sl if signal == 'LONG' else price + dist_sl,
                    'tp': price + (price * current_tp_pct) if signal == 'LONG' else price - (price * current_tp_pct),
                    'size': size,
                    'side': signal,
                    'start_time': timestamp
                }
                
                asset_trades.append({
                    'date': timestamp,
                    'type': 'ENTRY',
                    'price': price,
                    'size': size,
                    'corridor': adaptive['corridor_name'],
                    'regime': adaptive['regime']
                })
        
        # Fin de l'actif
        # Calculer stats pour cet actif
        pnl_asset = sum([t['pnl'] for t in asset_trades if t['type'] == 'EXIT'])
        asset_wr = len([t for t in asset_trades if t.get('pnl', 0) > 0]) / len([t for t in asset_trades if t['type'] == 'EXIT']) if asset_trades else 0
        
        results[symbol] = {
            'PnL': pnl_asset,
            'Trades': len([t for t in asset_trades if t['type'] == 'EXIT']),
            'WR': f"{asset_wr*100:.1f}%"
        }
        print(f"📊 Résultat {symbol}: ${pnl_asset:.2f} | {results[symbol]['Trades']} trades | WR {results[symbol]['WR']}")

    print("\n" + "="*50)
    print("🏆 RÉSULTATS GLOBAUX V5.1 (2025)")
    print("="*50)
    print(f"Capital Final: ${global_capital:.2f}")
    print(f"Performance: {((global_capital - initial_capital)/initial_capital)*100:.2f}%")
    print(f"Total Trades: {total_trades}")
    print(f"Win Rate Global: {(wins/total_trades)*100:.1f}%" if total_trades > 0 else "N/A")
    print("="*50)

if __name__ == "__main__":
    run_backtest()
