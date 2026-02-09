import boto3
import ccxt
import os
from decimal import Decimal

# --- CONFIGURATION ---
REGION = 'eu-west-3'
CONFIG_TABLE = 'EmpireConfig'

print("🔍 ÉTAPE 1 : Récupération des clés dans DynamoDB...")
try:
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(CONFIG_TABLE)
    resp = table.get_item(Key={'ConfigKey': 'BINANCE_CREDENTIALS'})
    
    if 'Item' not in resp:
        print("❌ ERREUR : Aucune clé 'BINANCE_CREDENTIALS' trouvée dans la table EmpireConfig.")
        exit()
    
    creds = resp['Item']
    api_key = creds.get('ApiKey')
    api_secret = creds.get('ApiSecret')
    
    print(f"✅ Clés récupérées (commençant par : {api_key[:5]}...)")

except Exception as e:
    print(f"❌ ERREUR AWS : {e}")
    exit()

print("\n🔍 ÉTAPE 2 : Connexion à Binance Testnet...")
try:
    # Initialisation CCXT avec mode Sandbox
    exchange = ccxt.binance({
        'apiKey': api_key,
        'secret': api_secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    exchange.set_sandbox_mode(True) 
    
    # Test de connectivité simple
    print("🛰️ Tentative d'appel au serveur Binance...")
    balance = exchange.fetch_balance()
    
    usdt_free = balance.get('USDT', {}).get('free', 0)
    usdt_total = balance.get('USDT', {}).get('total', 0)
    
    print(f"✅ CONNEXION RÉUSSIE !")
    print(f"💰 Solde USDT Libre : {usdt_free}")
    print(f"💰 Solde USDT Total (Equity) : {usdt_total}")
    
    if usdt_total == 0:
        print("⚠️ ATTENTION : Le solde est à 0. C'est peut-être pour ça que le Dashboard affiche $1000 (valeur de secours).")

except Exception as e:
    print(f"❌ ERREUR BINANCE : {e}")
    if "Invalid Api-Key ID" in str(e):
        print("\n👉 CONSEIL : Tes clés Testnet ont probablement expiré ou ne sont pas activées pour les Futures.")
    elif "Timestamp for this request" in str(e):
        print("\n👉 CONSEIL : L'heure de ton Mac n'est pas synchronisée avec le serveur Binance.")

print("\n--- TEST TERMINÉ ---")