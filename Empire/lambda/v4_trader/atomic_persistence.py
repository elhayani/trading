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
        Load all open positions from DynamoDB using GSI with projection optimization.
        Returns: {symbol: position_data}
        """
        try:
            # Query using status-timestamp-index for OPEN positions with projection
            response = self.table.query(
                IndexName='status-timestamp-index',
                KeyConditionExpression='#status = :open',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':open': 'OPEN'},
                ProjectionExpression='trader_id, symbol, entry_price, quantity, direction, stop_loss, take_profit, leverage, timestamp'
            )
            
            positions = {}
            for item in response.get('Items', []):
                symbol = item['trader_id'].replace('POSITION#', '')
                positions[symbol] = item
            
            logger.info(f"✅ Loaded {len(positions)} open positions")
            return positions
            
        except ClientError as e:
            logger.error(f"❌ Failed to load positions: {e}")
            return {}
        
        except Exception as e:
            logger.warning(f"[WARN] GSI Query failed, falling back to scan: {e}")
            try:
                response = self.table.scan(
                    FilterExpression='begins_with(trader_id, :prefix)',
                    ExpressionAttributeValues={':prefix': 'POSITION#'}
                )
                return {item['trader_id'].replace('POSITION#', ''): item for item in response.get('Items', [])}
            except Exception as e2:
                logger.error(f"[ERROR] Failed to load positions (Scan): {e2}")
                return {}
    
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
