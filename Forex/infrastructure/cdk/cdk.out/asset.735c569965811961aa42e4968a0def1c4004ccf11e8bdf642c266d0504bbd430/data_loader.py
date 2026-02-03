import yfinance as yf
import pandas as pd

class DataLoader:
    @staticmethod
    def get_latest_data(pair, period='60d', interval='1h'):
        """
        Récupère les données live depuis Yahoo Finance
        """
        ticker = f"{pair}=X"
        try:
            # Téléchargement
            df = yf.download(ticker, period=period, interval=interval, progress=False)
            
            if df.empty:
                print(f"❌ No data for {pair}")
                return None
                
            # Nettoyage des colonnes MultiIndex
            if isinstance(df.columns, pd.MultiIndex):
                # Garder uniquement le niveau 'Price' (Close, Open, High, Low)
                # et supprimer le niveau 'Ticker'
                df.columns = df.columns.get_level_values(0)
            
            # Standardisation
            df.columns = [col.lower() for col in df.columns]
            
            # Vérification des colonnes essentielles
            required = ['open', 'high', 'low', 'close']
            if not all(col in df.columns for col in required):
                print(f"❌ Incomplete data for {pair}: {df.columns}")
                return None
                
            # S'assurer que le datetime est un index ou une colonne utilisable
            # Avec yfinance, c'est l'index par défaut.
            
            return df
            
        except Exception as e:
            print(f"❌ Error fetching {pair}: {e}")
            return None
