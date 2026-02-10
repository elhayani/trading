import json
import os
import boto3
import logging
import requests
from datetime import datetime, timedelta

from exchange_connector import ExchangeConnector

# Setup Logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS Clients
dynamodb = boto3.resource('dynamodb')
ses = boto3.client('ses', region_name='eu-west-3')

def get_paris_time():
    """Returns current Paris time (UTC+1 for winter)"""
    return datetime.utcnow() + timedelta(hours=1)

# Tables à scanner
MAIN_TABLE = os.environ.get('HISTORY_TABLE', 'EmpireTradesHistory')
TABLES_TO_SCAN = [MAIN_TABLE, "EmpireCryptoV4", "EmpireForexHistory", "EmpireIndicesHistory", "EmpireCommoditiesHistory"]
RECIPIENT = "zelhayani@gmail.com"

def fetch_yahoo_price_lite(symbol):
    """Récupère le prix pour Forex/Indices/Commodities via Yahoo Finance"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=4)
        data = response.json()
        return float(data['chart']['result'][0]['meta']['regularMarketPrice'])
    except:
        return 0.0

def get_quote_currency(pair, asset_class):
    if asset_class == 'Forex': 
        return pair[3:] if len(pair) == 6 else 'USD'
    if asset_class == 'Crypto':
        if pair.endswith('USDT') or pair.endswith('USD'): return 'USD'
        if pair.endswith('EUR'): return 'EUR'
    if asset_class in ['Indices', 'Commodities']:
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
    except:
        return 1.0

def get_all_trades():
    all_items = []
    for table_name in TABLES_TO_SCAN:
        try:
            table = dynamodb.Table(table_name)
            # Scan all items (Limit/Filter optimization can be added later as tables grow)
            response = table.scan() 
            all_items.extend(response.get('Items', []))
        except Exception as e:
            logger.error(f"Error scanning {table_name}: {e}")
    return all_items

def lambda_handler(event, context):
    logger.info("📊 Generating Global Empire Report")
    
    try:
        all_trades = get_all_trades()
        exchange = ExchangeConnector('binance')
        
        # 1. Active Positions (Status = OPEN)
        open_trades = [t for t in all_trades if t.get('Status') == 'OPEN']
        
        # Group Active by Asset Class
        categories = {} 
        for t in open_trades:
            ac = t.get('AssetClass', 'Unknown')
            if ac not in categories: categories[ac] = {}
            pair = t.get('Pair')
            if pair not in categories[ac]: categories[ac][pair] = []
            categories[ac][pair].append(t)

        # --- FINANCIAL SUMMARY ---
        INITIAL_BUDGET = 20000.0  # Default Initial Capital Assumption
        total_buy = 0.0
        total_sell = 0.0
        realized_pnl = 0.0
        unrealized_pnl = 0.0
        open_positions_value = 0.0
        
        # Calculate totals from history (Closed Trades) and current open costs
        for t in all_trades:
            status = t.get('Status', 'OPEN')
            if status == 'SKIPPED': continue
            
            # Cost basis
            try:
                cost = float(t.get('Cost', 0) or 0)
                # Fallback if Cost is missing but we have EntryPrice * Size
                if cost == 0:
                    qty = float(t.get('Size', 0) or 0)
                    entry = float(t.get('EntryPrice', 0) or 0)
                    cost = qty * entry
            except:
                cost = 0.0
            
            total_buy += cost
            
            if status != 'OPEN':
                # For closed trades, Value is the exit value
                try:
                    val = float(t.get('Value', 0)) # Usually updated on close
                    # If Value missing, try ExitPrice * Size
                    if val == 0:
                        exit_price = float(t.get('ExitPrice', 0) or 0)
                        qty = float(t.get('Size', 0) or 0)
                        val = exit_price * qty
                except:
                    val = cost # Fallback break-even
                
                total_sell += val
                
                # Realized PnL
                try:
                    pnl = float(t.get('PnL', 0))
                except:
                    pnl = val - cost
                realized_pnl += pnl

        html_sections = ""
        
        # We will add Unrealized PnL during the Active Positions loop
        
        # --- SECTION 1: ACTIVE POSITIONS ---
        for ac, pairs in categories.items():
            html_sections += f"<div class='section-title'>{ac.upper()} - POSITIONS ACTIVES</div>"
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
                if ac == 'Crypto':
                    try:
                        curr_price = float(exchange.fetch_ticker(pair)['last'])
                    except:
                        curr_price = 0.0
                else:
                    curr_price = fetch_yahoo_price_lite(pair)
                    if curr_price == 0 and ac == 'Forex': curr_price = fetch_yahoo_price_lite(pair + "=X")

                total_qty = sum(float(t.get('Size', 0)) for t in trades_list)
                avg_entry = sum(float(t['EntryPrice']) for t in trades_list) / len(trades_list) if trades_list else 0
                direction = trades_list[0].get('Type', 'LONG').upper()

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
                # Use DB Cost (Margin) if available, else fallback to Entry Notional
                db_cost = sum(float(t.get('Cost', 0)) for t in trades_list)
                if db_cost > 0:
                    pos_cost = db_cost
                else:
                    pos_cost = entry_val_notional
                
                # Ensure Arithmetic Consistency: Value = Cost + PnL
                pos_value = pos_cost + pnl_eur
                
                unrealized_pnl += pnl_eur
                open_positions_value += pos_value
                
                pnl_pct = ((curr_price - avg_entry) / avg_entry * 100) if direction == 'LONG' else ((avg_entry - curr_price) / avg_entry * 100)
                
                if ac == 'Crypto': qty_fmt = f"{total_qty:.4f}"
                elif ac == 'Forex': qty_fmt = f"{total_qty:,.0f}"
                else: qty_fmt = f"{total_qty:.2f}"

                color = "#10B981" if pnl_pct > 0 else "#EF4444"

                html_sections += f"""
                <tr>
                    <td style="font-weight:bold;">{pair}</td>
                    <td style="text-align:center;"><span class="badge {direction}">{direction}</span></td>
                    <td style="text-align:right;">{qty_fmt}</td>
                    <td style="text-align:right;">€{pos_cost:,.2f}</td>
                    <td style="text-align:right;">€{pos_value:,.2f}</td>
                    <td style="text-align:right; font-weight:bold; color:{color};">{pnl_pct:+.2f}%</td>
                    <td style="text-align:right; font-weight:bold; color:{color};">{pnl_eur:+.2f}€</td>
                </tr>"""
            html_sections += "</tbody></table>"

        # Final Budget Calculation
        # Budget Current = Initial + Realized PnL + Unrealized PnL
        # Note: 'Total Buy' includes Open positions cost, 'Total Sell' is only closed.
        # Cash = Initial - Total Buy (Outflow) + Total Sell (Inflow)
        # Equity = Cash + Open Positions Value
        #        = Initial - Total Buy + Total Sell + Open Positions Value
        #        = Initial - (Closed Buy + Open Cost) + Total Sell + Open Value
        #        = Initial - Closed Buy + Total Sell - Open Cost + Open Value
        #        = Initial + Realized PnL + Unrealized PnL
        
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

        # --- TRIGGER & TIME WINDOWS ---
        now = get_paris_time()
        trigger_lookback = now - timedelta(minutes=30)
        
        paris_now = now
        daily_lookback = paris_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=1)  # Convert back to UTC for scan? Actually Dynamo uses Paris time now.
        # Wait, if Dynamo stores Paris time, lookback should be in Paris time.
        daily_lookback = paris_now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        trigger_lookback_iso = trigger_lookback.isoformat()
        daily_lookback_iso = daily_lookback.isoformat()
        
        # Check for RECENT EVENTS (All events including SKIPPED for analysis)
        recent_events = [
            t for t in all_trades 
            if t.get('Timestamp', '') > trigger_lookback_iso
        ]
        
        # If no recent events at all, SKIP sending email
        if not recent_events:
            logger.info("💤 No events in last 30m. Skipping report.")
            return {"status": "SKIPPED_NO_CHANGE"}
            
        logger.info(f"🚀 Triggered! {len(recent_events)} events found (including SKIPPED for analysis).")

        # --- SECTION: JOURNAL DU JOUR (Today's Activity) ---
        todays_events = [t for t in all_trades if t.get('Timestamp', '') > daily_lookback_iso]
        todays_events = sorted(todays_events, key=lambda x: x.get('Timestamp', ''), reverse=True)
        
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
                ts = ev.get('Timestamp', '')
                try:
                    # Parse timestamp
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    time_str = dt.strftime('%H:%M')
                except:
                    time_str = ts[-8:-3]
                
                pair = ev.get('Pair', 'N/A')
                status = ev.get('Status', 'UNKNOWN')
                tipo = ev.get('Type', 'INFO')
                
                # Determine Event Description & Color
                if status == 'OPEN':
                    event_desc = f"🟢 <b>OPEN {tipo}</b>"
                    row_bg = "#f0fdf4"
                elif 'CLOSED' in status or status == 'TP' or status == 'SL':
                    reason = ev.get('ExitReason', 'EXIT')
                    pnl = float(ev.get('PnL', 0)) if ev.get('PnL') else 0
                    event_desc = f"🔴 <b>CLOSED ({reason})</b>"
                    row_bg = "#fef2f2"
                elif status == 'SKIPPED':
                    reason = ev.get('ExitReason', '') or ev.get('AI_Reason', '')
                    event_desc = f"⚪ <i>Skipped: {reason}</i>"
                    row_bg = "#ffffff"
                else:
                    event_desc = f"{status}"
                    row_bg = "#ffffff"
                
                # PnL Display
                pnl_disp = ""
                if ev.get('PnL'):
                    val = float(ev.get('PnL'))
                    color = "#16a34a" if val > 0 else "#dc2626"
                    pnl_disp = f"<span style='color:{color};font-weight:bold;'>{val:+.2f}€</span>"

                html_sections += f"""
                <tr style="background-color:{row_bg};">
                    <td style="color:#64748b; font-size:11px;">{time_str}</td>
                    <td style="font-weight:bold;">{pair}</td>
                    <td style="font-size:11px; color:#334155;">{event_desc}</td>
                    <td style="text-align:right;">{pnl_disp}</td>
                </tr>"""
            html_sections += "</tbody></table>"

        # --- SECTION 2: RECENT AI TRADES (Last 10) ---
        # Exclude SKIPPED events (they are shown in ACTIVITÉ RÉCENTE)
        actual_trades = [t for t in all_trades if t.get('Status') != 'SKIPPED']
        recent_trades = sorted(actual_trades, key=lambda x: x.get('Timestamp', ''), reverse=True)[:10]
        
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
                # Format Date
                ts = t.get('Timestamp', '')
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    date_str = dt.strftime('%d/%m %H:%M')
                except:
                    date_str = ts[:16]

                pair = t.get('Pair')
                asset_class = t.get('AssetClass', 'Unknown')
                direction = t.get('Type', 'LONG').upper()
                
                status = t.get('Status', 'OPEN')
                exit_reason = t.get('ExitReason', '')
                
                # Get prices and quantities
                qty = float(t.get('Size', 0) or 0)
                entry_price = float(t.get('EntryPrice', 0) or 0)
                exit_price = float(t.get('ExitPrice', 0) or 0)
                
                # Format quantity based on asset class
                if asset_class == 'Crypto': qty_fmt = f"{qty:.4f}" if qty > 0 else "-"
                elif asset_class == 'Forex': qty_fmt = f"{qty:,.0f}" if qty > 0 else "-"
                else: qty_fmt = f"{qty:.2f}" if qty > 0 else "-"
                
                # Cost and Value
                cost = float(t.get('Cost', 0) or 0)
                
                if status == 'OPEN':
                    # For open positions, get current price and calculate on fly
                    if asset_class == 'Crypto':
                        try:
                            current_price = float(exchange.fetch_ticker(pair)['last'])
                        except:
                            current_price = entry_price
                    else:
                        current_price = fetch_yahoo_price_lite(pair)
                        if current_price == 0: current_price = fetch_yahoo_price_lite(pair + "=X")
                        if current_price == 0: current_price = entry_price
                    exit_price = current_price

                    # Correct Currency Conversion for OPEN trades
                    quote_currency = get_quote_currency(pair, asset_class)
                    eur_rate = get_eur_rate(quote_currency)
                    
                    curr_val_notional = (qty * current_price) / eur_rate
                    entry_val_notional = (qty * entry_price) / eur_rate
                    
                    # PnL Calc
                    if direction == 'SHORT':
                        pnl_eur = entry_val_notional - curr_val_notional
                    else:
                        pnl_eur = curr_val_notional - entry_val_notional
                    
                    # Fallback Cost
                    if cost == 0: cost = entry_val_notional
                    
                    # Consistent Value
                    value = cost + pnl_eur

                else:
                    # CLOSED/TP/SL: Trust DB values
                    value = float(t.get('Value', 0))
                    if cost == 0: cost = qty * entry_price # Fallback (might be raw, beware)
                    pnl_eur = float(t.get('PnL', 0)) if t.get('PnL') else (value - cost)
                pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 and exit_price > 0 else 0
                if direction == 'SHORT': pnl_pct = -pnl_pct
                
                # Format displays
                is_trade = status in ['OPEN', 'CLOSED', 'TP', 'SL']
                
                # PRIX (Unitaire au moment du signal/trade)
                price_fmt = f"${entry_price:,.2f}" if entry_price > 0 else "-"
                
                # Only show financial details for actual trades
                # PRIX ACHAT = COST (Total)
                entry_fmt = f"€{cost:,.2f}" if (is_trade and cost > 0) else "-"
                # PRIX ACTUEL/VENTE = VALUE (Total)
                exit_fmt = f"€{value:,.2f}" if (is_trade and value > 0) else "-"
                
                qty_fmt = qty_fmt if is_trade else "-"
                
                # Format status badge
                if status == 'OPEN':
                    status_badge = '<span style="background:#dbeafe;color:#1d4ed8;padding:2px 6px;border-radius:4px;font-size:10px;">OPEN</span>'
                elif exit_reason == 'STOP_LOSS':
                    status_badge = '<span style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:10px;">SL</span>'
                elif exit_reason == 'TAKE_PROFIT':
                    status_badge = '<span style="background:#dcfce7;color:#166534;padding:2px 6px;border-radius:4px;font-size:10px;">TP</span>'
                elif 'CLOSED' in status:
                     status_badge = '<span style="background:#e2e8f0;color:#475569;padding:2px 6px;border-radius:4px;font-size:10px;">CLOSED</span>'
                else:
                    # SKIPPED or INFO
                    status_badge = f'<span style="background:#f1f5f9;color:#64748b;padding:2px 6px;border-radius:4px;font-size:10px;">{status[:4]}</span>'
                
                # Format PnL
                pnl_color = '#16a34a' if pnl_eur >= 0 else '#dc2626'
                pnl_pct_str = f'<span style="color:{pnl_color};font-weight:bold;">{pnl_pct:+.2f}%</span>' if (is_trade and exit_price > 0) else '-'
                pnl_eur_str = f'<span style="color:{pnl_color};font-weight:bold;">{pnl_eur:+.2f}€</span>' if (is_trade and pnl_eur != 0) else '-'

                html_sections += f"""
                <tr>
                    <td style="color:#64748b; font-size:11px;">{date_str}</td>
                    <td style="font-weight:bold;">{pair}</td>
                    <td style="font-family:monospace; color:#0ea5e9;">{price_fmt}</td>
                    <td style="text-align:center;"><span class="badge {direction}">{direction}</span></td>
                    <td style="text-align:right;">{qty_fmt}</td>
                    <td style="text-align:right;">{entry_fmt}</td>
                    <td style="text-align:right;">{exit_fmt}</td>
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
        
        ses.send_email(
            Source=RECIPIENT,
            Destination={'ToAddresses': [RECIPIENT]},
            Message={'Subject': {'Data': f"🏛️ Empire Alert: {len(recent_events)} New Updates"}, 'Body': {'Html': {'Data': html_body}}}
        )
        logger.info("[SUCCESS] Email Sent.")
        return {"status": "SUCCESS"}
    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "ERROR"}
