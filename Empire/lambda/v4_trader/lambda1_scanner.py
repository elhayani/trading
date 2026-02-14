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
from typing import List

import boto3

# Configure log level based on environment
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
logging.getLogger().setLevel(getattr(logging, LOG_LEVEL))

# Imports from existing modules
from trading_engine import (
    AWSClients,
    TradingEngine,
    _get_binance_credentials,
    _get_binance_position_detail,
    _create_mock_binance_position,
    _get_real_binance_positions
)

# Session optimization imports
from datetime import datetime, timezone

def get_session_boost(symbol: str, hour_utc: int) -> float:
    """
    Multiplie le score de mobilité selon la session active.
    Retourne un coefficient 0.5 (pénalité) à 2.0 (boost).
    """
    s = symbol.replace('USDT', '')

    # Session Asie (00H-08H UTC) - Heure Paris = 01H-09H
    ASIA_TOKENS = ['BNB','TRX','ADA','DOT','ATOM','FIL',
                   'JASMY','ONE','ZIL','VET','IOTA','NEAR']
    # Session Europe (07H-16H UTC) - Heure Paris = 08H-17H  
    EU_TOKENS   = ['BTC','ETH','LTC','XRP','LINK','UNI',
                   'AAVE','MKR','SNX','ZEC','XMR']
    # Session US (13H-22H UTC) - Heure Paris = 14H-23H
    US_TOKENS   = ['SOL','AVAX','DOGE','SHIB','PEPE','ARB',
                   'OP','INJ','TIA','SEI','SUI']

    if 0 <= hour_utc < 8:    # Nuit Europe = Asie active
        if s in ASIA_TOKENS: return 2.0
        if s in US_TOKENS:   return 0.7
        return 1.0

    elif 7 <= hour_utc < 16:  # Journée Europe
        if s in EU_TOKENS:   return 1.8
        return 1.0

    elif 13 <= hour_utc < 22: # US actif
        if s in US_TOKENS:   return 2.0
        if s in EU_TOKENS:   return 1.5
        return 1.0

    else:                     # Transition
        return 1.0

def get_min_atr(hour_utc: int, btc_atr_pct: float) -> float:
    """
    ATR minimum adaptatif.
    Si BTC lui-même est peu volatile → tout le marché l'est → baisser le seuil.
    """
    # Base selon l'heure
    if 0 <= hour_utc < 7:    # Nuit profonde
        base = 0.20
    elif 13 <= hour_utc < 22: # Full US session
        base = 0.40
    else:
        base = 0.30

    # Ajustement selon volatilité BTC en temps réel
    # Si BTC ATR < 0.10% → marché mort → baisser encore
    if btc_atr_pct < 0.10:
        return base * 0.6
    elif btc_atr_pct > 0.30:
        return base * 1.3  # Marché chaud → être plus sélectif

    return base

def check_session_volume(ohlcv_1min: list, hour_utc: int) -> bool:
    """
    Vérifie que le volume RÉCENT est suffisant,
    pas le volume 24H qui dilue les pics sessionels.
    """
    if len(ohlcv_1min) < 60:
        return False

    # Volume des 60 dernières bougies 1min = 1 heure
    vol_1h = sum(c[5] * c[4] for c in ohlcv_1min[-60:])  # volume × close = USDT

    # Seuil horaire = volume 24H / 24 avec bonus session
    # Si on est dans la session principale de l'actif → seuil plus bas
    MIN_VOL_1H_USDT = 150_000   # $150K/heure = $3.6M/jour équivalent

    return vol_1h >= MIN_VOL_1H_USDT

def detect_night_pump(ohlcv_1min: list) -> tuple[bool, str]:
    """
    Détecte les mouvements anormaux qui signalent une opportunité nocturne.
    """
    if len(ohlcv_1min) < 20:
        return False, ""

    closes = [c[4] for c in ohlcv_1min]
    volumes = [c[5] for c in ohlcv_1min]

    # Mouvement des 5 dernières minutes vs les 15 précédentes
    move_5min = abs(closes[-1] - closes[-6])  / closes[-6]  * 100
    move_15min = abs(closes[-6] - closes[-21]) / closes[-21] * 100

    # Volume des 5 dernières minutes vs moyenne
    vol_5min = sum(volumes[-5:]) / 5
    vol_avg = sum(volumes[-20:-5]) / 15
    vol_ratio = vol_5min / vol_avg if vol_avg > 0 else 0

    # Pump détecté si mouvement récent > 3× le mouvement de fond + volume ×3
    if move_5min > 0.50 and move_5min > move_15min * 2 and vol_ratio > 3.0:
        direction = 'LONG' if closes[-1] > closes[-6] else 'SHORT'
        return True, direction

    return False, ""

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
            # Si l'API échoue, utiliser les symboles depuis env var ou liste minimal
            symbols_str = os.getenv('SYMBOLS', 'BTCUSDT,ETHUSDT')
            # Convertir au format interne si nécessaire
            symbols = [s.strip() for s in symbols_str.split(',') if s.strip()]
            # S'assurer du format /USDT:USDT
            symbols = [f"{s}/USDT:USDT" if not '/' in s else s for s in symbols]
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
                logger.warning(f"👻 GHOST TRADE DETECTED: {symbol} in DynamoDB but not on Binance")
                
                # Calculate risk to remove
                entry_price = float(pos_data.get('entry_price', 0))
                quantity = float(pos_data.get('quantity', 0))
                leverage = float(pos_data.get('leverage', 1))
                risk_dollars = (entry_price * quantity) / leverage
                
                # Log the trade as closed with GHOST_CLEANUP reason
                engine.persistence.log_trade_close(
                    symbol=symbol,
                    exit_price=0.0,
                    exit_time=datetime.now(timezone.utc).isoformat(),
                    pnl_pct=0.0,
                    pnl_usd=0.0,
                    exit_reason="GHOST_CLEANUP",
                    strategy="GHOST_DETECTION"
                )
                
                # Remove from risk manager
                engine.risk_manager.close_trade(symbol, entry_price)
                
                # Remove from atomic risk (CRITICAL!)
                engine.persistence.atomic_remove_risk(symbol, risk_dollars)
                
                ghost_cleaned += 1
                logger.info(f"🧹 Ghost {symbol} cleaned - Risk removed: ${risk_dollars:.2f}")
        
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
        
        # Step 1: Pré-tri intelligent avec optimisations session
        hour_utc = datetime.utcnow().hour
        logger.info(f"🌍 Session UTC {hour_utc}h - Pré-tri optimisé sur {len(symbols)} symboles...")
        mobility_start = time.time()
        
        # Fetch 5 bougies sur tous les actifs pour trier par mobilité
        mobility_scores = []
        night_pumps = []
        
        for symbol in symbols:
            try:
                ohlcv_micro = engine.exchange.fetch_ohlcv_1min(symbol, limit=5)
                if len(ohlcv_micro) >= 5:
                    # Calculer le mouvement récent (5 bougies)
                    last_move = abs(ohlcv_micro[-1][4] - ohlcv_micro[-5][4]) / ohlcv_micro[-5][4] * 100
                    
                    # Appliquer le boost de session
                    boost = get_session_boost(symbol, hour_utc)
                    weighted_score = last_move * boost
                    
                    mobility_scores.append((symbol, weighted_score, last_move, boost))
                    
                    # Détecter les pumps nocturnes (TOP 100 seulement pour performance)
                    if len(mobility_scores) <= 100:
                        ohlcv_pump = engine.exchange.fetch_ohlcv_1min(symbol, limit=20)
                        is_pump, direction = detect_night_pump(ohlcv_pump)
                        if is_pump:
                            night_pumps.append((symbol, weighted_score * 3.0, direction))  # Boost ×3 pour pumps
                            logger.info(f"🚀 NIGHT_PUMP {symbol}: {direction} (score: {weighted_score:.2f})")
                            
            except Exception as e:
                logger.warning(f"[MOBILITY] Failed to fetch {symbol}: {e}")
        
        # Ajouter les night pumps en tête de liste (priorité absolue)
        all_scores = night_pumps + mobility_scores
        
        # Trier du plus mobile au plus stable
        all_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Adapter le nombre d'actifs selon l'heure
        top_n = 60 if 0 <= hour_utc < 8 else 50  # Plus large la nuit
        symbols_sorted = [s for s, _, _, _ in all_scores[:top_n]]
        
        mobility_time = time.time() - mobility_start
        logger.info(f"⚡ Pré-tri optimisé: {len(symbols_sorted)} actifs en {mobility_time:.1f}s (boost session: {hour_utc}h)")
        
        # Step 2: Process only the mobile symbols
        logger.info(f"🔄 Processing {len(symbols_sorted)} symboles mobiles...")
        scan_start = time.time()
        
        opened_count = 0
        skipped_count = 0
        
        for symbol in symbols_sorted:
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
        total_duration = time.time() - start_time
        logger.info(f"✅ Processing complete in {scan_duration:.1f}s - {len(symbols_sorted)} mobiles")
        
        # Step 3: Save state
        engine.persistence.save_risk_state(engine.risk_manager.get_state())
        
        # ================================================================
        # RESPONSE
        # ================================================================
        
        response = {
            'lambda': 'SCANNER',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'duration_seconds': round(total_duration, 2),
            'mobility_duration': round(mobility_time, 2),
            'scan_duration': round(scan_duration, 2),
            'total_symbols': len(symbols),
            'mobile_symbols': len(symbols_sorted),
            'candidates_found': len(symbols_sorted),
            'positions_opened': opened_count,
            'opportunities_skipped': skipped_count,
            'total_open_positions': existing_count + opened_count,
            'symbols_scanned': len(symbols_sorted),
            'top_candidates': symbols_sorted[:5],
            'session_utc': hour_utc,
            'night_pumps_detected': len(night_pumps),
            'session_boost_enabled': TradingConfig.SESSION_BOOST_ENABLED
        }
        
        logger.info("=" * 80)
        logger.info(f"✅ LAMBDA 1 Complete: {opened_count} opened, {skipped_count} skipped")
        logger.info(f"📊 Processed: {len(symbols)} total → {len(symbols_sorted)} mobiles")
        logger.info(f"🌍 Session UTC {hour_utc}h | Night pumps: {len(night_pumps)}")
        logger.info(f"⏱️  Duration: {total_duration:.2f}s (mobility: {mobility_time:.1f}s)")
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
