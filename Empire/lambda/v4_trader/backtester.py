"""
Empire Backtester V11 - Validation Framework
=============================================
Validates trading strategies against historical data,
computing Sharpe, Sortino, Max Drawdown, Win Rate, and Profit Factor.
"""

import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BacktestResult:
    """Container for backtest performance metrics."""

    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.final_capital = initial_capital
        self.trades: List[Dict] = []
        self.equity_curve: List[float] = [initial_capital]

    def add_trade(
        self,
        entry_date,
        exit_date,
        entry_price: float,
        exit_price: float,
        quantity: float,
        pnl: float,
        commission: float,
        symbol: str,
        direction: str,
        reason: str,
    ):
        self.trades.append(
            {
                "entry_date": str(entry_date),
                "exit_date": str(exit_date),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "quantity": quantity,
                "pnl": round(pnl, 2),
                "commission": round(commission, 2),
                "net_pnl": round(pnl - commission, 2),
                "symbol": symbol,
                "direction": direction,
                "reason": reason,
            }
        )

    def calculate_metrics(self) -> Dict:
        """
        Compute full performance report:
        Sharpe, Sortino, Max Drawdown, Win Rate, Profit Factor, Avg Win/Loss.
        """
        if not self.trades:
            return {"error": "No trades executed"}

        df = pd.DataFrame(self.trades)
        net = df["net_pnl"]

        # ── Basic Stats ────────────────────────────────
        total_trades = len(df)
        winners = df[net > 0]
        losers = df[net < 0]
        win_count = len(winners)
        loss_count = len(losers)
        win_rate = (win_count / total_trades) * 100

        avg_win = winners["net_pnl"].mean() if win_count > 0 else 0.0
        avg_loss = losers["net_pnl"].mean() if loss_count > 0 else 0.0

        total_return_pct = (
            (self.final_capital - self.initial_capital) / self.initial_capital
        ) * 100

        total_commission = df["commission"].sum()

        # ── Profit Factor ──────────────────────────────
        gross_profit = winners["net_pnl"].sum() if win_count > 0 else 0.0
        gross_loss = abs(losers["net_pnl"].sum()) if loss_count > 0 else 1.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # ── Drawdown ───────────────────────────────────
        equity = pd.Series(self.equity_curve)
        running_max = equity.cummax()
        drawdown_pct = ((equity - running_max) / running_max) * 100
        max_dd = drawdown_pct.min()

        # ── Sharpe Ratio (annualized, 252 trading days) ─
        returns = net / self.initial_capital
        sharpe = 0.0
        if returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * (252 ** 0.5)

        # ── Sortino Ratio (downside only) ──────────────
        downside = returns[returns < 0]
        sortino = 0.0
        if len(downside) > 0 and downside.std() > 0:
            sortino = (returns.mean() / downside.std()) * (252 ** 0.5)

        # ── Expectancy ─────────────────────────────────
        expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

        return {
            "total_return_%": round(total_return_pct, 2),
            "final_capital": round(self.final_capital, 2),
            "total_trades": total_trades,
            "win_rate_%": round(win_rate, 2),
            "wins": win_count,
            "losses": loss_count,
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_%": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "expectancy_per_trade": round(expectancy, 2),
            "total_commission": round(total_commission, 2),
        }

    def print_report(self):
        """Pretty print the backtest results."""
        m = self.calculate_metrics()
        if "error" in m:
            print(f"❌ {m['error']}")
            return

        print("\n" + "=" * 60)
        print("📊 EMPIRE BACKTEST REPORT")
        print("=" * 60)
        print(f"  Capital    : ${self.initial_capital:,.2f} → ${m['final_capital']:,.2f}")
        print(f"  Return     : {m['total_return_%']:+.2f}%")
        print(f"  Trades     : {m['total_trades']} ({m['wins']}W / {m['losses']}L)")
        print(f"  Win Rate   : {m['win_rate_%']:.1f}%")
        print(f"  Avg Win    : ${m['avg_win']:,.2f}")
        print(f"  Avg Loss   : ${m['avg_loss']:,.2f}")
        print(f"  Expectancy : ${m['expectancy_per_trade']:,.2f} / trade")
        print("-" * 60)
        print(f"  Sharpe     : {m['sharpe_ratio']:.2f}")
        print(f"  Sortino    : {m['sortino_ratio']:.2f}")
        print(f"  Profit F.  : {m['profit_factor']:.2f}")
        print(f"  Max DD     : {m['max_drawdown_%']:.2f}%")
        print(f"  Commissions: ${m['total_commission']:,.2f}")
        print("=" * 60 + "\n")


class Backtester:
    """
    Walk-forward backtester.
    Requires a strategy object with .analyze(ohlcv) and .decide(analysis) methods.
    """

    def __init__(
        self,
        strategy=None,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,
    ):
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate  # 0.1% per leg

    def run(
        self,
        ohlcv_data: List,
        symbol: str = "TEST",
        sl_atr_mult: float = 2.0,
        tp_atr_mult: float = 4.0,
    ) -> BacktestResult:
        """
        Run backtest over OHLCV data.
        ohlcv_data: list of [timestamp, open, high, low, close, volume]
        """
        from market_analysis import analyze_market
        from risk_manager import RiskManager

        result = BacktestResult(self.initial_capital)
        capital = self.initial_capital
        risk_mgr = RiskManager()
        position = None

        if len(ohlcv_data) < 250:
            logger.error(f"🚫 Need 250+ candles, got {len(ohlcv_data)}")
            return result

        logger.info(f"🔬 Backtesting {symbol} | {len(ohlcv_data)} candles | Capital: ${capital:,.2f}")

        for i in range(250, len(ohlcv_data)):
            window = ohlcv_data[max(0, i - 250) : i + 1]
            current_candle = ohlcv_data[i]
            current_price = float(current_candle[4])  # close
            current_high = float(current_candle[2])
            current_low = float(current_candle[3])
            ts = current_candle[0]

            if position is not None:
                # ── EXIT CHECK ──────────────────────────────
                hit_sl = False
                hit_tp = False

                if position["direction"] == "LONG":
                    hit_sl = current_low <= position["stop_loss"]
                    hit_tp = current_high >= position["take_profit"]
                else:  # SHORT
                    hit_sl = current_high >= position["stop_loss"]
                    hit_tp = current_low <= position["take_profit"]

                exit_price = None
                exit_reason = None

                if hit_sl:
                    exit_price = position["stop_loss"]
                    exit_reason = "STOP_LOSS"
                elif hit_tp:
                    exit_price = position["take_profit"]
                    exit_reason = "TAKE_PROFIT"

                if exit_price:
                    if position["direction"] == "LONG":
                        pnl = (exit_price - position["entry_price"]) * position["quantity"]
                    else:
                        pnl = (position["entry_price"] - exit_price) * position["quantity"]

                    comm = (
                        position["quantity"] * exit_price * self.commission_rate
                    )  # exit commission
                    capital += pnl - comm
                    risk_mgr.daily_pnl += pnl - comm

                    result.add_trade(
                        position["entry_ts"],
                        ts,
                        position["entry_price"],
                        exit_price,
                        position["quantity"],
                        pnl,
                        position["entry_commission"] + comm,
                        symbol,
                        position["direction"],
                        exit_reason,
                    )
                    position = None

            else:
                # ── ENTRY CHECK ─────────────────────────────
                analysis = analyze_market(window)
                if analysis.get("market_context") in ("NO_DATA", "INSUFFICIENT_DATA"):
                    result.equity_curve.append(capital)
                    continue

                rsi = analysis["indicators"]["rsi"]
                atr = analysis.get("atr", 0)    # Audit Fix: Use root access
                score = analysis.get("score", 0) # Audit Fix: Use root access
                signal_type = analysis.get("signal_type", "NEUTRAL")

                # Need score >= 60 to pass Level 2
                if score < 60:
                    result.equity_curve.append(capital)
                    continue

                # Determine direction
                direction = None
                if signal_type == "LONG" or (rsi < 40 and score >= 60):
                    direction = "LONG"
                elif signal_type == "SHORT" or (rsi > 68 and score >= 60):
                    direction = "SHORT"

                if direction is None:
                    result.equity_curve.append(capital)
                    continue

                # Calculate stop/target
                sl = RiskManager.calculate_stop_loss(current_price, atr, direction, sl_atr_mult)
                if direction == "LONG":
                    tp = current_price + (atr * tp_atr_mult)
                else:
                    tp = current_price - (atr * tp_atr_mult)

                # Size by risk
                sizing = risk_mgr.calculate_position_size(
                    capital, current_price, sl, 
                    confidence=min(1.0, score / 100),
                    atr=atr  # Audit Fix: C1 Robust Stop
                )

                if sizing["blocked"] or sizing["quantity"] <= 0:
                    result.equity_curve.append(capital)
                    continue

                entry_comm = sizing["quantity"] * current_price * self.commission_rate
                capital -= entry_comm

                position = {
                    "entry_price": current_price,
                    "entry_ts": ts,
                    "quantity": sizing["quantity"],
                    "stop_loss": sl,
                    "take_profit": tp,
                    "direction": direction,
                    "entry_commission": entry_comm,
                }

            result.equity_curve.append(capital)

        # Close any remaining position at last price
        if position is not None:
            last_price = float(ohlcv_data[-1][4])
            if position["direction"] == "LONG":
                pnl = (last_price - position["entry_price"]) * position["quantity"]
            else:
                pnl = (position["entry_price"] - last_price) * position["quantity"]
            comm = position["quantity"] * last_price * self.commission_rate
            capital += pnl - comm
            result.add_trade(
                position["entry_ts"],
                ohlcv_data[-1][0],
                position["entry_price"],
                last_price,
                position["quantity"],
                pnl,
                position["entry_commission"] + comm,
                symbol,
                position["direction"],
                "END_OF_DATA",
            )

        result.final_capital = capital
        return result


# ── CLI Usage ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTC/USDT"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 365

    print(f"Loading {days} days of 1h data for {symbol}...")

    try:
        from exchange_connector import ExchangeConnector

        exchange = ExchangeConnector()
        exchange.initialize(mode="dry_run")
        ohlcv = exchange.fetch_ohlcv(symbol, "1h", limit=min(days * 24, 5000))
        print(f"Loaded {len(ohlcv)} candles")

        bt = Backtester(initial_capital=10000, commission_rate=0.001)
        result = bt.run(ohlcv, symbol=symbol)
        result.print_report()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
