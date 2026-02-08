# Copie de run_test_v2.py mais force YFinance au lieu de S3
import sys
sys.path.insert(0, '/Users/zakaria/Trading/Systeme_Test_Bedrock')
from run_test_v2 import *

# Patch pour forcer YFinance
original_fetch = fetch_market_data_with_fallback

def fetch_market_data_with_fallback_FORCE_YF(symbol, days, offset_days=0):
    """Force YFinance même si S3 a des données"""
    logger.info("🔄 FORCING YFINANCE (ignoring S3)")
    
    # Skip S3, go directly to fallback
    loader = S3Loader()
    
    # Check if crypto
    is_crypto = '/' in symbol or symbol in ['BTC-USD', 'ETH-USD', 'SOL-USD', 'BTCUSDT', 'ETHUSDT']
    
    if is_crypto:
        logger.info(f"🪙 Crypto detected, using Binance API for {symbol}...")
        try:
            data = fetch_crypto_from_binance(symbol, days, offset_days)
            if data:
                upload_data_to_s3(loader, symbol, data)
                return data
        except Exception as e:
            logger.warning(f"Binance fallback failed: {e}")
    
    # YFinance fallback (same as original but forced)
    logger.info(f"⚠️ Forcing YFinance for {symbol}...")
    try:
        import yfinance as yf
        from datetime import timedelta
        
        end_date = datetime.now() - timedelta(days=offset_days)
        start_date = end_date - timedelta(days=days + 5)
        
        is_index = symbol.startswith('^')
        
        if days > 730:
            interval = "1d"
        elif is_index and days > 30:
            interval = "1d"
            logger.info(f"📈 Index detected, using 1d interval")
        else:
            interval = "1h"
        
        logger.info(f"Downloading YF data ({interval}) for {symbol}...")
        df = yf.download(symbol, start=start_date, end=end_date, interval=interval, progress=False)
        
        if df.empty and interval == "1h":
             logger.warning("YF 1h Empty, trying 1d...")
             df = yf.download(symbol, start=start_date, end=end_date, interval="1d", progress=False)

        if not df.empty:
            import pandas as pd
            formatted_data = []
            for index, row in df.iterrows():
                try:
                    ts = int(index.timestamp() * 1000)
                    op = float(row['Open'].iloc[0]) if isinstance(row['Open'], pd.Series) else float(row['Open'])
                    hi = float(row['High'].iloc[0]) if isinstance(row['High'], pd.Series) else float(row['High'])
                    lo = float(row['Low'].iloc[0]) if isinstance(row['Low'], pd.Series) else float(row['Low'])
                    cl = float(row['Close'].iloc[0]) if isinstance(row['Close'], pd.Series) else float(row['Close'])
                    vo = float(row['Volume'].iloc[0]) if isinstance(row['Volume'], pd.Series) else float(row['Volume'])
                    formatted_data.append([ts, op, hi, lo, cl, vo])
                except:
                    ts = int(index.timestamp() * 1000)
                    formatted_data.append([ts, float(row['Open']), float(row['High']), float(row['Low']), float(row['Close']), float(row['Volume'])])

            logger.info(f"Loaded {len(formatted_data)} candles from YFinance for {symbol}")
            upload_data_to_s3(loader, symbol, formatted_data)
            return formatted_data
    except Exception as e:
        logger.error(f"YFinance Fallback failed: {e}")
        
    return []

# Monkey patch
import run_test_v2
run_test_v2.fetch_market_data_with_fallback = fetch_market_data_with_fallback_FORCE_YF

if __name__ == "__main__":
    run_test('Indices', '^GSPC', 365, offset_days=0)
