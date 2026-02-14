#!/usr/bin/env python3
"""
Script de téléchargement Binance Futures - Version Corrigée
Télécharge l'historique de TOUS les symboles USDT perpetuals pour les N derniers jours
Corrige les erreurs de division numpy et gère les rate limits
"""

import os
import time
import json
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional

# Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BinanceHistoryDownloader:
    def __init__(self):
        self.base_url = "https://fapi.binance.com"
        self.session = requests.Session()
        
    def get_futures_symbols(self) -> List[str]:
        """Récupérer TOUS les symboles Futures USDT actifs"""
        try:
            response = self.session.get(f"{self.base_url}/fapi/v1/exchangeInfo", timeout=10)
            response.raise_for_status()
            data = response.json()
            
            symbols = []
            for symbol_info in data['symbols']:
                if (symbol_info['status'] == 'TRADING' and 
                    symbol_info['contractType'] == 'PERPETUAL' and
                    symbol_info['quoteAsset'] == 'USDT'):
                    symbols.append(symbol_info['symbol'])
            
            logger.info(f"✅ Trouvé {len(symbols)} symboles Futures USDT actifs")
            return symbols
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération symboles: {e}")
            return []
    
    def download_symbol_worker(self, symbol: str, output_dir: str, days: int) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
        """Télécharger les données pour un symbole spécifique avec gestion d'erreurs"""
        try:
            # Calculer les timestamps
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # Convertir en millisecondes pour Binance API
            start_ms = int(start_time.timestamp() * 1000)
            end_ms = int(end_time.timestamp() * 1000)
            
            # URL API
            url = f"{self.base_url}/fapi/v1/klines"
            params = {
                'symbol': symbol,
                'interval': '1h',
                'startTime': start_ms,
                'endTime': end_ms,
                'limit': 1000
            }
            
            # Télécharger avec retry pour rate limits
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.session.get(url, params=params, timeout=30)
                    response.raise_for_status()
                    
                    data = response.json()
                    if not data:
                        logger.warning(f"⚠️ Aucune donnée pour {symbol}")
                        return None, None
                    
                    # Convertir en DataFrame
                    df = pd.DataFrame(data, columns=[
                        'timestamp', 'open', 'high', 'low', 'close', 'volume',
                        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                        'taker_buy_quote', 'ignore'
                    ])
                    
                    # Nettoyer et convertir avec gestion d'erreurs
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df['symbol'] = symbol
                    
                    # Conversion sécurisée avec gestion des valeurs invalides
                    numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_volume']
                    for col in numeric_cols:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    
                    # Supprimer les lignes avec des données invalides
                    df = df.dropna(subset=numeric_cols)
                    
                    if df.empty:
                        logger.warning(f"⚠️ Données invalides après nettoyage pour {symbol}")
                        return None, None
                    
                    # Calculer des indicateurs avec gestion d'erreurs
                    try:
                        df['range'] = df['high'] - df['low']
                        df['change'] = ((df['close'] - df['open']) / df['open'] * 100).round(2)
                    except Exception as e:
                        logger.warning(f"⚠️ Erreur calcul indicateurs pour {symbol}: {e}")
                        df['range'] = 0
                        df['change'] = 0
                    
                    # Statistiques
                    try:
                        stats = {
                            'symbol': symbol,
                            'total_candles': len(df),
                            'avg_volume': df['volume'].mean(),
                            'avg_volume_usd': df['quote_volume'].mean(),
                            'volatility': df['change'].std() if len(df) > 1 else 0,
                            'max_change': df['change'].max(),
                            'min_change': df['change'].min(),
                            'price_range': df['high'].max() - df['low'].min(),
                            'start_price': df['close'].iloc[0],
                            'end_price': df['close'].iloc[-1],
                            'total_volume': df['volume'].sum(),
                            'total_volume_usd': df['quote_volume'].sum()
                        }
                    except Exception as e:
                        logger.warning(f"⚠️ Erreur calcul stats pour {symbol}: {e}")
                        stats = {
                            'symbol': symbol,
                            'total_candles': len(df),
                            'avg_volume': 0,
                            'avg_volume_usd': 0,
                            'volatility': 0,
                            'max_change': 0,
                            'min_change': 0,
                            'price_range': 0,
                            'start_price': 0,
                            'end_price': 0,
                            'total_volume': 0,
                            'total_volume_usd': 0
                        }
                    
                    # Sauvegarder le fichier CSV
                    filename = f"{output_dir}/{symbol}.csv"
                    df.to_csv(filename, index=False)
                    
                    logger.info(f"✅ {symbol}: {len(df)} candles sauvegardés")
                    return df, stats
                    
                except requests.exceptions.RequestException as e:
                    if "429" in str(e):
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(f"⏳ Rate limit pour {symbol}, attente {wait_time}s...")
                        time.sleep(wait_time)
                        if attempt == max_retries - 1:
                            logger.error(f"❌ Échec {symbol} après {max_retries} tentatives")
                            return None, None
                        continue
                    else:
                        logger.error(f"❌ Erreur HTTP pour {symbol}: {e}")
                        return None, None
                        
        except Exception as e:
            logger.error(f"❌ Erreur {symbol}: {e}")
            return None, None
    
    def download_all_parallel(self, days=7, max_workers=5):
        """Télécharger TOUS les symboles en parallèle avec gestion des rate limits"""
        # Créer le répertoire
        output_dir = f"binance_history_{datetime.now().strftime('%Y%m%d')}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Récupérer TOUS les symboles disponibles
        symbols = self.get_futures_symbols()
        
        if not symbols:
            logger.error("❌ Aucun symbole trouvé")
            return None, None
        
        logger.info(f"🚀 Téléchargement de TOUS les {len(symbols)} symboles disponibles avec {max_workers} workers...")
        
        # Réduire le nombre de workers pour éviter les rate limits
        max_workers = min(max_workers, 5)
        
        # Préparer les arguments
        args_list = [(symbol, output_dir, days) for symbol in symbols]
        
        # Téléchargement parallèle avec gestion des erreurs
        all_data = []
        all_stats = []
        failed_symbols = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Soumettre les tâches par lots pour éviter les rate limits
            batch_size = 20
            for i in range(0, len(args_list), batch_size):
                batch = args_list[i:i+batch_size]
                
                # Soumettre le batch
                future_to_symbol = {
                    executor.submit(self.download_symbol_worker, symbol, output_dir, days): symbol 
                    for symbol, output_dir, days in batch
                }
                
                # Traiter les résultats du batch
                for future in as_completed(future_to_symbol):
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
                
                # Pause entre les batches pour éviter les rate limits
                if i + batch_size < len(args_list):
                    logger.info(f"⏸ Pause entre les batches ({i+batch_size}/{len(args_list)})")
                    time.sleep(2)
        
        # Combiner et sauvegarder
        if all_data:
            try:
                combined_df = pd.concat(all_data, ignore_index=True)
                
                # Fichier combiné
                combined_file = f"{output_dir}/all_futures_history_{days}days.csv"
                combined_df.to_csv(combined_file, index=False)
                
                # Statistiques
                stats_df = pd.DataFrame(all_stats)
                stats_file = f"{output_dir}/summary_stats.csv"
                stats_df.to_csv(stats_file, index=False)
                
                # Résumé JSON
                summary = {
                    'total_symbols': len(symbols),
                    'successful_downloads': len(all_stats),
                    'failed_downloads': len(failed_symbols),
                    'total_candles': sum(s['total_candles'] for s in all_stats),
                    'download_date': datetime.now().isoformat(),
                    'days_covered': days,
                    'failed_symbols': failed_symbols
                }
                
                summary_file = f"{output_dir}/download_summary.json"
                with open(summary_file, 'w') as f:
                    json.dump(summary, f, indent=2)
                
                logger.info(f"✅ Téléchargement terminé: {len(all_stats)} succès, {len(failed_symbols)} échecs")
                logger.info(f"📊 Données sauvegardées dans: {output_dir}")
                logger.info(f"📄 Fichiers: {combined_file}, {stats_file}, {summary_file}")
                
                return combined_df, summary
                
            except Exception as e:
                logger.error(f"❌ Erreur lors de la sauvegarde: {e}")
                return None, None
        else:
            logger.error("❌ Aucune donnée téléchargée")
            return None, None

def main():
    """Fonction principale"""
    downloader = BinanceHistoryDownloader()
    
    # Télécharger les 7 derniers jours
    df, summary = downloader.download_all_parallel(days=7, max_workers=3)
    
    if df is not None:
        logger.info("🎉 Téléchargement terminé avec succès!")
        logger.info(f"📊 Résumé: {summary['successful_downloads']}/{summary['total_symbols']} symboles téléchargés")
        logger.info(f"📈 Total candles: {summary['total_candles']}")
    else:
        logger.error("❌ Échec du téléchargement")

if __name__ == "__main__":
    main()
