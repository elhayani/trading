import os
import boto3
import json
import logging
from datetime import datetime, timedelta

# Configuration
DEFAULT_BUCKET = os.environ.get('TRADING_LOGS_BUCKET', 'empire-trading-data-paris')
REGION = 'eu-west-3'

logger = logging.getLogger(__name__)

class S3Loader:
    def __init__(self, bucket_name=DEFAULT_BUCKET, region_name=REGION):
        self.bucket = bucket_name
        self.s3_client = boto3.client('s3', region_name=region_name)
        
    def fetch_historical_data(self, symbol, days, offset_days=0):
        """
        Récupère 'days' jours de données de marché depuis S3.
        """
        end_time = datetime.now() - timedelta(days=offset_days)
        start_time = end_time - timedelta(days=days)

        # Check for Commodities (CSV format)
        if symbol in ['CL=F', 'CL', 'GC=F', 'GC']:
            return self._fetch_commodities_csv(symbol, start_time, end_time)

        start_year = start_time.year
        end_year = end_time.year
        years = range(start_year, end_year + 1)
        
        all_ohlcv = []
        safe_symbol = symbol.replace('/', '_')
        
        logger.info(f"Downloading historical data for {symbol} ({days} days)...")
        
        for y in years:
            key = f"historical/{safe_symbol}/{y}.json"
            try:
                resp = self.s3_client.get_object(Bucket=self.bucket, Key=key)
                file_content = resp['Body'].read().decode('utf-8')
                yearly_data = json.loads(file_content)
                all_ohlcv.extend(yearly_data)
                # logger.info(f"Loaded {key}: {len(yearly_data)} candles")
            except Exception as e:
                logger.warning(f"Failed to load {key}: {e}")
                
        # Filter by timestamp
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)
        
        filtered = [x for x in all_ohlcv if start_ts <= x[0] <= end_ts]
        filtered.sort(key=lambda x: x[0])
        
        return filtered

    def _fetch_commodities_csv(self, symbol, start_time, end_time):
        """
        Loads Commodities data from CSV: historical/commodities/{SYM}_1d_2010_2023.csv
        """
        import csv
        import io

        # Map symbol to file prefix
        if symbol in ['CL=F', 'CL']:
            file_key = "historical/commodities/CL_1d_2010_2023.csv"
        elif symbol in ['GC=F', 'GC']:
             file_key = "historical/commodities/GC_1d_2010_2023.csv"
        else:
            return []

        logger.info(f"Downloading CSV data for {symbol} from {file_key}...")

        try:
            resp = self.s3_client.get_object(Bucket=self.bucket, Key=file_key)
            content = resp['Body'].read().decode('utf-8')
            
            all_ohlcv = []
            reader = csv.DictReader(io.StringIO(content))
            
            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(end_time.timestamp() * 1000)
            
            for row in reader:
                # Date format YYYY-MM-DD
                dt_str = row.get('Date')
                if not dt_str: continue
                
                try:
                    dt = datetime.strptime(dt_str, "%Y-%m-%d")
                    ts = int(dt.timestamp() * 1000)
                    
                    if start_ts <= ts <= end_ts:
                        # Extract OHLCV
                        # CSV: Date,close,high,low,open,volume
                        # Output: [ts, open, high, low, close, volume]
                        ohlcv = [
                            ts,
                            float(row.get('open', 0)),
                            float(row.get('high', 0)),
                            float(row.get('low', 0)),
                            float(row.get('close', 0)),
                            float(row.get('volume', 0))
                        ]
                        all_ohlcv.append(ohlcv)
                except Exception as e:
                    continue

            all_ohlcv.sort(key=lambda x: x[0])
            logger.info(f"Loaded {len(all_ohlcv)} daily candles for {symbol}")
            return all_ohlcv

        except Exception as e:
            logger.error(f"Failed to load CSV {file_key}: {e}")
            return []

    def fetch_news_data(self, symbol, days, offset_days=0):
        """
        Récupère les news depuis S3 pour la même période.
        Structure supposée: news/{symbol}/{year}/{month}/{day}.json
        Ou plus simple: news/{symbol}/{year}.json contenant une liste d'articles timestampés
        """
        # TODO: Adapter selon la structure réelle du bucket S3 news
        # Pour l'instant on tente un chargement similaire aux données historiques
        # Si la structure news est 'news/SYMBOL/year.json'
        
        end_time = datetime.now() - timedelta(days=offset_days)
        start_time = end_time - timedelta(days=days)
        
        start_year = start_time.year
        end_year = end_time.year
        years = range(start_year, end_year + 1)
        
        all_news = []
        safe_symbol = symbol.replace('/', '_')
         
        logger.info(f"Downloading news data for {symbol} ({days} days)...")

        for y in years:
            # Essai 1: news/{symbol}/{year}.json
            key = f"news/{safe_symbol}/{y}.json"
            try:
                resp = self.s3_client.get_object(Bucket=self.bucket, Key=key)
                content = resp['Body'].read().decode('utf-8')
                data = json.loads(content)
                if isinstance(data, list):
                    all_news.extend(data)
                logger.info(f"Loaded news from {key}")
            except Exception as e:
                logger.warning(f"Failed to load news {key}: {e}")
                # Essai 2: news_data/{symbol}/{year}.json ?
                pass
        
        # Filtrer par date
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)
        
        # On suppose que les news ont un champ 'timestamp' ou 'date'
        filtered_news = []
        for n in all_news:
            ts = n.get('timestamp')
            if not ts and n.get('date'):
                # Tenter de parser la date
                try:
                    dt = datetime.fromisoformat(n['date'].replace('Z', '+00:00'))
                    ts = int(dt.timestamp() * 1000)
                except:
                    pass
            
            if ts and start_ts <= ts <= end_ts:
                filtered_news.append(n)
                
        return filtered_news

