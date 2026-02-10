import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode

# Tes clés du Futures Testnet
API_KEY = '8GMSKB5dEktu58yrd3P5NCNabI9mDHIY8zpvnO7ZXsIW3NnEzjD7Ppf5cZeoOCnC'
SECRET_KEY = '2V89JGWnqPdEL1ilbwx1va6r14Lc9g78ZufY3OJdQrjhRdZhE1DTc3nVBI6Y7sju'

# URL de base du Testnet Futures
BASE_URL = 'https://testnet.binancefuture.com'

# Helpers pour la signature et l'envoi
def get_timestamp():
    return int(time.time() * 1000)

def sign_params(params):
    query_string = urlencode(params)
    signature = hmac.new(SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature

def send_signed_request(method, endpoint, params={}):
    url = BASE_URL + endpoint
    params['timestamp'] = get_timestamp()
    params['signature'] = sign_params(params)
    headers = {'X-MBX-APIKEY': API_KEY}
    
    try:
        if method == 'GET':
            response = requests.get(url, params=params, headers=headers)
        elif method == 'POST':
            response = requests.post(url, params=params, headers=headers)
        return response.json()
    except Exception as e:
        print(f"❌ Erreur Réseau : {e}")
        return None

def get_market_price(symbol):
    url = BASE_URL + '/fapi/v1/ticker/price'
    try:
        response = requests.get(url, params={'symbol': symbol})
        data = response.json()
        return float(data['price'])
    except:
        return 0.0

def execute_test_trade_v2():
    symbol = 'BTCUSDT'
    quantity = 0.01  # 0.01 BTC
    
    print(f"🚀 Simulation V2 (Requests RAW) sur {symbol}...")
    print("Contournement de l'erreur -4120 via LIMIT SELL pour le TP")
    
    # 0. Initial check price
    current_price = get_market_price(symbol)
    print(f"📊 Prix actuel du marché : {current_price} USDT")
    
    # 1. MARKET BUY ORDER
    print(f"⏳ Envoi de l'ordre d'ACHAT (Market Buy) pour {quantity} BTC...")
    buy_params = {
        'symbol': symbol,
        'side': 'BUY',
        'type': 'MARKET',
        'quantity': quantity,
    }
    
    buy_response = send_signed_request('POST', '/fapi/v1/order', buy_params)
    
    if 'code' in buy_response and buy_response['code'] != 0:
         if buy_response['code'] < 0:
             print(f"❌ Echec de l'achat : {buy_response}")
             return
    
    # Retrieve execution price
    entry_price = float(buy_response.get('avgPrice', 0.0))
    if entry_price == 0:
        entry_price = current_price # Fallback
        
    print(f"✅ Achat Exécuté ! Prix Entrée Estimé : {entry_price} USDT")
    print(f"🆔 Order ID : {buy_response.get('orderId')}")
    
    # 2. CALCUL DES SEUILS (TP/SL)
    # TP = +2% | SL = -1%
    tp_price = round(entry_price * 1.02, 1) # Limit Sell Target
    sl_price = round(entry_price * 0.99, 1) # Monitoring Level
    
    print(f"🎯 Objectifs : Take Profit @ {tp_price} | Stop Loss @ {sl_price}")
    
    # 3. PLACEMENT DU TAKE PROFIT (LIMIT SELL)
    # Ceci remplace TAKE_PROFIT_MARKET qui est bloqué sur Testnet (-4120)
    print(f"💰 Placement du TAKE PROFIT (LIMIT SELL)...")
    tp_params = {
        'symbol': symbol,
        'side': 'SELL',
        'type': 'LIMIT',
        'quantity': quantity,
        'price': tp_price,
        'timeInForce': 'GTC',
        'reduceOnly': 'true', # Important pour ne pas short si on a déjà vendu
    }
    
    tp_response = send_signed_request('POST', '/fapi/v1/order', tp_params)
    if 'orderId' in tp_response:
        print(f"✅ TP (Limit) Activé (Order ID: {tp_response['orderId']})")
    else:
        print(f"⚠️  Erreur TP : {tp_response}")

    # 4. STOP LOSS (MONITORING)
    print(f"⚠️  Le STOP LOSS à {sl_price} doit être géré via le monitoring du bot")
    print("   car l'API Testnet bloque actuellement les ordres STOP sur cet endpoint.")
        
    print("\n✨ Simulation Complète ! Vérifiez votre P&L sur le Dashboard Testnet.")
    print("👉 https://testnet.binancefuture.com/en/futures/BTCUSDT")

if __name__ == "__main__":
    execute_test_trade_v2()
