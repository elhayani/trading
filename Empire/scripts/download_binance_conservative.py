#!/usr/bin/env python3
"""
Script conservative pour télécharger l'historique des 415 actifs de Binance Futures
Respecte les rate limits strictes
Période: Semaine dernière (7 jours)
"""

import requests
import pandas as pd
import os
import time
from datetime import datetime, timedelta
import json
import logging

# Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BinanceConservativeDownloader:
    def __init__(self):
        """Initialiser le client Binance API REST"""
        self.base_url = "https://fapi.binance.com"
        self.session = requests.Session()
        
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
    
    def download_all_sequential(self, days=7, delay=0.5):
        """Télécharger TOUS les symboles séquentiellement avec delay"""
        # Créer le répertoire
        output_dir = f"binance_history_{datetime.now().strftime('%Y%m%d')}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Récupérer TOUS les symboles disponibles
        symbols = self.get_futures_symbols()
        
        if not symbols:
            logger.error("❌ Aucun symbole trouvé")
            return None, None
        
        logger.info(f"🚀 Téléchargement séquentiel de TOUS les {len(symbols)} symboles disponibles (delay: {delay}s)...")
        
        # Téléchargement séquentiel
        all_data = []
        all_stats = []
        failed_symbols = []
        
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"🔄 [{i}/{len(symbols)}] {symbol}")
            
            df, stats = self.download_klines(symbol, days)
            if df is not None:
                all_data.append(df)
                all_stats.append(stats)
                
                # Sauvegarder individuellement
                filename = f"{output_dir}/{symbol}.csv"
                df.to_csv(filename, index=False)
                
                logger.info(f"✅ {symbol}: {len(df)} candles | Change: {stats['total_change']:.2f}%")
            else:
                failed_symbols.append(symbol)
                logger.warning(f"❌ Échec {symbol}")
            
            # Rate limiting
            time.sleep(delay)
            
            # Sauvegarde intermédiaire tous les 50 symboles
            if i % 50 == 0:
                logger.info(f"💾 Sauvegarde intermédiaire ({i} symboles)")
                if all_data:
                    combined_df = pd.concat(all_data, ignore_index=True)
                    combined_df.to_csv(f"{output_dir}/intermediate_{i}.csv", index=False)
        
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
            
            if summary['top_performers']:
                logger.info(f"🔥 Top: {summary['top_performers'][0]['symbol']} (+{summary['top_performers'][0]['total_change']:.2f}%)")
            if summary['worst_performers']:
                logger.info(f"💀 Pire: {summary['worst_performers'][0]['symbol']} ({summary['worst_performers'][0]['total_change']:.2f}%)")
            
            return combined_df, summary
        else:
            logger.error("❌ Aucune donnée téléchargée")
            return None, None

def main():
    """Fonction principale"""
    logger.info("🚀 Démarrage du téléchargement conservative Binance Futures")
    
    downloader = BinanceConservativeDownloader()
    
    # Télécharger avec 0.5s de delay entre chaque requête
    df, summary = downloader.download_all_sequential(days=7, delay=0.5)
    
    if df is not None:
        logger.info("\n✅ SUCCÈS TOTAL! Consultez le répertoire pour les fichiers.")
    else:
        logger.error("❌ Échec du téléchargement")

if __name__ == "__main__":
    main()
