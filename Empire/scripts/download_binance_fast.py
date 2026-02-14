#!/usr/bin/env python3
"""
Script rapide pour télécharger l'historique des 415 actifs de Binance Futures
Utilise l'API REST directement pour plus de vitesse
Période: Semaine dernière (7 jours)
"""

import requests
import pandas as pd
import os
import time
from datetime import datetime, timedelta
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BinanceFastDownloader:
    def __init__(self):
        """Initialiser le client Binance API REST"""
        self.base_url = "https://fapi.binance.com"
        self.session = requests.Session()
        self.lock = threading.Lock()
        
    def get_futures_symbols(self):
        """Récupérer tous les symboles Futures USDT"""
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
            
            logger.info(f"✅ Trouvé {len(symbols)} perpétuels USDT")
            return sorted(symbols)
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération symboles: {e}")
            return []
    
    def download_klines(self, symbol, days=7):
        """Télécharger les klines pour un symbole"""
        try:
            # Calculer les timestamps
            end_time = int(datetime.now().timestamp() * 1000)
            start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            
            # Paramètres
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
            
            # Convertir en DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            # Nettoyer et convertir
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['symbol'] = symbol
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            df['quote_volume'] = df['quote_volume'].astype(float)
            
            # Calculer des indicateurs
            df['range'] = df['high'] - df['low']
            df['change'] = ((df['close'] - df['open']) / df['open'] * 100).round(2)
            
            # Statistiques
            stats = {
                'symbol': symbol,
                'total_candles': len(df),
                'avg_volume': df['volume'].mean(),
                'avg_volume_usd': df['quote_volume'].mean(),
                'volatility': df['change'].std(),
                'max_change': df['change'].max(),
                'min_change': df['change'].min(),
                'price_range': df['high'].max() - df['low'].min(),
                'start_price': df['close'].iloc[0],
                'end_price': df['close'].iloc[-1],
                'total_change': ((df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0] * 100).round(2),
                'total_trades': df['trades'].sum(),
                'buy_ratio': (df['taker_buy_base'].sum() / df['volume'].sum() * 100).round(2)
            }
            
            return df, stats
            
        except Exception as e:
            logger.error(f"❌ Erreur {symbol}: {e}")
            return None, None
    
    def download_symbol_worker(self, args):
        """Worker pour le téléchargement parallèle"""
        symbol, output_dir, days = args
        df, stats = self.download_klines(symbol, days)
        
        if df is not None:
            # Sauvegarder le fichier CSV
            filename = f"{output_dir}/{symbol}.csv"
            df.to_csv(filename, index=False)
            
            with self.lock:
                logger.info(f"✅ {symbol}: {len(df)} candles | Change: {stats['total_change']:.2f}%")
            
            return df, stats
        else:
            with self.lock:
                logger.warning(f"❌ Échec {symbol}")
            return None, None
    
    def download_all_parallel(self, days=7, max_workers=10):
        """Télécharger TOUS les symboles en parallèle"""
        # Créer le répertoire
        output_dir = f"binance_history_{datetime.now().strftime('%Y%m%d')}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Récupérer TOUS les symboles disponibles
        symbols = self.get_futures_symbols()
        
        if not symbols:
            logger.error("❌ Aucun symbole trouvé")
            return None, None
        
        logger.info(f"🚀 Téléchargement de TOUS les {len(symbols)} symboles disponibles avec {max_workers} workers...")
        
        # Préparer les arguments
        args_list = [(symbol, output_dir, days) for symbol in symbols]
        
        # Téléchargement parallèle
        all_data = []
        all_stats = []
        failed_symbols = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Soumettre toutes les tâches
            future_to_symbol = {
                executor.submit(self.download_symbol_worker, args): args[0] 
                for args in args_list
            }
            
            # Traiter les résultats
            for i, future in enumerate(as_completed(future_to_symbol), 1):
                symbol = future_to_symbol[future]
                
                try:
                    df, stats = future.result()
                    if df is not None:
                        all_data.append(df)
                        all_stats.append(stats)
                    else:
                        failed_symbols.append(symbol)
                        
                except Exception as e:
                    logger.error(f"❌ Erreur traitement {symbol}: {e}")
                    failed_symbols.append(symbol)
                
                # Progression
                if i % 50 == 0:
                    logger.info(f"🔄 Progression: {i}/{len(symbols)} ({i/len(symbols)*100:.1f}%)")
        
        # Combiner et sauvegarder
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            
            # Fichier combiné
            combined_file = f"{output_dir}/all_futures_history_{days}days.csv"
            combined_df.to_csv(combined_file, index=False)
            
            # Statistiques
            stats_df = pd.DataFrame(all_stats)
            stats_df.to_csv(f"{output_dir}/symbols_stats.csv", index=False)
            
            # Résumé
            summary = {
                'download_date': datetime.now().isoformat(),
                'period_days': days,
                'total_symbols': len(symbols),
                'successful': len(all_data),
                'failed': len(failed_symbols),
                'total_candles': len(combined_df),
                'date_range': {
                    'start': combined_df['timestamp'].min().isoformat(),
                    'end': combined_df['timestamp'].max().isoformat()
                },
                'top_performers': sorted(all_stats, key=lambda x: x['total_change'], reverse=True)[:10],
                'worst_performers': sorted(all_stats, key=lambda x: x['total_change'])[:10],
                'most_volatile': sorted(all_stats, key=lambda x: x['volatility'], reverse=True)[:10],
                'highest_volume': sorted(all_stats, key=lambda x: x['avg_volume_usd'], reverse=True)[:10],
                'failed_symbols': failed_symbols
            }
            
            with open(f"{output_dir}/summary.json", 'w') as f:
                json.dump(summary, f, indent=2)
            
            # Afficher les résultats
            logger.info("\n🎉 TÉLÉCHARGEMENT TERMINÉ!")
            logger.info(f"📊 Succès: {len(all_data)}/{len(symbols)} symboles")
            logger.info(f"📈 Total candles: {len(combined_df):,}")
            logger.info(f"📁 Répertoire: {output_dir}")
            logger.info(f"🔥 Top: {summary['top_performers'][0]['symbol']} (+{summary['top_performers'][0]['total_change']:.2f}%)")
            logger.info(f"💀 Pire: {summary['worst_performers'][0]['symbol']} ({summary['worst_performers'][0]['total_change']:.2f}%)")
            
            return combined_df, summary
        else:
            logger.error("❌ Aucune donnée téléchargée")
            return None, None

def main():
    """Fonction principale"""
    logger.info("🚀 Démarrage du téléchargement rapide Binance Futures")
    
    downloader = BinanceFastDownloader()
    
    # Télécharger avec 10 workers en parallèle
    df, summary = downloader.download_all_parallel(days=7, max_workers=10)
    
    if df is not None:
        logger.info("\n✅ SUCCÈS TOTAL! Consultez le répertoire pour les fichiers.")
    else:
        logger.error("❌ Échec du téléchargement")

if __name__ == "__main__":
    main()
