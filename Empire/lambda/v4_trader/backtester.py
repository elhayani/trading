"""
Empire Backtester V11.2 - Absolute Imports
"""

import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime

# Absolute imports (Critique #1 New)
import config
from config import TradingConfig
import market_analysis
import risk_manager

logger = logging.getLogger(__name__)

class BacktestResult:
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.final_capital = initial_capital
        self.trades = []
        self.equity_curve = [initial_capital]

    def add_trade(self, entry_date, exit_date, entry_price, exit_price, quantity, pnl, commission, symbol, direction, reason):
        self.trades.append({
            "entry_date": str(entry_date), "exit_date": str(exit_date),
            "entry_price": entry_price, "exit_price": exit_price,
            "quantity": quantity, "pnl": round(pnl, 2),
            "commission": round(commission, 2), "net_pnl": round(pnl - commission, 2),
            "symbol": symbol, "direction": direction, "reason": reason,
        })

    def calculate_metrics(self) -> Dict:
        if not self.trades: return {"error": "No trades executed"}
        df = pd.DataFrame(self.trades)
        net = df["net_pnl"]
        total_trades = len(df)
        win_rate = (len(df[net > 0]) / total_trades) * 100
        total_return_pct = ((self.final_capital - self.initial_capital) / self.initial_capital) * 100
        returns = net / self.initial_capital
        sharpe = (returns.mean() / returns.std() * (252 ** 0.5)) if returns.std() > 0 else 0.0
        return {
            "total_return_%": round(total_return_pct, 2),
            "final_capital": round(self.final_capital, 2),
            "total_trades": total_trades,
            "win_rate_%": round(win_rate, 2),
            "sharpe_ratio": round(sharpe, 2),
        }

class Backtester:
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.commission_rate = TradingConfig.COMMISSION_RATE

    def run(self, ohlcv_data: List, symbol: str = "TEST", sl_atr_mult: float = 2.0, tp_atr_mult: float = 4.0) -> BacktestResult:
        result = BacktestResult(self.initial_capital)
        asset_class = market_analysis.classify_asset(symbol)
        capital = self.initial_capital
        risk_mgr = risk_manager.RiskManager()
        position = None
        current_day = None

        for i in range(TradingConfig.MIN_REQUIRED_CANDLES, len(ohlcv_data)):
            candle = ohlcv_data[i]
            ts, price = candle[0], float(candle[4])
            dt = datetime.fromtimestamp(ts/1000) if ts > 10**11 else datetime.fromtimestamp(ts)
            if current_day != dt.date():
                risk_mgr.reset_daily()
                current_day = dt.date()

            if position:
                hit_sl = (candle[3] <= position['sl']) if position['dir'] == 'LONG' else (candle[2] >= position['sl'])
                hit_tp = (candle[2] >= position['tp']) if position['dir'] == 'LONG' else (candle[3] <= position['tp'])
                if hit_sl or hit_tp:
                    exit_price = position['sl'] if hit_sl else position['tp']
                    pnl = (exit_price - position['entry']) * position['qty'] if position['dir'] == 'LONG' else (position['entry'] - exit_price) * position['qty']
                    comm = exit_price * position['qty'] * self.commission_rate
                    capital += pnl - comm
                    result.add_trade(position['ts'], ts, position['entry'], exit_price, position['qty'], pnl, position['comm'] + comm, symbol, position['dir'], "SL" if hit_sl else "TP")
                    position = None
            else:
                try:
                    ta = market_analysis.analyze_market(ohlcv_data[i-250:i], symbol=symbol, asset_class=asset_class)
                    if ta['signal_type'] != 'NEUTRAL':
                        sl = risk_mgr.calculate_stop_loss(price, ta['atr'], ta['signal_type'], multiplier=sl_atr_mult)
                        sizing = risk_mgr.calculate_position_size(capital, price, sl, confidence=ta['score']/100, direction=ta['signal_type'])
                        if not sizing['blocked']:
                            comm = price * sizing['quantity'] * self.commission_rate
                            capital -= comm
                            position = {'entry': price, 'qty': sizing['quantity'], 'sl': sl, 'tp': price + (ta['atr'] * tp_atr_mult) if ta['signal_type'] == 'LONG' else price - (ta['atr'] * tp_atr_mult), 'dir': ta['signal_type'], 'ts': ts, 'comm': comm}
                except: continue
            result.equity_curve.append(capital)
        result.final_capital = capital
        return result
