import sys
import os
import ccxt
import pandas as pd
import numpy as np
import time
import json
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError

# --- CONFIGURATION BEDROCK ---
# On initialise le client AWS Bedrock (Claude 3 Haiku)
# S'assure que les credentials AWS sont configurés dans l'environnement
try:
    # On force la région us-east-1 car Bedrock est souvent dispo là-bas pour les nouveaux modèles
    bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
    print("✅ AWS Bedrock Client Initialized (us-east-1)")
except Exception as e:
    print(f"⚠️ Warning: Impossible d'initier AWS Bedrock: {e}")
    bedrock_runtime = None

class AILogic:
    @staticmethod
    def ask_confirmation(symbol, date_str, indicators, patterns):
        """ Interroge Claude 3 Haiku via Bedrock pour valider ou booster le signal technique. """
        if not bedrock_runtime:
             return {"decision": "CONFIRM", "reason": "Bedrock Client Logic Error"}
        
        # Récupération VRAIES NEWS depuis CryptoCompare
        try:
            signal_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
        except:
            signal_date = None  # Fallback mode live
            print(f"⚠️ Date parsing failed for {date_str}, using current time")
        
        # Appel API news
        print(f"📰 Fetching news for {symbol} before {date_str}...")
        news_context = get_news_context(symbol, reference_date=signal_date)
        
        # LOG: Afficher les news récupérées
        if "Aucune news" in news_context:
            print(f"   ⚠️ No news found for {symbol}")
        elif "articles trouvés" in news_context:
            # Extraire le nombre d'articles
            import re
            match = re.search(r'(\d+) articles', news_context)
            if match:
                count = match.group(1)
                print(f"   ✅ {count} articles retrieved")
                
                # Extraire le sentiment
                sentiment_match = re.search(r'(\d+) positifs, (\d+) négatifs', news_context)
                if sentiment_match:
                    pos, neg = sentiment_match.groups()
                    print(f"   📊 Sentiment: {pos} positifs, {neg} négatifs")
        else:
            print(f"   ℹ️ News context: {news_context[:100]}...")
        
        # Fallback: Si aucune news, utiliser contexte neutre
        if "Aucune news" in news_context or not news_context.strip():
            news_context = "📰 NEWS: Aucune news significative dans les 24h précédentes (contexte neutre)"
             
        prompt = f"""
        DATE: {date_str} | ACTIF: {symbol}
        
        📊 DONNÉES TECHNIQUES:
        - RSI: {indicators['rsi']:.1f}
        - Volume Ratio: {indicators['vol_ratio']:.2f}x (vs moyenne 50 périodes)
        - Tendance SMA50: {indicators['slope']}
        - Patterns détectés: {patterns}
        
        {news_context}
        
        🎯 MISSION CRITIQUE: Tu es un Risk Manager STRICT mais RATIONNEL.
        Ce signal a passé des filtres techniques TRÈS SÉLECTIFS (RSI<32 + Volume>2.2x).
        Tu dois analyser le CONTEXTE NEWS pour détecter les VRAIS PIÈGES.
        
        ⛔ TU DOIS REJETER (CANCEL) si:
        1. **NEWS MAJORITAIREMENT NÉGATIVES** (> 60% des articles négatifs)
        2. News mentionnent: hack, scam, exchange bankruptcy, regulatory ban
        3. Divergence EXTRÊME: Technique excellent MAIS news catastrophiques
        
        ✅ CONFIRMER (CONFIRM) si:
        - News neutres OU mixtes (pas de red flags majeurs)
        - OU News légèrement négatives MAIS technique très fort (RSI<25, Vol>3x)
        - ET RSI entre 25-40 (oversold zone)
        - ET Volume > 2x
        
        🚀 BOOST (Levier x2) si:
        - News TRÈS positives (>60% positifs)
        - ET RSI < 28 (oversold fort)
        - ET Volume > 3x (spike massif)
        - ET Trend RISING
        
        ⚠️ NOUVELLE PHILOSOPHIE V2:
        - **Si NEWS neutres/mixtes → TRUST LA TECHNIQUE** (elle est déjà ultra-sélective)
        - **Only CANCEL si vraie catastrophe** (pas juste du FUD léger)
        - **Le marché surréagit souvent aux news** → Opportunités
        - Tu ne connais PAS le futur après {date_str}
        
        RÉPONSE JSON UNIQUEMENT:
        {{ "decision": "CONFIRM" | "CANCEL" | "BOOST", "reason": "Mention NEWS + Tech" }}
        """
        
        # Payload Claude 3 Messages API
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt}
                    ]
                }
            ],
            "temperature": 0.5  # Augmenté pour plus de variabilité
        }

        try:
            response = bedrock_runtime.invoke_model(
                modelId="anthropic.claude-3-haiku-20240307-v1:0",
                body=json.dumps(payload)
            )
            
            # Parsing de la réponse
            response_body = json.loads(response.get('body').read())
            content_text = response_body.get('content')[0].get('text')
            
            # DEBUG: Voir ce que Bedrock répond
            print(f"🤖 Bedrock @ {date_str}: {content_text[:150]}...")
            
            # Nettoyage JSON
            if "```json" in content_text:
                content_text = content_text.split("```json")[1].split("```")[0].strip()
            
            # Extraction du JSON pur si texte autour
            start_idx = content_text.find('{')
            end_idx = content_text.rfind('}') + 1
            if start_idx != -1 and end_idx != -1:
                 content_text = content_text[start_idx:end_idx]

            result = json.loads(content_text)
            print(f"   → Décision: {result.get('decision')} | Raison: {result.get('reason')}")
            return result
            
        except ClientError as e:
            print(f"⚠️ Bedrock API Error: {e}")
            return {"decision": "CONFIRM", "reason": "AWS Bedrock Error"}
        except Exception as e:
            print(f"⚠️ Parse Error: {e}")
            return {"decision": "CONFIRM", "reason": "Parse/Logic Error"}

# Ajout du path pour importer le moteur d'analyse
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../lambda/data_fetcher')))
try:
    from market_analysis import analyze_market
    from news_fetcher import get_news_context
except ImportError as e:
    print(f"❌ Erreur: Impossible d'importer les modules: {e}")
    sys.exit(1)

def fetch_historical_data(exchange, symbol, timeframe, days, offset_days=0):
    """
    Récupère 'days' jours de données depuis S3 (Mode Historique).
    """
    # Calcul Période
    end_time = datetime.now() - timedelta(days=offset_days)
    start_time = end_time - timedelta(days=days)
    
    # Années concernées
    start_year = start_time.year
    end_year = end_time.year
    years = range(start_year, end_year + 1)
    
    all_ohlcv = []
    bucket_name = os.environ.get('TRADING_LOGS_BUCKET')
    s3 = boto3.client('s3')
    
    if not bucket_name:
        print("❌ PB: TRADING_LOGS_BUCKET non défini.")
        return []

    print(f"📥 [S3] Récupération {symbol} ({days}j)...")
    
    safe_symbol = symbol.replace('/', '_')
    
    for y in years:
        key = f"historical/{safe_symbol}/{y}.json"
        try:
            resp = s3.get_object(Bucket=bucket_name, Key=key)
            file_content = resp['Body'].read().decode('utf-8')
            yearly_data = json.loads(file_content)
            all_ohlcv.extend(yearly_data)
        except Exception as e:
            # On ignore les erreurs "NoSuchKey" car l'année peut ne pas exister
            pass
            
    # Filtrage précis par date
    start_ts = int(start_time.timestamp() * 1000)
    end_ts = int(end_time.timestamp() * 1000)
    
    # Filter and Sort
    filtered = [x for x in all_ohlcv if start_ts <= x[0] <= end_ts]
    filtered.sort(key=lambda x: x[0])
    
    if len(filtered) > 0:
        print(f"✅ {len(filtered)} bougies chargées depuis S3.")
    else:
        print(f"⚠️ Aucune data S3 trouvée pour {symbol} sur la période.")
        
    return filtered

# GLOBAL LOG FILE SETUP
LOG_FILENAME = f"backtest_GLOBAL_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
with open(LOG_FILENAME, 'w') as f:
    f.write(f"SYMBOL,TIMESTAMP,TYPE,PRICE,RSI,SMA50,SLOPE,ATR,VOL_RATIO,BTC_BULLISH,PATTERNS,REASON,PROFIT\n")

def run_backtest(symbol='BTC/USDT', timeframe='1h', days=90, offset_days=0, leverage=1, verbose=True, btc_trend_map=None, btc_perf_map=None):
    """
    Exécute le backtest complet avec les paramètres donnés.
    btc_trend_map: Dictionnaire {timestamp: boolean} indiquant si BTC est bullish
    btc_perf_map: Dictionnaire {timestamp: float} indiquant perf 7j BTC
    """
    if verbose:
        print(f"\n🔄 Démarrage Backtest: {symbol} | Levier: x{leverage} | Période: -{days+offset_days}j à -{offset_days}j")

    # 1. Récupération Données Historiques
    exchange = None # S3
    ohlcv = fetch_historical_data(exchange, symbol, timeframe, days, offset_days)

    if len(ohlcv) < 50:
        if verbose: print("❌ Pas assez de données pour le backtest.")
        return

    # 2. Simulation Simulation Trading
    initial_capital = 1000 # USDT
    capital = initial_capital
    position = None
    trades = []

    # On a besoin d'un buffer pour les indicateurs (ex: 200 périodes pour SMA)
    # On augmente min_history pour couvrir SMA 200
    min_history = 300

    def log_trade(action, price, rsi, sma, slope, atr, vol, btc, patterns, reason, profit=""):
        with open(LOG_FILENAME, 'a') as f:
            slope_str = "RISING" if slope else "FLAT"
            vol_ratio = vol / (avg_vol if 'avg_vol' in locals() else vol)
            # Ajout du SYMBOL dans le log
            f.write(f"{symbol},{date_str},{action},{price},{rsi:.1f},{sma:.1f},{slope_str},{atr:.2f},{vol_ratio:.2f},{btc},{patterns},{reason},{profit}\n")

    # Statistiques
    drawdown_max = 0
    peak_capital = initial_capital

    for i in range(min_history, len(ohlcv)):
        window_ohlcv = ohlcv[i-min_history:i+1]
        current_candle = window_ohlcv[-1]
        timestamp = current_candle[0]
        current_price = current_candle[4]
        date_str = datetime.fromtimestamp(timestamp/1000).strftime('%Y-%m-%d %H:%M')

        # ANALYSE
        analysis = analyze_market(window_ohlcv)
        indicators = analysis['indicators']
        patterns = analysis['patterns']

        # Unpacking indicateurs
        rsi = indicators['rsi']
        atr = indicators['atr']
        sma_50 = indicators['sma_50']

        # SMA Slope Calculation (Pente sur 5 périodes)
        # On a besoin de l'historique de la SMA.
        # market_analysis retourne sma_50 courant, mais on peut le recalculer approximativement ou le demander
        # Pour faire simple ici, on regarde la diff avec le prix d'il y a 5 bougies si SMA non dispo en série
        # Ou mieux, on utilise le window_ohlcv pour recalculer les 2 dernières SMA

        closes = pd.Series([c[4] for c in window_ohlcv])
        sma_series = closes.rolling(window=50).mean()

        is_sma_rising = False
        is_strong_trend = False

        if len(sma_series) > 5:
            slope = sma_series.iloc[-1] - sma_series.iloc[-5]
            # On veut une pente positive significative (ex: > 0.1% du prix)
            is_sma_rising = slope > (current_price * 0.001)
            # Tendance FORTE : Pente > 0.3% du prix (Arbitraire pour le test)
            is_strong_trend = slope > (current_price * 0.003)

        # Volume Analysis - V2.5 ÉQUILIBRÉ
        current_vol = current_candle[5]
        # Calcul Volume Moyen (sur 20 dernières bougies)
        avg_vol = np.mean([c[5] for c in window_ohlcv[-20:]])
        is_high_volume = current_vol > (avg_vol * 1.8)  # Sweet spot: +80% volume

        # Patterns & Candles
        patterns = analysis['patterns']
        candles = analysis['candles']

        # Listes de patterns bull/bear
        bullish_patterns = ["HAMMER", "ENGULFING_BULLISH", "DOUBLE_BOTTOM_POTENTIAL", "ETE_BULLISH_POTENTIAL"]
        bearish_patterns = ["SHOOTING_STAR", "ENGULFING_BEARISH", "DOUBLE_TOP_POTENTIAL", "ETE_BEARISH_POTENTIAL"]

        has_bullish_signal = any(p in (patterns + candles) for p in bullish_patterns)
        has_bearish_signal = any(p in (patterns + candles) for p in bearish_patterns)

        decision = "WAIT"
        ai_boost_active = False

        # ----------------STRATÉGIE OPTIMISÉE (CRYPTO)----------------

        # CORRÉLATION BTC
        # On active la corrélation pour les ALTS sauf exceptions
        # Exception: SOL peut trader seul (Force relative)
        is_btc_bullish = True

        should_check_correlation = (symbol != 'BTC/USDT') and (symbol != 'SOL/USDT')

        if btc_trend_map and should_check_correlation:
            is_btc_bullish = btc_trend_map.get(timestamp, False)

        # Relative Strength (ETH only)
        # N'achète ETH que si perf 7j > Perf BTC 7j
        is_rs_strong = True
        if "ETH" in symbol and btc_perf_map:
             if i > 168:
                 past_close = ohlcv[i-168][4]
                 eth_perf = (current_price - past_close) / past_close
                 btc_perf = btc_perf_map.get(timestamp, 0)
                 # On veut ETH > BTC pour acheter
                 is_rs_strong = eth_perf > btc_perf
             else:
                 is_rs_strong = False # Pas assez d'historique

        # 1. FILTRE DE TENDANCE (Trend Filter)
        # Changement SMA 200 -> SMA 50 pour être plus réactif
        # + condition PENTE (Slope) pour éviter les ranges plats
        # + condition BTC CORRELATION (Si Altcoin)
        # + condition RS (Si ETH)
        is_uptrend = (sma_50 is not None) and (current_price > sma_50) and is_sma_rising and is_btc_bullish and is_rs_strong

        # 2. FILTRE DE VOLATILITÉ (Volatility Filter)
        # On veut un ATR minimum pour s'assurer qu'il y a du mouvement (éviter le bruit en range serré)
        # Seuil arbitraire bas pour l'exemple, à ajuster selon l'actif
        is_volatile_enough = (atr is not None) and (atr > current_price * 0.001)

        # 3. SIGNAL D'ENTRÉE RSI - V2.5 ÉQUILIBRÉ
        # RSI < 38 (Sweet spot between quality and quantity)
        rsi_buy_signal = (rsi is not None) and (rsi < 38)

        # LOGIQUE D'ACHAT
        if position is None:
            if rsi_buy_signal:
                if is_uptrend and is_volatile_enough:
                    # Confirmation Pattern + VOLUME
                    # On exige un pattern haussier + un volume significatif
                    if has_bullish_signal and is_high_volume:
                        # --- INTEGRATION IA ---
                        # Technical Check OK -> Ask AI for Validation/Boost
                        ai_indicators = {
                            'rsi': rsi,
                            'vol_ratio': current_vol / avg_vol,
                            'slope': "RISING" if is_sma_rising else "FLAT"
                        }
                        ai_res = AILogic.ask_confirmation(symbol, date_str, ai_indicators, patterns)

                        if ai_res.get('decision') == 'CANCEL':
                            # L'IA invalide le trade - LOGGER
                            if verbose: print(f"🤖 AI CANCELLED Trade @ {date_str} (Reason: {ai_res.get('reason')})")
                            sma_Val = sma_50 if sma_50 else 0
                            log_trade("AI_CANCEL", current_price, rsi, sma_Val, is_sma_rising, atr, current_vol, is_btc_bullish, has_bullish_signal, f"AI:CANCEL - {ai_res.get('reason')[:80]}")
                        else:
                            # CONFIRM ou BOOST
                            decision = "BUY"
                            if ai_res.get('decision') == 'BOOST':
                                ai_boost_active = True
                                if verbose: print(f"🚀 AI BOOSTED @ {date_str}")
                                sma_Val = sma_50 if sma_50 else 0
                                log_trade("AI_BOOST", current_price, rsi, sma_Val, is_sma_rising, atr, current_vol, is_btc_bullish, has_bullish_signal, f"AI:BOOST - {ai_res.get('reason')[:80]}")

                            sma_Val = sma_50 if sma_50 else 0
                            ai_reason = f"AI:{ai_res.get('decision')}"
                            log_trade("BUY", current_price, rsi, sma_Val, is_sma_rising, atr, current_vol, is_btc_bullish, has_bullish_signal, f"SIGNAL+VOL+{ai_reason}")
                    elif verbose:
                        reasons = []
                        if not has_bullish_signal: reasons.append("No Pattern")
                        if not is_high_volume: reasons.append(f"Low Vol ({current_vol:.0f} < {avg_vol*1.2:.0f})")
                        print(f"⚠️ [SKIP] Buy Signal @ {date_str} (RSI {rsi:.1f}) rejected: {', '.join(reasons)}")
                elif verbose:
                    reasons = []
                    if not is_uptrend:
                        sma_Val = sma_50 if sma_50 else 0
                        slope_str = "FLAT" if not is_sma_rising else "RISING"
                        btc_str = "OK" if is_btc_bullish else "BEARISH"
                        reasons.append(f"Trend (Price>SMA50: {current_price>sma_Val} | Slope: {slope_str} | BTC: {btc_str})")
                        log_trade("SKIP", current_price, rsi, sma_Val, is_sma_rising, atr, current_vol, is_btc_bullish, "NONE", f"SKIP: {reasons}")
                    if not is_volatile_enough: reasons.append("Low Volatility")
                    print(f"⚠️ [SKIP] Buy Signal @ {date_str} (RSI {rsi:.1f}) rejected by: {', '.join(reasons)}")

        # LOGIQUE DE VENTE (Gestion Position)
        elif position:
            entry_price = position['entry_price']

            # Calcul ATR au moment de l'entrée (stocké ou courant)
            # Pour simplifier, on recalcule des cibles dynamiques ou fixes

            # Risk Reward 1:3
            # Stop Loss : 1.5 x ATR
            # Take Profit : 4.5 x ATR (Ratio 3)
            # Ou simple % fixe si ATR instable

            # Approche dynamique ATR (Plus robuste)
            atr_sl_mult = 2.0  # Stop Loss = 2x ATR
            atr_tp_mult = 6.0  # Take Profit = 6x ATR (Risk Reward 1:3)

            trigger_atr = atr if atr is not None else (entry_price * 0.02) # Fallback 2%

            sl_price = entry_price - (trigger_atr * atr_sl_mult)
            if "ETH" in symbol:
                tp_price = entry_price * 1.08 # ETH: TP Fixe 8%
            else:
                tp_price = entry_price + (trigger_atr * atr_tp_mult)

            # Calcul PnL flottant pour décision
            current_pnl_pct = (current_price - entry_price) / entry_price

            # Gestion du Break-Even (Risk Free Trade)
            # Si le profit dépasse 3% (et qu'on n'a pas encore bougé le SL)
            # On considère que le SL est remonté au prix d'entrée
            if current_pnl_pct > 0.03:
                new_sl_price = entry_price * 1.002 # Break-Even + petit buffer frais (0.2%)
                if new_sl_price > sl_price:
                   sl_price = new_sl_price
                   # On ne log pas le changement pour pas spammer, mais c'est actif

            # Vérification Sorties
            if current_price <= sl_price:
                decision = "SELL" # Stop Loss hit
                # Si le SL était au BE, c'est une sortie neutre
                exit_reason = "BREAK_EVEN" if sl_price >= entry_price else "STOP_LOSS"
                if verbose: print(f"🛑 Stop Loss/BE Hit @ {current_price} ({exit_reason})")
            elif current_price >= tp_price:
                decision = "SELL" # Take Profit hit
                exit_reason = "TAKE_PROFIT"
                if verbose: print(f"💰 Take Profit Hit @ {current_price}")

            # Condition Panic Sell sur SOL (Volume Explosion Down)
            elif "SOL" in symbol and current_price < entry_price and current_vol > (avg_vol * 2.0):
                 decision = "SELL"
                 exit_reason = "SOL_PANIC_VOLUME"
                 if verbose: print(f"🚨 SOL Panic Exit (Vol > 2x)")

            elif has_bearish_signal:
                # OPTIMISATION ULTIME : "Smart Exit"
                # 1. Si Tendance FORTE (Strong Slope) : On IGNORE les signaux bearish (On vise le TP)
                # 2. Si Tendance FAIBLE/PLAT : On sort sur signal bearish (Prudence)
                # 3. Sécurité : Si on a déjà securisé un gain (>3%), on peut sortir aussi

                should_exit = False
                reason = "BEAR_PATTERN"

                if is_strong_trend:
                    if current_pnl_pct > 0.08: # Si déjà très haut, on peut sortir
                        should_exit = True
                        reason = "STRONG_TREND_SECURE"
                    else:
                        should_exit = False # ON GARDE
                else:
                    # Tendance Faible/Plate
                    # CHANGEMENT ZERO FRICTION:
                    # On ne sort JAMAIS sur signal bearish ici.
                    # On a activé le Break-Even à >3% (voir plus haut).
                    # Donc soit on tape le TP, soit on sort à 0 (BE).
                    # On ne coupe plus "au cas où".
                    should_exit = False
                    reason = "WEAK_TREND_IGNORED"

                if should_exit:
                    decision = "SELL"
                    exit_reason = reason
                    if verbose: print(f"📉 Bearish Exit ({exit_reason})")
            elif rsi > 75:
                decision = "SELL" # RSI Surchauffe (Exit sécurité)
                exit_reason = "RSI_OVERBOUGHT"

        # EXÉCUTION
        if decision == "BUY":
            # Calcul quantité (Risk Management basique : on mise tout le capital dispo)
            # Avec levier, on simule une exposition plus grande
            # Attention : Levier 'virtuel' sur le PnL

            # Gestion de taille de position & Levier Sélectif
            position_size_ratio = 1.0
            eff_leverage = leverage # Levier de base (défini en argument params)

            # Calcul Ratio Volume
            vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0

            # RÈGLE LEVIER DYNAMIQUE (BTC & SOL)
            # Si Vol > 2x Moyenne => High Conviction => Levier x2
            # OU Si IA dit "BOOST"
            if (symbol in ['BTC/USDT', 'SOL/USDT'] and vol_ratio > 2.0) or ai_boost_active:
                 eff_leverage = 2.0
                 reason_lev = "AI-BOOST" if ai_boost_active else f"VOL-RATIO {vol_ratio:.2f}"
                 if verbose: print(f"🔥 HIGH CONVICTION ({reason_lev}): Applying 2x Leverage on {symbol}")

            # Exception ETH (Position réduite)
            if "ETH" in symbol:
                position_size_ratio = 5.0/15.0 # Ratio ~0.33 (5% vs 15% standard)

            # Montant Notionnel = Capital * Ratio * Levier
            amount = (capital * position_size_ratio * eff_leverage) / current_price

            position = {
                'entry_price': current_price,
                'amount': amount,
                'time': date_str,
                'leverage': eff_leverage
            }
            if verbose:
                lev_str = f"x{eff_leverage}" if eff_leverage > 1 else ""
                print(f"🟢 [BUY]  {date_str} @ {current_price:<10} | RSI: {rsi:.1f} | {lev_str}")

        elif decision == "SELL":
            amount = position['amount']
            lev = position['leverage']
            entry_v = position['entry_price']

            # Calcul PnL
            # Valeur sortie
            exit_value = amount * current_price
            entry_value = amount * entry_v

            # Profit brut
            gross_profit = exit_value - entry_value

            # Mise à jour capital : On ajoute le profit (ou perte) au capital réel
            # Si levier, le profit est calculé sur le montant notionnel
            # Capital nouveau = Capital Ancien + (PnL)
            # Note: Si perte > Capital, liquidation.

            capital += gross_profit

            # Check Liquidation
            if capital <= 0:
                capital = 0
                print(f"💀 [LIQUIDATION] Compte à 0$ le {date_str}")
                break

            trades.append({
                'type': 'SELL',
                'entry': entry_v,
                'exit': current_price,
                'profit': gross_profit,
                'time': date_str,
                'pnl_pct': (gross_profit / (entry_value / lev)) * 100 # % sur capital investi
            })

            if verbose:
                icon = "✅" if gross_profit > 0 else "❌"
                print(f"{icon} [SELL] {date_str} @ {current_price:<10} | PnL: {gross_profit:+.2f}$ ({((current_price-entry_v)/entry_v)*100*lev:+.2f}%)")

            # Logger (Recalcul variables pour log)
            vol_ratio_log = current_vol / avg_vol if 'avg_vol' in locals() else 0
            sma_Val = sma_50 if sma_50 is not None else 0
            log_trade("SELL", current_price, rsi if rsi else 0, sma_Val, is_sma_rising, atr if atr else 0, current_vol, is_btc_bullish, has_bearish_signal, exit_reason, f"{gross_profit:.2f}")

            position = None

        # Tracking Drawdown
        if capital > peak_capital:
            peak_capital = capital
        dd = (peak_capital - capital) / peak_capital
        if dd > drawdown_max:
            drawdown_max = dd

    # RÉSULTATS FINAUX PÉRIODE
    perf_pct = ((capital - initial_capital) / initial_capital) * 100
    win_rate = 0
    if len(trades) > 0:
        wins = [t for t in trades if t['profit'] > 0]
        win_rate = (len(wins) / len(trades)) * 100

    print("-" * 40)
    print(f"RÉSULTAT ({days}j, Levier x{leverage})")
    print(f"Capital Final : {capital:.2f}$")
    print(f"Performance   : {perf_pct:+.2f}%")
    print(f"Trades        : {len(trades)}")
    print(f"Win Rate      : {win_rate:.1f}%")
    print(f"Max Drawdown  : {drawdown_max*100:.2f}%")
    print("-" * 40)

    return {
        "performance": perf_pct,
        "win_rate": win_rate,
        "trades": len(trades),
        "final_capital": capital
    }

if __name__ == "__main__":
    # --- SCÉNARIO VALIDATION ROBUSTESSE CRYPTO (S3 HISTORIQUE) ---
    
    # 1. Gestion des arguments (Année cible)
    target_year = 2024
    if len(sys.argv) > 1:
        for arg in sys.argv:
            if arg.isdigit() and len(arg) == 4 and arg.startswith("20"):
                target_year = int(arg)
                break
            
    print(f"\n🚀 BACKTEST HISTORIQUE S3 (ANNÉE {target_year})")
    
    # Selection de paires
    SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    
    # 0. Pré-chargement des données BTC pour la corrélation (Depuis S3)
    print("📥 Pré-chargement Reference BTC/USDT (S3)...")
    exchange = None # On n'utilise plus ccxt pour la data
    
    # Calcul offset pour viser le début de l'année cible
    now = datetime.now()
    start_of_target = datetime(target_year, 1, 1)
    offset_start = (now - start_of_target).days
    
    # On charge 1 année complète + buffer
    btc_ohlcv_all = fetch_historical_data(None, 'BTC/USDT', '1h', days=365+60, offset_days=max(0, offset_start - 365))
    
    if not btc_ohlcv_all:
         print("❌ Echec chargement BTC Reference via S3. Vérifiez le bucket.")
         btc_trend_map, btc_perf_map = {}, {}
    else:
        # Création Dataframe BTC (Identique)
        btc_df = pd.DataFrame(btc_ohlcv_all, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        btc_df['timestamp'] = pd.to_datetime(btc_df['timestamp'], unit='ms')
        btc_df['sma_50'] = btc_df['close'].rolling(window=50).mean()
        btc_df['slope'] = btc_df['sma_50'].diff(5)
        btc_df['is_bullish'] = btc_df['slope'] > 0
        btc_df['perf_7d'] = btc_df['close'].pct_change(168)
        
        # Maps
        btc_trend_map = dict(zip(btc_df['timestamp'].astype(np.int64) // 10**6, btc_df['is_bullish']))
        btc_perf_map = dict(zip(btc_df['timestamp'].astype(np.int64) // 10**6, btc_df['perf_7d']))

    # Calcul dynamique des offsets trimestriels
    date_q4_end = datetime(target_year + 1, 1, 1)
    offset_q4 = max(0, (now - date_q4_end).days)
    
    date_q3_end = datetime(target_year, 10, 1)
    offset_q3 = max(0, (now - date_q3_end).days)

    date_q2_end = datetime(target_year, 7, 1)
    offset_q2 = max(0, (now - date_q2_end).days)

    date_q1_end = datetime(target_year, 4, 1)
    offset_q1 = max(0, (now - date_q1_end).days)

    for SYMBOL in SYMBOLS:
        print(f"\n{'='*50}")
        print(f"💎 BACKTEST S3: {SYMBOL} ({target_year})")
        print(f"{'='*50}")

        # Q4
        print(f"\n📅 {target_year} Q4 (Oct-Dec)")
        res_q4 = run_backtest(SYMBOL, days=90, offset_days=offset_q4, leverage=1, verbose=False, btc_trend_map=btc_trend_map, btc_perf_map=btc_perf_map)
        
        # Q3
        print(f"\n📅 {target_year} Q3 (Jul-Sep)")
        res_q3 = run_backtest(SYMBOL, days=90, offset_days=offset_q3, leverage=1, verbose=False, btc_trend_map=btc_trend_map, btc_perf_map=btc_perf_map)

        # Q2
        print(f"\n📅 {target_year} Q2 (Apr-Jun)")
        res_q2 = run_backtest(SYMBOL, days=90, offset_days=offset_q2, leverage=1, verbose=False, btc_trend_map=btc_trend_map, btc_perf_map=btc_perf_map)

        # Q1
        print(f"\n📅 {target_year} Q1 (Jan-Mar)")
        res_q1 = run_backtest(SYMBOL, days=90, offset_days=offset_q1, leverage=1, verbose=False, btc_trend_map=btc_trend_map, btc_perf_map=btc_perf_map)

        # Synthèse Paire
        print(f"\n📊 Bilan {target_year} {SYMBOL}:")
        if res_q4: print(f"   Q4: {res_q4['performance']:+.2f}% ({res_q4['trades']} trades)")
        if res_q3: print(f"   Q3: {res_q3['performance']:+.2f}% ({res_q3['trades']} trades)")
        if res_q2: print(f"   Q2: {res_q2['performance']:+.2f}% ({res_q2['trades']} trades)")
        if res_q1: print(f"   Q1: {res_q1['performance']:+.2f}% ({res_q1['trades']} trades)")
