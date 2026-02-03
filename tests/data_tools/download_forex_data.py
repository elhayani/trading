#!/usr/bin/env python3
"""
Téléchargement de données Forex historiques depuis Yahoo Finance
Les paires Forex sur Yahoo utilisent le format: EURUSD=X
"""
import yfinance as yf
import pandas as pd
import os
from datetime import datetime, timedelta

# Créer le dossier data s'il n'existe pas
DATA_DIR = os.path.join(os.path.dirname(__file__), '../data')
os.makedirs(DATA_DIR, exist_ok=True)

def download_forex_data(pair='EURUSD', days=180):
    """
    Télécharge les données historiques d'une paire Forex
    """
    # Format Yahoo Finance pour Forex
    ticker = f"{pair}=X"
    
    print(f"📥 Téléchargement {pair} ({days} jours)...")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Téléchargement via yfinance
    data = yf.download(
        ticker,
        start=start_date.strftime('%Y-%m-%d'),
        end=end_date.strftime('%Y-%m-%d'),
        interval='1h',  # Bougies 1 heure
        progress=False
    )
    
    if data.empty:
        print(f"❌ Aucune donnée trouvée pour {pair}")
        return None
    
    print(f"✅ {len(data)} bougies téléchargées")
    
    # Flatten multi-index columns si présent
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] for col in data.columns]
    
    # Reset index pour avoir timestamp comme colonne
    data = data.reset_index()
    
    # Renommer 'Datetime' ou 'Date' en 'timestamp'
    if 'Datetime' in data.columns:
        data = data.rename(columns={'Datetime': 'timestamp'})
    elif 'Date' in data.columns:
        data = data.rename(columns={'Date': 'timestamp'})
    
    # Standardiser les noms de colonnes
    data.columns = [col.lower() for col in data.columns]
    
    # Convertir en format OHLCV standard (liste de listes)
    ohlcv = []
    for _, row in data.iterrows():
        ts = int(pd.to_datetime(row['timestamp']).timestamp() * 1000)
        ohlcv.append([
            ts,
            float(row['open']),
            float(row['high']),
            float(row['low']),
            float(row['close']),
            int(row['volume']) if 'volume' in row and pd.notna(row['volume']) else 0
        ])
    
    # Sauvegarder en CSV
    csv_path = os.path.join(DATA_DIR, f"{pair}_{days}d.csv")
    data.to_csv(csv_path, index=False)
    print(f"💾 Sauvegardé: {csv_path}")
    
    return ohlcv

def load_forex_data(pair='EURUSD', days=180):
    """
    Charge les données depuis le CSV local
    """
    csv_path = os.path.join(DATA_DIR, f"{pair}_{days}d.csv")
    
    if not os.path.exists(csv_path):
        print(f"📥 Données non trouvées, téléchargement...")
        return download_forex_data(pair, days)
    
    print(f"📂 Chargement depuis {csv_path}")
    data = pd.read_csv(csv_path)
    
    ohlcv = []
    for _, row in data.iterrows():
        ts = int(pd.to_datetime(row['timestamp']).timestamp() * 1000)
        ohlcv.append([
            ts,
            float(row['open']),
            float(row['high']),
            float(row['low']),
            float(row['close']),
            int(row['volume']) if pd.notna(row['volume']) else 0
        ])
    
    print(f"✅ {len(ohlcv)} bougies chargées")
    return ohlcv

if __name__ == "__main__":
    # Télécharger plusieurs paires
    pairs = ['EURUSD', 'GBPUSD', 'USDJPY']
    
    for pair in pairs:
        try:
            data = download_forex_data(pair, days=90)
            if data:
                print(f"   Premier: {data[0]}")
                print(f"   Dernier: {data[-1]}")
            print()
        except Exception as e:
            print(f"❌ Erreur {pair}: {e}")
