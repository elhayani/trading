
    def run_cycle(self, symbol: str, btc_rsi: Optional[float] = None) -> Dict:
        # Resolve to canonical symbol early (Audit #V11.6.8)
        symbol = self.exchange.resolve_symbol(symbol)
        asset_class = classify_asset(symbol)  # Define early for logging
        
        logger.info(f'\n{"="*70}\n[INFO] CYCLE START: {symbol}\n{"="*70}')
        try:
            # 1. COOLDOWN CHECK (Anti-Spam)
            if self._is_in_cooldown(symbol):
                logger.info(f'[COOLDOWN] {symbol} is in cooldown. Skipping.')
                return {'symbol': symbol, 'status': 'COOLDOWN'}

            # Load positions and manage them (check SL/TP/exits)
            positions = self.persistence.load_positions()
            if positions: 
                self._manage_positions(positions)
                # Reload positions after management (some may have been closed)
                positions = self.persistence.load_positions()
            
            # CRITICAL: Check real Binance position before trusting DynamoDB
            real_positions = self._get_real_binance_positions()
            if symbol in real_positions:
                logger.warning(f'[REAL_POSITION] {symbol} already open on Binance (managed)')
                
                # CRITICAL FIX: Manage Binance positions even if not in DynamoDB
                if symbol not in positions:
                    # Create mock position from Binance data for management
                    mock_positions = self._create_mock_binance_position(symbol)
                    if mock_positions:
                        # MERGE au lieu de REPLACE
                        positions.update(mock_positions)
                        # Sauvegarder la position récupérée en DynamoDB pour éviter re-création
                        # Note: mock_positions contains fully structured position dict keyed by symbol
                        self.persistence.save_position(symbol, mock_positions[symbol])
                        logger.info(f'[RECOVERY_SAVED] {symbol} synced to DynamoDB')
                        
                        # Gérer immédiatement la nouvelle position récupérée
                        self._manage_positions(positions)
                
                self.persistence.log_skipped_trade(symbol, 'Position already open on Binance', asset_class)
                return {'symbol': symbol, 'status': 'IN_POSITION_BINANCE'}
            
            if symbol in positions:
                logger.info(f'[INFO] Skip: Already in position for {symbol}')
                self.persistence.log_skipped_trade(symbol, 'Position already in DynamoDB', asset_class)
                return {'symbol': symbol, 'status': 'IN_POSITION'}
            
            # EMPIRE V13.0: REPLACE_LOW_PRIORITY - Flash Exit for USDC/USDT parking position
            # If USDC/USDT (forex) is open and a high-priority opportunity appears, eject immediately
            usdc_position = positions.get('USDC/USDT:USDT')
            if usdc_position and usdc_position.get('asset_class') == 'forex':
                # Check if current symbol is high-priority (crypto or commodity) with strong signal
                if asset_class in ['crypto', 'commodities']:
                    # Get quick score for current symbol
                    ohlcv_quick = self._get_ohlcv_smart(symbol, '1h')
                    ta_quick = analyze_market(ohlcv_quick, symbol=symbol, asset_class=asset_class)
                    quick_score = ta_quick.get('score', 0)
                    
                    if quick_score > 85:  # High-priority opportunity detected
                        logger.warning(f'[FLASH_EXIT] Ejecting USDC parking position for {symbol} (score: {quick_score})')
                        try:
                            # Close USDC immediately (market order)
                            usdc_direction = usdc_position.get('direction', 'LONG')
                            usdc_side = 'sell' if usdc_direction == 'LONG' else 'buy'
                            usdc_qty = usdc_position.get('quantity', 0)
                            
                            exit_order = self.exchange.create_market_order('USDC/USDT:USDT', usdc_side, usdc_qty)
                            exit_price = float(exit_order.get('average', 0))
                            
                            # Calculate PnL
                            entry_price = float(usdc_position.get('entry_price', 0))
                            if usdc_direction == 'LONG':
                                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                            else:
                                pnl_pct = ((entry_price - exit_price) / entry_price) * 100
                            
                            pnl = self.risk_manager.close_trade('USDC/USDT:USDT', exit_price)
                            
                            reason = f'Flash Exit for priority {symbol} (score: {quick_score}, USDC PnL: {pnl_pct:+.2f}%)'
                            self.persistence.log_trade_close(usdc_position['trade_id'], exit_price, pnl, reason)
                            self.persistence.delete_position('USDC/USDT:USDT')
                            self.atomic_persistence.atomic_remove_risk('USDC/USDT:USDT', float(usdc_position.get('risk_dollars', 0)))
                            
                            del positions['USDC/USDT:USDT']
                            balance = self.exchange.get_balance_usdt()  # Refresh balance
                            
                            logger.info(f'[FLASH_EXIT] USDC closed, capital freed: ${balance:.0f}')
                        except Exception as e:
                            logger.error(f'[ERROR] Flash exit failed: {e}')
            
            # Get balance early (needed for trim check and later logic)
            balance = self.exchange.get_balance_usdt()
            if balance < 10: raise ValueError('Insufficient balance ( < $10 )')
            
            # TRIM & SWITCH: Check if we should reduce existing positions for better opportunities
            # Only if we have positions AND low available capital
            if positions and balance < 500:  # Less than $500 available
                logger.info(f'[TRIM_CHECK] Low capital (${balance:.0f}), checking for better opportunities...')
            
            # Smart OHLCV Fetching (Audit #V11.5)
            ohlcv = self._get_ohlcv_smart(symbol, '1h')
            # Fix D: pass the V15 pre-score so analyze_market can use it as bonus
            _v15_score = getattr(self, '_scanner_scores', {}).get(symbol, 0)
            ta_result = analyze_market(ohlcv, symbol=symbol, asset_class=asset_class, scanner_score=_v15_score)
            
            # FIX #3: Score=0 means metrics calculation totally failed (silent exception in
            # calculate_all_metrics or analyze_market). Bail early — no useful signal to log.
            _early_score = ta_result.get('score', -1)
            if _early_score == 0 and ta_result.get('signal_type') == 'NEUTRAL':
                reason = f'Metrics failure (score=0) - no reliable data for {symbol}'
                logger.warning(f'[METRICS_FAIL] {symbol}: {reason}')
                self.persistence.log_skipped_trade(symbol, reason, asset_class)
                return {'symbol': symbol, 'status': 'METRICS_FAILURE', 'reason': reason}

            if ta_result.get('market_context', '').startswith('VOLATILITY_SPIKE'):
                # 🏛️ EMPIRE V15: High Volatility is Opportunity (if score is high)
                spike_score = ta_result.get('score', 0)
                reason = ta_result['market_context']
                
                if spike_score < 80:
                    self.persistence.log_skipped_trade(symbol, reason, asset_class)
                    return {'symbol': symbol, 'status': 'BLOCKED_SPIKE', 'reason': reason}
                else:
                    logger.info(f'[VOLATILITY_OPPORTUNITY] {symbol} Spike {reason} but Score {spike_score} > 80 - PROCEEDING')
            
            # OPT 4: Hard 2s timeout on news fetch via ThreadPoolExecutor.
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _news_ex:
                    _news_future = _news_ex.submit(
                        self.news_fetcher.get_news_sentiment_score, symbol
                    )
                    news_score = _news_future.result(timeout=2.0)
            except Exception:
                news_score = 0.0
            macro = macro_context.get_macro_context(state_table=self.aws.state_table)
            
            direction = 'SHORT' if ta_result.get('signal_type') == 'SHORT' else 'LONG'
            
            # FIX B: Force direction on RSI extremes (even if signal is NEUTRAL due to score)
            # This ensures VWAP and other filters check the correct side of the trade
            rsi_chk = ta_result.get('indicators', {}).get('rsi', 50)
            if rsi_chk > 70: direction = 'SHORT'
            elif rsi_chk < 30: direction = 'LONG'
            
            # 🏛️ EMPIRE V15: VWAP Anti-Suicide Filter (Config-based)
            dist_vwap = ta_result.get('dist_vwap', 0)
            _scanner_score = ta_result.get('score', 0)

            if direction == 'SHORT' and dist_vwap > TradingConfig.VWAP_SHORT_MAX_DIST:
                reason = f'VWAP Filter: Price above VWAP (+{dist_vwap:.2f}%) - Unsafe Short'
                self.persistence.log_skipped_trade(symbol, reason, asset_class)
                logger.info(f'[VWAP_BLOCK] {symbol} {reason}')
                return {'symbol': symbol, 'status': 'BLOCKED_VWAP', 'reason': reason}

            if direction == 'LONG' and dist_vwap < TradingConfig.VWAP_LONG_MIN_DIST:
                # FIX #2: High-conviction signals on alts can legitimately be below VWAP
                if _scanner_score >= 65:
                    logger.info(f'[VWAP_ALLOW] {symbol} below VWAP ({dist_vwap:.2f}%) but high score ({_scanner_score}) - allowing')
                else:
                    reason = f'VWAP Filter: Price below VWAP ({dist_vwap:.2f}%) - Unsafe Long'
                    self.persistence.log_skipped_trade(symbol, reason, asset_class)
                    logger.info(f'[VWAP_BLOCK] {symbol} {reason}')
                    return {'symbol': symbol, 'status': 'BLOCKED_VWAP', 'reason': reason}
            
            # 🆕 EMPIRE V15.1: ADX Trend Filter
            adx_raw = ta_result.get('adx')
            adx = adx_raw if adx_raw is not None else None
            di_plus = ta_result.get('indicators', {}).get('di_plus', 0)
            di_minus = ta_result.get('indicators', {}).get('di_minus', 0)
            
            if adx is None:
                logger.warning(f'[ADX_SKIP] {symbol}: ADX not available in ta_result, bypassing ADX filter')
                adx = 0
                _adx_filter_active = False
            else:
                _adx_filter_active = True

            if _adx_filter_active and adx < TradingConfig.ADX_MIN_TREND:
                score = ta_result.get('score', 0)
                if score < 60:
                    reason = f'ADX Filter: Weak trend (ADX={adx:.1f} < {TradingConfig.ADX_MIN_TREND}) - Waiting for momentum'
                    logger.info(f'[ADX_BLOCK] {symbol} {reason}')
                    self.persistence.log_skipped_trade(symbol, reason, asset_class)
                    return {'symbol': symbol, 'status': 'BLOCKED_ADX', 'reason': reason}

            if ta_result.get('signal_type') == 'NEUTRAL':
                # Build meaningful skip reason
                rsi = ta_result.get('rsi', 50)
                score = ta_result.get('score', 0)
                
                # EMPIRE V13.2: USDC/USDT low-priority entry logic (Optimized)
                if asset_class == 'stable' and 'USDC' in symbol:
                    if score < 30:
                         reason = 'USDC score too low (<30), skip priority check'
                         self.persistence.log_skipped_trade(symbol, reason, asset_class)
                         return {'symbol': symbol, 'status': 'LOW_PRIORITY_BLOCKED', 'reason': reason}

                    priority_symbols = [
                        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'XRP/USDT:USDT', 'BNB/USDT:USDT',  # Leaders (5)
                        'DOGE/USDT:USDT', 'AVAX/USDT:USDT', 'LINK/USDT:USDT', 'PAXG/USDT:USDT', 'SPX/USDT:USDT' 
                    ]
                    all_calm = True
                    
                    for priority_sym in priority_symbols:
                        if priority_sym in positions:
                            all_calm = False
                            break
                        try:
                            priority_ohlcv = self._get_ohlcv_smart(priority_sym, '1h')
                            priority_ta = analyze_market(priority_ohlcv, symbol=priority_sym, asset_class=classify_asset(priority_sym))
                            priority_score = priority_ta.get('score', 0)
                            
                            if priority_score >= 50:
                                all_calm = False
                                logger.info(f'[USDC_SKIP] {priority_sym} has score {priority_score} >= 50, skipping USDC parking')
                                break
                        except:
                            pass
                    
                    if not all_calm:
                        reason = 'Priority assets active (score >= 50), USDC parking not needed'
                        self.persistence.log_skipped_trade(symbol, reason, asset_class)
                        return {'symbol': symbol, 'status': 'LOW_PRIORITY_BLOCKED', 'reason': reason}
                    else:
                        logger.info(f'[USDC_PARKING] All priority assets calm, allowing USDC entry as parking position')
                else:
                    reasons = []
                    if rsi > 70:
                        reasons.append(f'RSI > 70 (overbought: {rsi:.1f})')
                    elif rsi < 30:
                        reasons.append(f'RSI < 30 (oversold: {rsi:.1f})')
                    else:
                        reasons.append(f'RSI neutral ({rsi:.1f})')

                    if score < 50:
                        rsi_val = ta_result.get('indicators', {}).get('rsi', 0)
                        vol_ratio = ta_result.get('indicators', {}).get('vol_ratio', 0)
                        context = ta_result.get('market_context', 'N/A')
                        reasons.append(f'Low Score ({score}/100) -> RSI:{rsi_val:.1f}, Vol:{vol_ratio:.1f}x, Ctx:{context}')
                    
                    if 'volume_spike' in ta_result.get('market_context', ''):
                        reasons.append('Low volume')
                    
                    trend = ta_result.get('market_context', '')
                    if 'Trend=' in trend:
                        try:
                            trend_val = trend.split('Trend=')[1].split('|')[0].strip()
                            if trend_val == 'SIDEWAYS':
                                reasons.append('Sideways trend')
                        except: pass
                    
                    reason = ' | '.join(reasons) if reasons else f'No clear signal (RSI={rsi:.1f}, Score={score})'
                    logger.info(f'[NO_SIGNAL] {symbol} skipped: {reason}')
                    self.persistence.log_skipped_trade(symbol, reason, asset_class)
                    return {'symbol': symbol, 'status': 'NO_SIGNAL', 'score': score, 'reason': reason}

            history_context = self.persistence.get_history_context()

            decision = self.decision_engine.evaluate_with_risk(
                context=macro, ta_result=ta_result, symbol=symbol,
                capital=balance, direction=direction, asset_class=asset_class,
                news_score=news_score, macro_regime=macro.get('regime', 'NORMAL'),
                btc_rsi=btc_rsi,
                history_context=history_context
            )
            
            if not decision['proceed']:
                logger.info(f'[INFO] Blocked: {decision["reason"]}')
                self.persistence.log_skipped_trade(symbol, decision['reason'], asset_class)
                return {'symbol': symbol, 'status': 'BLOCKED', 'reason': decision['reason']}
            
            real_positions = self._get_real_binance_positions()
            open_count = max(len(positions), len(real_positions))
            
            if open_count >= TradingConfig.MAX_OPEN_TRADES:
                if self._evaluate_early_exit_for_opportunity(positions, symbol, ta_result, decision):
                    open_count -= 1
                    logger.info(f'[EARLY_EXIT_SUCCESS] Slot freed for {symbol}')
                else:
                    reason = f'MAX_OPEN_TRADES reached ({open_count}/{TradingConfig.MAX_OPEN_TRADES})'
                    logger.warning(f'[SLOT_FULL] {reason}')
                    self.persistence.log_skipped_trade(symbol, reason, asset_class)
                    return {'symbol': symbol, 'status': 'SLOT_FULL', 'reason': reason}
            
            if positions and balance < 500 and decision['confidence'] >= 0.75:
                trim_result = self._evaluate_trim_and_switch(positions, symbol, decision, balance)
                if trim_result['action'] == 'TRIMMED':
                    balance = trim_result['freed_capital']
                    logger.info(f'[TRIM_SUCCESS] Freed ${balance:.0f} for {symbol} opportunity')
            
            return self._execute_entry(symbol, direction, decision, ta_result, asset_class, balance)
            
        except Exception as e:
            logger.error(f'[ERROR] Cycle error: {e}')
            return {'symbol': symbol, 'status': 'ERROR', 'error': str(e)}
    
    def _execute_entry(self, symbol, direction, decision, ta_result, asset_class, balance):
        # 1. Lock atomique AVANT tout
        lock_key = f'ENTRY_LOCK#{symbol}'
        lock_ttl = 30  # 30 secondes max
        
        try:
            self.aws.state_table.put_item(
                Item={
                    'trader_id': lock_key,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'ttl': int(time.time()) + lock_ttl
                },
                ConditionExpression='attribute_not_exists(trader_id)'
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(f'[LOCK_DENIED] {symbol} entry already in progress by another Lambda')
                return {'symbol': symbol, 'status': 'LOCK_CONFLICT', 'reason': 'Entry already in progress'}
            raise
        
        try:
            binance_pos = self._get_binance_position_detail(symbol)
            if binance_pos:
                reason = f'BINANCE_SYNC: Position already exists ({binance_pos["side"]} {binance_pos["quantity"]} @ ${binance_pos["entry_price"]:.2f})'
                logger.warning(f'[BINANCE_BLOCK] {symbol} — {reason}')
                self.persistence.log_skipped_trade(symbol, reason, asset_class)
                return {'symbol': symbol, 'status': 'BINANCE_ALREADY_OPEN', 'reason': reason}
            
            trade_id = f'V11-{uuid.uuid4().hex[:8]}'
            side = 'sell' if direction == 'SHORT' else 'buy'
            quantity = decision['quantity']
            
            market_info = self.exchange.get_market_info(symbol)
            min_amount = market_info.get('min_amount', 0)
            if quantity < min_amount: quantity = min_amount

            is_paxg = 'PAXG' in symbol
            leverage = TradingConfig.PAXG_LEVERAGE if is_paxg else TradingConfig.LEVERAGE
            
            try:
                order = self.exchange.create_market_order(symbol, side, quantity, leverage=leverage)
                real_entry = float(order.get('average', ta_result['price']))
                real_size = float(order.get('filled', quantity))
                
                theoretical_price = float(ta_result['price'])
                slippage_pct = abs((real_entry - theoretical_price) / theoretical_price) * 100
                
                if slippage_pct > 0.1:
                    logger.warning(f'⚠️ [TACTICAL_ALERT] High Entry Slippage: {slippage_pct:.3f}% for {symbol}')
                else:
                    logger.info(f'[OK] {direction} filled: {real_size} @ ${real_entry:.2f} (Slippage: {slippage_pct:.3f}%)')
                    
            except Exception as e:
                logger.error(f'[ERROR] Order failed: {e}')
                return {'symbol': symbol, 'status': 'ORDER_FAILED', 'error': str(e)}
            
            success, reason = self.atomic_persistence.atomic_check_and_add_risk(
                symbol=symbol,
                risk_dollars=decision['risk_dollars'],
                capital=balance,
                entry_price=real_entry,
                quantity=real_size,
                direction=direction
            )
            
            if not success:
                logger.error(f'[ALERT] Atomic risk check failed: {reason}. Attempting order rollback...')
                try:
                    rollback_side = 'sell' if direction == 'LONG' else 'buy'
                    self.exchange.create_market_order(symbol, rollback_side, real_size, leverage=leverage)
                    logger.info(f'[OK] Emergency rollback executed for {symbol}')
                except Exception as rollback_err:
                    logger.error(f'[CRITICAL] ROLLBACK FAILED: {rollback_err}')
                self.persistence.log_skipped_trade(symbol, reason, asset_class)
                return {'symbol': symbol, 'status': 'BLOCKED_ATOMIC', 'reason': reason}
            
            if is_paxg:
                tp_pct = TradingConfig.PAXG_TP
                sl_base = TradingConfig.PAXG_SL
                logger.info(f'[PAXG] Gold mode: Leverage {leverage}x | TP {tp_pct*100:.2f}% | SL {sl_base*100:.2f}%')
            elif asset_class == 'indices':
                tp_pct = TradingConfig.INDICES_TP
                sl_base = TradingConfig.INDICES_SL
                logger.info(f'[INDICES] Micro-Scalp: Leverage {leverage}x | TP {tp_pct*100:.2f}% | SL {sl_base*100:.2f}%')
            elif asset_class == 'forex':
                tp_pct = TradingConfig.FOREX_TP
                sl_base = TradingConfig.FOREX_SL
                logger.info(f'[FOREX] Micro-Scalp: Leverage {leverage}x | TP {tp_pct*100:.2f}% | SL {sl_base*100:.2f}%')
            else:
                tp_pct = TradingConfig.SCALP_TP_MIN 
                sl_base = TradingConfig.SCALP_SL if direction == 'LONG' else getattr(TradingConfig, 'SCALP_SL_SHORT', 0.0025)
            
            atr_perc = ta_result.get('atr_perc', 0)
            atr_sl_raw = (atr_perc / 100) * TradingConfig.ATR_SL_MULTIPLIER
            atr_sl = min(atr_sl_raw, sl_base * 2.5)
            
            sl_pct = max(sl_base, atr_sl)
            
            if sl_pct > sl_base:
                logger.info(f'🏛️ [ATR_ADAPT] High Volatility (ATR={atr_perc:.2f}%) -> SL widened to {sl_pct*100:.2f}%')
            else:
                logger.info(f'[ATR_NORMAL] Low Volatility (ATR={atr_perc:.2f}%) -> Using base SL {sl_base*100:.2f}%')

            # 🏛️ EMPIRE V13.10: LADDER EXIT STRATEGY (70% @ 0.25%, 30% @ 0.50%)
            if getattr(TradingConfig, 'USE_PROGRESSIVE_EXIT', False):
                tp1_pct = getattr(TradingConfig, 'TP_QUICK', 0.0025)
                tp2_pct = getattr(TradingConfig, 'TP_FINAL', 0.0050)
                
                if direction == 'LONG':
                    tp1 = real_entry * (1 + tp1_pct)
                    tp2 = real_entry * (1 + tp2_pct)
                    sl = real_entry * (1 - sl_pct)
                else:
                    tp1 = real_entry * (1 - tp1_pct)
                    tp2 = real_entry * (1 - tp2_pct)
                    sl = real_entry * (1 + sl_pct)
                
                size_tp1 = real_size * getattr(TradingConfig, 'QUICK_EXIT_PERCENTAGE', 0.70)
                size_tp2 = real_size - size_tp1 
                
                logger.info(f'[LADDER] Entry: ${real_entry:.4f} | TP1: ${tp1:.4f} (Size: {size_tp1:.3f}) | TP2: ${tp2:.4f} (Size: {size_tp2:.3f}) | SL: ${sl:.4f}')
                self.exchange.create_ladder_exit_orders(symbol, side, real_size, sl, tp1, size_tp1, tp2, size_tp2)
                
                tp = tp1
                detailed_reason_suffix = " | LADDER_EXIT"
            else:
                tp = real_entry * (1 + tp_pct) if direction == 'LONG' else real_entry * (1 - tp_pct)
                sl = real_entry * (1 - sl_pct) if direction == 'LONG' else real_entry * (1 + sl_pct)
                
                logger.info(f'[SCALP] Entry: ${real_entry:.4f} | TP: ${tp:.4f} ({tp_pct*100:.2f}%) | SL: ${sl:.4f} ({sl_pct*100:.2f}%)')
                self.exchange.create_sl_tp_orders(symbol, side, real_size, sl, tp)
                detailed_reason_suffix = ""
            
            reason_parts = []
            if 'rsi' in ta_result:
                reason_parts.append(f'RSI={ta_result["rsi"]:.1f}')
            if ta_result.get('market_context'):
                reason_parts.append(ta_result['market_context'])
            if decision.get('confidence'):
                reason_parts.append(f'AI={decision["confidence"]*100:.0f}%')
            if 'score' in ta_result:
                reason_parts.append(f'Score={ta_result["score"]}')
            reason_parts.append(f'Lev={leverage}x')
            
            detailed_reason = (' | '.join(reason_parts) if reason_parts else decision.get('reason', 'Signal detected')) + detailed_reason_suffix
            
            self.persistence.log_trade_open(
                trade_id, symbol, asset_class, direction, real_entry, real_size,
                (real_size * real_entry) / leverage, tp, sl, leverage,
                reason=detailed_reason
            )
            
            pos_data = {
                'trade_id': trade_id, 'entry_price': real_entry, 'quantity': real_size,
                'direction': direction, 'stop_loss': sl, 'take_profit': tp,
                'asset_class': asset_class,
                'risk_dollars': decision['risk_dollars'],
                'score': ta_result.get('score', 0),
                'ai_score': int(decision.get('confidence', 0) * 100),
                'entry_time': datetime.now(timezone.utc).isoformat()
            }
            self.persistence.save_position(symbol, pos_data)
            
            self.risk_manager.register_trade(symbol, real_entry, real_size, decision['risk_dollars'], decision['stop_loss'], direction)
            self.persistence.save_risk_state(self.risk_manager.get_state())
            
            self._record_trade_timestamp(symbol)
            
            logger.info(f'[OK] Position opened atomically: {direction} {symbol}')
            return {'symbol': symbol, 'status': f'{direction}_OPEN', 'trade_id': trade_id}

        finally:
            try:
                self.aws.state_table.delete_item(Key={'trader_id': lock_key})
            except:
                pass
    
    def _is_in_cooldown(self, symbol: str) -> bool:
        """Check if symbol is in cooldown period (anti-spam protection)"""
        return is_in_cooldown(self.aws.state_table, symbol, self.cooldown_seconds)
    
    def _record_trade_timestamp(self, symbol: str):
        """Record trade timestamp for cooldown tracking"""
        record_trade_timestamp(self.aws.state_table, symbol)
    
    def _get_real_binance_positions(self) -> List[str]:
        """Get actual open positions from Binance (source of truth)"""
        return get_real_binance_positions(self.exchange)
    
    def _get_binance_position_detail(self, symbol: str) -> Optional[Dict]:
        """Get real position detail from Binance for a specific symbol. Returns None if no position."""
        try:
            ccxt_ex = self.exchange.exchange if hasattr(self.exchange, 'exchange') else self.exchange
            positions = ccxt_ex.fapiPrivateV2GetPositionRisk()
            binance_sym = symbol.replace('/USDT:USDT', 'USDT').replace('/', '')
            for pos in positions:
                if pos.get('symbol') == binance_sym:
                    qty = abs(float(pos.get('positionAmt', 0)))
                    if qty > 0:
                        return {
                            'quantity': qty,
                            'side': 'LONG' if float(pos['positionAmt']) > 0 else 'SHORT',
                            'entry_price': float(pos.get('entryPrice', 0)),
                            'unrealized_pnl': float(pos.get('unRealizedProfit', 0)),
                            'mark_price': float(pos.get('markPrice', 0)),
                            'leverage': int(pos.get('leverage', 1))
                        }
            return None
        except Exception as e:
            logger.error(f'[BINANCE_SYNC] Failed to get position detail for {symbol}: {e}')
            return None
    
    def _create_mock_binance_position(self, symbol: str) -> Dict:
        """Create mock position data for Binance-only positions to enable SL/TP management"""
        try:
            positions = self.exchange.fetch_positions([symbol])
            if not positions:
                return {}
            
            pos_data = positions[0]
            if float(pos_data.get('contracts', 0)) == 0:
                return {}
            
            current_price = float(pos_data.get('markPrice', pos_data.get('info', {}).get('markPrice', 0)))
            if current_price == 0:
                current_price = float(pos_data.get('info', {}).get('lastPrice', 0))
            
            raw_info = pos_data.get('info', {})
            entry_price = float(raw_info.get('entryPrice', pos_data.get('entryPrice', 0)))
            leverage = int(raw_info.get('leverage', 1))
            side = pos_data['side'].lower()
            
            if entry_price == 0:
                entry_price = float(pos_data.get('lastPrice', 0))
            
            is_paxg = 'PAXG' in symbol
            asset_class = classify_asset(symbol)
            
            if is_paxg:
                tp_pct = TradingConfig.PAXG_TP
                sl_pct = TradingConfig.PAXG_SL
            elif asset_class == 'indices':
                tp_pct = TradingConfig.INDICES_TP
                sl_pct = TradingConfig.INDICES_SL
            elif asset_class == 'forex':
                tp_pct = TradingConfig.FOREX_TP
                sl_pct = TradingConfig.FOREX_SL
            else:
                tp_pct = TradingConfig.SCALP_TP_MIN
                sl_pct = TradingConfig.SCALP_SL if side == 'long' else getattr(TradingConfig, 'SCALP_SL_SHORT', 0.0025)
            
            if side == 'long':
                tp = entry_price * (1 + tp_pct)
                sl = entry_price * (1 - sl_pct)
            else:
                tp = entry_price * (1 - tp_pct)
                sl = entry_price * (1 + sl_pct)
            
            mock_position = {
                'direction': side.upper(),
                'entry_price': entry_price,
                'quantity': float(pos_data['contracts']),
                'stop_loss': sl,
                'take_profit': tp,
                'leverage': leverage,
                'entry_time': datetime.now(timezone.utc).isoformat(),
                'trade_id': f'RECOVERY-{symbol.replace("/", "")}',
                'asset_class': classify_asset(symbol)
            }
            
            logger.warning(f'🏛️ [RECOVERY_MOCK] {symbol} synced from Binance | Entry: ${entry_price:.4f} | SL: ${sl:.4f} (PnL Target: -{sl_pct*100:.2f}%)')
            return {symbol: mock_position}
            
        except Exception as e:
            logger.error(f'[MOCK_ERROR] Failed to create mock position for {symbol}: {e}')
            return {}
    
    def _evaluate_trim_and_switch(self, positions: Dict, new_symbol: str, new_decision: Dict, current_balance: float) -> Dict:
        """Evaluate if we should trim existing positions for better opportunities"""
        return evaluate_trim_and_switch(
            self.exchange,
            self.persistence,
            positions,
            new_symbol,
            new_decision,
            current_balance
        )

    def _evaluate_early_exit_for_opportunity(self, positions: Dict, new_symbol: str, new_ta: Dict, new_decision: Dict) -> bool:
        """
        🏛️ EMPIRE RULE: "Early Exit for Opportunity" (75% / Score+)
        Allows closing a stagnating trade to free a slot for a much better one.
        """
        new_score = new_ta.get('score', 0)
        new_ai_score = int(new_decision.get('confidence', 0) * 100)
        
        candidates = []
        for symbol, pos in positions.items():
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = float(ticker['last'])
                entry_price = float(pos.get('entry_price', 0))
                direction = pos['direction']
                
                if direction == 'LONG':
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100
                else:
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100
                
                if not (-0.15 <= pnl_pct <= 0.15):
                    continue
                
                entry_time_str = pos.get('entry_time')
                if not entry_time_str: continue
                
                entry_time = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
                time_open_min = (datetime.now(timezone.utc) - entry_time).total_seconds() / 60
                
                asset_class = pos.get('asset_class', 'crypto')
                threshold_map = {
                    'crypto': 20,
                    'indices': 30,
                    'commodities': 90,
                    'forex': 60
                }
                max_time = threshold_map.get(asset_class, 60)
                time_trigger = max_time * 0.75
                
                if time_open_min < time_trigger:
                    continue
                
                old_score = pos.get('score', 0)
                old_ai_score = pos.get('ai_score', 0)
                
                score_better = (new_score >= old_score + 10)
                ai_better = (new_ai_score >= old_ai_score + 10)
                
                if score_better or ai_better:
                    candidates.append({
                        'symbol': symbol,
                        'pnl_pct': pnl_pct,
                        'time_open': time_open_min,
                        'delta_score': new_score - old_score,
                        'delta_ai': new_ai_score - old_ai_score,
                        'pos_data': pos
                    })
            except Exception as e:
                logger.error(f'[EARLY_EXIT_ERR] Failed to evaluate {symbol}: {e}')
                continue
        
        if not candidates:
            return False
            
        candidates.sort(key=lambda x: x['time_open'], reverse=True)
        winner = candidates[0]
        
        reason = f'EARLY_EXIT for {new_symbol}: {winner["symbol"]} stagnating ({winner["time_open"]:.0f}m, {winner["pnl_pct"]:+.2f}%)'
        logger.warning(f'🏛️ [EARLY_EXIT] {reason} | Score+{winner["delta_score"]}, AI+{winner["delta_ai"]}')
        
        return self._close_position(winner['symbol'], winner['pos_data'], reason)

    def _close_position(self, symbol: str, pos: Dict, reason: str) -> bool:
        """Unifie la logique de fermeture de position Binance + DynamoDB"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = float(ticker['last'])
            
            binance_detail = self._get_binance_position_detail(symbol)
            if not binance_detail:
                logger.error(f'[CLOSE_ERR] No position found on Binance for {symbol}')
                self.persistence.delete_position(symbol)
                return False
                
            real_qty = binance_detail['quantity']
            direction = pos['direction']
            exit_side = 'sell' if direction == 'LONG' else 'buy'
            
            exit_order = self.exchange.create_market_order(symbol, exit_side, real_qty)
            exit_price = float(exit_order.get('average', current_price))
            
            self.atomic_persistence.atomic_remove_risk(symbol, float(pos.get('risk_dollars', 0)))
            pnl = self.risk_manager.close_trade(symbol, exit_price)
            self.persistence.save_risk_state(self.risk_manager.get_state())
            self.persistence.log_trade_close(pos['trade_id'], exit_price, pnl, reason, is_test=pos.get('is_test', False))
            self.persistence.delete_position(symbol)
            
            self.exchange.cancel_all_orders(symbol)
            
            logger.info(f'[OK] Closed {symbol} | PnL: ${pnl:.2f}')
            return True
        except Exception as e:
            logger.error(f'[CLOSE_FAILED] {symbol}: {e}')
            return False
