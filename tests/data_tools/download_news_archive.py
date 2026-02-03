"""
Script pour télécharger et préparer des archives de news crypto historiques
Sources: Kaggle datasets
"""

import os
import json
from datetime import datetime

# Dataset recommandé: "Crypto News +" sur Kaggle
# URL: https://www.kaggle.com/datasets/oliviervha/crypto-news

DATASET_INFO = """
📰 SOURCES DE NEWS CRYPTO HISTORIQUES

1. **Crypto News + (Kaggle)**
   - Période: Oct 2021 - Dec 2023
   - Contenu: Titres, texte complet, sources, sentiment
   - URL: https://www.kaggle.com/datasets/oliviervha/crypto-news
   
2. **Crypto News Headlines & Market Prices**
   - Période: 2021-2024
   - Contenu: Headlines + prices correlation
   - URL: https://www.kaggle.com/datasets/kaleenlakee/crypto-news-headlines-market-prices-by-date

3. **Sentiment Analysis of Bitcoin News (2021-2024)**
   - Période: 2021-2024
   - Contenu: Bitcoin news avec sentiment
   - URL: https://www.kaggle.com/datasets/ankurzing/sentiment-analysis-on-bitcoin-news

INSTRUCTIONS DE TÉLÉCHARGEMENT:
===============================

1. Installer Kaggle CLI:
   pip install kaggle

2. Configurer API Token:
   - Aller sur: https://www.kaggle.com/settings
   - Créer un nouveau token API
   - Placer kaggle.json dans: ~/.kaggle/

3. Télécharger le dataset (exemple):
   kaggle datasets download -d oliviervha/crypto-news
   
4. Extraire dans: /Users/zakaria/Trading/data/news_archive/

5. Le script news_fetcher.py sera mis à jour pour lire depuis ces archives
"""

def download_crypto_news_dataset():
    """
    Télécharge le dataset Crypto News + depuis Kaggle
    """
    print("📥 Téléchargement du dataset Crypto News+...")
    
    # Créer le dossier de destination
    archive_dir = "/Users/zakaria/Trading/data/news_archive"
    os.makedirs(archive_dir, exist_ok=True)
    
    try:
        # Utiliser l'API Kaggle Python directement
        from kaggle.api.kaggle_api_extended import KaggleApi
        
        api = KaggleApi()
        api.authenticate()
        
        print("✅ Authentification Kaggle réussie")
        print("📦 Téléchargement en cours...")
        
        # Télécharger le dataset
        api.dataset_download_files(
            'oliviervha/crypto-news',
            path=archive_dir,
            unzip=True
        )
        
        print(f"✅ Dataset téléchargé et extrait dans {archive_dir}")
        return True
            
    except ImportError:
        print("❌ Module Kaggle non installé")
        print("   Installation: pip install kaggle")
        return False
    except OSError as e:
        if "Could not find" in str(e) or "credentials" in str(e).lower():
            print("❌ Credentials Kaggle non configurées")
            print("\n📋 CONFIGURATION REQUISE:")
            print("   1. Aller sur: https://www.kaggle.com/settings")
            print("   2. Scroll jusqu'à 'API' section")
            print("   3. Cliquer 'Create New Token'")
            print("   4. Sauvegarder kaggle.json dans: ~/.kaggle/")
            print("   5. Relancer ce script")
            return False
        else:
            print(f"❌ Erreur: {e}")
            return False
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False


def create_news_index():
    """
    Crée un index rapide des news par date pour recherche efficace
    """
    archive_dir = "/Users/zakaria/Trading/data/news_archive"
    
    print("🔍 Création de l'index des news...")
    
    # TODO: Parser le CSV du dataset et créer un index JSON
    # Format: { "2023-01-15": [ {news1}, {news2}, ... ] }
    
    index = {}
    
    # Exemple de structure:
    # index["2023-01-15"] = [
    #     {
    #         "title": "Bitcoin surges past $20K",
    #         "text": "...",
    #         "source": "CoinDesk",
    #         "sentiment": "POSITIVE",
    #         "timestamp": "2023-01-15T10:30:00"
    #     }
    # ]
    
    index_path = os.path.join(archive_dir, "news_index.json")
    with open(index_path, 'w') as f:
        json.dump(index, f, indent=2)
    
    print(f"✅ Index créé: {index_path}")


if __name__ == "__main__":
    print(DATASET_INFO)
    print("\n" + "="*60 + "\n")
    
    choice = input("Télécharger le dataset maintenant? (y/n): ")
    
    if choice.lower() == 'y':
        if download_crypto_news_dataset():
            create_news_index()
        else:
            print("\n📖 Veuillez suivre les instructions ci-dessus pour télécharger manuellement")
    else:
        print("\n📖 Instructions sauvegardées. Télécharge manuellement quand tu es prêt.")
