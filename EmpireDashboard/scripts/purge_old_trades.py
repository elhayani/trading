#!/usr/bin/env python3
"""
Script pour purger les anciens trades et ne garder que les trades OPEN
"""
import boto3
from decimal import Decimal

# Tables à nettoyer
TABLES_TO_CLEAN = [
    "EmpireTradesHistory"
]

dynamodb = boto3.resource('dynamodb')

def purge_table(table_name):
    """Supprime tous les trades sauf OPEN"""
    print(f"\n🔍 Scanning {table_name}...")
    table = dynamodb.Table(table_name)

    try:
        response = table.scan()
        items = response.get('Items', [])

        # Pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))

        print(f"   📊 Total items: {len(items)}")

        # Compter par statut
        status_counts = {}
        for item in items:
            status = item.get('Status', 'UNKNOWN')
            status_counts[status] = status_counts.get(status, 0) + 1

        print(f"   📈 Status breakdown:")
        for status, count in status_counts.items():
            print(f"      - {status}: {count}")

        # Supprimer tous sauf OPEN
        deleted_count = 0
        kept_count = 0

        for item in items:
            status = item.get('Status', '').upper()

            if status == 'OPEN':
                kept_count += 1
                continue

            # Supprimer l'item
            key = {}
            # Détecter la clé primaire (varie selon la table)
            if 'TradeId' in item:
                key['TradeId'] = item['TradeId']
                if 'Timestamp' in item:
                    key['Timestamp'] = item['Timestamp']
            elif 'Pair' in item and 'Timestamp' in item:
                key['Pair'] = item['Pair']
                key['Timestamp'] = item['Timestamp']
            else:
                print(f"   ⚠️  Cannot determine key for item: {item}")
                continue

            try:
                table.delete_item(Key=key)
                deleted_count += 1

                if deleted_count % 50 == 0:
                    print(f"   🗑️  Deleted {deleted_count} items so far...")

            except Exception as e:
                print(f"   ❌ Error deleting item: {e}")

        print(f"   ✅ Deleted: {deleted_count}, Kept (OPEN): {kept_count}")

    except Exception as e:
        print(f"   ❌ Error scanning {table_name}: {e}")

def main():
    print("="*70)
    print("🧹 PURGE OLD TRADES - Keep Only OPEN Trades")
    print("="*70)

    # Confirmation
    print("\n⚠️  WARNING: This will DELETE all trades except OPEN ones!")
    print(f"   Tables to clean: {', '.join(TABLES_TO_CLEAN)}")
    print()
    confirm = input("Are you sure? Type 'YES' to continue: ")

    if confirm != 'YES':
        print("❌ Aborted.")
        return

    print("\n🚀 Starting cleanup...")

    for table_name in TABLES_TO_CLEAN:
        purge_table(table_name)

    print("\n" + "="*70)
    print("✅ CLEANUP COMPLETE!")
    print("="*70)
    print("\n💡 Next steps:")
    print("   1. Refresh your dashboard to see updated stats")
    print("   2. Only OPEN trades will be displayed")
    print()

if __name__ == "__main__":
    main()
