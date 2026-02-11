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
        
        try:
            # Prepare trade data
            trade_data = {
                'symbol': symbol,
                'risk': new_risk,
                'entry_price': Decimal(str(entry_price)),
                'quantity': Decimal(str(quantity)),
                'direction': direction,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # Atomic increment with condition
            response = self.table.update_item(
                Key={'trader_id': 'PORTFOLIO_RISK#GLOBAL'},
                UpdateExpression='''
                    SET total_risk = if_not_exists(total_risk, :zero) + :new_risk,
                        active_trades.#sym = :trade_data,
                        last_updated = :timestamp
                ''',
                ConditionExpression='''
                    attribute_not_exists(total_risk) OR 
                    (total_risk + :new_risk) <= :max_risk
                ''',
                ExpressionAttributeNames={
                    '#sym': symbol.replace('/', '_') # Standardize key for map
                },
                ExpressionAttributeValues={
                    ':zero': Decimal('0'),
                    ':new_risk': new_risk,
                    ':max_risk': max_risk,
                    ':trade_data': trade_data,
                    ':timestamp': datetime.now(timezone.utc).isoformat()
                },
                ReturnValues='UPDATED_NEW'
            )
            
            new_total = float(response['Attributes']['total_risk'])
            logger.info(f"[OK] Atomic risk registered: {symbol} ${risk_dollars:.2f} -> Portfolio Total: ${new_total:.2f}")
            return True, "OK"
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'ConditionalCheckFailedException':
                logger.error(f"[ALERT] Portfolio risk cap would be exceeded. Trade {symbol} blocked atomically.")
                return False, "PORTFOLIO_RISK_CAP_EXCEEDED"
            else:
                logger.error(f"[ERROR] DynamoDB atomic operation failed: {e}")
                return False, f"DYNAMODB_ERROR_{error_code}"
        
        except Exception as e:
            logger.error(f"[ERROR] Unexpected error in atomic risk check: {e}")
            return False, f"UNEXPECTED_ERROR_{str(e)}"
    
    def atomic_remove_risk(self, symbol: str, risk_dollars: float) -> bool:
        """
        Atomically decrement portfolio risk when closing a trade.
        """
        try:
            self.table.update_item(
                Key={'trader_id': 'PORTFOLIO_RISK#GLOBAL'},
                UpdateExpression='''
                    SET total_risk = total_risk - :risk 
                    REMOVE active_trades.#sym
                ''',
                ExpressionAttributeNames={
                    '#sym': symbol.replace('/', '_')
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
    
    def get_portfolio_risk_snapshot(self) -> Dict:
        """
        Get current portfolio risk state (non-atomic read).
        """
        try:
            response = self.table.get_item(Key={'trader_id': 'PORTFOLIO_RISK#GLOBAL'})
            item = response.get('Item', {})
            
            return {
                'total_risk': float(item.get('total_risk', 0)),
                'active_trades': item.get('active_trades', {}),
                'last_updated': item.get('last_updated', 'Never')
            }
        except Exception as e:
            logger.error(f"[ERROR] Failed to get portfolio snapshot: {e}")
            return {'total_risk': 0, 'active_trades': {}, 'last_updated': 'Error'}
