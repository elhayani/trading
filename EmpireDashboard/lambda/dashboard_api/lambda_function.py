import json
import boto3
import os
import traceback
from urllib.request import Request, urlopen
from urllib.error import URLError
from decimal import Decimal
from datetime import datetime

# Initialize DynamoDB Client
dynamodb = boto3.resource('dynamodb')
config_table_name = os.environ.get('CONFIG_TABLE', 'EmpireConfig')

# Tables to scan : On prend TOUT pour ne rien rater
TABLES_TO_SCAN = [
    "EmpireTradesHistory", 
    "EmpireCryptoV4", 
    "EmpireForexHistory", 
    "EmpireIndicesHistory", 
    "EmpireCommoditiesHistory"
]

config_table = dynamodb.Table(config_table_name)

# Binance API (for real balance)
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    print("⚠️ CCXT not available, will use calculated balances")

def get_binance_exchange():
    """Initialise l'objet exchange Binance (priorité au mode DEMO)"""
    try:
        if not CCXT_AVAILABLE: return None
        resp = config_table.get_item(Key={'ConfigKey': 'BINANCE_CREDENTIALS'})
        if 'Item' not in resp: return None
        creds = resp['Item']
        
        # Configuration de base
        config = {
            'apiKey': creds.get('ApiKey'),
            'secret': creds.get('ApiSecret'),
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        }

        # 1. Tentative en mode DEMO (le plus probable pour ces clés)
        try:
            ex_demo = ccxt.binance(config)
            if hasattr(ex_demo, 'enable_demo_trading'):
                ex_demo.enable_demo_trading(True)
            else:
                ex_demo.urls['api']['fapiPublic'] = 'https://vapi.binance.com'
                ex_demo.urls['api']['fapiPrivate'] = 'https://vapi.binance.com'
            
            ex_demo.fetch_balance()
            print("✅ Connecté au mode BINANCE DEMO")
            return ex_demo
        except Exception as e:
            print(f"ℹ️ Échec mode DEMO: {e}")

        # 2. Tentative en mode LIVE
        try:
            ex_live = ccxt.binance(config)
            ex_live.fetch_balance()
            print("✅ Connecté au mode BINANCE LIVE")
            return ex_live
        except Exception as e:
            print(f"❌ Échec mode LIVE: {e}")
            
        return None
    except: return None


def fetch_binance_balance(exchange):
    """Récupère le solde USDT (Wallet Balance) depuis Binance"""
    try:
        if not exchange: return None
        balance = exchange.fetch_balance()
        return float(balance.get('USDT', {}).get('total', 0))
    except Exception as e:
        print(f"❌ Erreur Balance Binance: {e}")
        return None

def fetch_oanda_balance():
    """Récupère le solde du compte Oanda via REST API v20"""
    try:
        resp = config_table.get_item(Key={'ConfigKey': 'OANDA_CREDENTIALS'})
        if 'Item' not in resp:
            print("ℹ️ Oanda: Aucune clé API configurée dans EmpireConfig")
            return None
        creds = resp['Item']
        token = creds.get('ApiToken') or creds.get('ApiKey')
        account_id = creds.get('AccountId')
        environment = creds.get('Environment', 'practice')  # 'practice' ou 'live'
        
        if not token or not account_id:
            print("⚠️ Oanda: Token ou AccountId manquant")
            return None
        
        # Oanda API endpoint
        if environment == 'live':
            base_url = 'https://api-fxtrade.oanda.com'
        else:
            base_url = 'https://api-fxpractice.oanda.com'
        
        url = f"{base_url}/v3/accounts/{account_id}/summary"
        req = Request(url, headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
        
        with urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            account = data.get('account', {})
            # NAV = Net Asset Value (balance + unrealized PnL)
            balance = float(account.get('balance', 0))
            nav = float(account.get('NAV', balance))
            unrealized_pnl = float(account.get('unrealizedPL', 0))
            
            print(f"✅ Oanda connecté: Balance=${balance:.2f}, NAV=${nav:.2f}, uPnL=${unrealized_pnl:.2f}")
            return {
                'balance': balance,
                'nav': nav,
                'unrealized_pnl': unrealized_pnl
            }
    except URLError as e:
        print(f"❌ Oanda API Error: {e}")
        return None
    except Exception as e:
        print(f"❌ Oanda Balance Error: {e}")
        return None

# Asset classification for multi-broker/multi-asset systems
COMMODITIES_SYMBOLS = ['PAXG', 'XAG', 'GOLD', 'SILVER']
FOREX_SYMBOLS = ['EUR', 'GBP', 'AUD', 'JPY', 'CHF', 'CAD']
INDICES_SYMBOLS = ['DEFI', 'NDX', 'GSPC', 'US30']

def get_paris_time():
    """Returns current Paris time (UTC+1 for winter)"""
    return datetime.utcnow() + timedelta(hours=1)

def classify_asset(symbol):
    """
    Classify a Binance/Broker symbol into Asset Class.
    Prioritizes specific prefixes/keywords.
    """
    symbol_upper = symbol.upper()
    
    # 1. Commodities
    if any(comm in symbol_upper for comm in COMMODITIES_SYMBOLS):
        return "Commodities"
    
    # 2. Forex
    if any(fx in symbol_upper for fx in FOREX_SYMBOLS):
        return "Forex"
    
    # 3. Indices
    if any(idx in symbol_upper for idx in INDICES_SYMBOLS):
        return "Indices"
    
    # Default
    return "Crypto"

def fetch_binance_positions(exchange):
    """Récupère les positions REELLES directement depuis l'API Binance"""
    try:
        if not exchange: return []
        positions = exchange.fetch_positions()
        live_trades = []
        paris_now = get_paris_time()
        
        for pos in positions:
            contracts = float(pos.get('contracts', 0) or 0)
            if contracts != 0:
                # Binance CCXT returns 'side' as 'long' or 'short'
                side = pos.get('side', '').lower()
                if side == 'short':
                    trade_type = 'SHORT'
                elif side == 'long':
                    trade_type = 'LONG'
                else:
                    # Fallback: negative contracts = short
                    trade_type = 'SHORT' if contracts < 0 else 'LONG'
                
                # Dynamic classification
                symbol = pos['symbol']
                asset_class = classify_asset(symbol)
                
                live_trades.append({
                    'TradeId': f"LIVE_{symbol}",
                    'Timestamp': paris_now.isoformat(),
                    'Pair': symbol,
                    'AssetClass': asset_class,
                    'Type': trade_type,
                    'Size': abs(contracts),
                    'EntryPrice': float(pos.get('entryPrice', 0) or 0),
                    'CurrentPrice': float(pos.get('markPrice', 0) or 0),
                    'Status': 'OPEN',
                    'Source': 'BINANCE',
                    'PnL': float(pos.get('unrealizedPnl', 0) or 0),
                    'AI_Reason': f'POSITION RÉELLE SUR BINANCE ({asset_class})'
                })
        return live_trades
    except Exception as e:
        print(f"⚠️ Erreur Binance Live: {e}")
        return []




def fetch_ticker_price(exchange, symbol):
    """Helper to get current price for exit calculation"""
    try:
        ticker = exchange.fetch_ticker(symbol)
        return float(ticker['last'])
    except:
        return 0.0

def reconcile_trades(db_trades, binance_positions, exchange):
    """
    Compare DB trades (OPEN) with Binance live positions.
    If a trade is OPEN in DB but missing in Binance, it means it was closed.
    We update the DB status to CLOSED with estimated PnL.
    """
    if not exchange: return

    table = dynamodb.Table('EmpireTradesHistory')
    
    # 1. Map active Binance symbols
    # binance_positions = list of dicts with 'Pair' (e.g. BTC/USDT)
    active_symbols = [p['Pair'] for p in binance_positions]
    
    # 2. Filter DB trades that are supposedly OPEN for Crypto
    db_open_crypto = [t for t in db_trades if t.get('Status') == 'OPEN' and t.get('AssetClass') == 'Crypto']
    
    for trade in db_open_crypto:
        if trade['Pair'] not in active_symbols:
            print(f"🔍 Auto-Sync: Closing detected for {trade['Pair']} (TradeId: {trade.get('TradeId')})")
            
            # Fetch current price as exit price
            exit_price = fetch_ticker_price(exchange, trade['Pair'])
            if exit_price == 0: continue

            # Calculate Final PnL
            size = float(trade.get('Size', 0))
            entry_price = float(trade.get('EntryPrice', 0))
            is_short = trade.get('Type') == 'SHORT'
            
            pnl = 0.0
            if entry_price > 0 and size > 0:
                if is_short:
                    pnl = (entry_price - exit_price) * size
                else:
                    pnl = (exit_price - entry_price) * size
            
            # Update DynamoDB
            try:
                # Use Decimal for DynamoDB
                pnl_decimal = Decimal(str(round(pnl, 2)))
                exit_decimal = Decimal(str(exit_price))
                
                table.update_item(
                    Key={
                        'TradeId': trade['TradeId'],
                        'Timestamp': trade['Timestamp']
                    },
                    UpdateExpression="SET #s = :s, ExitPrice = :ep, PnL = :p, ClosedAt = :c, AI_Reason = :r",
                    ExpressionAttributeNames={'#s': 'Status'},
                    ExpressionAttributeValues={
                        ':s': 'CLOSED',
                        ':ep': exit_decimal,
                        ':p': pnl_decimal,
                        ':c': get_paris_time().isoformat(),
                        ':r': "Auto-Reconciled: Closed on Binance"
                    }
                )
                print(f"✅ Synced: {trade['Pair']} CLOSED PnL={pnl}")
            except Exception as e:
                print(f"❌ Error syncing trade {trade['TradeId']}: {e}")


def fetch_current_price(symbol, asset_class):
    """Récupère le prix actuel via Yahoo Finance ou Binance"""
    try:
        if asset_class == 'Crypto':
            # Use Binance API for crypto (faster)
            pair = symbol.replace('/', '')  # SOL/USDT -> SOLUSDT
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={pair}"
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode())
                return float(data.get('price', 0))
        else:
            # Use Yahoo Finance for Forex/Indices/Commodities
            yahoo_symbol = symbol
            if asset_class == 'Forex' and '=X' not in symbol:
                yahoo_symbol = symbol + '=X'
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=1d"
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode())
                return float(data['chart']['result'][0]['meta']['regularMarketPrice'])
    except Exception as e:
        print(f"Error fetching price for {symbol}: {e}")
        return 0.0

class DecimalEncoder(json.JSONEncoder):
    """Helper class to convert Decimal items to float for JSON compatibility"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def get_all_trades():
    """Scan all 4 trading tables (same logic as reporter.py)"""
    all_items = []
    for table_name in TABLES_TO_SCAN:
        try:
            table = dynamodb.Table(table_name)
            response = table.scan()
            items = response.get('Items', [])
            
            def process_items(chunk):
                processed = []
                for item in chunk:
                    if 'PnL' in item: item['PnL'] = float(item['PnL'])
                    if 'Size' in item: item['Size'] = float(item['Size'])
                    if 'EntryPrice' in item: item['EntryPrice'] = float(item['EntryPrice'])
                    if 'CurrentPrice' in item: item['CurrentPrice'] = float(item['CurrentPrice'])
                    item['Source'] = 'DYNAMO'
                    processed.append(item)
                return processed

            all_items.extend(process_items(items))

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                all_items.extend(process_items(response.get('Items', [])))
        except Exception as e:
            print(f"Error scanning {table_name}: {e}")
    return all_items



def calculate_equity_curve(trades):
    initial_capital = 1000.0
    current_equity = initial_capital
    equity_curve = []

    # Filter for actual trades only (exclude SKIPPED/INFO)
    actual_trades = [t for t in trades if t.get('Status', '').upper() in ['OPEN', 'CLOSED', 'TP', 'SL']]

    if not actual_trades:
         # Default start point for empty history
        return [{'x': '2026-01-01T00:00:00', 'y': initial_capital}]

    # Sort trades by timestamp
    sorted_trades = sorted(actual_trades, key=lambda x: x.get('Timestamp', ''))

    # Start point (either Jan 1st 2026 or very first trade date if older)
    start_date = sorted_trades[0].get('Timestamp')
    # If first trade is after Jan 1st, we can prepend Jan 1st for better viz
    if start_date > '2026-01-01':
         equity_curve.append({'x': '2026-01-01T00:00:00', 'y': initial_capital})
    else:
         equity_curve.append({'x': start_date, 'y': initial_capital})

    for trade in sorted_trades:
        pnl = float(trade.get('PnL', 0.0))
        current_equity += pnl
        equity_curve.append({
            'x': trade.get('Timestamp'),
            'y': current_equity,
            'details': f"{trade.get('Pair')} ({trade.get('Type')}) PnL: {pnl}"
        })
    return equity_curve


def get_live_mode_status(asset_class):
    """Check if asset class is explicitly set to LIVE mode in Config"""
    try:
        resp = config_table.get_item(Key={'ConfigKey': f'{asset_class.upper()}_MODE'})
        if 'Item' in resp and resp['Item'].get('Value') == 'LIVE':
            return True
    except: 
        return False
    return False

def lambda_handler(event, context):
    print(f"📊 Dashboard API Request: {json.dumps(event)}")

    # Standard CORS Headers for all responses
    cors_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token'
    }

    try:
        # Determine Route
        # In HTTP API, path is event['rawPath'] or event['requestContext']['http']['path']
        path = event.get('rawPath') or event.get('path', '/')
        method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')

        # --- PANIC SWITCH STATUS (/status) ---
        if '/status' in path:
            if method == 'GET':
                statuses = {}
                for sys in ['Crypto', 'Forex', 'Indices', 'Commodities']:
                    try:
                        res = config_table.get_item(Key={'ConfigKey': f'PANIC_{sys.upper()}'})
                        statuses[sys] = res.get('Item', {}).get('Value', 'ACTIVE')
                    except:
                        statuses[sys] = 'ACTIVE'
                return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps(statuses)
                }

            elif method == 'POST':
                try:
                    body = json.loads(event.get('body', '{}'))
                    system = body.get('system')
                    new_status = body.get('status')
                    if system in ['Crypto', 'Forex', 'Indices', 'Commodities'] and new_status in ['ACTIVE', 'PANIC']:
                        config_table.put_item(Item={
                            'ConfigKey': f'PANIC_{system.upper()}',
                            'Value': new_status,
                            'UpdatedAt': datetime.utcnow().isoformat()
                        })
                        return {
                            'statusCode': 200,
                            'headers': cors_headers,
                            'body': json.dumps({'message': f'{system} set to {new_status}'})
                        }
                except:
                    pass
                return {'statusCode': 400, 'headers': cors_headers, 'body': json.dumps({'error': 'Invalid request'})}

        # --- CLOSE TRADE (/close-trade) ---
        if '/close-trade' in path and method == 'POST':
            try:
                body = json.loads(event.get('body', '{}'))
                symbol = body.get('symbol')  # ex: BTC/USDT
                side = body.get('side')      # SHORT ou LONG
                qty = float(body.get('qty', 0))
                
                if not symbol or not side or qty <= 0:
                    return {
                        'statusCode': 400,
                        'headers': cors_headers,
                        'body': json.dumps({'error': 'Missing symbol, side, or qty'})
                    }
                
                # Initialisation Binance
                exchange = get_binance_exchange()
                if not exchange:
                    return {
                        'statusCode': 500,
                        'headers': cors_headers,
                        'body': json.dumps({'error': 'Could not connect to Binance'})
                    }
                
                # Inversion de l'ordre pour fermer
                # Si on est SHORT, on BUY. Si on est LONG, on SELL.
                order_side = 'buy' if side.upper() == 'SHORT' else 'sell'
                
                print(f"⚡ Fermeture forcée : {order_side} {qty} {symbol}")
                
                order = exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=order_side,
                    amount=qty,
                    params={'reduceOnly': True}  # Sécurité critique
                )
                
                return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps({
                        'message': 'Trade fermé avec succès',
                        'order_id': order.get('id'),
                        'symbol': symbol,
                        'side': order_side,
                        'qty': qty
                    })
                }
            except Exception as e:
                print(f"❌ Erreur close-trade: {e}")
                return {
                    'statusCode': 500,
                    'headers': cors_headers,
                    'body': json.dumps({'error': str(e)})
                }


        # --- STATS LOGIC (/stats or default) ---
        query_params = event.get('queryStringParameters') or {}
        year_filter = query_params.get('year')

        all_trades = get_all_trades()

        if year_filter and year_filter != 'ALL':
            trades = [t for t in all_trades if t.get('Timestamp', '').startswith(year_filter)]

            # Start Balance (Cumulative from before the year) - only actual trades
            trades_before = [t for t in all_trades if t.get('Timestamp', '') < f"{year_filter}-01-01"]
            actual_trades_before = [t for t in trades_before if t.get('Status', '').upper() in ['OPEN', 'CLOSED', 'TP', 'SL']]
            pnl_before = sum(float(t.get('PnL', 0.0)) for t in actual_trades_before)
            start_equity = 1000.0 + pnl_before

            # Curve for target year - only actual trades
            actual_trades_year = [t for t in trades if t.get('Status', '').upper() in ['OPEN', 'CLOSED', 'TP', 'SL']]
            actual_trades_year.sort(key=lambda x: x.get('Timestamp', ''))
            run_equity = start_equity
            equity_data = [{'x': f"{year_filter}-01-01T00:00:00Z", 'y': start_equity}]

            for trade in actual_trades_year:
                pnl = float(trade.get('PnL', 0.0))
                run_equity += pnl
                equity_data.append({
                    'x': trade.get('Timestamp'),
                    'y': run_equity,
                    'details': f"{trade.get('Pair')} ({trade.get('Type')}) PnL: {pnl}"
                })
            current_display_equity = run_equity
        else:
            trades = all_trades
            equity_data = calculate_equity_curve(trades)
            # Calculate current equity from actual trades only
            actual_all_trades = [t for t in all_trades if t.get('Status', '').upper() in ['OPEN', 'CLOSED', 'TP', 'SL']]
            current_display_equity = 1000.0 + sum(float(t.get('PnL', 0.0)) for t in actual_all_trades)

        # Recent Trades & Key Stats
        # On filtre l'historique : on retire les 'OPEN' de DynamoDB pour la Crypto
        # car on va utiliser les LIVE de Binance à la place
        trades_for_table = [t for t in trades if not (t.get('AssetClass') == 'Crypto' and t.get('Status') == 'OPEN')]
        raw_recent_trades = sorted(trades_for_table, key=lambda x: x.get('Timestamp', ''), reverse=True)[:50]
        
        # LIVE POSITIONS FROM BINANCE
        binance_ex = get_binance_exchange()
        live_positions = fetch_binance_positions(binance_ex)
        
        # AUTO-RECONCILIATION
        if binance_ex:
            try:
                reconcile_trades(all_trades, live_positions, binance_ex)
            except Exception as e:
                print(f"⚠️ Reconciliation Error: {e}")

        recent_trades = live_positions + raw_recent_trades

        # Enrich OPEN positions with current price
        for trade in recent_trades:
            if trade.get('Status') == 'OPEN':
                symbol = trade.get('Pair')
                asset_class = trade.get('AssetClass', 'Unknown')
                current_price = fetch_current_price(symbol, asset_class)
                if current_price > 0:
                    trade['CurrentPrice'] = current_price
                    # Calculate current Value
                    qty = float(trade.get('Size', 0) or 0)
                    trade['Value'] = qty * current_price

        # Filter actual trades (exclude SKIPPED/INFO and DB OPEN Crypto)
        clean_db_actual = [t for t in trades if t.get('Status', '').upper() in ['OPEN', 'CLOSED', 'TP', 'SL']]
        clean_db_actual = [t for t in clean_db_actual if not (t.get('AssetClass') == 'Crypto' and t.get('Status') == 'OPEN')]
        
        # Merge with live positions for statistics
        all_stats_trades = live_positions + clean_db_actual
        
        total_pnl = sum(float(t.get('PnL', 0.0)) for t in all_stats_trades)
        win_count = sum(1 for t in all_stats_trades if float(t.get('PnL', 0.0)) > 0)
        total_count = len(all_stats_trades)
        win_rate = (win_count / total_count * 100) if total_count > 0 else 0

        # Allocation Breakdown (End of year state)
        if year_filter and year_filter != 'ALL':
            cutoff = f"{int(year_filter)+1}-01-01"
            cum_trades = [t for t in all_trades if t.get('Timestamp', '') < cutoff]
        else:
            cum_trades = all_trades

        # =====================================================================
        # FETCH REAL BALANCES FROM BROKERS
        # =====================================================================
        binance_balance = fetch_binance_balance(binance_ex)
        print(f"DEBUG: Binance Balance = {binance_balance}")
        
        oanda_data = fetch_oanda_balance()  # Returns {balance, nav, unrealized_pnl} or None
        oanda_balance = oanda_data['balance'] if oanda_data else None
        oanda_unrealized = oanda_data['unrealized_pnl'] if oanda_data else 0
        print(f"DEBUG: Oanda Balance = {oanda_balance}")

        # =====================================================================
        # ALLOCATION LOGIC
        # Binance → Crypto (80%) + Commodities (20%)
        # Oanda   → Forex (50%) + Indices (50%)  [fallback CALC $200 if not connected]
        # =====================================================================
        
        # Split ratios
        CRYPTO_SHARE = 0.80
        COMMODITIES_SHARE = 0.20
        FOREX_SHARE = 0.50
        INDICES_SHARE = 0.50
        
        # Fallback allocations (only if broker not connected)
        FOREX_FALLBACK = 200.0
        INDICES_FALLBACK = 200.0
        
        # Separate live Binance positions by asset class
        crypto_live_positions = [p for p in live_positions if p.get('AssetClass') == 'Crypto']
        commodities_live_positions = [p for p in live_positions if p.get('AssetClass') == 'Commodities']

        allocations = {}
        for asset_class in ['Crypto', 'Forex', 'Indices', 'Commodities']:

            # Data from DynamoDB (trade history)
            asset_trades = [t for t in cum_trades if t.get('AssetClass') == asset_class]
            db_actual = [t for t in asset_trades if t.get('Status', '').upper() in ['OPEN', 'CLOSED', 'TP', 'SL']]
            db_closed = [t for t in db_actual if t.get('Status', '').upper() != 'OPEN']
            
            closed_pnl = sum(float(t.get('PnL', 0.0)) for t in db_closed)
            closed_count = len(db_closed)
            open_count = sum(1 for t in db_actual if t.get('Status', '').upper() == 'OPEN')
            
            # Default Calculation (Calculated)
            pnl = sum(float(t.get('PnL', 0.0)) for t in db_actual)
            current = 0
            source = 'CALCULATED'

            # ── BINANCE: Crypto (80%) ──
            if asset_class == 'Crypto' and binance_balance is not None:
                unrealized_live = sum(float(p.get('PnL', 0)) for p in crypto_live_positions)
                pnl = closed_pnl + unrealized_live
                current = (binance_balance * CRYPTO_SHARE) + unrealized_live
                open_count = len(crypto_live_positions)
                source = 'LIVE'
            
            # ── BINANCE: Commodities (20%) ──
            elif asset_class == 'Commodities' and binance_balance is not None:
                unrealized_live = sum(float(p.get('PnL', 0)) for p in commodities_live_positions)
                pnl = closed_pnl + unrealized_live
                current = (binance_balance * COMMODITIES_SHARE) + unrealized_live
                open_count = len(commodities_live_positions)
                source = 'LIVE'
            
            # ── OANDA: Forex (50%) ──
            elif asset_class == 'Forex' and oanda_balance is not None:
                current = oanda_balance * FOREX_SHARE
                pnl = closed_pnl + (oanda_unrealized * FOREX_SHARE)
                source = 'LIVE'
            
            # ── OANDA: Indices (50%) ──
            elif asset_class == 'Indices' and oanda_balance is not None:
                current = oanda_balance * INDICES_SHARE
                pnl = closed_pnl + (oanda_unrealized * INDICES_SHARE)
                source = 'LIVE'
            
            # ── FALLBACK: Forex/Indices not connected ──
            elif asset_class == 'Forex':
                current = FOREX_FALLBACK + pnl
            elif asset_class == 'Indices':
                current = INDICES_FALLBACK + pnl

            allocations[asset_class] = {
                'initial': round(current - pnl, 2),
                'current': round(current, 2),
                'pnl': round(pnl, 2),
                'total': open_count + closed_count,
                'open': open_count,
                'closed': closed_count,
                'source': source
            }

        # RECALCUL TOTAL EQUITY (Dynamic sum of all allocations)
        total_current_equity = sum(a['current'] for a in allocations.values())

        response_body = {
            'stats': {
                'total_pnl': round(total_pnl, 2),
                'win_rate': round(win_rate, 1),
                'total_trades': total_count,
                'current_equity': round(total_current_equity, 2)
            },
            'allocations': allocations,
            'equity_curve': equity_data,
            'recent_trades': recent_trades,
            'year': year_filter or 'ALL',
            'debug': {
                'ccxt_available': CCXT_AVAILABLE,
                'binance_connected': binance_ex is not None,
                'binance_balance': binance_balance,
                'oanda_connected': oanda_balance is not None,
                'oanda_balance': oanda_balance,
                'live_pos_count': len(live_positions)
            }
        }

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(response_body, cls=DecimalEncoder)
        }

    except Exception as e:
        print(f"🔥 Lambda Error: {e}")
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': str(e), 'trace': traceback.format_exc()})
        }
