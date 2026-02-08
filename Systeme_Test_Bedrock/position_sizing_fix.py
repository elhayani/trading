"""
FIX pour position_sizing.py - Calcul basé sur le risque
Ligne 252-254 à remplacer
"""

# ============================================================================
# AVANT (BUGUÉ) - Ligne 252-254
# ============================================================================
"""
# Calculer la quantité si entry_price fourni
if entry_price and entry_price > 0:
    quantity = position_usd / entry_price  # ❌ ERREUR - Pas basé sur le risque
    result['quantity'] = round(quantity, 8)
"""

# ============================================================================
# APRÈS (CORRIGÉ) - Risk-Based Position Sizing
# ============================================================================
CORRECT_CODE = """
# Calculer la quantité basée sur le RISQUE (stop loss)
if entry_price and entry_price > 0:
    if stop_loss and stop_loss > 0:
        # 🎯 RISK-BASED SIZING (la bonne méthode)
        # Risque = 2% du capital (configurable)
        risk_per_trade = 0.02  # 2%
        risk_amount_usd = current_capital * risk_per_trade

        # Distance du stop loss en prix absolu
        sl_distance = abs(entry_price - stop_loss)

        # Quantité = Montant à risquer / Distance du SL
        # Si SL = 5%, on met moins de capital
        # Si SL = 1%, on peut mettre plus de capital
        quantity = risk_amount_usd / sl_distance

        # Position notionnelle réelle
        actual_position_usd = quantity * entry_price

        result['quantity'] = round(quantity, 8)
        result['actual_position_usd'] = round(actual_position_usd, 2)
        result['risk_amount_usd'] = round(risk_amount_usd, 2)

        logger.info(f"💰 Risk-Based Sizing: {quantity:.4f} units @ ${entry_price:.2f} = ${actual_position_usd:.2f} (Risk: ${risk_amount_usd:.2f})")

    else:
        # Fallback si pas de stop loss (utiliser position_usd comme avant)
        quantity = position_usd / entry_price
        result['quantity'] = round(quantity, 8)
        logger.warning(f"⚠️ No SL provided, using fixed position sizing: {quantity:.4f} units")
"""

# ============================================================================
# EXEMPLE DE CALCUL
# ============================================================================
def example_calculation():
    print("="*80)
    print("📊 EXEMPLE: Différence entre les deux méthodes")
    print("="*80)

    # Paramètres
    current_capital = 20000
    entry_price = 6000
    stop_loss = 5700  # -5% SL

    print(f"\nParamètres:")
    print(f"  Capital: ${current_capital:,}")
    print(f"  Entry: ${entry_price}")
    print(f"  Stop Loss: ${stop_loss} (-5%)")
    print(f"  SL Distance: ${entry_price - stop_loss}")

    # MÉTHODE BUGUÉE (actuelle)
    print(f"\n❌ MÉTHODE ACTUELLE (BUGUÉE):")
    position_usd_fixed = 3000  # Position fixe
    quantity_old = position_usd_fixed / entry_price
    max_loss_old = quantity_old * (entry_price - stop_loss)
    risk_pct_old = (max_loss_old / current_capital) * 100

    print(f"  Position USD: ${position_usd_fixed}")
    print(f"  Quantité: {quantity_old:.4f} parts")
    print(f"  Position Notionnelle: ${quantity_old * entry_price:.2f}")
    print(f"  Perte Max (si SL hit): ${max_loss_old:.2f}")
    print(f"  Risque Réel: {risk_pct_old:.2f}% du capital ⚠️")

    # MÉTHODE CORRECTE (risk-based)
    print(f"\n✅ MÉTHODE CORRIGÉE (RISK-BASED):")
    risk_per_trade = 0.02  # 2%
    risk_amount = current_capital * risk_per_trade
    sl_distance = entry_price - stop_loss
    quantity_new = risk_amount / sl_distance
    position_usd_new = quantity_new * entry_price

    print(f"  Risque Voulu: 2% = ${risk_amount:.2f}")
    print(f"  Quantité: {quantity_new:.4f} parts")
    print(f"  Position Notionnelle: ${position_usd_new:.2f}")
    print(f"  Perte Max (si SL hit): ${risk_amount:.2f}")
    print(f"  Risque Réel: {risk_per_trade*100:.1f}% du capital ✅")

    print(f"\n📊 DIFFÉRENCE:")
    print(f"  Quantité: {quantity_old:.4f} → {quantity_new:.4f} ({(quantity_new/quantity_old - 1)*100:+.0f}%)")
    print(f"  Position: ${position_usd_fixed:.0f} → ${position_usd_new:.0f} ({(position_usd_new/position_usd_fixed - 1)*100:+.0f}%)")
    print(f"  Profits potentiels: x{position_usd_new/position_usd_fixed:.1f}")
    print("="*80)

if __name__ == "__main__":
    example_calculation()

    print("\n📝 INSTRUCTIONS D'APPLICATION:")
    print("="*80)
    print("1. Ouvrir: /Users/zakaria/Trading/Indices/lambda/indices_trader/position_sizing.py")
    print("2. Aller à la ligne 252-254")
    print("3. Remplacer par le code CORRECT ci-dessus")
    print("4. Sauvegarder")
    print("5. Relancer le backtest")
    print("="*80)
