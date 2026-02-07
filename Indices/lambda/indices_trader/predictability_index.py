"""
🏛️ PREDICTABILITY INDEX MODULE - Empire V5.1 Anti-Erratic Shield
=================================================================
Calcule l'indice de prédictibilité technique d'un actif.
Détecte automatiquement les actifs erratiques/manipulés.

L'indice est basé sur 3 métriques:
1. AUTOCORRELATION - Les rendements suivent-ils un pattern ?
2. R² (Trend Fit) - Le prix suit-il sa tendance (régression linéaire) ?
3. WICK RATIO - Y a-t-il beaucoup de mèches erratiques ?

Usage:
    from predictability_index import (
        calculate_predictability_score,
        is_asset_erratic,
        get_predictability_adjustment
    )
    
    # Dans la stratégie
    score = calculate_predictability_score(df)
    if is_asset_erratic(df):
        logger.warning(f"⚠️ {symbol} - Asset erratique, QUARANTINE")
        return None  # Skip ce trade
    
    # Ou ajuster les paramètres automatiquement
    adjustments = get_predictability_adjustment(df)
    volume_filter = base_volume_filter * adjustments['volume_multiplier']
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional
import warnings

# ==================== CONFIGURATION ====================

# Seuils de prédictibilité (sur 100)
PREDICTABILITY_THRESHOLDS = {
    'EXCELLENT': 80,      # Asset ultra propre (NASDAQ, EURUSD)
    'GOOD': 60,           # Asset fiable
    'MODERATE': 40,       # Asset moyen - prudence
    'POOR': 25,           # Asset erratique - filtres stricts
    'ERRATIC': 0,         # Asset toxique - QUARANTINE
}

# Poids de chaque métrique dans le score final
METRIC_WEIGHTS = {
    'autocorrelation': 0.35,  # L'autocorr est un bon indicateur de tendance
    'trend_fit': 0.40,        # R² est le meilleur indicateur de suivi de tendance
    'wick_ratio': 0.25,       # Les mèches indiquent la manipulation
}

# Fenêtres d'analyse
LOOKBACK_PERIODS = {
    'short': 20,    # Court terme (dernières 20 bougies)
    'medium': 50,   # Moyen terme
    'long': 100,    # Long terme
}


# ==================== MÉTRIQUES INDIVIDUELLES ====================

def calculate_autocorrelation(returns: pd.Series, lag: int = 1) -> float:
    """
    Calcule l'autocorrélation des rendements.
    
    L'autocorrélation mesure si les mouvements de prix dans une direction
    tendent à être suivis par d'autres mouvements dans la même direction.
    
    - Autocorr haute (>0.3): Tendance persistante = PRÉDICTIBLE
    - Autocorr basse (<0.1): Bruit aléatoire = ERRATIQUE
    
    Returns:
        float: Valeur entre 0 et 1 (normalisée)
    """
    if len(returns) < lag + 10:
        return 0.5  # Pas assez de données
    
    try:
        # Calculer l'autocorrélation avec le lag spécifié
        autocorr = returns.autocorr(lag=lag)
        
        if pd.isna(autocorr):
            return 0.5
        
        # Nous voulons une autocorrélation positive (trend following)
        # Normaliser entre 0 et 1
        # autocorr est entre -1 et 1, on le mappe sur 0-1
        normalized = (autocorr + 1) / 2
        
        # Boost légèrement les valeurs positives (on veut des trends)
        if autocorr > 0:
            normalized = min(1.0, normalized * 1.2)
        
        return max(0, min(1, normalized))
        
    except Exception:
        return 0.5


def calculate_trend_fit(prices: pd.Series) -> float:
    """
    Calcule le coefficient de détermination R².
    
    R² mesure à quel point le prix suit une régression linéaire.
    - R² élevé (>0.7): Le prix suit une tendance claire = PRÉDICTIBLE
    - R² faible (<0.3): Le prix oscille de manière erratique = IMPRÉVISIBLE
    
    Returns:
        float: Valeur entre 0 et 1 (R²)
    """
    if len(prices) < 10:
        return 0.5  # Pas assez de données
    
    try:
        # Créer l'axe temporel (0, 1, 2, ... n)
        x = np.arange(len(prices))
        y = prices.values
        
        # Vérifier les NaN
        mask = ~np.isnan(y)
        if np.sum(mask) < 10:
            return 0.5
        
        x_clean = x[mask]
        y_clean = y[mask]
        
        # Régression linéaire
        coeffs = np.polyfit(x_clean, y_clean, 1)
        y_pred = np.polyval(coeffs, x_clean)
        
        # Calcul du R²
        ss_res = np.sum((y_clean - y_pred) ** 2)
        ss_tot = np.sum((y_clean - np.mean(y_clean)) ** 2)
        
        if ss_tot == 0:
            return 1.0  # Prix constant = parfaitement prédictible (edge case)
        
        r_squared = 1 - (ss_res / ss_tot)
        
        return max(0, min(1, r_squared))
        
    except Exception:
        return 0.5


def calculate_wick_ratio(df: pd.DataFrame) -> float:
    """
    Calcule le ratio de mèches (wicks) par rapport au corps des bougies.
    
    Les mèches importantes indiquent:
    - Manipulation de prix
    - Faux breakouts
    - Volatilité erratique
    
    Un ratio de mèches élevé = asset imprévisible
    
    Returns:
        float: Score entre 0 et 1 (1 = propre, 0 = plein de mèches)
    """
    required_cols = ['Open', 'High', 'Low', 'Close']
    if not all(col in df.columns for col in required_cols):
        # Essayer avec des colonnes en minuscules
        df_cols = {col.capitalize(): col for col in df.columns}
        if not all(col in df_cols for col in ['Open', 'High', 'Low', 'Close']):
            return 0.5  # Données manquantes
    
    try:
        # Normaliser les noms de colonnes
        if 'open' in df.columns:
            opens = df['open']
            highs = df['high']
            lows = df['low']
            closes = df['close']
        else:
            opens = df['Open']
            highs = df['High']
            lows = df['Low']
            closes = df['Close']
        
        # Corps de la bougie (body)
        bodies = np.abs(closes - opens)
        
        # Taille totale de la bougie (high - low)
        total_ranges = highs - lows
        
        # Éviter division par zéro
        total_ranges = total_ranges.replace(0, np.nan)
        
        # Ratio corps/total (1 = pas de mèche, 0 = que des mèches)
        body_ratios = bodies / total_ranges
        
        # Moyenne du ratio (plus c'est haut, moins il y a de mèches)
        avg_body_ratio = body_ratios.mean()
        
        if pd.isna(avg_body_ratio):
            return 0.5
        
        return max(0, min(1, avg_body_ratio))
        
    except Exception:
        return 0.5


# ==================== SCORE GLOBAL ====================

def calculate_predictability_score(
    df: pd.DataFrame,
    lookback: int = None,
    weights: Dict[str, float] = None
) -> Dict:
    """
    🎯 FONCTION PRINCIPALE
    Calcule le score de prédictibilité global (0-100).
    
    Args:
        df: DataFrame avec colonnes OHLCV
        lookback: Nombre de bougies à analyser (défaut: 50)
        weights: Poids personnalisés des métriques
    
    Returns:
        dict avec:
        - score: Score global 0-100
        - grade: 'EXCELLENT', 'GOOD', 'MODERATE', 'POOR', 'ERRATIC'
        - metrics: Détail de chaque métrique
        - recommendation: Action suggérée
    """
    lookback = lookback or LOOKBACK_PERIODS['medium']
    weights = weights or METRIC_WEIGHTS
    
    # Utiliser seulement les N dernières bougies
    if len(df) > lookback:
        df_slice = df.tail(lookback).copy()
    else:
        df_slice = df.copy()
    
    if len(df_slice) < 15:
        return {
            'score': 50,
            'grade': 'MODERATE',
            'metrics': {},
            'recommendation': '⚠️ Données insuffisantes - Mode prudent',
            'is_erratic': False,
        }
    
    # Calculer les rendements
    close_col = 'Close' if 'Close' in df_slice.columns else 'close'
    if close_col not in df_slice.columns:
        return {
            'score': 50,
            'grade': 'MODERATE',
            'metrics': {},
            'recommendation': '⚠️ Pas de colonne Close - Mode prudent',
            'is_erratic': False,
        }
    
    prices = df_slice[close_col].dropna()
    returns = prices.pct_change().dropna()
    
    # Calculer chaque métrique
    metrics = {
        'autocorrelation': calculate_autocorrelation(returns),
        'trend_fit': calculate_trend_fit(prices),
        'wick_ratio': calculate_wick_ratio(df_slice),
    }
    
    # Score pondéré (sur 100)
    weighted_score = sum(
        metrics[key] * weights.get(key, 0.33) * 100
        for key in metrics
    )
    
    score = round(weighted_score, 1)
    
    # Déterminer le grade
    grade = 'ERRATIC'
    for grade_name, threshold in PREDICTABILITY_THRESHOLDS.items():
        if score >= threshold:
            grade = grade_name
            break
    
    # Recommandation basée sur le grade
    recommendations = {
        'EXCELLENT': '🏛️ Asset parfait - Stratégie normale',
        'GOOD': '✅ Asset fiable - Stratégie normale',
        'MODERATE': '⚠️ Asset moyen - Filtres légèrement augmentés',
        'POOR': '🛑 Asset erratique - Volume filter x1.5, position réduite',
        'ERRATIC': '🚫 QUARANTINE - Ne pas trader cet asset!',
    }
    
    return {
        'score': score,
        'grade': grade,
        'metrics': {
            'autocorrelation': round(metrics['autocorrelation'] * 100, 1),
            'trend_fit': round(metrics['trend_fit'] * 100, 1),
            'wick_ratio': round(metrics['wick_ratio'] * 100, 1),
        },
        'recommendation': recommendations.get(grade, ''),
        'is_erratic': grade in ['POOR', 'ERRATIC'],
    }


def calculate_predictability_change(
    df: pd.DataFrame,
    short_period: int = 20,
    long_period: int = 100
) -> Dict:
    """
    Détecte si un actif devient plus ou moins prédictible.
    Utile pour détecter les changements de régime en temps réel.
    
    Returns:
        dict avec:
        - short_score: Score sur les 20 dernières bougies
        - long_score: Score sur les 100 dernières bougies
        - trend: 'IMPROVING', 'STABLE', 'DEGRADING'
        - delta: Différence entre short et long
    """
    if len(df) < long_period:
        return {
            'short_score': 50,
            'long_score': 50,
            'trend': 'UNKNOWN',
            'delta': 0,
        }
    
    short_result = calculate_predictability_score(df, lookback=short_period)
    long_result = calculate_predictability_score(df, lookback=long_period)
    
    delta = short_result['score'] - long_result['score']
    
    if delta > 10:
        trend = 'IMPROVING'
    elif delta < -10:
        trend = 'DEGRADING'
    else:
        trend = 'STABLE'
    
    return {
        'short_score': short_result['score'],
        'long_score': long_result['score'],
        'trend': trend,
        'delta': round(delta, 1),
    }


# ==================== FONCTIONS D'ACTION ====================

def is_asset_erratic(df: pd.DataFrame, threshold: int = 30) -> bool:
    """
    🛑 VETO SIMPLE
    Retourne True si l'asset est trop erratique pour être tradé.
    
    Args:
        df: DataFrame OHLCV
        threshold: Score en dessous duquel l'asset est considéré erratique
    
    Returns:
        bool: True = Ne pas trader, False = OK
    """
    result = calculate_predictability_score(df)
    return result['score'] < threshold


def get_predictability_adjustment(
    df: pd.DataFrame,
    base_params: Dict = None
) -> Dict:
    """
    🎯 FONCTION D'AJUSTEMENT AUTOMATIQUE
    Retourne les multiplicateurs à appliquer selon la prédictibilité.
    
    Plus l'asset est erratique, plus les filtres sont stricts.
    
    Returns:
        dict avec:
        - volume_multiplier: Multiplier le filtre de volume
        - position_multiplier: Réduire la taille de position
        - rsi_adjustment: Ajuster le seuil RSI
        - should_trade: False si l'asset est en quarantine
    """
    result = calculate_predictability_score(df)
    score = result['score']
    grade = result['grade']
    
    # Ajustements par grade
    adjustments = {
        'EXCELLENT': {
            'volume_multiplier': 0.9,    # Moins strict sur le volume
            'position_multiplier': 1.2,  # Position légèrement plus grosse
            'rsi_adjustment': 5,         # RSI peut être plus haut
            'tp_multiplier': 1.0,        # TP normal
            'sl_multiplier': 1.0,        # SL normal
            'should_trade': True,
        },
        'GOOD': {
            'volume_multiplier': 1.0,
            'position_multiplier': 1.0,
            'rsi_adjustment': 0,
            'tp_multiplier': 1.0,
            'sl_multiplier': 1.0,
            'should_trade': True,
        },
        'MODERATE': {
            'volume_multiplier': 1.2,    # Légèrement plus strict
            'position_multiplier': 0.9,
            'rsi_adjustment': -3,        # RSI plus bas exigé
            'tp_multiplier': 0.8,        # TP plus court (sortir vite)
            'sl_multiplier': 0.9,        # SL légèrement plus serré
            'should_trade': True,
        },
        'POOR': {
            'volume_multiplier': 1.5,    # Beaucoup plus strict
            'position_multiplier': 0.5,  # Demi-position
            'rsi_adjustment': -10,       # RSI très bas exigé
            'tp_multiplier': 0.6,        # TP très court
            'sl_multiplier': 0.7,        # SL serré
            'should_trade': True,        # Autorisé mais avec prudence
        },
        'ERRATIC': {
            'volume_multiplier': 2.0,
            'position_multiplier': 0.0,  # Pas de position!
            'rsi_adjustment': -20,
            'tp_multiplier': 0.5,
            'sl_multiplier': 0.5,
            'should_trade': False,       # 🚫 QUARANTINE
        },
    }
    
    adj = adjustments.get(grade, adjustments['MODERATE'])
    
    return {
        **adj,
        'score': score,
        'grade': grade,
        'recommendation': result['recommendation'],
    }


def calculate_symbol_health(symbol: str, df: pd.DataFrame) -> Dict:
    """
    🏥 BILAN DE SANTÉ D'UN ACTIF
    Fonction de diagnostic complète pour le dashboard.
    
    Returns:
        dict complet avec toutes les métriques et recommandations
    """
    pred_result = calculate_predictability_score(df)
    change_result = calculate_predictability_change(df)
    adj_result = get_predictability_adjustment(df)
    
    # Calculer la volatilité réalisée
    close_col = 'Close' if 'Close' in df.columns else 'close'
    if close_col in df.columns:
        returns = df[close_col].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252) * 100  # Annualisée en %
    else:
        volatility = 0
    
    # Assembler le rapport
    health_report = {
        'symbol': symbol,
        'predictability': {
            'score': pred_result['score'],
            'grade': pred_result['grade'],
            'metrics': pred_result['metrics'],
        },
        'trend': {
            'short_score': change_result['short_score'],
            'long_score': change_result['long_score'],
            'direction': change_result['trend'],
            'delta': change_result['delta'],
        },
        'volatility': round(volatility, 2),
        'adjustments': {
            'volume_multiplier': adj_result['volume_multiplier'],
            'position_multiplier': adj_result['position_multiplier'],
            'rsi_adjustment': adj_result['rsi_adjustment'],
        },
        'tradeable': adj_result['should_trade'],
        'recommendation': adj_result['recommendation'],
    }
    
    # Ajouter un emoji de statut
    status_emoji = {
        'EXCELLENT': '🏛️',
        'GOOD': '✅',
        'MODERATE': '⚠️',
        'POOR': '🛑',
        'ERRATIC': '🚫',
    }
    health_report['status_emoji'] = status_emoji.get(pred_result['grade'], '❓')
    
    return health_report


# ==================== TEST (si exécuté directement) ====================

if __name__ == '__main__':
    print("=" * 60)
    print("🏛️ PREDICTABILITY INDEX - Test Module")
    print("=" * 60)
    
    # Générer des données de test
    np.random.seed(42)
    
    # Asset propre (tendance claire)
    clean_prices = 100 + np.cumsum(np.random.randn(100) * 0.5 + 0.1)
    clean_df = pd.DataFrame({
        'Open': clean_prices - 0.3,
        'High': clean_prices + 0.5,
        'Low': clean_prices - 0.5,
        'Close': clean_prices,
    })
    
    # Asset erratique (beaucoup de bruit)
    noisy_prices = 100 + np.cumsum(np.random.randn(100) * 3)
    noisy_df = pd.DataFrame({
        'Open': noisy_prices,
        'High': noisy_prices + np.random.rand(100) * 5,  # Grandes mèches
        'Low': noisy_prices - np.random.rand(100) * 5,
        'Close': noisy_prices + np.random.randn(100) * 2,
    })
    
    print("\n📊 Test Asset PROPRE (tendance haussière claire):")
    print("-" * 50)
    result = calculate_predictability_score(clean_df)
    print(f"Score: {result['score']}/100 - Grade: {result['grade']}")
    print(f"Metrics: {result['metrics']}")
    print(f"Recommendation: {result['recommendation']}")
    
    print("\n📊 Test Asset ERRATIQUE (bruit + grandes mèches):")
    print("-" * 50)
    result = calculate_predictability_score(noisy_df)
    print(f"Score: {result['score']}/100 - Grade: {result['grade']}")
    print(f"Metrics: {result['metrics']}")
    print(f"Recommendation: {result['recommendation']}")
    
    print("\n🔧 Ajustements pour l'asset erratique:")
    print("-" * 50)
    adj = get_predictability_adjustment(noisy_df)
    print(f"Volume Filter: x{adj['volume_multiplier']}")
    print(f"Position Size: x{adj['position_multiplier']}")
    print(f"RSI Adjustment: {adj['rsi_adjustment']}")
    print(f"Should Trade: {adj['should_trade']}")
    
    print("\n🏥 Bilan de santé complet:")
    print("-" * 50)
    health = calculate_symbol_health('TEST', noisy_df)
    print(f"Status: {health['status_emoji']} {health['predictability']['grade']}")
    print(f"Trend: {health['trend']['direction']} (Δ{health['trend']['delta']})")
    print(f"Volatility: {health['volatility']}%")
    print(f"Tradeable: {health['tradeable']}")
