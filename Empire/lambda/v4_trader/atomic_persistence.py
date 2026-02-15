"""
Atomic DynamoDB operations with conditional expressions.
Prevents race conditions in concurrent Lambda executions.
"""
import logging
from decimal import Decimal
from typing import Dict, Tuple
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class AtomicPersistence:
    """
    Provides atomic operations for risk management using DynamoDB conditional writes.
    """
    
    def __init__(self, state_table):
        """
        Args:
            state_table: boto3 DynamoDB Table resource
        """
        self.table = state_table
        
    def load_positions(self) -> Dict[str, Dict]:
        """
        🏛️ EMPIRE V16.3: Load positions from DynamoDB (Memory Memory)
        Source of Truth shared between Scanner and Closer.
        """
        try:
            # Query the GSI for OPEN positions
            response = self.table.query(
                IndexName='status-timestamp-index',
                KeyConditionExpression='#status = :open',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':open': 'OPEN'}
            )
            
            positions = {}
            for item in response.get('Items', []):
                # Robust Decimal to float conversion
                pos = self._from_decimal(item)
                # Use 'symbol' field as key, fallback to trader_id
                symbol = pos.get('symbol', pos.get('trader_id', '').replace('POSITION#', ''))
                if symbol:
                    positions[symbol] = pos
            
            logger.info(f"✅ Loaded {len(positions)} positions from Memory (DynamoDB)")
            return positions
            
        except Exception as e:
            logger.error(f"❌ Failed to load memory positions: {e}")
            return {}

    def _from_decimal(self, obj):
        """Recursively convert Decimal to float/int"""
        if isinstance(obj, list):
            return [self._from_decimal(i) for i in obj]
        elif isinstance(obj, dict):
            return {k: self._from_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, Decimal):
            return float(obj) if obj % 1 > 0 else int(obj)
        return obj
    
    def atomic_check_and_add_risk(
        self, 
        symbol: str, 
        risk_dollars: float, 
        capital: float,
        entry_price: float,
        quantity: float,
        direction: str,
        max_portfolio_pct: float = 0.20
    ) -> Tuple[bool, str]:
        """
        Atomically check portfolio risk cap and register trade.
        Uses DynamoDB conditional expression to prevent race conditions.
        """
        max_risk = Decimal(str(capital * max_portfolio_pct))
        new_risk = Decimal(str(risk_dollars))
        # Pre-calculate the threshold: if current total_risk <= this, it's safe to add
        risk_threshold = max_risk - new_risk
        
        # Prepare safe symbol for DynamoDB keys
        safe_symbol = symbol.replace('/', '_').replace(':', '-')
        
        try:
            # Prepare trade data
            trade_data = {
                'symbol': symbol,  # Keep original symbol for display
                'risk': new_risk,
                'entry_price': Decimal(str(entry_price)),
                'quantity': Decimal(str(quantity)),
                'direction': direction,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Ensure active_trades map exists first
            try:
                response = self.table.update_item(
                    Key={'trader_id': 'PORTFOLIO_RISK#GLOBAL'},
                    UpdateExpression='SET total_risk = if_not_exists(total_risk, :start) + :new_risk, last_updated = :ts, #active_trades = if_not_exists(#active_trades, :empty)',
                    ConditionExpression='attribute_not_exists(total_risk) OR (total_risk + :new_risk) <= :max_risk',
                    ExpressionAttributeNames={
                        '#active_trades': 'active_trades'
                    },
                    ExpressionAttributeValues={
                        ':start': 0,
                        ':new_risk': new_risk,
                        ':max_risk': max_risk,
                        ':ts': datetime.now(timezone.utc).isoformat(),
                        ':empty': {}
                    },
                    ReturnValues='ALL_NEW'
                )
                
                updated_risk = float(response['Attributes'].get('total_risk', 0))
                
                # Add to active trades map
                self.table.update_item(
                    Key={'trader_id': 'PORTFOLIO_RISK#GLOBAL'},
                    UpdateExpression='SET active_trades.#symbol = :trade_data',
                    ExpressionAttributeNames={
                        '#symbol': safe_symbol
                    },
                    ExpressionAttributeValues={
                        ':trade_data': trade_data
                    }
                )
                
                return True, f"Risk registered: ${risk_dollars:.2f} (Total: ${updated_risk:.2f})"
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                    return False, f"Risk limit exceeded. Attempted: ${risk_dollars:.2f}, Max: ${max_risk:.2f}"
                raise
        
        except Exception as e:
            logger.error(f"[ERROR] Unexpected error in atomic risk check: {e}")
            return False, f"UNEXPECTED_ERROR_{str(e)}"
    
    def atomic_remove_risk(self, symbol: str, risk_dollars: float) -> bool:
        """
        Atomically decrement portfolio risk when closing a trade.
        """
        # Prepare safe symbol for DynamoDB keys
        safe_symbol = symbol.replace('/', '_').replace(':', '-')
        
        try:
            self.table.update_item(
                Key={'trader_id': 'PORTFOLIO_RISK#GLOBAL'},
                UpdateExpression='''
                    SET total_risk = total_risk - :risk 
                    REMOVE active_trades.#sym
                ''',
                ExpressionAttributeNames={
                    '#sym': safe_symbol  # Use sanitized symbol for DynamoDB key
                },
                ExpressionAttributeValues={
                    ':risk': Decimal(str(risk_dollars))
                },
            )
            logger.info(f"[OK] Atomic risk removed: {symbol} ${risk_dollars:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to atomically remove risk for {symbol}: {e}")
            return False
    
    
