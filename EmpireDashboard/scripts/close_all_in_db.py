import boto3

REGION = 'eu-west-3'
TABLES = ["EmpireTradesHistory", "EmpireCryptoV4", "EmpireForexHistory", "EmpireIndicesHistory", "EmpireCommoditiesHistory"]

dynamodb = boto3.resource('dynamodb', region_name=REGION)

def force_clean_dashboard():
    print("🧹 NETTOYAGE RADICAL DES TABLES...")

    for table_name in TABLES:
        table = dynamodb.Table(table_name)
        try:
            response = table.scan()
            items = response.get('Items', [])

            if not items:
                print(f"✅ {table_name} est déjà vide ou propre.")
                continue

            for item in items:
                if item.get('Status') == 'OPEN':
                    # On change le statut dans l'objet local
                    item['Status'] = 'CLOSED'
                    if 'PnL' not in item or item['PnL'] == 0:
                        from decimal import Decimal
                        item['PnL'] = Decimal('0.0')

                    # On ré-injecte l'objet entier (écrase l'ancien avec le nouveau statut)
                    table.put_item(Item=item)
                    print(f"   [FIXED] {table_name} -> {item.get('Pair', 'Unknown')}")

            print(f"✨ {table_name} synchronisée.")
        except Exception as e:
            print(f"❌ Erreur sur {table_name}: {e}")

if __name__ == "__main__":
    force_clean_dashboard()