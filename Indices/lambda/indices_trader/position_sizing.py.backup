"""
🏛️ POSITION SIZING MODULE - Empire V5.1 Compound Interest System
==================================================================
Calcul dynamique de la taille de position basé sur le capital actuel.

Au lieu d'allouer un montant fixe (ex: 400€), le bot lit le solde actuel
du compte avant chaque trade et calcule:
    Position_Size = (Capital_Actuel * Risk_Multiplier_du_Couloir) / Nombre_Actifs

Cela permet le "compound interest" - les gains s'additionnent et font boule de neige.

Usage:
    from position_sizing import calculate_position_size, get_account_balance
    
    # Option 1: Taille de position basée sur le capital DynamoDB
    position = calculate_position_size(
        symbol='GC=F',
        initial_capital=1000.0,
        dynamo_table='EmpireCommoditiesHistory'
    )
    
    # Option 2: Taille de position avec capital fourni
    position = calculate_position_size_from_capital(
        symbol='GC=F',
        current_capital=1250.0,  # Capital après gains
        num_assets=2
    )
"""

import logging
from typing import Optional, Dict
from decimal import Decimal

logger = logging.getLogger(__name__)

# Import du module micro_corridors pour le risk_multiplier
try:
    from micro_corridors import (
        get_corridor_params,
        get_adaptive_params,
        MarketRegime
    )
    MICRO_CORRIDORS_AVAILABLE = True
except ImportError:
    MICRO_CORRIDORS_AVAILABLE = False


# ==================== CONFIGURATION ====================

# Limites de sécurité
MIN_POSITION_SIZE = 10.0      # Minimum 10$ par position
MAX_POSITION_SIZE = 5000.0    # Maximum 5000$ par position
MAX_RISK_PER_TRADE = 0.02     # Maximum 2% du capital par trade

# Nombre d'actifs par asset class (pour la diversification)
ASSETS_PER_CLASS = {
    'Crypto': 3,        # BTC, ETH, SOL
    'Forex': 3,         # EURUSD, GBPUSD, USDJPY
    'Indices': 3,       # NDX, GSPC, DJI
    'Commodities': 2,   # Gold, Oil
}


# ==================== FONCTIONS DE CALCUL DU CAPITAL ====================

def get_account_balance(
    dynamo_table_name: str,
    initial_capital: float,
    asset_class: str = 'Unknown'
) -> Dict:
    """
    📊 Calcule le solde actuel du compte en lisant les PnL depuis DynamoDB.
    
    Args:
        dynamo_table_name: Nom de la table DynamoDB (ex: 'EmpireCommoditiesHistory')
        initial_capital: Capital initial investi
        asset_class: Classe d'actif pour le filtrage
        
    Returns:
        Dict avec:
        - current_capital: Capital actuel (initial + PnL)
        - total_pnl: Somme des PnL réalisés
        - open_exposure: Capital actuellement investi (positions ouvertes)
        - available_capital: Capital disponible pour nouveaux trades
        - win_rate: Taux de réussite
    """
    try:
        import boto3
        from boto3.dynamodb.conditions import Attr
        
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(dynamo_table_name)
        
        # Scanner toutes les transactions
        response = table.scan()
        items = response.get('Items', [])
        
        # Calculer les métriques
        total_pnl = 0.0
        open_exposure = 0.0
        winning_trades = 0
        losing_trades = 0
        
        for item in items:
            status = item.get('Status', '').upper()
            
            # Ignorer les logs SKIPPED
            if status == 'SKIPPED':
                continue
                
            if status == 'CLOSED':
                # Récupérer le PnL (peut être string ou Decimal)
                pnl_raw = item.get('PnL', 0)
                if isinstance(pnl_raw, Decimal):
                    pnl = float(pnl_raw)
                elif isinstance(pnl_raw, str):
                    try:
                        pnl = float(pnl_raw)
                    except ValueError:
                        pnl = 0.0
                else:
                    pnl = float(pnl_raw) if pnl_raw else 0.0
                
                total_pnl += pnl
                
                if pnl > 0:
                    winning_trades += 1
                elif pnl < 0:
                    losing_trades += 1
                    
            elif status == 'OPEN':
                # Additionner l'exposition ouverte
                cost_raw = item.get('Cost', item.get('Size', 0))
                if isinstance(cost_raw, Decimal):
                    cost = float(cost_raw)
                elif isinstance(cost_raw, str):
                    try:
                        cost = float(cost_raw)
                    except ValueError:
                        cost = 0.0
                else:
                    cost = float(cost_raw) if cost_raw else 0.0
                
                open_exposure += cost
        
        # Calculer le capital actuel
        current_capital = initial_capital + total_pnl
        available_capital = current_capital - open_exposure
        
        # Win rate
        total_closed = winning_trades + losing_trades
        win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0.0
        
        return {
            'current_capital': round(current_capital, 2),
            'total_pnl': round(total_pnl, 2),
            'open_exposure': round(open_exposure, 2),
            'available_capital': round(available_capital, 2),
            'win_rate': round(win_rate, 1),
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'initial_capital': initial_capital,
        }
        
    except Exception as e:
        logger.error(f"Erreur lecture DynamoDB: {e}")
        # Fallback: retourner le capital initial
        return {
            'current_capital': initial_capital,
            'total_pnl': 0.0,
            'open_exposure': 0.0,
            'available_capital': initial_capital,
            'win_rate': 0.0,
            'winning_trades': 0,
            'losing_trades': 0,
            'initial_capital': initial_capital,
            'error': str(e),
        }


# ==================== FONCTIONS DE POSITION SIZING ====================

def calculate_position_size_from_capital(
    symbol: str,
    current_capital: float,
    num_assets: int = 2,
    entry_price: float = None,
    stop_loss: float = None
) -> Dict:
    """
    💰 Calcule la taille de position basée sur le capital fourni.
    
    Formule: Position_Size = (Capital * Risk_Multiplier * Capital_Fraction) / Nombre_Actifs
    
    Args:
        symbol: Le symbole à trader (pour récupérer le risk_multiplier)
        current_capital: Capital actuel du compte
        num_assets: Nombre d'actifs dans cette classe
        entry_price: Prix d'entrée (optionnel, pour calcul de quantité)
        stop_loss: Stop loss (optionnel, pour calcul risk-based)
        
    Returns:
        Dict avec:
        - position_usd: Taille de position en USD
        - risk_multiplier: Multiplicateur du corridor
        - capital_fraction: Fraction du capital à utiliser
        - quantity: Quantité à acheter (si entry_price fourni)
        - max_loss_usd: Perte maximale (si SL fourni)
    """
    # Récupérer les paramètres adaptatifs du corridor
    if MICRO_CORRIDORS_AVAILABLE:
        params = get_adaptive_params(symbol)
        risk_multiplier = params.get('risk_multiplier', 1.0)
        aggressiveness = params.get('aggressiveness', 'MEDIUM')
        corridor_name = params.get('corridor_name', 'Default')
    else:
        risk_multiplier = 1.0
        aggressiveness = 'MEDIUM'
        corridor_name = 'Default'
    
    # Fraction du capital à utiliser selon l'agressivité
    if aggressiveness == 'HIGH':
        capital_fraction = 0.20     # 20% du capital par trade en mode agressif
    elif aggressiveness == 'MEDIUM':
        capital_fraction = 0.15     # 15% du capital en mode standard
    else:  # LOW
        capital_fraction = 0.10     # 10% en mode prudent
    
    # Calcul de base: répartition équitable entre les actifs
    base_position = (current_capital * capital_fraction) / num_assets
    
    # Appliquer le multiplicateur du corridor
    position_usd = base_position * risk_multiplier
    
    # Appliquer les limites de sécurité
    position_usd = max(MIN_POSITION_SIZE, min(position_usd, MAX_POSITION_SIZE))
    
    # Ne pas dépasser le capital disponible
    position_usd = min(position_usd, current_capital * 0.5)  # Max 50% du capital sur un trade
    
    result = {
        'position_usd': round(position_usd, 2),
        'risk_multiplier': risk_multiplier,
        'capital_fraction': capital_fraction,
        'aggressiveness': aggressiveness,
        'corridor_name': corridor_name,
        'current_capital': current_capital,
        'num_assets': num_assets,
    }
    
    # Calculer la quantité si entry_price fourni
    if entry_price and entry_price > 0:
        quantity = position_usd / entry_price
        result['quantity'] = round(quantity, 8)
    
    # Calculer la perte max si SL fourni
    if entry_price and stop_loss and entry_price > 0:
        sl_distance_pct = abs(entry_price - stop_loss) / entry_price
        max_loss_usd = position_usd * sl_distance_pct
        result['max_loss_usd'] = round(max_loss_usd, 2)
        result['max_loss_pct'] = round(sl_distance_pct * 100, 2)
    
    return result


def calculate_position_size(
    symbol: str,
    initial_capital: float,
    dynamo_table: str,
    asset_class: str = 'Unknown',
    entry_price: float = None,
    stop_loss: float = None
) -> Dict:
    """
    🎯 FONCTION PRINCIPALE - Position Sizing Cumulatif Complet
    
    Lit le capital actuel depuis DynamoDB et calcule la taille de position.
    C'est la fonction à utiliser dans les Lambda handlers.
    
    Args:
        symbol: Le symbole à trader
        initial_capital: Capital initial investi
        dynamo_table: Nom de la table DynamoDB
        asset_class: Classe d'actif (pour le nombre d'actifs)
        entry_price: Prix d'entrée (optionnel)
        stop_loss: Stop loss (optionnel)
        
    Returns:
        Dict combinant balance info + position sizing
    """
    # Récupérer le solde actuel
    balance = get_account_balance(dynamo_table, initial_capital, asset_class)
    
    # Nombre d'actifs pour cette classe
    num_assets = ASSETS_PER_CLASS.get(asset_class, 2)
    
    # Calculer la position avec le capital disponible
    position = calculate_position_size_from_capital(
        symbol=symbol,
        current_capital=balance['available_capital'],
        num_assets=num_assets,
        entry_price=entry_price,
        stop_loss=stop_loss
    )
    
    # Combiner les résultats
    return {
        **balance,
        **position,
        'asset_class': asset_class,
    }


# ==================== UTILITY FUNCTIONS ====================

def get_position_sizing_summary(position_info: Dict) -> str:
    """Génère un résumé lisible du position sizing"""
    
    summary = f"""
💰 POSITION SIZING SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Capital Initial: ${position_info.get('initial_capital', 0):,.2f}
Capital Actuel:  ${position_info.get('current_capital', 0):,.2f}
PnL Réalisé:     ${position_info.get('total_pnl', 0):,.2f}
Win Rate:        {position_info.get('win_rate', 0):.1f}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 POSITION CALCULÉE
Taille Position: ${position_info.get('position_usd', 0):,.2f}
Risk Multiplier: {position_info.get('risk_multiplier', 1.0):.1f}x
Corridor:        {position_info.get('corridor_name', 'N/A')}
Agressivité:     {position_info.get('aggressiveness', 'MEDIUM')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return summary.strip()


# ==================== TEST ====================

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🏛️ POSITION SIZING MODULE - TEST")
    print("=" * 60)
    
    # Test sans DynamoDB (calcul direct)
    test_symbols = ['^NDX', 'EURUSD', 'GC=F', 'SOL/USDT']
    test_capital = 1000.0
    
    print(f"\n📊 Test avec Capital = ${test_capital:,.2f}")
    print("-" * 60)
    
    for symbol in test_symbols:
        result = calculate_position_size_from_capital(
            symbol=symbol,
            current_capital=test_capital,
            num_assets=2,
            entry_price=100.0,
            stop_loss=97.0
        )
        
        print(f"\n{symbol}:")
        print(f"  Position: ${result['position_usd']:,.2f}")
        print(f"  Multiplier: {result['risk_multiplier']:.1f}x")
        print(f"  Aggressiveness: {result['aggressiveness']}")
        print(f"  Corridor: {result['corridor_name']}")
        if 'max_loss_usd' in result:
            print(f"  Max Loss: ${result['max_loss_usd']:.2f} ({result['max_loss_pct']:.1f}%)")
