import ccxt
import boto3
from datetime import datetime
from decimal import Decimal

print("--- INITIALISATION DU SCRIPT ---")

# CONFIGURATION
API_KEY = '8GMSKB5dEktu58yrd3P5NCNabI9mDHIY8zpvnO7ZXsIW3NnEzjD7Ppf5cZeoOCnC'
SECRET_KEY = '2V89JGWnqPdEL1ilbwx1va6r14Lc9g78ZufY3OJdQrjhRdZhE1DTc3nVBI6Y7sju'
REGION = 'eu-west-3'
TABLES = ["EmpireTradesHistory", "EmpireCryptoV4", "EmpireForexHistory", "EmpireIndicesHistory", "EmpireCommoditiesHistory"]

# Initialisation Binance (LIVE)
try:
    exchange = ccxt.binance({
        'apiKey': API_KEY, 'secret': SECRET_KEY, 'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    print("✅ API Binance (Live) : OK")
except Exception as e:
    print(f"❌ Erreur Init Binance : {e}")

# Initialisation DynamoDB
try:
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    config_table = dynamodb.Table('EmpireConfig')
    
    # SAUVEGARDE DES CREDENTIALS POUR LA LAMBDA
    print("🔐 Sauvegarde des credentials dans EmpireConfig...")
    config_table.put_item(Item={
        'ConfigKey': 'BINANCE_CREDENTIALS',
        'ApiKey': API_KEY,
        'ApiSecret': SECRET_KEY,
        'UpdatedAt': datetime.utcnow().isoformat()
    })
    print("✅ Credentials sauvegardés.")
    
    print("✅ DynamoDB : OK")
except Exception as e:
    print(f"❌ Erreur Init DynamoDB : {e}")

def run_cleanup():
    print("\n🚀 RECHERCHE DE POSITIONS OUVERTES...")

    # 1. FERMETURE BINANCE
    try:
        positions = exchange.fetch_positions()
        open_pos = [p for p in positions if float(p['contracts']) != 0]

        if not open_pos:
            print("ℹ️ Aucune position réelle trouvée sur Binance.")
        else:
            for pos in open_pos:
                symbol = pos['symbol']
                size = float(pos['contracts'])
                side = 'sell' if size > 0 else 'buy'
                print(f"📉 Fermeture de {symbol} sur Binance...")
                exchange.create_order(symbol, 'market', side, abs(size), params={'reduceOnly': True})
                print(f"✅ Position {symbol} fermée.")
    except Exception as e:
        print(f"⚠️ Erreur lors du nettoyage Binance : {e}")

    # 2. NETTOYAGE DYNAMODB
    print("\n📂 SYNCHRONISATION DYNAMODB...")
    for table_name in TABLES:
        table = dynamodb.Table(table_name)
        try:
            response = table.scan()
            items = response.get('Items', [])
            open_items = [i for i in items if i.get('Status') == 'OPEN']

            if not open_items:
                print(f"   - {table_name}: OK (Rien à fermer)")
                continue

            for item in open_items:
                # Gestion de la clé primaire selon le schéma de la table
                key = {}
                if 'TradeId' in item: 
                    key['TradeId'] = item['TradeId']
                    # On ne met le Sort Key QUE si la table l'utilise aussi
                    if table_name in ["EmpireTradesHistory"] and 'Timestamp' in item:
                        key['Timestamp'] = item['Timestamp']
                elif 'Timestamp' in item:
                    key['Timestamp'] = item['Timestamp']

                print(f"   - {table_name}: Fermeture trade {item.get('Pair')}...")
                table.update_item(
                    Key=key,
                    UpdateExpression="SET #st = :val",
                    ExpressionAttributeNames={'#st': 'Status'},
                    ExpressionAttributeValues={':val': 'CLOSED'}
                )
            print(f"✅ {table_name} nettoyée.")
        except Exception as e:
            print(f"⚠️ Erreur table {table_name} : {e}")

    print("\n✨ NETTOYAGE TERMINÉ. Vérifie ton Dashboard.")

# APPEL EXPLICITE DE LA FONCTION
run_cleanup()