import logging
import itertools
from typing import List, Dict

# Absolute imports (Critique #1 New)
import backtester
from backtester import Backtester
import config
from config import TradingConfig

logger = logging.getLogger(__name__)

class ParameterOptimizer:
    def __init__(self, ohlcv_data: List, symbol: str, initial_capital: float = 10000.0):
        self.data = sorted(ohlcv_data, key=lambda x: x[0])
        self.symbol = symbol
        self.capital = initial_capital
    
    def walk_forward_search(self, param_grid: Dict, train_pct: float = 0.7) -> List[Dict]:
        split_idx = int(len(self.data) * train_pct)
        train_data = self.data[:split_idx]
        val_data = self.data[split_idx:]
        
        keys, values = param_grid.keys(), param_grid.values()
        combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
        
        results = []
        for params in combinations:
            try:
                m_train = Backtester(self.capital).run(train_data, self.symbol, **params).calculate_metrics()
                m_val = Backtester(self.capital).run(val_data, self.symbol, **params).calculate_metrics()
                if 'error' in m_train or 'error' in m_val: continue
                
                score = (m_train['sharpe_ratio'] * 0.6) + (m_val['sharpe_ratio'] * 0.4)
                results.append({'params': params, 'combined_sharpe': round(score, 2), 'val_return': m_val['total_return_%']})
            except: continue
                
        results.sort(key=lambda x: x['combined_sharpe'], reverse=True)
        return results
