import logging
from typing import Dict, Optional, Union

# Absolute imports (Critique #1 New)
import config
from config import TradingConfig

logger = logging.getLogger(__name__)

class RiskManager:
    """
    Centralized risk management. Enforces portfolio limits & circuit breakers.
    """

    def __init__(self, commission_rate: float = None, slippage_buffer: float = None):
        self.daily_pnl = 0.0
        self.active_trades: Dict[str, Dict] = {}
        self.commission_rate = commission_rate or TradingConfig.COMMISSION_RATE
        self.slippage_buffer = slippage_buffer or TradingConfig.SLIPPAGE_BUFFER
        self._current_volume_24h = 0  # Volume 24h de l'actif en cours
    
    def set_current_volume_24h(self, volume_24h: float):
        """Définir le volume 24h pour la protection liquidité"""
        self._current_volume_24h = volume_24h
    
    def get_adaptive_leverage(self, score: int, vix: float = 20.0) -> int:
        """
        V16.7.8 Adaptive Leverage with VIX Volatility Adjustment.
        
        Returns leverage based on signal score and macro volatility:
        - Score 90+: x7 (Elite) -> Reduced by VIX
        - Score 80+: x5 (Strong)
        - Score 70+: x3 (Good)
        - Score 60+: x2 (Limit)
        
        Volatility Penalty:
        - VIX > 25: -1x leverage
        - VIX > 35: -2x leverage (Min 1x)
        """
        # Base leverage by score
        if score >= 90:
            base_lev = 7
        elif score >= 80:
            base_lev = 5
        elif score >= 70:
            base_lev = 3
        else:
            base_lev = 2
            
        # Volatility adjustment
        if vix > 35:
            base_lev -= 2
        elif vix > 25:
            base_lev -= 1
            
        # Hard floor at 1x
        leverage = max(1, base_lev)
        
        # Elite Protection: Score 95+ should stay at least 2x even if VIX is high
        if score >= 95:
            leverage = max(2, leverage)
            
        return int(leverage)

    def calculate_position_size(
        self,
        capital: float,
        entry_price: float,
        stop_loss_price: float,
        confidence: float = 1.0,
        atr: float = 0.0,
        direction: str = "LONG",
        leverage: float = None,
        compound_capital: float = None,
        signal_score: int = 60,
        symbol: str = "UNKNOWN",
        vix: float = 20.0
    ) -> Dict[str, Union[float, bool, str]]:
        # Convert all inputs to float to prevent Decimal/float arithmetic errors
        entry_price = float(entry_price)
        stop_loss_price = float(stop_loss_price)
        capital = float(capital)
        atr = float(atr)
        
        # 2. Si TradingConfig.USE_COMPOUND == True et compound_capital est fourni :
        if TradingConfig.USE_COMPOUND and compound_capital is not None:
            if compound_capital <= 0:
                logger.error(f"[RISK] Invalid compound_capital: {compound_capital}, using base capital")
                capital_to_use = capital
            else:
                capital_to_use = compound_capital
        else:
            capital_to_use = capital
        
        # Appliquer le levier adaptatif selon le score et la volatilité
        leverage = self.get_adaptive_leverage(signal_score, vix)
        logger.info(f"[LEVERAGE] Score {signal_score} | VIX {vix:.1f} → Leverage x{leverage}")
        
        if entry_price <= 0: return self._blocked("INVALID_ENTRY_PRICE", stop_loss_price)

        # 1. Daily loss circuit breaker
        if capital_to_use > 0 and abs(self.daily_pnl / capital_to_use) >= TradingConfig.MAX_DAILY_LOSS_PCT:
            return self._blocked("DAILY_LOSS_LIMIT", stop_loss_price)

        # 2. Puissance de Frappe (Striking Power) - 🏛️ EMPIRE V13.8
        # Logic: Position Size = (Capital / Slots) * Leverage * Confidence
        # This ensures that lev x3 means "3x the allocated margin"
        confidence = max(TradingConfig.MIN_CONFIDENCE, min(TradingConfig.MAX_CONFIDENCE, confidence))
        margin_per_slot = capital_to_use / TradingConfig.MAX_OPEN_TRADES
        target_notional = margin_per_slot * leverage * confidence
        quantity = target_notional / entry_price
        
        # 3. Protection liquidité - limiter le notionnel max
        volume_24h = getattr(self, '_current_volume_24h', 0)  # Volume 24h de l'actif
        if volume_24h > 0:
            max_notional = volume_24h * TradingConfig.MAX_NOTIONAL_PCT_OF_VOLUME
            actual_notional = quantity * entry_price
            
            if actual_notional > max_notional:
                # Réduire la taille pour respecter la limite de liquidité
                quantity = max_notional / entry_price
                logger.warning(f"[LIQUIDITY_CAP] {symbol} size capped at ${max_notional:.0f} (was ${actual_notional:.0f})")
                
                # Recalculer avec la nouvelle quantité
                target_notional = max_notional

        # 3. Risk budget and distance to stop
        eff_entry = entry_price * (1 + self.slippage_buffer) if direction == "LONG" else entry_price * (1 - self.slippage_buffer)
        price_risk = abs(eff_entry - stop_loss_price)
        
        min_risk = max(entry_price * 0.001, atr * 0.5) if atr > 0 else (entry_price * 0.001)
        if price_risk < min_risk: return self._blocked("STOP_TOO_TIGHT", stop_loss_price)

        # 4. Safety Cap: Do not exceed MAX_LOSS_PER_TRADE
        risk_budget = capital_to_use * TradingConfig.MAX_LOSS_PER_TRADE * confidence
        if price_risk > 0 and (margin_per_slot * leverage * price_risk) > risk_budget:
            return self._blocked("RISK_BUDGET_EXCEEDED", stop_loss_price)
        
        # 5. Garde-fou perte max par trade (2% par défaut, 3% pour Elite 95+)
        max_loss_pct = TradingConfig.MAX_LOSS_PER_TRADE_PCT
        if signal_score >= 95:
            max_loss_pct = max(max_loss_pct, 3.0) # Elite protection
            
        max_loss_usd = capital_to_use * (max_loss_pct / 100)
        sl_distance_pct = abs(entry_price - stop_loss_price) / entry_price
        max_notional = max_loss_usd / sl_distance_pct if sl_distance_pct > 0 else float('inf')
        actual_notional = margin_per_slot * leverage
        
        if actual_notional > max_notional:
            # Réduire le levier pour respecter la limite de perte max
            adaptive_leverage = leverage  # Sauvegarder le levier adaptatif original
            new_leverage = int(max_notional / margin_per_slot)
            new_leverage = max(1, new_leverage)
            
            # 🚨 V16.7.8 FIX: Alert when adaptive leverage is degraded
            if new_leverage < adaptive_leverage:
                logger.warning(f"🚨 [LEVERAGE_DEGRADED] {symbol} Score {signal_score}: Adaptive x{adaptive_leverage} → Capped x{new_leverage} (Max loss: ${max_loss_usd:.0f}, SL distance: {sl_distance_pct:.2%})")
                if signal_score >= 90:
                    logger.error(f"⚠️ [ELITE_DEGRADED] Elite signal (score {signal_score}) degraded from x{adaptive_leverage} to x{new_leverage}! Profitability at risk!")
            
            leverage = new_leverage
            # Recalculer avec le nouveau levier
            target_notional = margin_per_slot * leverage
            quantity = target_notional / entry_price

        # 5.1 Hard Cap: Do not exceed MAX_POSITION_SIZE_USDT (🏛️ EMPIRE V16.7.3)
        max_pos_size = getattr(TradingConfig, 'MAX_POSITION_SIZE_USDT', 2500)
        current_notional = quantity * entry_price
        if current_notional > max_pos_size:
            quantity = max_pos_size / entry_price
            logger.warning(f"[SIZE_CAP] {symbol} size capped at ${max_pos_size} (was ${current_notional:.0f})")

        # 6. Portfolio cap
        total_risk = sum(t["risk"] for t in self.active_trades.values())
        available_risk = (capital_to_use * TradingConfig.MAX_PORTFOLIO_RISK_PCT) - total_risk
        
        if available_risk <= 0: return self._blocked("PORTFOLIO_RISK_CAP", stop_loss_price)
        
        current_risk = quantity * price_risk
        if current_risk > available_risk:
            quantity = available_risk / price_risk
            current_risk = quantity * price_risk

        return {
            "quantity": quantity,
            "leverage": leverage,
            "adaptive_leverage": leverage,  # Levier adaptatif final
            "risk": current_risk,
            "confidence": confidence,
            "blocked": False,
            "reason": "PROCEED"
        }

    @staticmethod
    def calculate_stop_loss(entry_price: float, atr: float, direction: str = "LONG", multiplier: float = None) -> float:
        # Convert to float to avoid Decimal/float operation errors
        entry_price = float(entry_price)
        atr = float(atr)
        mult = multiplier if multiplier is not None else TradingConfig.SL_MULTIPLIER
        
        # Calculate distance based on ATR
        if atr > 0:
            dist_atr = atr * mult
        else:
            dist_atr = 0
            
        # Enforce MIN_SL_PCT floor (conflit ATR vs Fixe)
        min_dist = entry_price * getattr(TradingConfig, 'MIN_SL_PCT', 0.0045)
        final_dist = max(dist_atr, min_dist)
        
        return round(entry_price - final_dist if direction == "LONG" else entry_price + final_dist, 8)

    def register_trade(self, symbol: str, entry: float, qty: float, risk: float, sl: float, direction: str):
        self.active_trades[symbol] = {"entry": entry, "size": qty, "risk": risk, "stop_loss": sl, "direction": direction}

    def close_trade(self, symbol: str, exit_price: float) -> float:
        if symbol not in self.active_trades: return 0.0
        t = self.active_trades.pop(symbol)
        pnl = (exit_price - t["entry"]) * t["size"] if t["direction"] == "LONG" else (t["entry"] - exit_price) * t["size"]
        self.daily_pnl += pnl
        return pnl

    def reset_daily(self):
        self.daily_pnl = 0.0

    def _blocked(self, reason: str, sl: float) -> Dict:
        return {"quantity": 0, "risk_dollars": 0, "stop_loss": sl, "blocked": True, "reason": reason}

    def get_state(self) -> Dict: return {"daily_pnl": self.daily_pnl, "active_trades": self.active_trades}
    def load_state(self, state: Dict):
        if not state: return
        self.daily_pnl = float(state.get("daily_pnl", 0.0))
        self.active_trades = state.get("active_trades", {})
