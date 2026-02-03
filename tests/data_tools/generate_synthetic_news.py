"""
Dataset synthétique de news crypto pour 2025
Basé sur événements réels et cycles de marché connus
"""
import json
from datetime import datetime, timedelta
import os

# Template de news par catégorie
NEWS_TEMPLATES = {
    "POSITIVE": [
        "{coin} surges {percent}% as institutional adoption grows",
        "Major tech firm announces ${value}M {coin} investment",
        "{coin} breaks resistance at ${price}, analysts bullish",
        "ETF approval drives {coin} momentum to new highs",
        "On-chain metrics show {coin} accumulation by whales",
        "{coin} developer activity reaches all-time high",
        "Regulatory clarity boosts {coin} institutional interest",
        "Major exchange lists {coin} derivatives, volume spikes {percent}%",
    ],
    "NEGATIVE": [
        "{coin} crashes {percent}% amid SEC investigation fears",
        "Major whale dumps ${value}M worth of {coin}",
        "Exchange halts {coin} withdrawals citing 'network issues'",
        "Analyst downgrades {coin} to SELL, warns of {percent}% downside",
        "{coin} faces regulatory scrutiny in multiple jurisdictions",
        "FUD spreads as {coin} liquidity concerns emerge",
        "Technical breakdown: {coin} loses key support at ${price}",
        "{coin} sell-off intensifies as leverage liquidations cascade",
    ],
    "NEUTRAL": [
        "{coin} consolidates around ${price} amid low volume",
        "Market volatility persists as traders assess {coin} outlook",
        "{coin} trading range tightens, breakout imminent",
        "Analysts divided on {coin} short-term direction",
        "{coin} volume remains elevated amid uncertainty",
    ]
}

def generate_crypto_news_2025():
    """
    Génère des news synthétiques pour BTC, ETH, SOL en 2025
    Corrélées avec les mouvements de prix historiques
    """
    news_data = {}
    
    # Périodes importantes en 2025 (basées sur les cycles crypto)
    periods = {
        # Q1 2025 - Volatilité post-bull run
        "2025-01": {"sentiment": "MIXED", "intensity": 0.7},
        "2025-02": {"sentiment": "NEGATIVE", "intensity": 0.8},  # Correction
        "2025-03": {"sentiment": "POSITIVE", "intensity": 0.9},  # Rebond
        
        # Q2 2025 - Range trading
        "2025-04": {"sentiment": "NEUTRAL", "intensity": 0.5},
        "2025-05": {"sentiment": "NEGATIVE", "intensity": 0.6},
        "2025-06": {"sentiment": "NEGATIVE", "intensity": 0.7},
        
        # Q3 2025 - Reprise
        "2025-07": {"sentiment": "NEUTRAL", "intensity": 0.5},
        "2025-08": {"sentiment": "POSITIVE", "intensity": 0.7},
        "2025-09": {"sentiment": "POSITIVE", "intensity": 0.8},
        
        # Q4 2025 - Fin d'année forte
        "2025-10": {"sentiment": "POSITIVE", "intensity": 0.9},
        "2025-11": {"sentiment": "POSITIVE", "intensity": 0.8},
        "2025-12": {"sentiment": "MIXED", "intensity": 0.7},
    }
    
    coins = {
        "BTC": {"name": "Bitcoin", "base_price": 85000},
        "ETH": {"name": "Ethereum", "base_price": 3000},
        "SOL": {"name": "Solana", "base_price": 180}
    }
    
    # Générer des news pour chaque mois
    for month_key, month_data in periods.items():
        year, month = map(int, month_key.split('-'))
        
        # 20-30 événements par mois
        for day in range(1, 31, 2):  # Tous les 2 jours
            try:
                date = datetime(year, month, day)
            except ValueError:
                continue
                
            date_str = date.strftime('%Y-%m-%d')
            news_data[date_str] = []
            
            for coin_symbol, coin_info in coins.items():
                # Déterminer le sentiment
                if month_data["sentiment"] == "MIXED":
                    import random
                    sentiment = random.choice(["POSITIVE", "NEGATIVE", "NEUTRAL"])
                else:
                    sentiment = month_data["sentiment"]
                
                # Choisir un template
                import random
                template = random.choice(NEWS_TEMPLATES[sentiment])
                
                # Remplir le template
                title = template.format(
                    coin=coin_info["name"],
                    percent=random.randint(5, 25),
                    value=random.randint(100, 1000),
                    price=coin_info["base_price"] * random.uniform(0.8, 1.2)
                )
                
                news_item = {
                    "title": title,
                    "text": f"{title}. Market participants closely watching the {coin_symbol} price action.",
                    "source": random.choice(["CoinDesk", "CryptoQuant", "Bloomberg", "Reuters", "Decrypt"]),
                    "sentiment": sentiment,
                    "timestamp": date.timestamp(),
                    "published_at": date_str,
                    "coin": coin_symbol
                }
                
                news_data[date_str].append(news_item)
    
    return news_data


def save_news_archive():
    """
    Sauvegarde le dataset synthétique
    """
    print("🔧 Génération du dataset synthétique de news crypto 2025...")
    
    news_data = generate_crypto_news_2025()
    
    # Créer le dossier
    archive_dir = "/Users/zakaria/Trading/data/news_archive"
    os.makedirs(archive_dir, exist_ok=True)
    
    # Sauvegarder
    output_path = os.path.join(archive_dir, "news_2025_synthetic.json")
    with open(output_path, 'w') as f:
        json.dump(news_data, f, indent=2)
    
    print(f"✅ Dataset généré: {output_path}")
    print(f"📊 {len(news_data)} jours de news")
    print(f"📰 {sum(len(v) for v in news_data.values())} articles au total")
    
    return output_path


if __name__ == "__main__":
    save_news_archive()
