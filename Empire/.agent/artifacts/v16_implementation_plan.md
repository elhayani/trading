# 🏛️ Empire V16.0 - Momentum Scalping Implementation Plan

## 📋 Executive Summary
**Objective**: Transform Empire from 30min mean-reversion to 1min pure momentum scalping
**Target**: 40-70 trades/day @ 55-60% win rate → +1% daily net
**Strategy**: EMA5/13 crossover + volume surge + price thrust on 1-minute timeframe

---

## 🎯 Phase 1: Configuration Overhaul (config.py)

### Changes Required:
1. **Remove Legacy Parameters**
   - ❌ Delete: `MIN_TECHNICAL_SCORE_*` (replaced by `MIN_MOMENTUM_SCORE`)
   - ❌ Delete: `VWAP_*`, `ADX_*` filters (not used in momentum)
   - ❌ Delete: News sentiment references

2. **Clarify Momentum Parameters**
   ```python
   # Momentum Strategy (1-minute pure momentum)
   LEVERAGE_BASE = 5              # Base leverage (adaptive 2-7)
   MAX_OPEN_TRADES = 3
   MIN_VOLUME_24H = 5_000_000     # $5M minimum
   
   # TP/SL Dynamic (ATR-based)
   TP_MULTIPLIER = 2.0            # TP = 2 × ATR_1min
   SL_MULTIPLIER = 1.0            # SL = 1 × ATR_1min
   MAX_HOLD_CANDLES = 10          # Force exit after 10 minutes
   
   # Momentum Indicators
   EMA_FAST = 5
   EMA_SLOW = 13
   VOLUME_SURGE_RATIO = 1.5
   MIN_MOMENTUM_SCORE = 60
   MIN_ATR_PCT_1MIN = 0.25
   
   # Compound
   USE_COMPOUND = True
   ```

3. **Add Missing Parameters**
   - `MAX_HOLD_MINUTES = 10` (explicit time limit)
   - `FORCE_EXIT_AFTER_CANDLES = 10`
   - `SESSION_BOOST_MULTIPLIER = 2.0` (max boost)

---

## 🎯 Phase 2: Risk Manager Adaptive Leverage Fix

### Current Issue:
```python
# risk_manager.py line 26-40
def get_adaptive_leverage(self, score: int, base_leverage: int = 5):
    if score >= 90: leverage = min(7, base_leverage + 2)   # ❌ 5+2=7 OK
    elif score >= 80: leverage = base_leverage              # ❌ 5 OK
    elif score >= 70: leverage = max(3, base_leverage - 2)  # ❌ 5-2=3 OK
    else: leverage = max(2, base_leverage - 3)              # ❌ 5-3=2 OK
```

### Fix Required:
```python
def get_adaptive_leverage(self, score: int) -> int:
    """
    V16 Adaptive Leverage (independent of base config)
    Score 90+: x7 (Elite signals)
    Score 80+: x5 (Strong signals)
    Score 70+: x3 (Good signals)
    Score 60+: x2 (Limit signals)
    """
    if score >= 90: return 7
    elif score >= 80: return 5
    elif score >= 70: return 3
    else: return 2
```

---

## 🎯 Phase 3: Market Analysis - Momentum Focus

### Current Issue:
- `analyze_market()` still uses RSI/ADX/VWAP scoring (30min logic)
- `analyze_momentum()` exists but not fully integrated

### Solution:
1. **Rename Functions**:
   - `analyze_market()` → `analyze_market_legacy()` (keep for fallback)
   - `analyze_momentum()` → `analyze_market()` (make it primary)

2. **Ensure ATR-based TP/SL**:
   ```python
   # market_analysis.py line 549-554
   if signal == 'LONG':
       tp_price = close_current + (atr_current * TradingConfig.TP_MULTIPLIER)
       sl_price = close_current - (atr_current * TradingConfig.SL_MULTIPLIER)
   else:  # SHORT
       tp_price = close_current - (atr_current * TradingConfig.TP_MULTIPLIER)
       sl_price = close_current + (atr_current * TradingConfig.SL_MULTIPLIER)
   ```

---

## 🎯 Phase 4: Trading Engine - Compound Capital Fix

### Current Issue:
```python
# trading_engine.py line 539
compound_capital=capital_actuel if TradingConfig.USE_COMPOUND else None
# ❌ NameError: 'capital_actuel' is not defined
```

### Fix Required:
```python
# Calculate compound capital from DynamoDB history
def get_compound_capital(self, base_capital: float) -> float:
    """
    Calculate current capital including realized PnL from closed trades.
    """
    try:
        # Query closed trades from last 24h
        response = self.aws.trades_table.query(
            IndexName='status-timestamp-index',
            KeyConditionExpression='#status = :closed',
            ExpressionAttributeNames={'#status': 'Status'},
            ExpressionAttributeValues={':closed': 'CLOSED'},
            ScanIndexForward=False,  # Most recent first
            Limit=100
        )
        
        total_pnl = sum(float(item.get('PnL', 0)) for item in response.get('Items', []))
        compound_capital = base_capital + total_pnl
        
        logger.info(f"[COMPOUND] Base: ${base_capital:.2f} + PnL: ${total_pnl:.2f} = ${compound_capital:.2f}")
        return max(base_capital, compound_capital)  # Never go below base
        
    except Exception as e:
        logger.error(f"[COMPOUND_ERROR] {e}")
        return base_capital
```

Then use:
```python
# trading_engine.py line 535-540
if TradingConfig.USE_COMPOUND:
    compound_capital = self.get_compound_capital(balance)
else:
    compound_capital = None

decision = self.decision_engine.evaluate_with_risk(
    ...
    compound_capital=compound_capital
)
```

---

## 🎯 Phase 5: Position Management - MAX_HOLD_CANDLES

### Current Issue:
- Time-based exit exists but uses hours (30min/1h logic)
- No enforcement of 10-candle (10-minute) max hold

### Fix Required:
```python
# trading_engine.py _manage_positions()
# Add after line 799:

# V16: MAX_HOLD_CANDLES enforcement (10 minutes = 10 candles)
if entry_time_str:
    entry_time = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
    time_open_minutes = (datetime.now(timezone.utc) - entry_time).total_seconds() / 60
    
    if time_open_minutes >= TradingConfig.MAX_HOLD_CANDLES:
        logger.warning(f"[MAX_HOLD] {symbol} held for {time_open_minutes:.1f}min (max: {TradingConfig.MAX_HOLD_CANDLES}min)")
        should_exit_time = True
        exit_reason = f"MAX_HOLD_{time_open_minutes:.0f}min"
```

---

## 🎯 Phase 6: Session Boost Integration

### Current Status:
- `get_session_boost()` exists in `lambda1_scanner.py`
- `calculate_elite_score_light()` uses session scoring
- **BUT**: Trading engine doesn't apply session boost to final decision

### Solution:
Session boost is already integrated in scanner's `elite_score`. No change needed in trading_engine since it trusts scanner data.

**Validation**: Ensure scanner's session component (10% weight) is properly calculated.

---

## 🎯 Phase 7: Scanner-Engine Integration

### Current Flow:
```
Scanner (lambda1_scanner.py)
  ├─ Phase 1: Server-side filter (415 → 150 symbols)
  ├─ Phase 2: Fetch 60 klines (1min)
  ├─ Phase 3: unified_mobility_check()
  ├─ Phase 4: calculate_elite_score_light()
  └─ Phase 5: Pass to trading_engine.run_cycle(scanner_data)

Trading Engine (trading_engine.py)
  ├─ Receives scanner_data with elite_score, direction, TP/SL
  ├─ ❌ PROBLEM: Calls analyze_momentum() again (duplicate work!)
  └─ Should: Trust scanner 100% and skip re-analysis
```

### Fix:
```python
# trading_engine.py line 478-503
if scanner_data:
    # ✅ Use scanner data directly (no re-analysis)
    ta_result = {
        'signal_type': scanner_data['direction'],
        'score': scanner_data['elite_score'],
        'price': scanner_data['current_price'],
        'atr': scanner_data['atr'],
        'tp_price': scanner_data['tp_price'],
        'sl_price': scanner_data['sl_price'],
        'volume_ratio': scanner_data['vol_ratio'],
        'volume_24h_usdt': scanner_data.get('volume_24h', 0),
        'blocked': False,
        'scanner_validated': True
    }
    signal_type = scanner_data['direction']
    # Skip NEUTRAL check - scanner already validated
else:
    # Fallback: should never happen
    raise ValueError("Scanner data required for V16 momentum strategy")
```

---

## 🎯 Phase 8: Performance Targets Update

### Current Config:
```python
TARGET_DAILY_RETURN = 0.01      # +1% per day ✅
TARGET_TRADES_PER_DAY = 12      # ❌ Should be 40-70
TARGET_WIN_RATE = 0.58          # ✅ 58% win rate
```

### Fix:
```python
# V16 Momentum Scalping Targets
TARGET_DAILY_RETURN = 0.01      # +1% per day
TARGET_TRADES_PER_DAY = 50      # 40-70 range (median)
TARGET_WIN_RATE = 0.58          # 58% win rate
TARGET_AVG_HOLD_TIME = 5        # 5 minutes average
```

---

## 📊 Validation Checklist

### Pre-Deployment:
- [ ] Config.py: All legacy parameters removed
- [ ] Risk Manager: Adaptive leverage independent of base
- [ ] Market Analysis: analyze_momentum() is primary
- [ ] Trading Engine: Compound capital properly calculated
- [ ] Position Management: MAX_HOLD_CANDLES enforced
- [ ] Scanner Integration: No duplicate analysis
- [ ] TP/SL: ATR-based (not percentage-based)
- [ ] Session Boost: Properly weighted in elite_score

### Post-Deployment Monitoring:
- [ ] Avg trades/day: 40-70 range
- [ ] Avg hold time: 2-10 minutes
- [ ] Win rate: 55-60%
- [ ] Daily return: +1% target
- [ ] Max drawdown: <5%
- [ ] Leverage distribution: 70% at x5-x7 (high conviction)

---

## 🚀 Deployment Order

1. **config.py** - Foundation (all parameters)
2. **risk_manager.py** - Adaptive leverage fix
3. **market_analysis.py** - Momentum primary
4. **trading_engine.py** - Compound capital + MAX_HOLD
5. **lambda1_scanner.py** - Validate session boost
6. **Test Integration** - Dry run 1 hour
7. **Deploy Live** - Monitor first 24h closely

---

## 🎯 Success Metrics (First 24h)

| Metric | Target | Acceptable | Red Flag |
|--------|--------|------------|----------|
| Trades Opened | 40-70 | 30-80 | <20 or >100 |
| Win Rate | 55-60% | 50-65% | <45% |
| Avg Hold Time | 5min | 2-10min | >15min |
| Daily Return | +1% | +0.5% to +2% | <0% or >3% |
| Max Drawdown | <5% | <7% | >10% |

---

**Status**: Ready for implementation
**Estimated Time**: 2-3 hours
**Risk Level**: Medium (significant strategy change)
**Rollback Plan**: Revert to V15.9 config if win rate <45% after 50 trades
