"""
🔗 Empire Trading API Backend
Connecte le dashboard à Binance pour données réelles
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import boto3
import json
import logging
from datetime import datetime, timedelta
import os
import time
import hmac
import hashlib

# Configuration
app = Flask(__name__)
CORS(app)

# AWS clients
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-1')
secrets_client = boto3.client('secretsmanager', region_name='ap-northeast-1')

# Tables
trades_table = dynamodb.Table('EmpireTradesHistory')
skipped_table = dynamodb.Table('EmpireSkippedTrades')

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BinanceAPI:
    """Client Binance pour données réelles"""
    
    def __init__(self):
        self.api_key = None
        self.secret_key = None
        self.demo_mode = os.environ.get('BINANCE_DEMO_MODE', 'true').lower() in ('1', 'true', 'yes', 'y', 'on')
        self.base_url = "https://demo-fapi.binance.com" if self.demo_mode else "https://fapi.binance.com"
        self._load_credentials()
    
    def _load_credentials(self):
        """Charge les clés API depuis AWS Secrets Manager"""
        try:
            secret_response = secrets_client.get_secret_value(
                SecretId='trading/binance'
            )
            secret_data = json.loads(secret_response['SecretString'])
            
            self.api_key = secret_data.get('api_key') or secret_data.get('apiKey') or secret_data.get('API_KEY')
            self.secret_key = secret_data.get('secret') or secret_data.get('secretKey') or secret_data.get('SECRET_KEY') or secret_data.get('api_secret') or secret_data.get('secret_key')
            
            if self.api_key: self.api_key = self.api_key.strip()
            if self.secret_key: self.secret_key = self.secret_key.strip()
            
            logger.info("✅ Binance credentials loaded from Secrets Manager")
            
        except Exception as e:
            logger.error(f"❌ Error loading credentials: {e}")
    
    def get_account_info(self):
        """Informations du compte Binance"""
        try:
            import requests
            
            endpoint = "/fapi/v2/account"
            timestamp = int(time.time() * 1000)
            
            # Signature
            query_string = f"timestamp={timestamp}"
            signature = hmac.new(
                self.secret_key.encode(),
                query_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Request
            headers = {
                'X-MBX-APIKEY': self.api_key
            }
            
            url = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Binance account info received: {data.get('totalWalletBalance', 'N/A')}")
                return data
            else:
                logger.error(f"❌ Binance API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting account info: {e}")
            return None
    
    def get_positions(self):
        """Positions ouvertes"""
        try:
            account_info = self.get_account_info()
            if account_info and 'positions' in account_info:
                return [pos for pos in account_info['positions'] if float(pos['positionAmt']) != 0]
            return []
        except Exception as e:
            logger.error(f"❌ Error getting positions: {e}")
            return []
    
    def get_open_orders(self):
        """Ordres ouverts"""
        try:
            import requests
            
            endpoint = "/fapi/v1/openOrders"
            timestamp = int(time.time() * 1000)
            
            query_string = f"timestamp={timestamp}"
            signature = hmac.new(
                self.secret_key.encode(),
                query_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            headers = {'X-MBX-APIKEY': self.api_key}
            url = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            return []
            
        except Exception as e:
            logger.error(f"❌ Error getting open orders: {e}")
            return []

    def _signed_get(self, endpoint, params=None):
        """GET signé Binance Futures (demo/live selon base_url)."""
        try:
            import requests

            if not self.api_key or not self.secret_key:
                return None

            params = params or {}
            params['timestamp'] = int(time.time() * 1000)

            query_string = "&".join([f"{k}={params[k]}" for k in sorted(params.keys())])
            signature = hmac.new(
                self.secret_key.encode(),
                query_string.encode(),
                hashlib.sha256
            ).hexdigest()

            headers = {'X-MBX-APIKEY': self.api_key}
            url = f"{self.base_url}{endpoint}?{query_string}&signature={signature}"
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()

            logger.error(f"❌ Binance signed GET error {endpoint}: {response.status_code} - {response.text}")
            return None
        except Exception as e:
            logger.error(f"❌ Binance signed GET exception {endpoint}: {e}")
            return None

    def get_income_history(self, days=7, income_type=None, limit=1000):
        """Historique income Binance Futures (REALIZED_PNL, COMMISSION, etc.)."""
        try:
            start_time = int((datetime.utcnow() - timedelta(days=int(days))).timestamp() * 1000)
            params = {
                'startTime': start_time,
                'limit': int(limit)
            }
            if income_type:
                params['incomeType'] = income_type
            data = self._signed_get('/fapi/v1/income', params=params)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"❌ Error getting income history: {e}")
            return []

    def get_realized_pnl_trades(self, days=7):
        """Construit une liste de 'trades' depuis REALIZED_PNL (source de vérité Binance)."""
        items = self.get_income_history(days=days, income_type='REALIZED_PNL')
        trades = []
        for it in items:
            try:
                ts_ms = int(it.get('time') or 0)
                trades.append({
                    'timestamp': ts_ms,
                    'symbol': it.get('symbol', ''),
                    'type': 'REALIZED_PNL',
                    'price': None,
                    'quantity': None,
                    'pnl': float(it.get('income', 0) or 0),
                    'status': 'CLOSED',
                    'trade_id': it.get('tranId')
                })
            except Exception:
                continue

        trades.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return trades

# Instance Binance
binance_api = BinanceAPI()

@app.route('/api/account')
def get_account():
    """Informations du compte Binance"""
    try:
        account_info = binance_api.get_account_info()
        
        if account_info:
            return jsonify({
                'status': 'success',
                'data': {
                    'totalWalletBalance': float(account_info.get('totalWalletBalance', 0)),
                    'totalUnrealizedPnl': float(account_info.get('totalUnrealizedPnl', 0)),
                    'totalMarginBalance': float(account_info.get('totalMarginBalance', 0)),
                    'totalPositionInitialMargin': float(account_info.get('totalPositionInitialMargin', 0)),
                    'availableBalance': float(account_info.get('availableBalance', 0)),
                    'maxWithdrawAmount': float(account_info.get('maxWithdrawAmount', 0))
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Binance account info unavailable'
            })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/positions')
def get_positions():
    """Positions ouvertes"""
    try:
        positions = binance_api.get_positions()
        
        formatted_positions = []
        for pos in positions:
            # Handle potential missing keys in different Binance response versions
            symbol = pos.get('symbol', 'UNKNOWN')
            pamt = float(pos.get('positionAmt', 0))
            if pamt == 0: continue # Double check
            
            # Determine side correctly for UI
            side = pos.get('positionSide', 'BOTH')
            if side == 'BOTH':
                side = 'LONG' if pamt > 0 else 'SHORT'
                
            formatted_positions.append({
                'symbol': symbol,
                'side': side,
                'size': abs(pamt),
                'entryPrice': float(pos.get('entryPrice', 0)),
                'markPrice': float(pos.get('markPrice', 0)),
                'pnl': float(pos.get('unrealizedPnl', 0)),
                'pnl_pct': float(pos.get('percentage', 0)) if pos.get('percentage') else 0,
                'leverage': int(pos.get('leverage', 1))
            })
        
        return jsonify({
            'status': 'success',
            'data': formatted_positions
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/trades')
def get_trades():
    """Historique des trades (Binance: source de vérité)"""
    try:
        days = request.args.get('days', '7')
        trades = binance_api.get_realized_pnl_trades(days=int(days))

        if not trades:
            return jsonify({'status': 'success', 'data': []})

        return jsonify({'status': 'success', 'data': trades})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/skipped-trades')
def get_skipped_trades():
    """Trades ignorés avec raisons"""
    try:
        # Récupérer depuis DynamoDB
        response = skipped_table.scan(
            Limit=50,
            FilterExpression='#s = :status',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':status': 'SKIPPED'}
        )
        
        skipped = response.get('Items', [])
        
        # Formatter les skipped trades
        formatted_skipped = []
        for trade in skipped:
            formatted_skipped.append({
                'timestamp': trade.get('timestamp', 0),
                'symbol': trade.get('symbol', ''),
                'type': trade.get('side', ''),
                'price': float(trade.get('price', 0)),
                'quantity': float(trade.get('quantity', 0)),
                'status': trade.get('status', ''),
                'reason': trade.get('reason', ''),
                'signal_strength_pct': float(trade.get('signal_strength', 0)) * 100,  # Pourcentage
                'momentum_score': float(trade.get('momentum_score', 0)),
                'volume_surge': float(trade.get('volume_surge', 0)),
                'btc_trend': trade.get('btc_trend', ''),
                'skip_reason': trade.get('skip_reason', '')
            })
        
        # Trier par timestamp décroissant
        formatted_skipped.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'status': 'success',
            'data': formatted_skipped
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/budget')
def get_budget():
    """Budget et capital"""
    try:
        # Récupérer compte Binance
        account_info = binance_api.get_account_info()
        
        if account_info:
            total_balance = float(account_info['totalWalletBalance'])
            available_balance = float(account_info['availableBalance'])
            margin_used = float(account_info['totalPositionInitialMargin'])
            unrealized_pnl = float(account_info['totalUnrealizedPnl'])
            
            # Budget allocation
            budget_allocation = {
                'total_balance': total_balance,
                'available_balance': available_balance,
                'margin_used': margin_used,
                'unrealized_pnl': unrealized_pnl,
                'margin_ratio': (margin_used / total_balance * 100) if total_balance > 0 else 0,
                'free_margin': available_balance,
                'buying_power': available_balance * 5,  # Levier x5
                'risk_utilization': (margin_used / total_balance * 100) if total_balance > 0 else 0
            }
        else:
            return jsonify({'status': 'error', 'message': 'Binance account info unavailable'})

        return jsonify({'status': 'success', 'data': budget_allocation})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/stats')
def get_stats():
    """Statistiques de trading"""
    try:
        # Récupérer tous les trades
        response = trades_table.scan()
        trades = response.get('Items', [])
        
        # Récupérer skipped trades
        skipped_response = skipped_table.scan()
        skipped_trades = skipped_response.get('Items', [])
        
        if not trades:
            return jsonify({
                'status': 'success',
                'data': {
                    'total_trades': 0,
                    'skipped_trades': len(skipped_trades),
                    'win_rate': 0.0,
                    'total_pnl': 0.0,
                    'avg_win': 0.0,
                    'avg_loss': 0.0,
                    'max_drawdown': 0.0,
                    'sharpe_ratio': 0.0
                }
            })
        
        # Calculer les stats
        closed_trades = [t for t in trades if t.get('status') == 'CLOSED']
        winning_trades = [t for t in closed_trades if float(t.get('pnl', 0)) > 0]
        losing_trades = [t for t in closed_trades if float(t.get('pnl', 0)) < 0]
        
        total_trades = len(closed_trades)
        skipped_count = len(skipped_trades)
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        total_pnl = sum(float(t.get('pnl', 0)) for t in closed_trades)
        avg_win = sum(float(t.get('pnl', 0)) for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(float(t.get('pnl', 0)) for t in losing_trades) / len(losing_trades) if losing_trades else 0
        
        return jsonify({
            'status': 'success',
            'data': {
                'total_trades': total_trades,
                'skipped_trades': skipped_count,
                'win_rate': round(win_rate, 2),
                'total_pnl': round(total_pnl, 2),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades)
            }
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/ticker/<symbol>')
def get_ticker(symbol):
    """Prix temps réel d'un symbole"""
    try:
        import requests
        
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                'status': 'success',
                'data': {
                    'symbol': data['symbol'],
                    'price': float(data['price'])
                }
            })
        else:
            return jsonify({'status': 'error', 'message': 'Symbol not found'})
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/health')
def health_check():
    """Health check de l'API"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
