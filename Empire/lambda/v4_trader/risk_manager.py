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

    def calculate_position_size(
        self,
        capital: float,
        entry_price: float,
        stop_loss_price: float,
        confidence: float = 1.0,
        atr: float = 0.0,
        direction: str = "LONG",
        leverage: float = None
    ) -> Dict[str, Union[float, bool, str]]:
        # Convert all inputs to float to prevent Decimal/float arithmetic errors
        entry_price = float(entry_price)
        stop_loss_price = float(stop_loss_price)
        capital = float(capital)
        atr = float(atr)
        
        # Force leverage to 1 for scalping safety (or use config default)
        leverage = leverage or TradingConfig.LEVERAGE
        logger.info(f"[SCALPING] Using leverage: {leverage}x")
        
        if entry_price <= 0: return self._blocked("INVALID_ENTRY_PRICE", stop_loss_price)

        # 1. Daily loss circuit breaker
        if capital > 0 and abs(self.daily_pnl / capital) >= TradingConfig.MAX_DAILY_LOSS_PCT:
            return self._blocked("DAILY_LOSS_LIMIT", stop_loss_price)

        # 2. Risk budget
        confidence = max(TradingConfig.MIN_CONFIDENCE, min(TradingConfig.MAX_CONFIDENCE, confidence))
        risk_budget = capital * TradingConfig.MAX_LOSS_PER_TRADE * confidence

        # 3. Distance to stop
        eff_entry = entry_price * (1 + self.slippage_buffer) if direction == "LONG" else entry_price * (1 - self.slippage_buffer)
        price_risk = abs(eff_entry - stop_loss_price)
        
        min_risk = max(entry_price * 0.001, atr * 0.5) if atr > 0 else (entry_price * 0.001)
        if price_risk < min_risk: return self._blocked("STOP_TOO_TIGHT", stop_loss_price)

        quantity = risk_budget / price_risk

        # 4. Portfolio cap (Note: Atomic layer in persistence handles concurrent enforce)
        total_risk = sum(t["risk"] for t in self.active_trades.values())
        available = (capital * TradingConfig.MAX_PORTFOLIO_RISK_PCT) - total_risk
        
        if available <= 0: return self._blocked("PORTFOLIO_RISK_CAP", stop_loss_price)
        if risk_budget > available:
            risk_budget = available
            quantity = risk_budget / price_risk

        return {
            "quantity": round(quantity, 8),
            "risk_dollars": round(risk_budget, 2),
            "stop_loss": stop_loss_price,
            "estimated_commission": round(quantity * entry_price * self.commission_rate * 2, 2),
            "blocked": False, "reason": "OK", "direction": direction
        }

    @staticmethod
    def calculate_stop_loss(entry_price: float, atr: float, direction: str = "LONG", multiplier: float = 2.0) -> float:
        # Convert to float to avoid Decimal/float operation errors
        entry_price = float(entry_price)
        atr = float(atr)
        
        if atr <= 0: return round(entry_price * (0.98 if direction == "LONG" else 1.02), 8)
        dist = atr * multiplier
        return round(entry_price - dist if direction == "LONG" else entry_price + dist, 8)

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
