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
        symbols_str = os.getenv('SYMBOLS', '')
        symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]
        
        engine = TradingEngine(
            capital=capital,
            symbols=symbols,
            mode=os.getenv('TRADING_MODE', 'dry_run')
        )
        
        # Load state
        engine.load_state()
        
        # Count existing positions (for logging only)
        existing_positions = len([
            p for p in engine.persistence.positions.values() 
            if p.get('status') == 'OPEN'
        ])
        
        logger.info(f"📊 Current State: {existing_positions} open positions")
        logger.info(f"💰 Capital: ${capital:.2f}")
        
        # ================================================================
        # CORE WORKFLOW: SCAN + OPEN ONLY
        # ================================================================
        
        # Step 1: Scan market
        logger.info(f"🔎 Scanning {len(symbols)} symbols...")
        scan_start = time.time()
        
        top_symbols = engine.scanner.scan(symbols, max_assets=15)
        
        scan_duration = time.time() - scan_start
        logger.info(f"✅ Scan complete in {scan_duration:.1f}s - {len(top_symbols)} candidates")
        
        # Step 2: Process each candidate (OPEN only)
        opened_count = 0
        skipped_count = 0
        
        for symbol in top_symbols:
            # Check if already have position
            if symbol in engine.persistence.positions:
                pos = engine.persistence.positions[symbol]
                if pos.get('status') == 'OPEN':
                    logger.info(f"⏭️  {symbol} - Already have open position, skipping")
                    continue
            
            # Check if in cooldown (anti-spam)
            from anti_spam_helpers import is_in_cooldown
            if is_in_cooldown(symbol, engine.persistence):
                logger.info(f"⏸️  {symbol} - In cooldown (5 min), skipping")
                skipped_count += 1
                continue
            
            # Attempt to open position
            try:
                result = engine._process_symbol_for_entry(symbol)
                
                if result and result.get('action') == 'OPENED':
                    opened_count += 1
                    logger.info(f"✅ {symbol} - Position OPENED")
                elif result and result.get('action') == 'SKIPPED':
                    skipped_count += 1
                    reason = result.get('reason', 'Unknown')
                    logger.info(f"⏭️  {symbol} - SKIPPED: {reason}")
                    
            except Exception as e:
                logger.error(f"❌ {symbol} - Error processing: {e}")
                skipped_count += 1
        
        # Step 3: Save state
        engine.save_state()
        
        # ================================================================
        # RESPONSE
        # ================================================================
        
        duration = time.time() - start_time
        
        response = {
            'lambda': 'SCANNER',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'duration_seconds': round(duration, 2),
            'scan_duration': round(scan_duration, 2),
            'candidates_found': len(top_symbols),
            'positions_opened': opened_count,
            'opportunities_skipped': skipped_count,
            'total_open_positions': existing_positions + opened_count,
            'symbols_scanned': len(symbols),
            'top_candidates': top_symbols[:5]
        }
        
        logger.info("=" * 80)
        logger.info(f"✅ LAMBDA 1 Complete: {opened_count} opened, {skipped_count} skipped")
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
