#!/usr/bin/env python3
"""
Script pour télécharger l'historique des 415 actifs de Binance Futures
Période: Semaine dernière (7 jours)
Format: CSV avec OHLCV data
"""

import ccxt
import pandas as pd
import os
import time
from datetime import datetime, timedelta
import json
import logging

# Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BinanceHistoryDownloader:
    def __init__(self):
        """Initialiser le client Binance Futures"""
        self.exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY', ''),
            'secret': os.getenv('BINANCE_SECRET', ''),
            'sandbox': False,  # Production
            'enableRateLimit': True,
            'timeout': 30000,
        })
        
        # Forcer le mode Futures
        self.exchange.set_sandbox_mode(False)
        self.exchange.options['defaultType'] = 'future'
        
    def get_all_futures_symbols(self):
        """Récupérer tous les symboles disponibles sur Binance Futures"""
        try:
            markets = self.exchange.load_markets()
            futures_symbols = []
            
            for symbol, market in markets.items():
                if market.get('type') == 'future' and market.get('active', True):
                    # Filtrer uniquement les paires USDT
                    if symbol.endswith('/USDT'):
                        futures_symbols.append(symbol)
            
            logger.info(f"✅ Trouvé {len(futures_symbols)} actifs Futures USDT")
            return sorted(futures_symbols)
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération symboles: {e}")
            return []
    
    def download_symbol_history(self, symbol, days=7):
        """Télécharger l'historique pour un symbole"""
        try:
            # Calculer les dates
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # Convertir en timestamps
            since = self.exchange.parse8601(start_time.isoformat())
            
            logger.info(f"📥 Téléchargement {symbol} ({days} jours)...")
            
            # Récupérer les données OHLCV
            ohlcv = self.exchange.fetch_ohlcv(
                symbol, 
                timeframe='1h',  # 1 heure pour avoir assez de données
                since=since,
                limit=1000  # Max par requête
            )
            
            if not ohlcv:
                logger.warning(f"⚠️  Pas de données pour {symbol}")
                return None
            
            # Convertir en DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['symbol'] = symbol
            
            # Calculer des indicateurs de base
            df['range'] = df['high'] - df['low']
            df['change'] = ((df['close'] - df['open']) / df['open'] * 100).round(2)
            df['volume_usd'] = (df['volume'] * df['close']).round(2)
            
            logger.info(f"✅ {symbol}: {len(df)} candles téléchargées")
            return df
            
        except Exception as e:
            logger.error(f"❌ Erreur {symbol}: {e}")
            return None
    
    def download_all_history(self, days=7, max_symbols=415):
        """Télécharger l'historique pour tous les symboles"""
        # Créer le répertoire de sortie
        output_dir = f"binance_history_{datetime.now().strftime('%Y%m%d')}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Récupérer tous les symboles
        symbols = self.get_all_futures_symbols()
        
        # Limiter si nécessaire
        if len(symbols) > max_symbols:
            symbols = symbols[:max_symbols]
            logger.info(f"📊 Limité à {max_symbols} symboles")
        
        # Télécharger pour chaque symbole
        all_data = []
        failed_symbols = []
        
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"🔄 Progression: {i}/{len(symbols)} - {symbol}")
            
            df = self.download_symbol_history(symbol, days)
            if df is not None:
                all_data.append(df)
                
                # Sauvegarder individuellement
                filename = f"{output_dir}/{symbol.replace('/', '_')}.csv"
                df.to_csv(filename, index=False)
                
            else:
                failed_symbols.append(symbol)
            
            # Rate limiting
            time.sleep(0.1)
            
            # Sauvegarde intermédiaire tous les 50 symboles
            if i % 50 == 0:
                logger.info(f"💾 Sauvegarde intermédiaire ({i} symboles)")
                self.save_combined_data(all_data, output_dir, f"intermediate_{i}")
        
        # Combiner toutes les données
        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            
            # Sauvegarder le fichier combiné
            combined_file = f"{output_dir}/all_futures_history_{days}days.csv"
            combined_df.to_csv(combined_file, index=False)
            
            # Créer un résumé
            summary = {
                'download_date': datetime.now().isoformat(),
                'period_days': days,
                'total_symbols': len(symbols),
                'successful_downloads': len(all_data),
                'failed_downloads': len(failed_symbols),
                'total_candles': len(combined_df),
                'date_range': {
                    'start': combined_df['timestamp'].min().isoformat(),
                    'end': combined_df['timestamp'].max().isoformat()
                },
                'failed_symbols': failed_symbols
            }
            
            with open(f"{output_dir}/summary.json", 'w') as f:
                json.dump(summary, f, indent=2)
            
            logger.info(f"🎉 Terminé! {len(all_data)} symboles téléchargés")
            logger.info(f"📁 Fichiers sauvegardés dans: {output_dir}")
            logger.info(f"📊 Total candles: {len(combined_df)}")
            logger.info(f"❌ Échecs: {len(failed_symbols)} symboles")
            
            return combined_df, summary
        else:
            logger.error("❌ Aucune donnée téléchargée")
            return None, None
    
    def save_combined_data(self, data_list, output_dir, filename):
        """Sauvegarder les données combinées"""
        if data_list:
            combined_df = pd.concat(data_list, ignore_index=True)
            combined_df.to_csv(f"{output_dir}/{filename}.csv", index=False)

def main():
    """Fonction principale"""
    logger.info("🚀 Démarrage du téléchargement de l'historique Binance Futures")
    
    # Vérifier les variables d'environnement
    if not os.getenv('BINANCE_API_KEY'):
        logger.error("❌ BINANCE_API_KEY non défini")
        return
    
    if not os.getenv('BINANCE_SECRET'):
        logger.error("❌ BINANCE_SECRET non défini")
        return
    
    # Créer le downloader
    downloader = BinanceHistoryDownloader()
    
    # Télécharger l'historique (7 jours = semaine dernière)
    df, summary = downloader.download_all_history(days=7, max_symbols=415)
    
    if df is not None:
        logger.info("✅ Téléchargement terminé avec succès!")
        logger.info(f"📊 Résumé: {summary['successful_downloads']}/{summary['total_symbols']} symboles")
    else:
        logger.error("❌ Échec du téléchargement")

if __name__ == "__main__":
    main()
