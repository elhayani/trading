import json
import os
import boto3
from exchange_connector import ExchangeConnector
from config import TradingConfig
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_excess_positions():
    # 1. Get credentials
    region = 'eu-west-3'
    secretsmanager = boto3.client('secretsmanager', region_name=region)
    secret_name = 'trading/binance'
    
    response = secretsmanager.get_secret_value(SecretId=secret_name)
    secret = json.loads(response['SecretString'])
    api_key = secret.get('api_key') or secret.get('apiKey')
    api_secret = secret.get('api_secret') or secret.get('secret')
    
    # 2. Initialize Exchange
    exchange = ExchangeConnector(
        api_key=api_key,
        secret=api_secret,
        live_mode=False # Force Testnet as currently configured
    )
    
    # 3. Get Real Binance Positions
    from anti_spam_helpers import get_real_binance_positions
    real_symbols = get_real_binance_positions(exchange)
    
    logger.info(f"Detected {len(real_symbols)} positions on Binance: {real_symbols}")
    
    limit = 0
    if len(real_symbols) <= limit:
        logger.info("Count is already within limit. No action needed.")
        return

    to_close_count = len(real_symbols) - limit
    logger.info(f"Targeting {to_close_count} positions for closure to reach limit of {limit}")
    
    # Sort symbols by some criteria? Let's just take the last ones to keep the "Big" ones
    # Typically BTC, ETH, SOL are at the start of alphabet or important.
    # Let's keep: BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT, BNB/USDT:USDT
    favorites = []
    
    to_close = [s for s in real_symbols if s not in favorites]
    # If still more than to_close_count, slice it
    to_close = to_close[:to_close_count]
    
    logger.info(f"Symbols to close: {to_close}")
    
    for symbol in to_close:
        try:
            # Get detail to know side and quantity
            ccxt_ex = exchange.exchange
            positions = ccxt_ex.fapiPrivateV2GetPositionRisk()
            binance_sym = symbol.replace('/USDT:USDT', 'USDT').replace('/', '')
            
            detail = None
            for pos in positions:
                if pos.get('symbol') == binance_sym:
                    qty = abs(float(pos.get('positionAmt', 0)))
                    if qty > 0:
                        detail = {
                            'quantity': qty,
                            'side': 'LONG' if float(pos['positionAmt']) > 0 else 'SHORT'
                        }
                        break
            
            if detail:
                logger.info(f"Closing {symbol}: {detail['side']} {detail['quantity']}")
                close_side = 'sell' if detail['side'] == 'LONG' else 'buy'
                res = exchange.close_position(symbol, close_side, detail['quantity'])
                logger.info(f"Result for {symbol}: {res.get('status', 'unknown')}")
        except Exception as e:
            logger.error(f"Failed to close {symbol}: {e}")

if __name__ == "__main__":
    cleanup_excess_positions()
