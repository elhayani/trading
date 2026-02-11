"""
Empire Risk Manager V11 - Production Grade
==========================================
ATR-based dynamic Stop Loss, position sizing by risk budget,
daily loss circuit breaker, and portfolio-level exposure cap.
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Centralized risk management for all trade entries.
    Enforces:
      - Max 2% loss per trade
      - Max 5% daily loss
      - Max 20% portfolio at risk simultaneously
      - ATR-based dynamic stop-loss
      - Commission-aware sizing
    """

    # ── Risk Limits ──────────────────────────────────────────────
    MAX_LOSS_PER_TRADE = 0.02   # 2% of capital per trade
    MAX_DAILY_LOSS     = 0.05   # 5% of capital per day
    MAX_PORTFOLIO_RISK = 0.20   # 20% of capital in open risk
    COMMISSION_RATE    = 0.001  # 0.1% per leg (Binance maker fee)

    def __init__(self):
        self.daily_pnl = 0.0
        self.active_trades: Dict[str, Dict] = {}

    # ── Position Sizing ──────────────────────────────────────────
    def calculate_position_size(
        self,
        capital: float,
        entry_price: float,
        stop_loss_price: float,
        confidence: float = 1.0,
        atr: float = 0.0  # Audit Fix: Needed for robust stop check
    ) -> Dict:
        """
        Risk-based position sizing.
        Returns: {quantity, risk_dollars, stop_loss, estimated_commission, blocked, reason}
        """

        # 1. Daily loss circuit breaker
        if capital > 0 and abs(self.daily_pnl / capital) >= self.MAX_DAILY_LOSS:
            logger.error(
                f"🛑 Daily loss limit reached: {self.daily_pnl:.2f} / {capital:.2f}"
            )
            return self._blocked("DAILY_LOSS_LIMIT", stop_loss_price)

        # 2. Per-trade risk budget (capped by confidence 0.3-1.0)
        confidence = max(0.3, min(1.0, confidence))
        risk_budget = capital * self.MAX_LOSS_PER_TRADE * confidence

        # 3. Distance to stop (price risk per unit)
        price_risk = abs(entry_price - stop_loss_price)
        
        # Audit Fix: Use ATR-based floor if available, else 0.1% dynamic floor (C1)
        min_risk_threshold = max(entry_price * 0.001, atr * 0.5) if atr > 0 else (entry_price * 0.001)
        
        if price_risk < min_risk_threshold: 
            logger.error(f"🛑 Stop loss too close ({price_risk:.4f} < {min_risk_threshold:.4f} [ATR={atr:.2f}])")
            return self._blocked("STOP_TOO_TIGHT", stop_loss_price)

        quantity = risk_budget / price_risk

        # 4. Portfolio-level exposure cap
        total_risk = sum(t["risk"] for t in self.active_trades.values())
        available = (capital * self.MAX_PORTFOLIO_RISK) - total_risk
        if available <= 0:
            logger.warning("🛑 Portfolio risk cap reached → blocking trade")
            return self._blocked("PORTFOLIO_RISK_CAP", stop_loss_price)

        if risk_budget > available:
            logger.warning(
                f"⚠️ Reducing size: risk {risk_budget:.2f} > available {available:.2f}"
            )
            risk_budget = available
            quantity = risk_budget / price_risk

        # 5. Commission check (round-trip)
        gross_value = quantity * entry_price
        commission = gross_value * self.COMMISSION_RATE * 2  # buy + sell
        if commission > risk_budget * 0.5:
            # Commission eats > 50% of risk budget → trade not worth it
            logger.warning(
                f"⚠️ Commission ${commission:.2f} > 50% of risk ${risk_budget:.2f} → shrinking"
            )
            quantity *= 0.5
            commission = quantity * entry_price * self.COMMISSION_RATE * 2

        return {
            "quantity": round(quantity, 8),
            "risk_dollars": round(risk_budget, 2),
            "stop_loss": stop_loss_price,
            "estimated_commission": round(commission, 2),
            "blocked": False,
            "reason": "OK",
        }

    # ── Dynamic Stop-Loss ────────────────────────────────────────
    @staticmethod
    def calculate_stop_loss(
        entry_price: float,
        atr: float,
        direction: str = "LONG",
        multiplier: float = 2.0,
    ) -> float:
        """
        ATR-based dynamic stop-loss.
        multiplier=2.0 → 2× ATR distance (industry standard).
        """
        if atr <= 0:
            # Fallback: fixed 2% stop
            fallback_pct = 0.02
            logger.warning("⚠️ ATR ≤ 0 → using fixed 2% stop")
            return (
                entry_price * (1 - fallback_pct)
                if direction == "LONG"
                else entry_price * (1 + fallback_pct)
            )

        distance = atr * multiplier
        if direction == "LONG":
            return round(entry_price - distance, 8)
        else:
            return round(entry_price + distance, 8)

    # ── Trade Lifecycle ──────────────────────────────────────────
    def register_trade(
        self, symbol: str, entry_price: float, quantity: float, risk_dollars: float, stop_loss: float = 0.0
    ):
        """Register an active trade for portfolio risk tracking."""
        self.active_trades[symbol] = {
            "entry": entry_price,
            "size": quantity,
            "risk": risk_dollars,
            "stop_loss": stop_loss  # Track for trailing stop
        }
        logger.info(f"✅ RiskManager: {symbol} registered | Risk: ${risk_dollars:.2f} | SL: ${stop_loss:.2f}")

    def update_trailing_stop(
        self,
        symbol: str,
        current_price: float,
        atr: float,
        direction: str = "LONG",
        trail_mult: float = 2.0
    ) -> float:
        """
        Update trailing stop-loss to lock in profits.
        Returns the new stop-loss price.
        """
        if symbol not in self.active_trades:
            return 0.0
        
        trade = self.active_trades[symbol]
        current_sl = trade.get("stop_loss", 0.0)
        
        if direction == "LONG":
            # Only move SL up
            new_sl = current_price - (atr * trail_mult)
            if new_sl > current_sl:
                trade["stop_loss"] = new_sl
                logger.info(f"📈 Trailing stop updated: {symbol} ${current_sl:.2f} → ${new_sl:.2f}")
                return new_sl
        else:  # SHORT
            # Only move SL down
            new_sl = current_price + (atr * trail_mult)
            # If current_sl is 0 (uninitialized), we accept the new one. 
            # Otherwise, new_sl must be lower than current_sl
            if current_sl == 0.0 or new_sl < current_sl:
                trade["stop_loss"] = new_sl
                logger.info(f"📉 Trailing stop updated: {symbol} ${current_sl:.2f} → ${new_sl:.2f}")
                return new_sl
        
        return current_sl

    def close_trade(self, symbol: str, exit_price: float) -> float:
        """Close trade, update daily PnL, return realized PnL."""
        if symbol not in self.active_trades:
            logger.warning(f"⚠️ RiskManager: unknown trade {symbol}")
            return 0.0

        trade = self.active_trades.pop(symbol)
        pnl = (exit_price - trade["entry"]) * trade["size"]
        self.daily_pnl += pnl
        logger.info(
            f"🔒 RiskManager: {symbol} closed | PnL: ${pnl:.2f} | Daily: ${self.daily_pnl:.2f}"
        )
        return pnl

    def reset_daily(self):
        """Reset daily PnL counter (call at midnight UTC)."""
        logger.info(f"📊 Daily PnL reset (was ${self.daily_pnl:.2f})")
        self.daily_pnl = 0.0

    def get_exposure_summary(self) -> Dict:
        """Current risk exposure snapshot."""
        total_risk = sum(t["risk"] for t in self.active_trades.values())
        return {
            "active_positions": len(self.active_trades),
            "total_risk_dollars": round(total_risk, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "symbols": list(self.active_trades.keys()),
        }

    # ── Internals ────────────────────────────────────────────────
    @staticmethod
    def _blocked(reason: str, stop_loss: float) -> Dict:
        return {
            "quantity": 0,
            "risk_dollars": 0,
            "stop_loss": stop_loss,
            "estimated_commission": 0,
            "blocked": True,
            "reason": reason,
        }
