#!/usr/bin/env python3
"""
🧪 TEST DEMO ENDPOINTS
Test local pour valider la configuration demo
"""

import ccxt
import os

# Vos clés demo
api_key = "iLNzCTdF8k2VDzMNhlzBVm0SzvfAKeVOtG5Be3V4JG7rpNlOYbAvSk6Z0T3GAtdM"
secret = "445UuL9z1HP6GrDwf8SGezLy14Nap7CIt67hqx25YuFFlQ6jC4RA15iowF64iRw6"

# Init CCXT
exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',
        'fetchConfig': False,  # Disable SAPI config calls
    }
})

# Disable ALL SAPI calls (not available in demo)
exchange.has['fetchBalance'] = False
exchange.has['fetchAccountStatus'] = False
exchange.has['fetchMyTrades'] = False
exchange.has['fetchDepositAddress'] = False
exchange.has['fetchDeposits'] = False
exchange.has['fetchWithdrawals'] = False

# Force demo
demo_domain = "https://demo-fapi.binance.com"
exchange.hostname = "demo-fapi.binance.com"

for collection in ['api', 'fapiPublic', 'fapiPrivate', 'fapiPrivateV2', 'sapi']:
    if collection in exchange.urls:
        for key in exchange.urls[collection]:
            if isinstance(exchange.urls[collection][key], str):
                url = exchange.urls[collection][key]
                url = url.replace("https://fapi.binance.com", demo_domain)
                url = url.replace("https://api.binance.com", demo_domain)
                url = url.replace("https://sapi.binance.com", demo_domain)
                exchange.urls[collection][key] = url

# exchange.setSandboxMode(True)  # Deprecated - use demo endpoints directly

# Test
try:
    # Fetch markets (simple test)
    markets = exchange.fetch_markets()
    print(f"✅ Markets fetched: {len(markets)}")
    
    # Fetch positions (might trigger SAPI)
    try:
        positions = exchange.fetch_positions()
        print(f"✅ Positions fetched: {len(positions)}")
    except Exception as pos_err:
        print(f"⚠️ Positions failed (SAPI issue): {pos_err}")
    
    # Test market order (small)
    # symbol = "BTC/USDT:USDT"
    # order = exchange.create_market_order(symbol, 'buy', 0.001)
    # print(f"✅ Order created: {order}")
    
except Exception as e:
    print(f"❌ Error: {e}")
