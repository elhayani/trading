"""
Dataset synthétique de news crypto pour 2024
Basé sur les événements: Bitcoin Halving (Avril 2024), Bull Run modéré, ETF approvals
"""
import json
from datetime import datetime, timedelta
import os
import random

# Événements majeurs 2024
CRYPTO_EVENTS_2024 = {
    # Q1 - Préparation ETF + Anticipation Halving
    "2024-01": {"sentiment": "POSITIVE", "intensity": 0.8, "event": "Bitcoin ETF approval speculation"},
    "2024-02": {"sentiment": "POSITIVE", "intensity": 0.7, "event": "ETF inflows surge"},
    "2024-03": {"sentiment": "POSITIVE", "intensity": 0.8, "event": "Pre-halving rally"},
    
    # Q2 - HALVING BITCOIN (Avril 2024) - Événement MAJEUR
    "2024-04": {"sentiment": "VERY_POSITIVE", "intensity": 1.0, "event": "BITCOIN HALVING (4th)"},
    "2024-05": {"sentiment": "POSITIVE", "intensity": 0.8, "event": "Post-halving momentum"},
    "2024-06": {"sentiment": "NEUTRAL", "intensity": 0.5, "event": "Consolidation phase"},
    
    # Q3 - Été calme
    "2024-07": {"sentiment": "NEUTRAL", "intensity": 0.5, "event": "Summer consolidation"},
    "2024-08": {"sentiment": "POSITIVE", "intensity": 0.6, "event": "Altcoin season begins"},
    "2024-09": {"sentiment": "POSITIVE", "intensity": 0.7, "event": "DeFi resurgence"},
    
    # Q4 - Bull run fin d'année
    "2024-10": {"sentiment": "POSITIVE", "intensity": 0.8, "event": "Q4 bull momentum"},
    "2024-11": {"sentiment": "VERY_POSITIVE", "intensity": 0.9, "event": "New ATH attempts"},
    "2024-12": {"sentiment": "POSITIVE", "intensity": 0.8, "event": "Year-end rally"},
}

# Templates spécifiques 2024
NEWS_TEMPLATES_2024 = {
    "VERY_POSITIVE": [
        "🚀 {coin} surges {percent}% as {event}",
        "{coin} breaks ${price} resistance - {event} drives momentum",
        "Institutional FOMO: {coin} up {percent}% on {event}",
        "{coin} hits new 2024 high at ${price} amid {event}",
        "Bullish: {coin} gains {percent}% as {event} accelerates",
        "{event} propels {coin} to ${price}, analysts target higher",
    ],
    "POSITIVE": [
        "{coin} rallies {percent}% on {event} optimism",
        "{coin} breaks out: {event} boosts confidence",
        "Strong momentum: {coin} up {percent}% as {event}",
        "{coin} tests ${price} on {event} tailwinds",
        "Accumulation continues: {coin} rises {percent}% amid {event}",
    ],
    "NEUTRAL": [
        "{coin} consolidates around ${price} amid {event}",
        "{coin} holds gains despite {event} volatility",
        "Range-bound: {coin} stable at ${price} as {event}",
    ],
    "NEGATIVE": [
        "{coin} dips {percent}% on {event} concerns",
        "Profit-taking: {coin} down {percent}% despite {event}",
        "{coin} corrects from ${price} amid {event}",
    ]
}

def generate_crypto_news_2024():
    """
    Génère des news synthétiques pour 2024 (année bullish)
    """
    news_data = {}
    
    coins = {
        "BTC": {"name": "Bitcoin", "base_price": 45000},
        "ETH": {"name": "Ethereum", "base_price": 2800},
        "SOL": {"name": "Solana", "base_price": 110}
    }
    
    for month_key, month_data in CRYPTO_EVENTS_2024.items():
        year, month = map(int, month_key.split('-'))
        event = month_data["event"]
        base_sentiment = month_data["sentiment"]
        
        # Plus de news pour les mois importants
        news_frequency = 2 if month_data["intensity"] >= 0.8 else 3
        
        for day in range(1, 31, news_frequency):
            try:
                date = datetime(year, month, day)
            except ValueError:
                continue
                
            date_str = date.strftime('%Y-%m-%d')
            news_data[date_str] = []
            
            for coin_symbol, coin_info in coins.items():
                # Déterminer sentiment
                if base_sentiment == "VERY_POSITIVE":
                    sentiment = random.choice(["VERY_POSITIVE", "POSITIVE", "POSITIVE"])
                    templates = NEWS_TEMPLATES_2024["VERY_POSITIVE"]
                elif base_sentiment == "POSITIVE":
                    sentiment = random.choice(["POSITIVE", "POSITIVE", "NEUTRAL"])
                    templates = NEWS_TEMPLATES_2024["POSITIVE"]
                elif base_sentiment == "NEGATIVE":
                    sentiment = "NEGATIVE"
                    templates = NEWS_TEMPLATES_2024["NEGATIVE"]
                else:
                    sentiment = "NEUTRAL"
                    templates = NEWS_TEMPLATES_2024["NEUTRAL"]
                
                # Mapper pour format attendu
                mapped_sentiment = {
                    "VERY_POSITIVE": "POSITIVE",
                    "POSITIVE": "POSITIVE",
                    "NEUTRAL": "NEUTRAL",
                    "NEGATIVE": "NEGATIVE"
                }[sentiment]
                
                template = random.choice(templates)
                
                title = template.format(
                    coin=coin_info["name"],
                    percent=random.randint(3, 15) if "POSITIVE" in sentiment else random.randint(2, 8),
                    price=coin_info["base_price"] * random.uniform(0.9, 1.3),
                    event=event
                )
                
                news_item = {
                    "title": title,
                    "text": f"{title}. Market participants are {sentiment.lower()} about {coin_symbol} prospects.",
                    "source": random.choice(["CoinDesk", "CryptoQuant", "Bloomberg", "Decrypt", "CoinTelegraph"]),
                    "sentiment": mapped_sentiment,
                    "timestamp": date.timestamp(),
                    "published_at": date_str,
                    "coin": coin_symbol,
                    "event": event
                }
                
                news_data[date_str].append(news_item)
    
    return news_data


def save_news_archive_2024():
    """
    Sauvegarde le dataset 2024
    """
    print("🔧 Génération du dataset NEWS CRYPTO 2024 (BULL MARKET)...")
    print("   - Avril 2024: BITCOIN HALVING")
    print("   - Q4 2024: Bull momentum\n")
    
    news_data = generate_crypto_news_2024()
    
    archive_dir = "/Users/zakaria/Trading/data/news_archive"
    os.makedirs(archive_dir, exist_ok=True)
    
    output_path = os.path.join(archive_dir, "news_2024_synthetic.json")
    with open(output_path, 'w') as f:
        json.dump(news_data, f, indent=2)
    
    print(f"✅ Dataset 2024 généré: {output_path}")
    print(f"📊 {len(news_data)} jours de news")
    print(f"📰 {sum(len(v) for v in news_data.values())} articles au total")
    
    # Stats par événement
    print("\n📌 Événements majeurs couverts:")
    for month, data in CRYPTO_EVENTS_2024.items():
        print(f"   {month}: {data['event']}")
    
    return output_path


if __name__ == "__main__":
    save_news_archive_2024()
