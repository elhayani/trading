"""
Trim & Switch Strategy - Dynamic Capital Reallocation
Allows bot to reduce profitable positions to free capital for better opportunities
"""
import logging
from typing import Dict, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def evaluate_trim_and_switch(
    exchange,
    persistence,
    positions: Dict,
    new_symbol: str,
    new_decision: Dict,
    current_balance: float
) -> Dict:
    """
    Evaluate if we should trim existing positions to free capital for a better opportunity.
    
    Strategy:
    1. Find profitable positions (PnL > 0.3%)
    2. Compare new opportunity confidence vs existing positions
    3. If new opportunity is significantly better (confidence +0.15), trim 50% of weakest position
    4. Free capital for new trade
    
    Args:
        exchange: Exchange connector
        persistence: Persistence layer
        positions: Current open positions
        new_symbol: Symbol of new opportunity
        new_decision: Decision dict with confidence for new opportunity
        current_balance: Current available balance
    
    Returns:
        Dict with action ('TRIMMED' or 'NO_ACTION') and freed_capital
    """
    try:
        new_confidence = new_decision.get('confidence', 0.0)
        
        # Minimum confidence threshold for trim & switch
        if new_confidence < 0.75:
            logger.info(f"[TRIM_SKIP] New opportunity confidence too low ({new_confidence:.2f})")
            return {'action': 'NO_ACTION', 'freed_capital': current_balance}
        
        # Evaluate existing positions
        position_scores = []
        for symbol, pos in positions.items():
            try:
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                entry_price = float(pos.get('entry_price', 0))
                direction = pos['direction']
                quantity = float(pos.get('quantity', 0))
                
                # Calculate PnL %
                if direction == 'LONG':
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100
                else:
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100
                
                # Consider both profitable AND losing positions for trimming
                # Profitable: trim to secure gains
                # Losing (but not hit SL yet): cut loss if better opportunity appears
                if pnl_pct > 0.3 or (pnl_pct < 0 and pnl_pct > -0.5):  # Profit OR small loss
                    position_value = quantity * current_price
                    
                    # Estimate "remaining potential" (inverse of PnL - higher PnL = less potential)
                    # A position at +0.5% has less potential than one at +0.1%
                    remaining_potential = max(0, 1.0 - (pnl_pct / 100))
                    
                    position_scores.append({
                        'symbol': symbol,
                        'pnl_pct': pnl_pct,
                        'position_value': position_value,
                        'remaining_potential': remaining_potential,
                        'direction': direction,
                        'quantity': quantity,
                        'current_price': current_price
                    })
                    
            except Exception as e:
                logger.warning(f"[TRIM_ERROR] Failed to evaluate {symbol}: {e}")
                continue
        
        if not position_scores:
            logger.info("[TRIM_SKIP] No profitable positions to trim")
            return {'action': 'NO_ACTION', 'freed_capital': current_balance}
        
        # Sort by remaining potential (lowest first = best to trim)
        # For losing positions, prioritize cutting the biggest loser
        position_scores.sort(key=lambda x: (x['pnl_pct'] if x['pnl_pct'] < 0 else -x['remaining_potential']))
        
        # Trim the position with lowest remaining potential (or biggest loss)
        to_trim = position_scores[0]
        
        # Different thresholds for profitable vs losing positions
        if to_trim['pnl_pct'] < 0:
            # For losing positions: more aggressive, only need 10% better confidence
            confidence_delta = new_confidence - 0.5  # Losing position has low confidence (0.5)
            min_delta = 0.10
            logger.info(f"[CUT_LOSS_CHECK] Position {to_trim['symbol']} at {to_trim['pnl_pct']:.2f}%, evaluating cut...")
        else:
            # For profitable positions: conservative, need 15% better confidence
            confidence_delta = new_confidence - to_trim['remaining_potential']
            min_delta = 0.15
        
        if confidence_delta < min_delta:
            logger.info(f"[TRIM_SKIP] New opportunity not significantly better (delta: {confidence_delta:.2f}, need: {min_delta})")
            return {'action': 'NO_ACTION', 'freed_capital': current_balance}
        
        # Trim 50% of the position
        trim_symbol = to_trim['symbol']
        trim_quantity = to_trim['quantity'] * 0.5
        trim_side = 'sell' if to_trim['direction'] == 'LONG' else 'buy'
        
        action_type = "CUT_LOSS" if to_trim['pnl_pct'] < 0 else "TRIM_PROFIT"
        logger.warning(f"[{action_type}] Trimming 50% of {trim_symbol} (PnL: {to_trim['pnl_pct']:+.2f}%) for {new_symbol} opportunity")
        
        # Execute trim order
        try:
            trim_order = exchange.create_market_order(trim_symbol, trim_side, trim_quantity)
            freed_value = trim_quantity * to_trim['current_price']
            
            logger.info(f"[TRIM_SUCCESS] Freed ${freed_value:.0f} from {trim_symbol}")
            
            # Update position in DynamoDB (reduce quantity by 50%)
            pos_data = positions[trim_symbol]
            pos_data['quantity'] = to_trim['quantity'] * 0.5
            persistence.save_position(trim_symbol, pos_data)
            
            # Log the trim action
            persistence.log_trade_close(
                trade_id=pos_data.get('trade_id', 'TRIM'),
                symbol=trim_symbol,
                exit_price=to_trim['current_price'],
                pnl=(to_trim['pnl_pct'] / 100) * freed_value,
                reason=f"TRIM_50% for {new_symbol} opportunity (conf: {new_confidence:.2f})"
            )
            
            return {
                'action': 'TRIMMED',
                'freed_capital': current_balance + freed_value,
                'trimmed_symbol': trim_symbol,
                'trimmed_amount': freed_value
            }
            
        except Exception as e:
            logger.error(f"[TRIM_FAILED] Failed to execute trim order: {e}")
            return {'action': 'NO_ACTION', 'freed_capital': current_balance}
        
    except Exception as e:
        logger.error(f"[TRIM_ERROR] Trim & Switch evaluation failed: {e}")
        return {'action': 'NO_ACTION', 'freed_capital': current_balance}
