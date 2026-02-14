from typing import Dict, List
import logging
from exchange_connector import ExchangeConnector
from binance_metrics import BinanceMetrics
import time

logger = logging.getLogger(__name__)

class BinanceNativeScanner:
    """
    Scanner utilisant UNIQUEMENT les données natives Binance
    Pipeline optimisé : Ticker -> OHLCV -> OrderBook/Trades
    """
    
    def __init__(self, exchange: ExchangeConnector):
        self.exchange = exchange
        self.metrics = BinanceMetrics()
    
    def scan(self, symbols: List[str], max_assets: int = 15) -> List[str]:
        """
        Scan complet avec filtrage progressif
        Retourne la liste des meilleurs symboles à trader
        """
        logger.info(f"[SCAN_V15] Starting Binance Native Scan on {len(symbols)} assets...")
        
        # 1. FETCH RAPIDE (Tickers 24h)
        # Filtre: Volume USDT > 5M (Liquidité minimale pour scalping)
        valid_candidates = []
        try:
            tickers = self.exchange.get_all_tickers()
            for s in symbols:
                # Resolve symbol format match with CCXT
                # CCXT tickers keys can be different.
                # Here we assume symbols list is already formatted like 'BTC/USDT:USDT'
                # but fetch_tickers returns 'BTC/USDT:USDT' or 'BTC/USDT' depending on driver
                
                # Check direct match
                t = tickers.get(s)
                if not t:
                    # Try alternate format
                    base = s.split('/')[0] if '/' in s else s
                    for key in tickers:
                        if key.startswith(base + '/USDT'):
                            t = tickers[key]
                            break
                
                if t:
                    quote_vol = t.get('quoteVolume', 0)
                    if quote_vol and quote_vol > 1_000_000: # 1M USDT minimum (Volume capture plus large)
                        # Score préliminaire: Variation prix + Volume
                        valid_candidates.append({
                            'symbol': s, 
                            'vol_24h': quote_vol,
                            'change_24h': abs(t.get('percentage', 0))
                        })
        except Exception as e:
            logger.error(f"[SCAN_V15] Ticker fetch failed: {e}")
            return symbols[:max_assets] # Fallback
            
        # Trie par Volume décroissant et garde top 50 pour analyse approfondie
        valid_candidates.sort(key=lambda x: x['vol_24h'], reverse=True)
        level1_filtered = valid_candidates[:50]
        logger.info(f"[SCAN_V15] Level 1 Filter: {len(level1_filtered)} assets selected (Vol > 1M)")
        
        scored_assets = []

        # 2. ANALYSE PROFONDE — OPT 2: score all 50 assets in parallel.
        # Sequential: 50 assets x ~1,500ms = 75,000ms
        # Parallel (10 workers): ceil(50/10) x ~500ms = 2,500ms  (30x faster)
        # max_workers=10 is safe for Binance rate limits (1200 req/min weight budget).
        from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed
        symbols_to_score = [item['symbol'] for item in level1_filtered]

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_symbol = {
                executor.submit(self.score_symbol_binance_native, sym): sym
                for sym in symbols_to_score
            }
            for future in _as_completed(future_to_symbol):
                sym = future_to_symbol[future]
                try:
                    score_data = future.result()
                    if score_data['score'] > 0:
                        # FIX #4: Pre-filter spike assets below 80 score
                        if score_data.get('volatility_spike') and score_data['score'] < 80:
                            logger.info(f"[SCAN_V15] Pre-filter spike {sym} (score={score_data['score']} < 80)")
                            continue
                        scored_assets.append(score_data)
                except Exception as e:
                    logger.warning(f"[SCAN_V15] Failed to score {sym}: {e}")
        
        # 3. CLASSEMENT FINAL
        # Trier par score décroissant
        scored_assets.sort(key=lambda x: x['score'], reverse=True)
        # Fix D: expose scored list so TradingEngine can cache symbol->score mapping
        self._last_scored_assets = scored_assets
        
        # Log Top 5 details
        for i, res in enumerate(scored_assets[:5]):
            logger.info(f"🏆 #{i+1} {res['symbol']} Score={res['score']} | Signals={', '.join(res['signals'])}")
            
        final_list = [item['symbol'] for item in scored_assets[:max_assets]]
        return final_list

    def score_symbol_binance_native(self, symbol: str) -> Dict:
        """
        Score basé uniquement sur les données Binance.
        OPT 1: Les 4 fetches sont lancés en parallèle via ThreadPoolExecutor
        pour passer de ~1.5s séquentiel à ~0.6s parallèle par asset.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        try:
            # OPT 1: Parallel fetch — all 4 I/O calls fire simultaneously.
            # Sequential was: ohlcv(300ms) + ticker(200ms) + orderbook(400ms) + trades(600ms) = 1,500ms
            # Parallel is:    max(300, 200, 400, 500ms) = ~500ms  (3x faster per asset)
            # trades limit reduced 200->100: halves payload, still enough for aggression signal
            results = {}
            errors = {}
            fetches = {
                'ohlcv':     lambda: self.exchange.fetch_ohlcv(symbol, '1h', limit=50),
                'ticker':    lambda: self.exchange.fetch_ticker(symbol),
                'orderbook': lambda: self.exchange.fetch_order_book_analysis(symbol, limit=50),
                'trades':    lambda: self.exchange.fetch_recent_trades_analysis(symbol, limit=100),
            }
            with ThreadPoolExecutor(max_workers=4) as ex:
                futures = {ex.submit(fn): name for name, fn in fetches.items()}
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        results[name] = future.result()
                    except Exception as e:
                        errors[name] = e
                        results[name] = {} if name in ('orderbook', 'trades') else None

            ohlcv             = results.get('ohlcv')
            ticker            = results.get('ticker') or {}
            orderbook_analysis = results.get('orderbook') or {}
            trades_analysis   = results.get('trades') or {}

            if ohlcv is None:
                raise RuntimeError(f"OHLCV fetch failed: {errors.get('ohlcv')}")
            
            # ========== CALCUL DES MÉTRIQUES (ALL-IN-ONE) ==========
            
            # Use the new optimized method
            metrics_all = self.metrics.calculate_all_metrics(ohlcv)
            
            if not metrics_all:
                return {'symbol': symbol, 'score': 0, 'signals': [], 'error': 'METRICS_FAILED'}

            # Check Data Quality
            quality = metrics_all.get('quality', {})
            if not quality.get('usable', False):
                 return {'symbol': symbol, 'score': 0, 'signals': [], 'error': f"BAD_DATA: {quality.get('reason')}"}
            
            volume_profile = metrics_all['volume_profile']
            delta = metrics_all['delta']
            buy_sell = metrics_all['buy_sell']
            intensity = metrics_all['intensity']
            volatility = metrics_all['volatility']
            momentum = metrics_all['momentum']
            
            # ========== SCORING (Max 100) ==========
            
            score = 0
            signals = []
            direction = None
            
            # 1. MOMENTUM (25 points) - Focus Vitesse
            if momentum['shift_detected']:
                score += 25
                signals.append(f"MOMENTUM_SHIFT_{momentum['direction']}")
                direction = 'LONG' if momentum['direction'] == 'BULLISH' else 'SHORT'
            elif abs(momentum['acceleration']) > 1:
                score += 15
                signals.append("MOMENTUM_BUILD")
            
            # 2. BUY/SELL PRESSURE (20 points) - 52% Signal
            buy_pct = buy_sell['buy_percentage']
            if buy_pct > 60:
                score += 20
                signals.append("STRONG_BUY_PRESSURE")
                if direction != 'SHORT': direction = 'LONG'
            elif buy_pct > 52:  # 52% = Signal (User Request)
                score += 15
                signals.append("MODERATE_BUY_PRESSURE")
                if direction != 'SHORT': direction = 'LONG'
            elif buy_pct < 40:
                score += 20
                signals.append("STRONG_SELL_PRESSURE")
                if direction != 'LONG': direction = 'SHORT'
            elif buy_pct < 48:  # 48% (Symétrique 52%)
                score += 15
                signals.append("MODERATE_SELL_PRESSURE")
                if direction != 'LONG': direction = 'SHORT'
            
            # 3. DELTA VOLUME (20 points) - ±10% Signal
            delta_pct = delta['delta_pct']
            if delta_pct > 30:
                score += 20
                signals.append("STRONG_BULLISH_DELTA")
                if direction != 'SHORT': direction = 'LONG'
            elif delta_pct > 10:  # ±10% = Signal (User Request)
                score += 15
                signals.append("BULLISH_DELTA")
                if direction != 'SHORT': direction = 'LONG'
            elif delta_pct < -30:
                score += 20
                signals.append("STRONG_BEARISH_DELTA")
                if direction != 'LONG': direction = 'SHORT'
            elif delta_pct < -10:  # ±10% = Signal (User Request)
                score += 15
                signals.append("BEARISH_DELTA")
                if direction != 'LONG': direction = 'SHORT'
            
            # 4. ORDER BOOK IMBALANCE (15 points) - Équilibre ±0.2
            imb = orderbook_analysis.get('imbalance', 0)
            if imb > 0.3:
                score += 15
                signals.append("STRONG_ORDERBOOK_BUY")
                if direction != 'SHORT': direction = 'LONG'
            elif imb > 0.2:  # ±0.2 seuil équilibré
                score += 10
                signals.append("ORDERBOOK_BUY_PRESSURE")
                if direction != 'SHORT': direction = 'LONG'
            elif imb < -0.3:
                score += 15
                signals.append("STRONG_ORDERBOOK_SELL")
                if direction != 'LONG': direction = 'SHORT'
            elif imb < -0.2:  # ±0.2 seuil équilibré
                score += 10
                signals.append("ORDERBOOK_SELL_PRESSURE")
                if direction != 'LONG': direction = 'SHORT'
            
            # 5. WHALE ACTIVITY (10 points)
            if intensity['whale_activity'] > 20:
                score += 10
                signals.append("WHALE_ACTIVE")
            
            # 6. VOLATILITY (10 points) - Privilégier NORMAL et HIGH
            # FIX #4: Detect spike (1H candle > 4%) to allow pre-filter in scan()
            current_candle_pct = abs((ohlcv[-1][4] - ohlcv[-1][1]) / ohlcv[-1][1] * 100) if ohlcv else 0
            is_spike = current_candle_pct > 4.0
            if volatility['regime'] in ['NORMAL', 'HIGH']:
                score += 10
                signals.append(f"VOLATILITY_{volatility['regime']}")
            elif volatility['regime'] == 'LOW':
                score += 5
                signals.append("LOW_VOLATILITY_SQUEEZE")
            
            # 7. PRICE VS POC (10 points)
            poc_distance = volume_profile.get('current_vs_poc', 100)
            if abs(poc_distance) < 1:  # Prix proche du POC (support fort)
                score += 10
                signals.append("NEAR_POC_SUPPORT")
            
            # 8. RECENT TRADES AGGRESSION (10 points) - Moins extrême ±0.25
            aggr = trades_analysis.get('aggression', 0)
            if aggr > 0.4:
                score += 10
                signals.append("VERY_AGGRESSIVE_BUYERS")
                if direction != 'SHORT': direction = 'LONG'
            elif aggr > 0.25:  # ±0.25 moins extrême
                score += 7  # Points partiels
                signals.append("AGGRESSIVE_BUYERS")
                if direction != 'SHORT': direction = 'LONG'
            elif aggr < -0.4:
                score += 10
                signals.append("VERY_AGGRESSIVE_SELLERS")
                if direction != 'LONG': direction = 'SHORT'
            elif aggr < -0.25:  # ±0.25 moins extrême
                score += 7  # Points partiels
                signals.append("AGGRESSIVE_SELLERS")
                if direction != 'LONG': direction = 'SHORT'
            
            # BONUS: Convergence Rapide (3 signaux suffisent)
            if len(signals) >= 3:
                score += 10
                signals.append("MULTI_CONFIRMATION_FAST")
            
            return {
                'symbol': symbol,
                'score': min(score, 100),
                'direction': direction or 'NEUTRAL',
                'signals': signals,
                'volatility_spike': is_spike,  # FIX #4: used by scan() pre-filter
                'metrics': {
                    'price_change_24h': ticker.get('percentage', 0),
                    'volume_24h_usdt': ticker.get('quoteVolume', 0),
                    'buy_pressure': buy_sell['buy_percentage'],
                    'delta_pct': delta['delta_pct'],
                    'orderbook_imbalance': imb,
                    'whale_activity': intensity['whale_activity'],
                    'volatility': volatility['regime'],
                    'poc_distance': poc_distance,
                    'momentum_shift': momentum['shift_detected'],
                    'quality_score': quality.get('quality_score', 0)
                },
                'price': ticker['last']
            }
            
        except Exception as e:
            logger.error(f"Failed to score {symbol}: {e}")
            return {'symbol': symbol, 'score': 0, 'error': str(e), 'signals': []}
