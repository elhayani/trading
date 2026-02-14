#!/usr/bin/env python3
"""
Script simple pour télécharger l'historique des 415 actifs de Binance Futures
Sans warnings, mode silencieux
Période: Semaine dernière (7 jours)
"""

import requests
import pandas as pd
import os
import time
from datetime import datetime, timedelta
import json

# Configuration silencieuse
import logging
logging.basicConfig(level=logging.ERROR)  # Seulement les erreurs

class BinanceSimpleDownloader:
    def __init__(self):
        self.base_url = "https://fapi.binance.com"
        self.session = requests.Session()
        
    def get_futures_symbols(self):
        try:
            url = f"{self.base_url}/fapi/v1/exchangeInfo"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            symbols = []
            
            for symbol_info in data['symbols']:
                if (symbol_info['status'] == 'TRADING' and 
                    symbol_info['contractType'] == 'PERPETUAL' and
                    symbol_info['quoteAsset'] == 'USDT'):
                    symbols.append(symbol_info['symbol'])
            
            return sorted(symbols)
            
        except Exception:
            return []
    
    def download_klines(self, symbol, days=7):
        try:
            end_time = int(datetime.now().timestamp() * 1000)
            start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            
            params = {
                'symbol': symbol,
                'interval': '1h',
                'startTime': start_time,
                'endTime': end_time,
                'limit': 1000
            }
            
            url = f"{self.base_url}/fapi/v1/klines"
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            klines = response.json()
            
            if not klines:
                return None, None
            
            # DataFrame simple
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['symbol'] = symbol
            
            # Conversion simple
            for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
                df[col] = df[col].astype(float)
            
            df['change'] = ((df['close'] - df['open']) / df['open'] * 100).round(2)
            
            # Stats simples
            stats = {
                'symbol': symbol,
                'total_candles': len(df),
                'start_price': df['close'].iloc[0],
                'end_price': df['close'].iloc[-1],
                'total_change': ((df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0] * 100).round(2),
                'avg_volume': df['volume'].mean(),
                'volatility': df['change'].std()
            }
            
            return df, stats
            
        except Exception:
            return None, None
    
    def download_all(self, days=7, delay=1.0):
        # Répertoire de sortie
        output_dir = f"binance_history_{datetime.now().strftime('%Y%m%d')}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Récupérer TOUS les symboles disponibles
        symbols = self.get_futures_symbols()
        
        if not symbols:
            print("❌ Aucun symbole trouvé")
            return None, None
        
        print(f"🚀 Téléchargement de TOUS les {len(symbols)} symboles disponibles...")
        
        all_data = []
        all_stats = []
        failed = []
        
        for i, symbol in enumerate(symbols, 1):
            print(f"[{i:3d}/{len(symbols)}] {symbol}", end=' ')
            
            df, stats = self.download_klines(symbol, days)
            if df is not None:
                all_data.append(df)
                all_stats.append(stats)
                
                # Sauvegarder
                filename = f"{output_dir}/{symbol}.csv"
                df.to_csv(filename, index=False)
                
                print(f"✅ {len(df)}c {stats['total_change']:+.1f}%")
            else:
                failed.append(symbol)
                print("❌")
            
            # Delay
            time.sleep(delay)
        
        # Résultats finaux
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            
            # Fichier combiné
            combined_file = f"{output_dir}/all_futures_history_{days}days.csv"
            combined_df.to_csv(combined_file, index=False)
            
            # Stats
            stats_df = pd.DataFrame(all_stats)
            stats_df.to_csv(f"{output_dir}/stats.csv", index=False)
            
            # Résumé
            summary = {
                'date': datetime.now().isoformat(),
                'period_days': days,
                'total_symbols': len(symbols),
                'successful': len(all_data),
                'failed': len(failed),
                'total_candles': len(combined_df),
                'top_performers': sorted(all_stats, key=lambda x: x['total_change'], reverse=True)[:5],
                'worst_performers': sorted(all_stats, key=lambda x: x['total_change'])[:5],
                'failed_symbols': failed
            }
            
            with open(f"{output_dir}/summary.json", 'w') as f:
                json.dump(summary, f, indent=2)
            
            # Affichage final
            print("\n🎉 TÉLÉCHARGEMENT TERMINÉ!")
            print(f"📊 Succès: {len(all_data)}/{len(symbols)} symboles")
            print(f"📈 Total candles: {len(combined_df):,}")
            print(f"📁 Répertoire: {output_dir}")
            
            if summary['top_performers']:
                top = summary['top_performers'][0]
                print(f"🔥 Top: {top['symbol']} {top['total_change']:+.2f}%")
            
            return combined_df, summary
        else:
            print("❌ Aucune donnée téléchargée")
            return None, None

def main():
    print("🚀 Téléchargement Binance Futures (mode silencieux)")
    
    downloader = BinanceSimpleDownloader()
    df, summary = downloader.download_all(days=7, delay=1.0)
    
    if df is not None:
        print("\n✅ Terminé avec succès!")
    else:
        print("\n❌ Échec du téléchargement")

if __name__ == "__main__":
    main()
