import unittest
from lambda.v4_trader.risk_manager import RiskManager
from lambda.v4_trader.config import TradingConfig

class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.rm = RiskManager(commission_rate=0.001, slippage_buffer=0.001)
        self.capital = 10000.0

    def test_position_sizing_long(self):
        # Entry at 100, SL at 95 (5% risk)
        # Risk budget = 10000 * 0.02 * 1.0 = 200
        # Price risk = 5 + slippage (0.1) = 5.1
        # Qty = 200 / 5.1 ~= 39.21
        res = self.rm.calculate_position_size(
            capital=self.capital,
            entry_price=100.0,
            stop_loss_price=95.0,
            confidence=1.0,
            direction="LONG"
        )
        self.assertFalse(res['blocked'])
        self.assertGreater(res['quantity'], 0)
        self.assertEqual(res['risk_dollars'], 200.0)

    def test_daily_loss_circuit_breaker(self):
        self.rm.daily_pnl = -600.0 # 6% loss
        res = self.rm.calculate_position_size(
            capital=self.capital,
            entry_price=100.0,
            stop_loss_price=95.0,
            direction="LONG"
        )
        self.assertTrue(res['blocked'])
        self.assertEqual(res['reason'], "DAILY_LOSS_LIMIT")

    def test_portfolio_risk_cap(self):
        # Register a trade with $1500 risk (15% of capital)
        self.rm.register_trade("BTC/USDT", 60000, 1.0, 1500.0, 58500, "LONG")
        
        # Try to register another $1000 risk (Total 25% > 20% cap)
        res = self.rm.calculate_position_size(
            capital=self.capital,
            entry_price=100.0,
            stop_loss_price=90.0, # 10% risk
            confidence=1.0,
            direction="LONG"
        )
        # It should reduce size to fit remaining 5% ($500)
        self.assertFalse(res['blocked'])
        self.assertEqual(res['risk_dollars'], 500.0)

if __name__ == '__main__':
    unittest.main()
