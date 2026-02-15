import json
import os
import boto3
import logging
import requests
import html
import pytz
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from exchange_connector import ExchangeConnector

# Setup Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS Clients
dynamodb = boto3.resource('dynamodb')
PARIS_TZ = pytz.timezone('Europe/Paris')

def get_paris_time():
    """Returns current Paris time using pytz (Audit Fix #4)"""
    return datetime.now(PARIS_TZ)

# Configuration from Environment (Audit Fix #3, #10)
MAIN_TABLE = os.environ.get('HISTORY_TABLE', 'EmpireTradesHistory')
DEFAULT_TABLES = f"{MAIN_TABLE},EmpireCryptoV4,EmpireForexHistory,EmpireIndicesHistory,EmpireCommoditiesHistory"
TABLES_TO_SCAN = os.environ.get('REPORTER_TABLES', DEFAULT_TABLES).split(',')
RECIPIENT = os.environ.get('RECIPIENT_EMAIL', 'zelhayani@gmail.com')
INITIAL_BUDGET = float(os.environ.get('INITIAL_BUDGET', '20000.0'))
SES_REGION = os.environ.get('AWS_REGION', 'ap-northeast-1')
ses = boto3.client('ses', region_name=SES_REGION)
s3 = boto3.client('s3', region_name=SES_REGION)
DASHBOARD_BUCKET = os.environ.get('DASHBOARD_BUCKET')

def get_yahoo_ticker(symbol):
    """Maps internal symbols to Yahoo Finance tickers (Audit Fix #11)"""
    # 🏛️ EMPIRE V13.8: Specific Mappings
    ticker_map = {
        'SPX/USDT:USDT': '^GSPC',
        'DAX/USDT:USDT': '^GDAXI',
        'NDX/USDT:USDT': '^IXIC',
        'OIL/USDT:USDT': 'CL=F',
        'PAXG/USDT:USDT': 'GC=F', # Gold proxy
    }
    if symbol in ticker_map:
        return ticker_map[symbol]
    
    # Generic cleaning
    s = symbol.split('/')[0]
    if 'EUR/USD' in symbol: return 'EURUSD=X'
    if 'GBP/USD' in symbol: return 'GBPUSD=X'
    if 'USD/JPY' in symbol: return 'USDJPY=X'
    
    return s

def fetch_yahoo_price_lite(symbol):
    """Récupère le prix pour Forex/Indices/Commodities via Yahoo Finance"""
    try:
        ticker = get_yahoo_ticker(symbol)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=4)
        response.raise_for_status()
        data = response.json()
        return float(data['chart']['result'][0]['meta']['regularMarketPrice'])
    except Exception as e:
        logger.error(f"⚠️ Yahoo Price Error ({symbol} -> {ticker if 'ticker' in locals() else 'N/A'}): {e}")
        return 0.0

def get_quote_currency(pair, asset_class):
    # Normalize for robust comparison (Audit Fix)
    ac = str(asset_class or "").lower()
    if ac == 'forex': 
        return pair[3:] if len(pair) == 6 else 'USD'
    if ac == 'crypto':
        if pair.endswith('USDT') or pair.endswith('USD'): return 'USD'
        if pair.endswith('EUR'): return 'EUR'
    if ac in ['indices', 'commodities']:
        if pair.startswith('^FCHI'): return 'EUR' # CAC40
        return 'USD'
    return 'USD'

def get_eur_rate(quote_currency):
    if quote_currency == 'EUR': return 1.0
    try:
        # Map USDT -> USD
        sym = 'USD' if quote_currency == 'USDT' else quote_currency
        rate = fetch_yahoo_price_lite(f"EUR{sym}=X")
        return rate if rate > 0 else 1.0
    except Exception as e:
        logger.warning(f"⚠️ EUR Rate Error ({quote_currency}): {e}")
        return 1.0

def normalize_trade(item: dict) -> dict:
    """
    Normalize fields from various versions (snake_case vs PascalCase) (Audit Fix #1).
    Ensures consistency across all tables.
    """
    def to_float(val, default=0.0):
        try:
            return float(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    # Mapping logic: check snake_case (current V11) then PascalCase (Legacy)
    res = {
        'symbol': item.get('symbol') or item.get('Symbol') or item.get('Pair') or 'UNKNOWN',
        'status': item.get('status') or item.get('Status') or 'UNKNOWN',
        'asset_class': (item.get('asset_class') or item.get('AssetClass') or 'Unknown').capitalize(),
        'entry_price': to_float(item.get('entry_price') or item.get('EntryPrice')),
        'side': (item.get('side') or item.get('Type') or 'LONG').upper(),
        'size': to_float(item.get('size') or item.get('Size') or item.get('quantity') or item.get('Quantity')),
        'cost': to_float(item.get('cost') or item.get('Cost')),
        'pnl': to_float(item.get('pnl') or item.get('PnL')),
        'exit_reason': item.get('exit_reason') or item.get('ExitReason') or item.get('Reason') or item.get('reason') or '',
        'timestamp': item.get('timestamp') or item.get('Timestamp') or '',
        'exit_price': to_float(item.get('exit_price') or item.get('ExitPrice')),
        'trade_id': item.get('trade_id') or item.get('Trade_ID') or item.get('trader_id') or 'N/A'
    }
    
    # Financial Consistency Check (Audit Fix Round 4)
    # If cost is 0 but entry/size exist, recalculate
    if res['cost'] == 0 and res['entry_price'] > 0 and res['size'] > 0:
        res['cost'] = res['entry_price'] * res['size']
    
    # If PnL is 0 and status is CLOSED, attempt to estimate if possible
    if res['pnl'] == 0 and res['status'].upper() in ['CLOSED', 'EXIT', 'SL', 'TP'] and res['exit_price'] > 0:
        if res['side'] == 'LONG':
            res['pnl'] = (res['exit_price'] - res['entry_price']) * res['size']
        else:
            res['pnl'] = (res['entry_price'] - res['exit_price']) * res['size']

    return res

def get_all_trades():
    """Fetches all trades from multiple tables with pagination (Audit Fix #2)"""
    all_items = []
    for table_name in TABLES_TO_SCAN:
        try:
            table = dynamodb.Table(table_name)
            response = table.scan()
            data = response.get('Items', [])
            
            # Pagination loop
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                data.extend(response.get('Items', []))
                
            # Normalize items immediately
            all_items.extend([normalize_trade(i) for i in data])
            logger.info(f"✅ Fetched {len(data)} items from {table_name}")
        except Exception as e:
            logger.error(f"❌ Error scanning table {table_name}: {e}")
    return all_items

def format_reason_text(reason):
    """Sniper-style formatting for trade reasons (Compact & Icons)"""
    if not reason: return ""
    r = str(reason).upper()
    
    if "GHOST" in r: return "🧹 GHOST"
    if "SYNC" in r: return "🧹 SYNC"
    if "POSITION" in r and "RÉELLE" in r: return "🟢 ACTIVE"
    if "TAKE_PROFIT" in r or "TP_HIT" in r or "TP" == r: return "✅ TAKE PROFIT"
    if "STOP_LOSS" in r or "SL_HIT" in r or "SL" == r: return "🛑 STOP LOSS"
    if "TIMEOUT" in r or "MAX_HOLD" in r: return "⏱️ TIMEOUT"
    if "PROFIT_1PCT" in r: return "💰 TARGET HIT"
    if "ANTI_TREND" in r: return "🛡️ RESCUE"
    
    # Generic cleanup
    r = r.replace("EXIT: ", "").replace("CLOSED: ", "").replace("_", " ")
    return r[:20]

def lambda_handler(event, context):
    logger.info("📊 Generating Global Empire Report")
    
    try:
        all_trades = get_all_trades()
        if not all_trades:
            logger.warning("⚠️ No trades found in any table.")
            return {"status": "EMPTY_RESOURCES"}

        exchange = ExchangeConnector('binance')
        price_cache = {}  # Audit Fix #5: Avoid Redundant API Calls

        def get_current_price(pair, asset_class):
            if pair in price_cache:
                return price_cache[pair]
            
            try:
                # Robust case-insensitive check
                ac = str(asset_class or "").capitalize()
                if ac == 'Crypto':
                    price = float(exchange.fetch_ticker(pair)['last'])
                else:
                    price = fetch_yahoo_price_lite(pair)
                    if price == 0 and asset_class == 'Forex':
                        price = fetch_yahoo_price_lite(pair + "=X")
                
                price_cache[pair] = price
                return price
            except Exception as e:
                logger.error(f"Error fetching price for {pair}: {e}")
                return 0.0

        # 1. Active Positions (Status = OPEN)
        open_trades = [t for t in all_trades if t['status'] == 'OPEN']
        
        # Group Active by Asset Class
        categories = {} 
        for t in open_trades:
            ac = t['asset_class']
            if ac not in categories: categories[ac] = {}
            pair = t['symbol']
            if pair not in categories[ac]: categories[ac][pair] = []
            categories[ac][pair].append(t)

        # --- FINANCIAL SUMMARY ---
        total_buy = 0.0
        total_sell = 0.0
        realized_pnl = 0.0
        unrealized_pnl = 0.0
        open_positions_value = 0.0
        
        # Calculate totals
        for t in all_trades:
            status = t['status']
            if status == 'SKIPPED': continue
            
            # Cost basis
            cost = t['cost']
            if cost == 0:
                cost = t['size'] * t['entry_price']
            
            total_buy += cost
            
            if status != 'OPEN':
                # For closed trades, calculate exit value
                exit_price = t['exit_price']
                val = exit_price * t['size']
                if val == 0:
                    val = cost # Fallback
                
                total_sell += val
                
                # Realized PnL
                pnl = t['pnl']
                if pnl == 0 and val > 0:
                    # Infer PnL if not explicitly stated
                    if t['side'] == 'SHORT':
                        pnl = cost - val
                    else:
                        pnl = val - cost
                realized_pnl += pnl

        html_sections = ""
        
        # --- SECTION 1: ACTIVE POSITIONS ---
        for ac, pairs in categories.items():
            html_sections += f"<div class='section-title'>{html.escape(ac.upper())} - POSITIONS ACTIVES</div>"
            html_sections += """<table class="empire-table">
                <thead><tr>
                    <th style='text-align:left'>ACTIF</th>
                    <th style='text-align:center'>TYPE</th>
                    <th style='text-align:right'>QTÉ</th>
                    <th style='text-align:right'>PRIX ACHAT (Total)</th>
                    <th style='text-align:right'>PRIX ACTUEL (Total)</th>
                    <th style='text-align:right'>PnL %</th>
                    <th style='text-align:right'>PnL €</th>
                </tr></thead><tbody>"""
            
            for pair, trades_list in pairs.items():
                curr_price = get_current_price(pair, ac)

                total_qty = sum(t['size'] for t in trades_list)
                # Audit Fix #6: Weighted Average Entry Price
                avg_entry = sum(t['entry_price'] * t['size'] for t in trades_list) / total_qty if total_qty > 0 else 0
                direction = trades_list[0]['side']

                # Conversion Currency Logic
                quote_currency = get_quote_currency(pair, ac)
                eur_rate = get_eur_rate(quote_currency)
                
                # Calculate Notional Values in EUR
                curr_val_notional = (total_qty * curr_price) / eur_rate
                entry_val_notional = (total_qty * avg_entry) / eur_rate
                
                # Determine PnL (Based on Notional Variation)
                if direction == 'SHORT':
                    pnl_eur = entry_val_notional - curr_val_notional
                else:
                    pnl_eur = curr_val_notional - entry_val_notional

                # Cost & Display Value
                pos_cost = sum(t['cost'] for t in trades_list)
                if pos_cost == 0:
                    pos_cost = entry_val_notional
                
                # Value = Cost + PnL
                pos_value = pos_cost + pnl_eur
                
                unrealized_pnl += pnl_eur
                open_positions_value += pos_value
                
                # Audit Fix #7: Correct PnL % calculation
                if avg_entry > 0 and curr_price > 0:
                    if direction == 'LONG':
                        pnl_pct = ((curr_price - avg_entry) / avg_entry * 100)
                    else:
                        pnl_pct = ((avg_entry - curr_price) / avg_entry * 100)
                else:
                    pnl_pct = 0.0
                
                if ac == 'Crypto': qty_fmt = f"{total_qty:.4f}"
                elif ac == 'Forex': qty_fmt = f"{total_qty:,.0f}"
                else: qty_fmt = f"{total_qty:.2f}"

                color = "#10B981" if pnl_eur >= 0 else "#EF4444"

                html_sections += f"""
                <tr>
                    <td style="font-weight:bold;">{html.escape(pair)}</td>
                    <td style="text-align:center;"><span class="badge {html.escape(direction)}">{html.escape(direction)}</span></td>
                    <td style="text-align:right;">{qty_fmt}</td>
                    <td style="text-align:right;">€{pos_cost:,.2f}</td>
                    <td style="text-align:right;">€{pos_value:,.2f}</td>
                    <td style="text-align:right; font-weight:bold; color:{color};">{pnl_pct:+.2f}%</td>
                    <td style="text-align:right; font-weight:bold; color:{color};">{pnl_eur:+.2f}€</td>
                </tr>"""
            html_sections += "</tbody></table>"

        current_budget = INITIAL_BUDGET + realized_pnl + unrealized_pnl
        
        # Build Summary HTML
        summary_html = f"""
        <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; margin-bottom: 20px;">
            <div style="background:#f1f5f9; padding:15px; border-radius:8px; text-align:center;">
                <div style="font-size:10px; color:#64748b; font-weight:bold;">BUDGET INITIAL</div>
                <div style="font-size:16px; font-weight:bold; color:#1e293b;">€{INITIAL_BUDGET:,.0f}</div>
            </div>
            <div style="background:#dcfce7; padding:15px; border-radius:8px; text-align:center;">
                <div style="font-size:10px; color:#166534; font-weight:bold;">TOTAL VENTE</div>
                <div style="font-size:16px; font-weight:bold; color:#166534;">€{total_sell:,.2f}</div>
            </div>
            <div style="background:#fee2e2; padding:15px; border-radius:8px; text-align:center;">
                <div style="font-size:10px; color:#991b1b; font-weight:bold;">TOTAL ACHAT</div>
                <div style="font-size:16px; font-weight:bold; color:#991b1b;">€{total_buy:,.2f}</div>
            </div>
            <div style="background:#3b82f6; padding:15px; border-radius:8px; text-align:center;">
                <div style="font-size:10px; color:#1e3a8a; font-weight:bold;">BUDGET ACTUEL</div>
                <div style="font-size:16px; font-weight:bold; color:#1e3a8a;">€{current_budget:,.2f}</div>
            </div>
        </div>
        """
        
        # Prepend summary to html_sections
        html_sections = summary_html + html_sections

        if not open_trades:
            html_sections += "<div style='text-align:center;padding:30px;color:#94a3b8;'>💤 Aucune position active</div>"

        # --- TRIGGER & TIME WINDOWS (Audit Fix #4) ---
        now = get_paris_time()
        trigger_lookback = now - timedelta(minutes=30)
        daily_lookback = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        recent_events = []
        todays_events = []
        
        for t in all_trades:
            ts_str = t['timestamp']
            if not ts_str:
                continue
            try:
                # Parse and normalize to Paris time for reliable comparison
                ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                ts_paris = ts_dt.astimezone(PARIS_TZ)
                
                if ts_paris >= trigger_lookback:
                    recent_events.append(t)
                if ts_paris >= daily_lookback:
                    todays_events.append(t)
            except Exception as e:
                logger.warning(f"Could not parse timestamp {ts_str}: {e}")

        # If no recent events (at all, including SKIPPED), skip the email (Audit Fix #9)
        if not recent_events:
            logger.info("💤 No recent events (30m). Skipping report.")
            return {"status": "SKIPPED_NO_CHANGE"}
            
        logger.info(f"🚀 Triggered! {len(recent_events)} recent events found.")

        # --- SECTION: JOURNAL DU JOUR (Today's Activity) ---
        todays_events = sorted(todays_events, key=lambda x: x['timestamp'], reverse=True)
        
        if todays_events:
            html_sections += f"<div class='section-title' style='border-left-color: #f59e0b;'>JOURNAL DU JOUR ({now.strftime('%d/%m')})</div>"
            html_sections += """<table class="empire-table">
                <thead><tr>
                    <th style='text-align:left'>HEURE</th>
                    <th style='text-align:left'>ACTIF</th>
                    <th style='text-align:left'>EVENT</th>
                    <th style='text-align:right'>PnL</th>
                </tr></thead><tbody>"""
            
            for ev in todays_events:
                ts = ev['timestamp']
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    time_str = dt.strftime('%H:%M')
                except:
                    time_str = ts[-8:-3] if len(ts) > 8 else ts
                
                pair = ev['symbol']
                status = ev['status']
                tipo = ev['side']
                
                clean_reason = format_reason_text(ev.get('exit_reason', ''))

                if status == 'OPEN':
                    event_desc = f"🟢 <b>OPEN {html.escape(tipo)}</b>"
                    row_bg = "#f0fdf4"
                elif 'CLOSED' in status or status in ['TP', 'SL']:
                    event_desc = f"🔴 <b>CLOSED</b> <span style='color:#64748b;font-size:10px'>| {html.escape(clean_reason)}</span>"
                    row_bg = "#fef2f2"
                elif status == 'SKIPPED':
                    event_desc = f"⚪ <i>SKIP</i> <span style='color:#94a3b8;font-size:10px'>| {html.escape(clean_reason)}</span>"
                    row_bg = "#ffffff"
                else:
                    event_desc = f"{html.escape(status)}"
                    row_bg = "#ffffff"
                
                # PnL Display
                pnl_disp = ""
                pnl_val = ev['pnl']
                if pnl_val != 0:
                    color = "#16a34a" if pnl_val > 0 else "#dc2626"
                    pnl_disp = f"<span style='color:{color};font-weight:bold;'>{pnl_val:+.2f}€</span>"

                html_sections += f"""
                <tr style="background-color:{row_bg};">
                    <td style="color:#64748b; font-size:11px;">{time_str}</td>
                    <td style="font-weight:bold;">{html.escape(pair)}</td>
                    <td style="font-size:11px; color:#334155;">{event_desc}</td>
                    <td style="text-align:right;">{pnl_disp}</td>
                </tr>"""
            html_sections += "</tbody></table>"

        # --- SECTION 2: RECENT AI TRADES (Last 10) ---
        actual_trades = [t for t in all_trades if t['status'] != 'SKIPPED']
        recent_trades = sorted(actual_trades, key=lambda x: x['timestamp'], reverse=True)[:10]
        
        if recent_trades:
            html_sections += "<div class='section-title' style='border-left-color: #8b5cf6;'>RECENT AI TRADES</div>"
            html_sections += """<table class="empire-table">
                <thead><tr>
                    <th style='text-align:left'>DATE</th>
                    <th style='text-align:left'>ACTIF</th>
                    <th style='text-align:right'>PRIX</th>
                    <th style='text-align:center'>TYPE</th>
                    <th style='text-align:right'>QTÉ</th>
                    <th style='text-align:right'>PRIX ACHAT (Total)</th>
                    <th style='text-align:right'>PRIX ACTUEL (Total)</th>
                    <th style='text-align:center'>STATUS</th>
                    <th style='text-align:right'>PnL %</th>
                    <th style='text-align:right'>PnL €</th>
                </tr></thead><tbody>"""
                
            for t in recent_trades:
                ts = t['timestamp']
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    date_str = dt.strftime('%d/%m %H:%M')
                except:
                    date_str = ts[:16]

                pair = t['symbol']
                ac = t['asset_class']
                direction = t['side']
                status = t['status']
                exit_reason = t['exit_reason']
                
                qty = t['size']
                entry_price = t['entry_price']
                
                # Price Cache use
                current_price = get_current_price(pair, ac)
                exit_price = t['exit_price'] if status != 'OPEN' else current_price
                if exit_price == 0: exit_price = current_price
                
                quote_currency = get_quote_currency(pair, ac)
                eur_rate = get_eur_rate(quote_currency)
                
                if status == 'OPEN':
                    curr_val_notional = (qty * current_price) / eur_rate
                    entry_val_notional = (qty * entry_price) / eur_rate
                    pnl_eur = (entry_val_notional - curr_val_notional) if direction == 'SHORT' else (curr_val_notional - entry_val_notional)
                    cost = t['cost'] if t['cost'] > 0 else entry_val_notional
                    value = cost + pnl_eur
                else:
                    cost = t['cost'] if t['cost'] > 0 else (qty * entry_price) / eur_rate
                    pnl_eur = t['pnl'] if t['pnl'] != 0 else (exit_price * qty / eur_rate - cost)
                    value = cost + pnl_eur

                # Audit Fix #7: Correct PnL % calculation for recent trades
                if entry_price > 0 and exit_price > 0:
                    if direction == 'LONG':
                        pnl_pct = ((exit_price - entry_price) / entry_price * 100)
                    else:
                        pnl_pct = ((entry_price - exit_price) / entry_price * 100)
                else:
                    pnl_pct = 0.0
                
                # Format status badge
                # Format status badge (Sniper Style)
                reason_clean = format_reason_text(exit_reason) if exit_reason else status
                
                if status == 'OPEN':
                    status_badge = '<span style="background:#dbeafe;color:#1d4ed8;padding:2px 6px;border-radius:4px;font-size:10px;">🟢 OPEN</span>'
                elif exit_reason and "STOP_LOSS" in str(exit_reason) or status == 'SL':
                    status_badge = '<span style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:10px;">🛑 SL</span>'
                elif exit_reason and "TAKE_PROFIT" in str(exit_reason) or status == 'TP':
                    status_badge = '<span style="background:#dcfce7;color:#166534;padding:2px 6px;border-radius:4px;font-size:10px;">✅ TP</span>'
                else:
                    # Generic (Ghost, Timeout, Sync...)
                    text = reason_clean if reason_clean else status[:8]
                    status_badge = f'<span style="background:#f1f5f9;color:#475569;padding:2px 6px;border-radius:4px;font-size:10px;">{html.escape(text)}</span>'
                
                color = '#16a34a' if pnl_eur >= 0 else '#dc2626'
                pnl_pct_str = f'<span style="color:{color};font-weight:bold;">{pnl_pct:+.2f}%</span>'
                pnl_eur_str = f'<span style="color:{color};font-weight:bold;">{pnl_eur:+.2f}€</span>'

                html_sections += f"""
                <tr>
                    <td style="color:#64748b; font-size:11px;">{date_str}</td>
                    <td style="font-weight:bold;">{html.escape(pair)}</td>
                    <td style="font-family:monospace; color:#0ea5e9;">${entry_price:,.2f}</td>
                    <td style="text-align:center;"><span class="badge {html.escape(direction)}">{html.escape(direction)}</span></td>
                    <td style="text-align:right;">{qty:,.4f}</td>
                    <td style="text-align:right;">€{cost:,.2f}</td>
                    <td style="text-align:right;">€{value:,.2f}</td>
                    <td style="text-align:center;">{status_badge}</td>
                    <td style="text-align:right;">{pnl_pct_str}</td>
                    <td style="text-align:right;">{pnl_eur_str}</td>
                </tr>"""
            html_sections += "</tbody></table>"

        # --- Construction de l'Email (Style Dashboard) ---
        html_body = f"""
        <html>
        <head><style>
            body {{ font-family: sans-serif; background: #f8fafc; padding: 20px; }}
            .container {{ max-width: 800px; margin: auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
            .header {{ background: #1e293b; color: white; padding: 20px; text-align: center; }}
            .section-title {{ font-size: 12px; font-weight: bold; color: #64748b; padding: 20px 20px 10px 20px; border-left: 4px solid #3b82f6; }}
            .empire-table {{ width: 100%; border-collapse: collapse; }}
            .empire-table th {{ background: #f1f5f9; padding: 12px; font-size: 11px; color: #64748b; }}
            .empire-table td {{ padding: 12px; border-bottom: 1px solid #f1f5f9; font-size: 13px; word-break: break-word; white-space: normal; }}
            .badge {{ padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }}
            .badge.LONG {{ background: #dcfce7; color: #166534; }}
            .badge.SHORT {{ background: #fee2e2; color: #991b1b; }}
        </style></head>
        <body>
            <div class="container">
                <div class="header"><h1>🏛️ EMPIRE GLOBAL STATUS</h1></div>
                <div style="padding: 10px;">{html_sections}</div>
                <div style="padding: 20px; font-size: 10px; color: #94a3b8; text-align: center;">Updated: {get_paris_time().strftime('%Y-%m-%d %H:%M')}</div>
            </div>
        </body></html>
        """
        
        if not open_trades and not todays_events:
            logger.info("💤 No significant activity to report. Skipping email.")
            return {"status": "SKIPPED_NO_CONTENT"}

        # 🏛️ EMPIRE V16.7.4: Generate Signed URL for Dashboard (1 hour validity)
        presigned_url = None
        if DASHBOARD_BUCKET:
            try:
                key = "index.html"
                s3.put_object(
                    Bucket=DASHBOARD_BUCKET,
                    Key=key,
                    Body=html_body,
                    ContentType='text/html'
                )
                presigned_url = s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': DASHBOARD_BUCKET, 'Key': key},
                    ExpiresIn=3600
                )
                logger.info(f"✅ Dashboard URL generated: {presigned_url[:50]}...")
            except Exception as e:
                logger.error(f"❌ Error generating dashboard URL: {e}")

        # Inject URL into email body if available
        if presigned_url:
            dashboard_link_html = f"""
            <div style="text-align:center; padding: 20px; background: #fdf2f2; border: 1px dashed #f87171; border-radius: 8px; margin: 10px;">
                <p style="margin:0; font-weight:bold; color:#b91c1c;">🚀 ACCÈS DASHBOARD LIVE (1 heure)</p>
                <a href="{presigned_url}" style="display:inline-block; margin-top:10px; padding:12px 24px; background:#ef4444; color:white; text-decoration:none; border-radius:6px; font-weight:bold;">VOIR MON EMPIRE EN DIRECT</a>
            </div>
            """
            html_body = html_body.replace('<div class="header">', dashboard_link_html + '<div class="header">')

        ses.send_email(
            Source=RECIPIENT,
            Destination={'ToAddresses': [RECIPIENT]},
            Message={
                'Subject': {'Data': f"🏛️ Empire Report: {len(open_trades)} Open | {len(todays_events)} Today"},
                'Body': {'Html': {'Data': html_body}}
            }
        )
        logger.info("[SUCCESS] Email Sent.")
        return {"status": "SUCCESS"}
    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "ERROR"}
