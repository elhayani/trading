import ccxt
import datetime

def check_2022_data():
    exchange = ccxt.binance()
    symbol = 'BTC/USDT'
    # 2022-01-01 00:00:00 UTC
    since = int(datetime.datetime(2022, 1, 1).timestamp() * 1000)
    
    try:
        print(f"Testing connectivity to Binance for {symbol} starting 2022-01-01...")
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', since=since, limit=5)
        if len(ohlcv) > 0:
            print("✅ Successfully fetched data.")
            print(f"First candle: {datetime.datetime.fromtimestamp(ohlcv[0][0]/1000)}")
            return True
        else:
            print("⚠️ No data returned.")
            return False
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return False

if __name__ == "__main__":
    check_2022_data()
