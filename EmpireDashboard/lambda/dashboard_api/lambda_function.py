import json
import boto3
import os
import traceback
from urllib.request import Request, urlopen
from urllib.error import URLError
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import concurrent.futures

# Initialize DynamoDB Client
dynamodb = boto3.resource('dynamodb')
config_table_name = os.environ.get('CONFIG_TABLE', 'EmpireConfig')
config_table = dynamodb.Table(config_table_name)
 
# Unified History Table
TABLES_TO_SCAN = ["EmpireTradesHistory"]
trades_table = dynamodb.Table("EmpireTradesHistory")

# Global cache to mitigate API Gateway 30s timeout and DDB scan costs
_TRADES_CACHE = {
    'items': [],
    'timestamp': datetime.min
}
CACHE_TTL_SECONDS = 60

# Binance API (for real balance)
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    print("⚠️ CCXT not available, will use calculated balances")

def normalize_symbol(s):
    """Global Helper pour la réconciliation"""
    if not s: return ""
    return s.replace('/', '').replace(':', '').replace('-', '').replace('USDT', '').upper()

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
            ex_demo.set_sandbox_mode(True)
            
            # Elite Sniper Fix - preserve path structure, replace only domains
            demo_domain = "demo-fapi.binance.com"
            for collection in ['test', 'api']:
                if collection in ex_demo.urls:
                    for key in ex_demo.urls[collection]:
                        if isinstance(ex_demo.urls[collection][key], str):
                            url = ex_demo.urls[collection][key]
                            url = url.replace("fapi.binance.com", demo_domain)
                            url = url.replace("testnet.binancefuture.com", demo_domain)
                            url = url.replace("api.binance.com", demo_domain)
                            url = url.replace("demo-fdemo-fapi.binance.com", demo_domain)
                            ex_demo.urls[collection][key] = url
            ex_demo.options['fetchConfig'] = False
            
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

# Asset classification for multi-broker/multi-asset systems
COMMODITIES_SYMBOLS = ['PAXG', 'XAG', 'GOLD', 'SILVER']
FOREX_SYMBOLS = ['EUR', 'GBP', 'AUD', 'JPY', 'CHF', 'CAD']
INDICES_SYMBOLS = ['DEFI', 'NDX', 'GSPC', 'US30', 'SPX']

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
    """Récupère les positions RÉELLES directement depuis l'API Binance"""
    try:
        if not exchange: return []
        positions = exchange.fetch_positions()
        live_trades = []
        paris_now = get_paris_time()
        
        for pos in positions:
            # On vérifie plusieurs champs pour la taille (binance peut varier selon l'asset)
            # 1. 'contracts' (standard CCXT)
            # 2. 'amount' (alternatif CCXT)
            # 3. 'info.positionAmt' (Donnée brute Binance)
            contracts = float(pos.get('contracts', 0) or 0)
            amount = float(pos.get('amount', 0) or 0)
            info_amt = float(pos.get('info', {}).get('positionAmt', 0))
            
            # La taille réelle est le premier qui n'est pas nul
            size = contracts or amount or info_amt
            
            if size != 0:
                # Type de trade : basé sur le signe de la taille ou le champ 'side'
                side = pos.get('side', '').lower()
                if side == 'short' or size < 0:
                    trade_type = 'SHORT'
                else:
                    trade_type = 'LONG'
                
                # Dynamic classification (Crypto, Forex, Indices, Commodities)
                symbol = pos['symbol']
                asset_class = classify_asset(symbol)
                
                # Levier et Marge (Crucial pour Binance Futures)
                info = pos.get('info', {})
                
                # 1. Notionnel (Poids total sur le marché)
                notional = abs(float(pos.get('notional') or 0))
                if notional == 0:
                    entry_price = float(pos.get('entryPrice', 0) or 0)
                    notional = abs(size) * (entry_price or float(pos.get('currentPrice', 0) or 0))

                # 2. Marge / Mise (Ticket d'entrée)
                # Binance peut envoyer la marge dans plein de champs différents selon le mode
                raw_margin = float(
                    info.get('initialMargin') or 
                    info.get('isolatedMargin') or 
                    info.get('positionInitialMargin') or 
                    info.get('posMargin') or
                    0
                )
                
                # 3. Levier (Extraction et Recalcul)
                # On essaie de lire le levier rapporté
                leverage = float(pos.get('leverage') or info.get('leverage') or 0)
                
                # SÉCURITÉ : Si on a le notionnel et la marge, on calcule le levier réel
                # (Car Binance rapporte souvent '1' si le mode n'est pas explicitement setté par l'API)
                if notional > 0 and raw_margin > 0:
                    calculated_leverage = round(notional / raw_margin)
                    # Si le levier rapporté est 1 mais que le calcul donne > 1.5, on fait confiance au calcul
                    if leverage <= 1.1 and calculated_leverage > 1.5:
                        leverage = calculated_leverage
                elif leverage > 0 and raw_margin == 0:
                    # Fallback si on a le levier mais pas la marge
                    raw_margin = notional / leverage
                
                # Valeur par défaut si tout échoue (peu probable maintenant)
                if leverage == 0: leverage = 1.0
                if raw_margin == 0: raw_margin = notional

                live_trades.append({
                    'TradeId': f"LIVE_{symbol}",
                    'Timestamp': paris_now.isoformat(),
                    'Pair': symbol,
                    'AssetClass': asset_class,
                    'Type': trade_type,
                    'Size': abs(size),
                    'EntryPrice': float(pos.get('entryPrice', 0) or 0),
                    'CurrentPrice': float(pos.get('markPrice', 0) or 0),
                    'Status': 'OPEN',
                    'Source': 'BINANCE',
                    'PnL': float(pos.get('unrealizedPnl', 0) or 0),
                    'Notional': notional,
                    'Margin': raw_margin,
                    'Leverage': leverage,
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
    
    # 1. Map active Binance symbols (use set for O(1) lookup)
    active_symbols_norm = {normalize_symbol(p['Pair']) for p in binance_positions}
    
    # 2. Filter DB trades that are supposedly OPEN
    db_open_trades = [t for t in db_trades if t.get('Status', '').upper() == 'OPEN']
    
    reconciled_count = 0
    MAX_RECONCILE_PER_CALL = 5 # Limit to prevent timeout

    for trade in db_open_trades:
        if reconciled_count >= MAX_RECONCILE_PER_CALL:
            break
            
        db_pair_norm = normalize_symbol(trade.get('Pair'))
        is_active = db_pair_norm in active_symbols_norm

        if not is_active:
            reconciled_count += 1
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
                # Use Decimal for DynamoDB - Solid string conversion + clean rounding
                pnl_decimal = Decimal(str(round(float(pnl), 2)))
                exit_decimal = Decimal(str(float(exit_price)))
                
                table.update_item(
                    Key={
                        'TradeId': str(trade['TradeId']),
                        'Timestamp': str(trade['Timestamp'])
                    },
                    UpdateExpression="SET #s = :s, ExitPrice = :ep, PnL = :p, ClosedAt = :c, AI_Reason = :r",
                    ExpressionAttributeNames={'#s': 'Status'},
                    ExpressionAttributeValues={
                        ':s': 'CLOSED',
                        ':ep': exit_decimal,
                        ':p': pnl_decimal,
                        ':c': str(get_paris_time().isoformat()),
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

def safe_float(val, default=0.0):
    try:
        if val is None: return default
        return float(val)
    except:
        return default

class DecimalEncoder(json.JSONEncoder):
    """Helper class to convert Decimal and datetime items for JSON compatibility"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, set)):
            if isinstance(obj, set): return list(obj)
            return obj.isoformat()
        return super(DecimalEncoder, self).default(obj)

def scan_table_worker(table_name):
    """Worker function for parallel DDB scanning (No Pagination to avoid timeout)"""
    try:
        table = dynamodb.Table(table_name)
        response = table.scan() # Returns up to 1MB
        return response.get('Items', [])
    except Exception as e:
        print(f"❌ Error scanning {table_name}: {e}")
        return []

def get_all_trades(start_time=None):
    """Scan trading table (SEQUENTIAL & SAFE)"""
    global _TRADES_CACHE
    
    now = datetime.utcnow()
    # Purge/Cutoff sync: Last 3 days starting from midnight UTC
    cutoff_date = (now - timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_str = cutoff_date.isoformat()

    if (now - _TRADES_CACHE['timestamp']).total_seconds() < CACHE_TTL_SECONDS:
        print("🕯️ Using trades cache (TTL hit)")
        return [t for t in _TRADES_CACHE['items'] if t.get('Timestamp', '') >= cutoff_str]

    print(f"⚡ Cache expired, scanning EmpireTradesHistory (Since {cutoff_str})...")
    
    # Sequential Scan for stability
    # Use FilterExpression to reduce data transfer if possible, but keeping it simple for now
    try:
        raw_items = scan_table_worker("EmpireTradesHistory")
    except Exception as e:
        print(f"❌ Scan failed: {e}")
        return []

    processed = []
    for item in raw_items:
        ts = item.get('Timestamp', '')
        if ts < cutoff_str: continue 

        if start_time and (datetime.utcnow() - start_time).total_seconds() > 25:
            break

        # ROBUST CONVERSION
        if 'PnL' in item: item['PnL'] = safe_float(item.get('PnL'))
        if 'Size' in item: item['Size'] = safe_float(item.get('Size'))
        if 'EntryPrice' in item: item['EntryPrice'] = safe_float(item.get('EntryPrice'))
        if 'CurrentPrice' in item: item['CurrentPrice'] = safe_float(item.get('CurrentPrice'))
        
        item['Source'] = 'DYNAMO'
        processed.append(item)
            
    processed.sort(key=lambda x: x.get('Timestamp', ''), reverse=True)
    _TRADES_CACHE['items'] = processed
    _TRADES_CACHE['timestamp'] = now
    return processed



def calculate_equity_curve(trades, initial_capital=1000.0):
    current_equity = initial_capital
    equity_curve = []
    now_iso = datetime.utcnow().isoformat()

    # Filter for actual trades only (exclude SKIPPED/INFO)
    actual_trades = [t for t in trades if t.get('Status', '').upper() in ['OPEN', 'CLOSED', 'TP', 'SL']]

    if not actual_trades:
         # Default: start + now so Chart.js can draw a line
        return [
            {'x': '2026-01-01T00:00:00', 'y': initial_capital},
            {'x': now_iso, 'y': initial_capital, 'details': 'Current (no trades yet)'}
        ]

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
        pnl = safe_float(trade.get('PnL', 0.0))
        current_equity += pnl
        equity_curve.append({
            'x': trade.get('Timestamp'),
            'y': current_equity,
            'details': f"{trade.get('Pair')} ({trade.get('Type')}) PnL: {pnl}"
        })

    # Always append a "now" point so the chart extends to current time
    equity_curve.append({'x': now_iso, 'y': current_equity, 'details': 'Current'})
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
    start_time = datetime.utcnow()
    print(f"📊 Dashboard API Request: {json.dumps(event)}")

    # Standard CORS Headers for all responses
    cors_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token'
    }

    # Initialize CloudWatch Logs client
    logs_client = boto3.client('logs', region_name='eu-west-3')

    try:
        # Determine Route
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
                order_side = 'buy' if side.upper() == 'SHORT' else 'sell'
                print(f"⚡ Fermeture forcée : {order_side} {qty} {symbol}")
                
                order = exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=order_side,
                    amount=qty,
                    params={'reduceOnly': True}
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

        # --- TRANSACTIONS / INCOME HISTORY (/transactions) ---
        if '/transactions' in path:
            try:
                # Parse query params for time range (default: last 7 days)
                qp = event.get('queryStringParameters') or {}
                days = int(qp.get('days', '30'))
                days = min(days, 90)  # Cap at 90 days
                
                # Calculate cutoff timestamp
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                cutoff_iso = cutoff.isoformat()
                
                # Fetch all recent trades from DynamoDB (including those with DynamoDB errors)
                # Add limit to prevent excessive reads
                response = trades_table.scan(
                    FilterExpression='#ts > :cutoff',
                    ExpressionAttributeNames={
                        '#ts': 'Timestamp'
                    },
                    ExpressionAttributeValues={
                        ':cutoff': cutoff_iso
                    },
                    Limit=1000  # Prevent excessive DynamoDB reads
                )
                
                all_trades = response.get('Items', [])
                # Separate trades with PnL from those without (DynamoDB errors)
                closed_trades = []
                error_trades = []
                
                for trade in all_trades:
                    status = trade.get('Status', '').upper()
                    pnl = float(trade.get('PnL', 0))
                    
                    # Skip OPEN trades
                    if status == 'OPEN':
                        continue
                    
                    # Trades with PnL (successfully closed)
                    if pnl != 0 or status == 'CLOSED':
                        closed_trades.append(trade)
                    # Trades without PnL (DynamoDB errors during closure)
                    elif status in ['SKIPPED', 'BLOCKED', 'ERROR']:
                        error_trades.append(trade)
                
                # Process and summarize
                transactions = []
                summary = {
                    'REALIZED_PNL': 0,
                    'COMMISSION': 0,
                    'TOTAL_TRADES': 0,
                    'WINNING_TRADES': 0,
                    'LOSING_TRADES': 0,
                    'DYNAMODB_ERRORS': len(error_trades)
                }
                
                for trade in closed_trades:
                    pnl = float(trade.get('PnL', 0))
                    symbol = trade.get('Symbol', trade.get('Pair', ''))
                    timestamp = trade.get('ExitTime', trade.get('Timestamp', ''))
                    trade_id = trade.get('TradeID', '')
                    
                    # Estimate commission (0.04% per side = 0.08% total)
                    entry_price = float(trade.get('EntryPrice', 0))
                    size = float(trade.get('Size', 0))
                    commission = -(entry_price * size * 0.0008) if entry_price and size else 0
                    
                    # Add PnL transaction
                    transactions.append({
                        'timestamp': timestamp,
                        'symbol': symbol,
                        'type': 'REALIZED_PNL',
                        'amount': round(pnl, 6),
                        'info': trade_id
                    })
                    
                    # Add commission transaction
                    if commission != 0:
                        transactions.append({
                            'timestamp': timestamp,
                            'symbol': symbol,
                            'type': 'COMMISSION',
                            'amount': round(commission, 6),
                            'info': trade_id
                        })
                    
                    # Update summary
                    summary['REALIZED_PNL'] += pnl
                    summary['COMMISSION'] += commission
                    summary['TOTAL_TRADES'] += 1
                    if pnl > 0:
                        summary['WINNING_TRADES'] += 1
                    elif pnl < 0:
                        summary['LOSING_TRADES'] += 1
                
                # Round summary values
                for key in summary:
                    if isinstance(summary[key], float):
                        summary[key] = round(summary[key], 6)
                
                # Sort by timestamp descending
                transactions.sort(key=lambda x: x['timestamp'], reverse=True)
                
                total_income = round(summary['REALIZED_PNL'] + summary['COMMISSION'], 6)
                
                return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps({
                        'transactions': transactions[:500],
                        'summary': summary,
                        'total': total_income,
                        'days': days,
                        'count': len(transactions)
                    }, cls=DecimalEncoder)
                }
            except Exception as e:
                print(f"❌ Erreur transactions: {e}")
                traceback.print_exc()
                return {
                    'statusCode': 500,
                    'headers': cors_headers,
                    'body': json.dumps({'error': str(e)})
                }

        # --- LAMBDA CLOUDWATCH LOGS (/lambda-logs) ---
        if '/lambda-logs' in path:
            def fetch_group_logs(lg_name):
                try:
                    streams = logs_client.describe_log_streams(
                        logGroupName=lg_name,
                        orderBy='LastEventTime',
                        descending=True,
                        limit=2 # Just latest 2 streams
                    ).get('logStreams', [])
                    
                    group_logs = []
                    # Purge/Limit: Last 3 days starting from midnight UTC
                    cutoff_date = (datetime.utcnow() - timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
                    cutoff_ms = int(cutoff_date.timestamp() * 1000)
                    
                    for s in streams:
                        events = logs_client.get_log_events(
                            logGroupName=lg_name,
                            logStreamName=s['logStreamName'],
                            limit=30, # "Bride" per stream
                            startTime=cutoff_ms,
                            startFromHead=False
                        ).get('events', [])
                        
                        for ev in events:
                            message = ev['message'].strip()
                            if not message: continue
                            
                            is_error = any(kw in message.upper() for kw in ['ERROR', 'EXCEPTION', 'FAIL', 'CRITICAL', 'FATAL', '520'])
                            
                            if is_error:
                                group_logs.append({
                                    'Timestamp': datetime.fromtimestamp(ev['timestamp']/1000).isoformat(),
                                    'Source': lg_name.split('/')[-1],
                                    'Type': 'ERROR',
                                    'Message': message[:1000],
                                    'Stream': s['logStreamName']
                                })
                    return group_logs
                except Exception as e:
                    print(f"⚠️ Skip log group {lg_name}: {e}")
                    return []

            try:
                # Actual Log Groups from Audit #V11.2
                target_groups = [
                    '/aws/lambda/V4HybridLiveTrader',
                    '/aws/lambda/V4StatusReporter',
                    '/aws/lambda/ForexLiveTrader',
                    '/aws/lambda/IndicesLiveTrader',
                    '/aws/lambda/CommoditiesLiveTrader'
                ]
                
                all_logs = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    results = list(executor.map(fetch_group_logs, target_groups))
                    for res in results:
                        all_logs.extend(res)
                
                # Sort by timestamp descending
                all_logs.sort(key=lambda x: x['Timestamp'], reverse=True)
                
                return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps({'logs': all_logs[:150]}) # Final "Bride"
                }
            except Exception as e:
                print(f"🔥 logs final fail: {e}")
                return { 'statusCode': 500, 'headers': cors_headers, 'body': json.dumps({'error': str(e)}) }


        # --- STATS LOGIC (/stats or default) ---
        query_params = event.get('queryStringParameters') or {}
        year_filter = query_params.get('year')

        # 1. Fetch All Trades from DDB (Parallel & Safe)
        all_trades_from_db = get_all_trades(start_time=start_time)

        # 2. Get Real-time Data from Binance
        binance_ex = get_binance_exchange()
        live_positions = fetch_binance_positions(binance_ex)
        binance_balance = fetch_binance_balance(binance_ex)

        # AUTO-RECONCILIATION
        if binance_ex:
            # Watchdog check (API GW 30s limit)
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed < 20:
                try:
                    reconcile_trades(all_trades_from_db, live_positions, binance_ex)
                except Exception as e:
                    print(f"⚠️ Reconciliation Error: {e}")
            else:
                print(f"⚠️ Skipping reconciliation to avoid timeout (Elapsed: {elapsed}s)")

        for lp in live_positions:
            lp_norm = normalize_symbol(lp.get('Pair'))
            # On cherche un trade OPEN dont le symbole normalisé correspond
            matching_db_trade = next((t for t in all_trades_from_db 
                                   if normalize_symbol(t.get('Pair')) == lp_norm 
                                   and t.get('Status', '').upper() == 'OPEN'), None)
            
            if matching_db_trade:
                # On prend la raison la plus complète disponible
                db_reason = matching_db_trade.get('AI_Reason') or matching_db_trade.get('Reason') or matching_db_trade.get('reason')
                if db_reason:
                    lp['AI_Reason'] = db_reason

        # 3. Allocation Breakdown Logic
        if year_filter and year_filter != 'ALL':
            cutoff = f"{int(year_filter)+1}-01-01"
            cum_trades = [t for t in all_trades_from_db if t.get('Timestamp', '') < cutoff]
        else:
            cum_trades = all_trades_from_db

        CRYPTO_SHARE = 0.40
        COMMODITIES_SHARE = 0.20
        FOREX_SHARE = 0.20
        INDICES_SHARE = 0.20

        # Dynamic Fallbacks based on typical ~5k budget
        CRYPTO_FALLBACK = 2000.0
        COMMODITIES_FALLBACK = 1000.0
        FOREX_FALLBACK = 1000.0
        INDICES_FALLBACK = 1000.0

        crypto_live = [p for p in live_positions if p.get('AssetClass') == 'Crypto']
        commo_live = [p for p in live_positions if p.get('AssetClass') == 'Commodities']
        forex_live = [p for p in live_positions if p.get('AssetClass') == 'Forex']
        indices_live = [p for p in live_positions if p.get('AssetClass') == 'Indices']

        allocations = {}
        for asset_class in ['Crypto', 'Forex', 'Indices', 'Commodities']:
            asset_trades = [t for t in cum_trades if t.get('AssetClass') == asset_class]
            db_actual = [t for t in asset_trades if t.get('Status', '').upper() in ['OPEN', 'CLOSED', 'TP', 'SL']]
            db_closed = [t for t in db_actual if t.get('Status', '').upper() != 'OPEN']
            
            closed_pnl = sum(safe_float(t.get('PnL', 0.0)) for t in db_closed)
            closed_count = len(db_closed)
            
            pnl = closed_pnl
            current = 0
            open_count = 0
            source = 'CALCULATED'

            if asset_class == 'Crypto':
                unrealized = sum(safe_float(p.get('PnL', 0)) for p in crypto_live)
                pnl = closed_pnl + unrealized
                open_count = len(crypto_live)
                if binance_balance is not None:
                    current = (binance_balance * CRYPTO_SHARE) + unrealized
                    source = 'LIVE'
                else:
                    current = CRYPTO_FALLBACK + pnl

            elif asset_class == 'Commodities':
                unrealized = sum(safe_float(p.get('PnL', 0)) for p in commo_live)
                pnl = closed_pnl + unrealized
                open_count = len(commo_live)
                if binance_balance is not None:
                    current = (binance_balance * COMMODITIES_SHARE) + unrealized
                    source = 'LIVE'
                else:
                    current = COMMODITIES_FALLBACK + pnl

            elif asset_class == 'Forex':
                unrealized = sum(safe_float(p.get('PnL', 0)) for p in forex_live)
                pnl = closed_pnl + unrealized
                open_count = len(forex_live)
                if binance_balance is not None:
                    current = (binance_balance * FOREX_SHARE) + unrealized
                    source = 'LIVE'
                else:
                    current = FOREX_FALLBACK + pnl

            elif asset_class == 'Indices':
                unrealized = sum(safe_float(p.get('PnL', 0)) for p in indices_live)
                pnl = closed_pnl + unrealized
                open_count = len(indices_live)
                if binance_balance is not None:
                    current = (binance_balance * INDICES_SHARE) + unrealized
                    source = 'LIVE'
                else: 
                    current = INDICES_FALLBACK + pnl

            share_pct = {'Crypto': CRYPTO_SHARE, 'Commodities': COMMODITIES_SHARE, 'Forex': FOREX_SHARE, 'Indices': INDICES_SHARE}.get(asset_class, 0.25) * 100
            
            allocations[asset_class] = {
                'initial': round(current - pnl, 2),
                'current': round(current, 2),
                'pnl': round(pnl, 2),
                'total': open_count + closed_count,
                'open': open_count,
                'closed': closed_count,
                'source': source,
                'share_pct': share_pct
            }

        # 4. Global Stats
        total_current_equity = sum(a['current'] for a in allocations.values())
        
        # Consistent logic for 'Total PnL' (Sum of all individual asset PnLs)
        total_pnl = sum(a['pnl'] for a in allocations.values())
        
        # List of all trades used for stats (Live + DDB)
        clean_db_actual = [t for t in all_trades_from_db if t.get('Status', '').upper() in ['OPEN', 'CLOSED', 'TP', 'SL']]
        clean_db_actual = [t for t in clean_db_actual if not (t.get('AssetClass') == 'Crypto' and t.get('Status') == 'OPEN')]
        all_stats_trades = live_positions + clean_db_actual
        
        win_count = sum(1 for t in all_stats_trades if safe_float(t.get('PnL', 0.0)) > 0)
        total_count = len(all_stats_trades)
        win_rate = (win_count / total_count * 100) if total_count > 0 else 0

        # 5. Equity Curve Generation
        base_capital_for_graph = total_current_equity - total_pnl

        if year_filter and year_filter != 'ALL':
            trades_year = [t for t in all_trades_from_db if t.get('Timestamp', '').startswith(year_filter)]
            trades_before = [t for t in all_trades_from_db if t.get('Timestamp', '') < f"{year_filter}-01-01"]
            pnl_before = sum(safe_float(t.get('PnL', 0.0)) for t in trades_before if t.get('Status', '').upper() in ['OPEN', 'CLOSED', 'TP', 'SL'])
            equity_data = calculate_equity_curve(trades_year, base_capital_for_graph + pnl_before)
        else:
            equity_data = calculate_equity_curve(all_trades_from_db, base_capital_for_graph)

        # 6. Recent Trades with Price Enrichment (Limited to last 48h for the table)
        # CRITICAL: We EXCLUDE all 'OPEN' trades from the database to avoid ghost positions (0$ x1).
        # Live positions are exclusively handled by the 'live_positions' list from Binance.
        trades_filtered = [t for t in all_trades_from_db if t.get('Status', '').upper() != 'OPEN']
        
        cutoff_48h = (datetime.now() - timedelta(hours=48)).isoformat()
        raw_recent = [t for t in trades_filtered if t.get('Timestamp', '') > cutoff_48h]
        
        # --- AUDIT V11.4: Grouping & Filtering by Occurrences (Backend optimization) ---
        # "N'affiche pas qd c'est moins de 4" - Reduce payload by only sending significant groups
        occurrence_counts = {}
        for t in all_trades_from_db:
            pair = t.get('Pair') or t.get('Symbol') or 'UNK'
            reason = t.get('ExitReason') or t.get('AI_Reason') or t.get('Reason') or t.get('reason') or '-'
            key = f"{pair}||{reason}"
            occurrence_counts[key] = occurrence_counts.get(key, 0) + 1
        
        # Filter raw_recent history trades based on global occurrence count
        raw_recent = [t for t in raw_recent if occurrence_counts.get(f"{t.get('Pair') or t.get('Symbol') or 'UNK'}||{t.get('ExitReason') or t.get('AI_Reason') or t.get('Reason') or t.get('reason') or '-'}", 0) >= 4]
        
        raw_recent = sorted(raw_recent, key=lambda x: x.get('Timestamp', ''), reverse=True)
        recent_trades = live_positions + raw_recent

        for trade in recent_trades:
            # Watchdog check inside loop
            if (datetime.utcnow() - start_time).total_seconds() > 27:
                print("🚨 Early exit from price enrichment to beat timeout")
                break

            # Optimization: Skip price fetch if markPrice was already provided by Binance
            if trade.get('Status') == 'OPEN' and not trade.get('CurrentPrice'):
                current_price = fetch_current_price(trade.get('Pair'), trade.get('AssetClass', 'Unknown'))
                if current_price > 0:
                    trade['CurrentPrice'] = current_price
                    trade['Value'] = float(trade.get('Size', 0) or 0) * current_price

        # 7. Skipped Trades (Audit #V11.6: Last 50 Skips)
        # We extract these separately to avoid them being hidden by the "4+ occurrences" filter of the history tab
        skipped_trades = [t for t in all_trades_from_db if (t.get('Status', '').upper() == 'SKIPPED' or 'SKIP' in t.get('Status', '').upper())]
        skipped_trades = sorted(skipped_trades, key=lambda x: x.get('Timestamp', ''), reverse=True)[:50]

        # 8. Final Response
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
            'skipped_trades': skipped_trades,
            'year': year_filter or 'ALL',
            'debug': {
                'ccxt_available': CCXT_AVAILABLE,
                'binance_connected': binance_ex is not None,
                'binance_balance': binance_balance,
                'live_pos_count': len(live_positions),
                'graph_base_capital': round(base_capital_for_graph, 2)
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
