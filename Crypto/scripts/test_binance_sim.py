import ccxt
import time
import pprint

# Tes clés du Futures Testnet
API_KEY = '8GMSKB5dEktu58yrd3P5NCNabI9mDHIY8zpvnO7ZXsIW3NnEzjD7Ppf5cZeoOCnC'
SECRET_KEY = '2V89JGWnqPdEL1ilbwx1va6r14Lc9g78ZufY3OJdQrjhRdZhE1DTc3nVBI6Y7sju'

# Initialisation CCXT
# NOTE: set_sandbox_mode(True) is deprecated for futures in CCXT.
# We must manually override the endpoints to point to Testnet.

exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'  # Cible les Futures USDT-M (Perp)
    }
})

# OVERRIDE MANUEL DES ESPointes (Endpoints)
# On redirige les appels "fapi" (Futures API) vers le domaine du Testnet
# CRUCIAL: Ne pas mettre de chemin /fapi/v1 ici, CCXT l'ajoute tout seul.
exchange.urls['api']['fapiPublic'] = 'https://testnet.binancefuture.com'
exchange.urls['api']['fapiPrivate'] = 'https://testnet.binancefuture.com'
exchange.urls['api']['fapiPrivateV2'] = 'https://testnet.binancefuture.com'

# Pour les appels publics qui pourraient passer par l'API Spot par défaut ?
# Mieux vaut laisser l'API spot par défaut si on n'utilise pas le testnet spot.

def connect_to_empire_sim():
    try:
        print("🔗 Connexion à l Titre V4 (CCXT) - Simulation Binance...")
        
        # 1. Récupération du solde spécifique aux Futures
        # balance = exchange.fetch_balance()
        balance = exchange.fetch_balance({'type': 'future'})
        
        # Sur le Futures Testnet, on cherche l'USDT
        usdt_total = 0.0
        usdt_free = 0.0
        
        # Check standard 'free' dictionary first
        if 'USDT' in balance['free']:
             usdt_free = balance['free']['USDT']
             usdt_total = balance['total']['USDT']
        
        # Fallback to info parsing (more robust for some CCXT versions)
        if usdt_total == 0:
             if 'assets' in balance['info']:
                 for asset in balance['info']['assets']:
                     if asset['asset'] == 'USDT':
                         usdt_total = float(asset['walletBalance'])
                         usdt_free = float(asset['availableBalance'])
                         break

        print(f"✅ Statut : CONNECTÉ (Via CCXT)")
        print(f"💰 Capital Total (Demo) : {usdt_total} USDT")
        print(f"💵 Capital Disponible   : {usdt_free} USDT")
        
        # 2. Récupération du prix actuel du BTC
        ticker = exchange.fetch_ticker('BTC/USDT')
        print(f"📈 Prix actuel BTC/USDT : {ticker['last']} USDT")
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur de liaison CCXT : {e}")
        # import traceback
        # traceback.print_exc()
        return False

if __name__ == "__main__":
    connect_to_empire_sim()
