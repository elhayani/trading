#!/usr/bin/env python3
"""
Script pour regrouper tous les fichiers CSV de Binance en un seul fichier
Ajoute une colonne 'asset' contenant le nom de l'actif
"""

import os
import pandas as pd
import glob
from datetime import datetime

def merge_all_csv_with_asset():
    """Regrouper tous les fichiers CSV en un seul avec colonne asset"""
    
    # Répertoire contenant les fichiers CSV
    input_dir = "binance_history_20260214"
    
    # Vérifier si le répertoire existe
    if not os.path.exists(input_dir):
        print(f"❌ Répertoire {input_dir} introuvable")
        return
    
    # Trouver tous les fichiers CSV individuels (exclure les fichiers combinés)
    csv_files = glob.glob(f"{input_dir}/*.csv")
    csv_files = [f for f in csv_files if not any(x in f for x in ['all_futures_history', 'summary_stats', 'download_summary'])]
    
    if not csv_files:
        print("❌ Aucun fichier CSV individuel trouvé")
        return
    
    print(f"📁 Trouvé {len(csv_files)} fichiers CSV à traiter")
    
    # Liste pour stocker tous les DataFrames
    all_dfs = []
    
    # Traiter chaque fichier
    for i, csv_file in enumerate(csv_files, 1):
        try:
            # Extraire le nom de l'actif du nom de fichier
            asset_name = os.path.basename(csv_file).replace('.csv', '')
            
            # Lire le fichier CSV
            df = pd.read_csv(csv_file)
            
            # Ajouter la colonne asset
            df['asset'] = asset_name
            
            # Réorganiser les colonnes pour mettre asset en premier
            cols = ['asset'] + [col for col in df.columns if col != 'asset']
            df = df[cols]
            
            all_dfs.append(df)
            
            if i % 50 == 0:
                print(f"🔄 Progression: {i}/{len(csv_files)} fichiers traités")
                
        except Exception as e:
            print(f"❌ Erreur traitement {csv_file}: {e}")
    
    if not all_dfs:
        print("❌ Aucune donnée à fusionner")
        return
    
    # Fusionner tous les DataFrames
    print("🔧 Fusion des données...")
    merged_df = pd.concat(all_dfs, ignore_index=True)
    
    # Trier par timestamp puis par asset
    merged_df = merged_df.sort_values(['timestamp', 'asset'])
    
    # Sauvegarder le fichier fusionné
    output_file = f"{input_dir}/merged_all_assets_with_names.csv"
    merged_df.to_csv(output_file, index=False)
    
    # Statistiques
    total_rows = len(merged_df)
    unique_assets = merged_df['asset'].nunique()
    date_range = f"{merged_df['timestamp'].min()} à {merged_df['timestamp'].max()}"
    
    print(f"✅ Fusion terminée!")
    print(f"📊 Fichier sauvegardé: {output_file}")
    print(f"📈 Statistiques:")
    print(f"   - Total lignes: {total_rows:,}")
    print(f"   - Actifs uniques: {unique_assets}")
    print(f"   - Période: {date_range}")
    print(f"   - Colonnes: {list(merged_df.columns)}")
    
    # Afficher un aperçu
    print("\n📋 Aperçu des données:")
    print(merged_df.head(10))
    
    return output_file

if __name__ == "__main__":
    merge_all_csv_with_asset()
