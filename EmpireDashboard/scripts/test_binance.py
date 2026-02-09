import ccxt
API_KEY = '8GMSKB5dEktu58yrd3P5NCNabI9mDHIY8zpvnO7ZXsIW3NnEzjD7Ppf5cZeoOCnC'
SECRET_KEY = '2V89JGWnqPdEL1ilbwx1va6r14Lc9g78ZufY3OJdQrjhRdZhE1DTc3nVBI6Y7sju'

def test_mode(name, sandbox, type='future'):
    print(f"\n--- Testing {name} {type} (Sandbox: {sandbox}) ---")
    try:
        exchange = ccxt.binance({
            'apiKey': API_KEY,
            'secret': SECRET_KEY,
            'options': {'defaultType': type}
        })
        if sandbox:
            if type == 'future':
                exchange.urls['api']['fapiPublic'] = 'https://testnet.binancefuture.com'
                exchange.urls['api']['fapiPrivate'] = 'https://testnet.binancefuture.com'
            else:
                exchange.set_sandbox_mode(True)
        
        balance = exchange.fetch_balance()
        if type == 'future':
            val = balance.get('USDT', {}).get('total')
        else:
            val = balance.get('total', {}).get('USDT')
        print(f"✅ Success! USDT: {val}")
    except Exception as e:
        print(f"❌ Failed: {e}")

test_mode("MAINNET", False, 'future')
test_mode("MAINNET", False, 'spot')
test_mode("TESTNET", True, 'future')

