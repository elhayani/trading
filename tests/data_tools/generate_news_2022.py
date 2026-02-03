"""
Dataset synthétique de news crypto pour 2022
Basé sur les VRAIS événements majeurs de 2022: Terra/Luna, FTX, Bear Market
"""
import json
from datetime import datetime, timedelta
import os
import random

# Événements majeurs 2022
CRYPTO_EVENTS_2022 = {
    # Q1 - Début de la correction
    "2022-01": {"sentiment": "NEGATIVE", "intensity": 0.6, "event": "Fed tightening fears"},
    "2022-02": {"sentiment": "NEGATIVE", "intensity": 0.7, "event": "Russia-Ukraine war impact"},
    "2022-03": {"sentiment": "NEGATIVE", "intensity": 0.6, "event": "Market volatility"},
    
    # Q2 - CRASH TERRA LUNA (Mai 2022) - Événement MAJEUR
    "2022-04": {"sentiment": "NEGATIVE", "intensity": 0.7, "event": "Pre-crash concerns"},
    "2022-05": {"sentiment": "VERY_NEGATIVE", "intensity": 1.0, "event": "TERRA/LUNA COLLAPSE $40B"},
    "2022-06": {"sentiment": "VERY_NEGATIVE", "intensity": 0.9, "event": "Contagion effects, Celsius freeze"},
    
    # Q3 - Bear market profond
    "2022-07": {"sentiment": "NEGATIVE", "intensity": 0.8, "event": "3AC bankruptcy"},
    "2022-08": {"sentiment": "NEGATIVE", "intensity": 0.6, "event": "Bear market bottom forming"},
    "2022-09": {"sentiment": "NEGATIVE", "intensity": 0.7, "event": "Ethereum Merge anxiety"},
    
    # Q4 - CRASH FTX (Novembre 2022) - Événement CATASTROPHIQUE
    "2022-10": {"sentiment": "NEGATIVE", "intensity": 0.6, "event": "Market stabilization attempt"},
    "2022-11": {"sentiment": "CATASTROPHIC", "intensity": 1.0, "event": "FTX COLLAPSE $32B fraud"},
    "2022-12": {"sentiment": "VERY_NEGATIVE", "intensity": 0.9, "event": "Crypto winter, regulatory scrutiny"},
}

# Templates spécifiques aux événements de 2022
NEWS_TEMPLATES_2022 = {
    "VERY_NEGATIVE": [
        "{coin} plummets {percent}% as {event}",
        "BREAKING: {event} - {coin} loses ${value}B market cap",
        "{coin} crashes to ${price} amid {event} panic",
        "Massive liquidations: {coin} down {percent}%, {event}",
        "{coin} faces existential crisis as {event}",
        "Emergency: {event} triggers {coin} sell-off",
        "Contagion fears: {coin} down {percent}% post-{event}",
    ],
    "CATASTROPHIC": [
        "🚨 BREAKING: {event} - {coin} crashes {percent}%",
        "DISASTER: {event} wipes out ${value}B from {coin}",
        "{coin} in freefall: {percent}% crash as {event}",
        "EMERGENCY: {event} - {coin} trading halted on exchanges",
        "Bloodbath: {coin} down {percent}%, {event} triggers panic",
        "Market meltdown: {event} causes {coin} to plunge {percent}%",
    ],
    "NEGATIVE": [
        "{coin} drops {percent}% on {event} concerns",
        "{coin} under pressure as {event} weighs on market",
        "Bearish: {coin} slides {percent}% amid {event}",
        "{coin} tests support at ${price} as {event} continues",
        "Selling pressure: {coin} down {percent}% on {event}",
    ],
    "NEUTRAL": [
        "{coin} consolidates around ${price} despite {event}",
        "{coin} holds key levels despite {event} uncertainty",
        "Mixed signals: {coin} stable at ${price} amid {event}",
    ]
}

def generate_crypto_news_2022():
    """
    Génère des news synthétiques RÉALISTES pour 2022
    """
    news_data = {}
    
    coins = {
        "BTC": {"name": "Bitcoin", "base_price": 40000},
        "ETH": {"name": "Ethereum", "base_price": 2500},
        "SOL": {"name": "Solana", "base_price": 100}
    }
    
    for month_key, month_data in CRYPTO_EVENTS_2022.items():
        year, month = map(int, month_key.split('-'))
        event = month_data["event"]
        base_sentiment = month_data["sentiment"]
        
        # Plus de news pour les mois catastrophiques
        news_frequency = 2 if month_data["intensity"] >= 0.9 else 3
        
        for day in range(1, 31, news_frequency):
            try:
                date = datetime(year, month, day)
            except ValueError:
                continue
                
            date_str = date.strftime('%Y-%m-%d')
            news_data[date_str] = []
            
            for coin_symbol, coin_info in coins.items():
                # Ajuster le sentiment selon la gravité
                if base_sentiment == "CATASTROPHIC":
                    sentiment = random.choice(["CATASTROPHIC", "VERY_NEGATIVE"])
                    templates = NEWS_TEMPLATES_2022["CATASTROPHIC"]
                elif base_sentiment == "VERY_NEGATIVE":
                    sentiment = random.choice(["VERY_NEGATIVE", "NEGATIVE"])
                    templates = NEWS_TEMPLATES_2022["VERY_NEGATIVE"]
                elif base_sentiment == "NEGATIVE":
                    sentiment = "NEGATIVE"
                    templates = NEWS_TEMPLATES_2022["NEGATIVE"]
                else:
                    sentiment = "NEUTRAL"
                    templates = NEWS_TEMPLATES_2022["NEUTRAL"]
                
                # Mapper pour le format attendu
                mapped_sentiment = {
                    "CATASTROPHIC": "NEGATIVE",
                    "VERY_NEGATIVE": "NEGATIVE",
                    "NEGATIVE": "NEGATIVE",
                    "NEUTRAL": "NEUTRAL"
                }[sentiment]
                
                template = random.choice(templates)
                
                title = template.format(
                    coin=coin_info["name"],
                    percent=random.randint(10, 40) if "NEGATIVE" in sentiment else random.randint(2, 8),
                    value=random.randint(5, 50),
                    price=coin_info["base_price"] * random.uniform(0.5, 0.9),
                    event=event
                )
                
                news_item = {
                    "title": title,
                    "text": f"{title}. {event} has sent shockwaves through the {coin_symbol} market.",
                    "source": random.choice(["CoinDesk", "Bloomberg", "Reuters", "WSJ", "FT"]),
                    "sentiment": mapped_sentiment,
                    "timestamp": date.timestamp(),
                    "published_at": date_str,
                    "coin": coin_symbol,
                    "event": event
                }
                
                news_data[date_str].append(news_item)
    
    return news_data


def save_news_archive_2022():
    """
    Sauvegarde le dataset 2022
    """
    print("🔧 Génération du dataset NEWS CRYPTO 2022 (ÉVÉNEMENTS RÉELS)...")
    print("   - Mai 2022: TERRA/LUNA COLLAPSE")
    print("   - Novembre 2022: FTX COLLAPSE\n")
    
    news_data = generate_crypto_news_2022()
    
    archive_dir = "/Users/zakaria/Trading/data/news_archive"
    os.makedirs(archive_dir, exist_ok=True)
    
    output_path = os.path.join(archive_dir, "news_2022_synthetic.json")
    with open(output_path, 'w') as f:
        json.dump(news_data, f, indent=2)
    
    print(f"✅ Dataset 2022 généré: {output_path}")
    print(f"📊 {len(news_data)} jours de news")
    print(f"📰 {sum(len(v) for v in news_data.values())} articles au total")
    
    # Stats par événement
    print("\n📌 Événements majeurs couverts:")
    for month, data in CRYPTO_EVENTS_2022.items():
        print(f"   {month}: {data['event']}")
    
    return output_path


if __name__ == "__main__":
    save_news_archive_2022()
