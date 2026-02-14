"""
Lambda 1: SCANNER / OPENER
==========================
Fréquence: 1 minute
Rôle: Scan market + Open positions UNIQUEMENT
Ne touche PAS aux positions ouvertes (géré par Lambda 2 et 3)
"""

import json
import os
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List

import boto3

# Imports from existing modules
from v4_hybrid_lambda import (
    AWSClients,
    TradingEngine,
    logger
)
from config import TradingConfig

def lambda_handler(event, context):
    """
    Lambda 1 Handler: Scanner + Opener
    
    Workflow:
    1. Load state from DynamoDB
    2. Scan market (50 assets)
    3. Filter elite setups (Gate 1: TA + Gate 2: Bedrock)
    4. OPEN positions if signals found
    5. Save state
    6. DO NOT check existing positions (Lambda 2/3 handle that)
    """
    
    start_time = time.time()
    logger.info("=" * 80)
    logger.info(f"🔍 LAMBDA 1 - SCANNER/OPENER Started")
    logger.info("=" * 80)
    
    try:
        # Initialize trading engine
        capital = float(os.getenv('CAPITAL', '1000'))
        engine = TradingEngine()
        
        # Récupérer TOUS les symboles disponibles de Binance Futures
        logger.info("🔍 Récupération de TOUS les symboles Binance Futures...")
        try:
            # Utiliser la même méthode que les scripts de téléchargement
            import requests
            response = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=10)
            response.raise_for_status()
            data = response.json()
            
            symbols = []
            for symbol_info in data['symbols']:
                if (symbol_info['status'] == 'TRADING' and 
                    symbol_info['contractType'] == 'PERPETUAL' and
                    symbol_info['quoteAsset'] == 'USDT'):
                    symbols.append(symbol_info['symbol'])
            
            logger.info(f"✅ Trouvé {len(symbols)} symboles Futures USDT actifs")
            
            # Limiter pour éviter timeout (configurable via env var)
            max_symbols = int(os.getenv('MAX_SYMBOLS_PER_SCAN', '100'))
            if len(symbols) > max_symbols:
                symbols = symbols[:max_symbols]
                logger.info(f"📊 Limité à {max_symbols} symboles pour éviter timeout")
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération symboles: {e}")
            # Fallback sur la liste par défaut
            symbols_str = os.getenv('SYMBOLS', 'BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT,XRP/USDT:USDT,BNB/USDT:USDT')
            symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]
            logger.info(f"🔄 Utilisation liste fallback: {len(symbols)} symboles")
        
        # Load state (Architecture 3-Lambda: RiskManager handles state)
        engine.risk_manager.load_state(engine.persistence.load_risk_state())
        
        # ================================================================
        # SYNC BIDIRECTIONNEL: Nettoyer les ghost trades
        # ================================================================
        logger.info("🔄 Starting bidirectional sync...")
        
        dynamo_positions = engine.persistence.load_positions()
        binance_positions = engine._get_real_binance_positions()
        
        ghost_cleaned = 0
        for symbol, pos_data in dynamo_positions.items():
            if symbol not in binance_positions:
                logger.warning(f"� GHOST DETECTED: {symbol} exists in DynamoDB but not on Binance - CLEANING")
                # Marquer comme GHOST et nettoyer
                engine.persistence.log_trade_close(
                    trade_id=pos_data.get('trade_id', f"POSITION#{symbol}"),
                    exit_price=pos_data.get('entry_price', 0),
                    pnl=0,
                    reason="GHOST_CLEANUP: Position not found on Binance"
                )
                # Supprimer de risk_manager
                engine.risk_manager.close_trade(symbol, pos_data.get('entry_price', 0))
                ghost_cleaned += 1
        
        # Sauvegarder l'état après nettoyage
        if ghost_cleaned > 0:
            engine.persistence.save_risk_state(engine.risk_manager.get_state())
            logger.info(f"💾 State saved after cleaning {ghost_cleaned} ghosts")
        
        existing_count = len(dynamo_positions) - ghost_cleaned
        logger.info(f"📊 Sync complete: {existing_count} real positions, {ghost_cleaned} ghosts cleaned")
        logger.info(f"💰 Capital: ${capital:.2f}")
        logger.info(f"� Max Trades Limit: {TradingConfig.MAX_OPEN_TRADES}")
        
        # ================================================================
        # CORE WORKFLOW: SCAN + OPEN ONLY
        # ================================================================
        
        # Step 1: Process TOUS les symboles disponibles
        logger.info(f"🔄 Processing TOUS les {len(symbols)} symboles disponibles...")
        scan_start = time.time()
        
        # Step 2: Process each symbol (OPEN only)
        opened_count = 0
        skipped_count = 0
        
        for symbol in symbols:
            # Attempt to open position - checks for limit, already open, and cooldown are now INSIDE engine
            try:
                result = engine.run_cycle(symbol)
                
                status = result.get('status', '')
                if 'OPEN' in status:
                    opened_count += 1
                    logger.info(f"✅ {symbol} - Position OPENED ({status})")
                elif 'SKIPPED' in status or 'BLOCKED' in status or 'NO_SIGNAL' in status:
                    skipped_count += 1
                    reason = result.get('reason', status)
                    logger.info(f"⏭️  {symbol} - SKIPPED: {reason}")
                    
            except Exception as e:
                logger.error(f"❌ {symbol} - Error processing: {e}")
                skipped_count += 1
        
        scan_duration = time.time() - scan_start
        logger.info(f"✅ Processing complete in {scan_duration:.1f}s - {len(symbols)} symbols")
        
        # Step 3: Save state
        engine.persistence.save_risk_state(engine.risk_manager.get_state())
        
        # ================================================================
        # RESPONSE
        # ================================================================
        
        duration = time.time() - start_time
        
        response = {
            'lambda': 'SCANNER',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'duration_seconds': round(duration, 2),
            'scan_duration': round(scan_duration, 2),
            'candidates_found': len(symbols),
            'positions_opened': opened_count,
            'opportunities_skipped': skipped_count,
            'total_open_positions': existing_count + opened_count,
            'symbols_scanned': len(symbols),
            'top_candidates': symbols[:5]
        }
        
        logger.info("=" * 80)
        logger.info(f"✅ LAMBDA 1 Complete: {opened_count} opened, {skipped_count} skipped")
        logger.info(f"📊 Processed: {len(symbols)} symbols total")
        logger.info(f"⏱️  Duration: {duration:.2f}s")
        logger.info("=" * 80)
        
        return {
            'statusCode': 200,
            'body': json.dumps(response)
        }
        
    except Exception as e:
        logger.error(f"❌ LAMBDA 1 FATAL ERROR: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'lambda': 'SCANNER'
            })
        }
