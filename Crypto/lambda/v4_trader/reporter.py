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

# Tables à scanner (Si tu as plusieurs tables, ajoute-les ici)
TABLES_TO_SCAN = ["EmpireCryptoV4", "EmpireForexHistory", "EmpireIndicesHistory", "EmpireCommoditiesHistory"]
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
                    <th style='text-align:right'>ENTRÉE</th>
                    <th style='text-align:right'>ACTUEL</th>
                    <th style='text-align:right'>PnL</th>
                </tr></thead><tbody>"""
            
            for pair, trades_list in pairs.items():
                if ac == 'Crypto':
                    curr_price = float(exchange.fetch_ticker(pair)['last'])
                else:
                    curr_price = fetch_yahoo_price_lite(pair)
                    if curr_price == 0 and ac == 'Forex': curr_price = fetch_yahoo_price_lite(pair + "=X")

                total_qty = sum(float(t.get('Size', 0)) for t in trades_list)
                avg_entry = sum(float(t['EntryPrice']) for t in trades_list) / len(trades_list)
                
                # Current Value of this position
                pos_value = total_qty * curr_price
                pos_cost = sum(float(t.get('Cost', 0)) for t in trades_list)
                if pos_cost == 0: pos_cost = total_qty * avg_entry
                
                unrealized_pnl += (pos_value - pos_cost)
                open_positions_value += pos_value
                
                direction = trades_list[0].get('Type', 'LONG').upper()
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
                    <td style="text-align:right;">${avg_entry:,.2f}</td>
                    <td style="text-align:right;">${curr_price:,.2f}</td>
                    <td style="text-align:right; font-weight:bold; color:{color};">{pnl_pct:+.2f}%</td>
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

        # --- SECTION: RECENT ACTIVITY (Last 30 min, or since 22h for 10h report) ---
        now = datetime.utcnow()
        current_hour = now.hour
        
        # Special case: 10h (9h UTC) = Morning report = Scan depuis 22h veille (21h UTC)
        if current_hour == 9:  # 10h Paris = 9h UTC
            lookback = now.replace(hour=21, minute=0, second=0, microsecond=0) - timedelta(days=1) if now.hour >= 21 else now.replace(hour=21, minute=0, second=0, microsecond=0) - timedelta(days=1)
            lookback = datetime(now.year, now.month, now.day, 21, 0, 0) - timedelta(days=1)
            lookback_label = "depuis 22h hier"
        else:
            lookback = now - timedelta(minutes=30)
            lookback_label = "30 dernières minutes"
        
        lookback_iso = lookback.isoformat()
        
        # Filter recent events (SKIPPED = NO_SIGNAL + AI_VETO)
        recent_events = [t for t in all_trades if t.get('Status') == 'SKIPPED' and t.get('Timestamp', '') > lookback_iso]
        recent_events = sorted(recent_events, key=lambda x: x.get('Timestamp', ''), reverse=True)
        
        if recent_events:
            html_sections += f"<div class='section-title' style='border-left-color: #f59e0b;'>ACTIVITÉ RÉCENTE ({lookback_label})</div>"
            html_sections += """<table class="empire-table">
                <thead><tr>
                    <th style='text-align:left'>HEURE</th>
                    <th style='text-align:left'>ACTIF</th>
                    <th style='text-align:left'>RAISON</th>
                </tr></thead><tbody>"""
            
            for ev in recent_events[:20]:  # Limit to 20 events
                ts = ev.get('Timestamp', '')
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    time_str = dt.strftime('%H:%M')
                except:
                    time_str = ts[-8:-3] if len(ts) > 8 else ts
                
                pair = ev.get('Pair', 'N/A')
                reason = ev.get('ExitReason', 'Unknown')
                
                html_sections += f"""
                <tr>
                    <td style="color:#64748b; font-size:11px;">{time_str}</td>
                    <td style="font-weight:bold;">{pair}</td>
                    <td style="font-size:11px; color:#475569;">{reason[:80]}</td>
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
                    <th style='text-align:center'>TYPE</th>
                    <th style='text-align:center'>STATUS</th>
                    <th style='text-align:left'>AI REASON</th>
                    <th style='text-align:right'>PnL</th>
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
                direction = t.get('Type', 'LONG').upper()
                
                status = t.get('Status', 'OPEN')
                exit_reason = t.get('ExitReason', '')
                pnl = float(t.get('PnL', 0)) if t.get('PnL') else None
                
                # Get AI Reason
                ai_reason = t.get('AI_Reason', t.get('ai_reason', ''))
                ai_reason_short = ai_reason[:60] + "..." if len(ai_reason) > 60 else ai_reason
                
                # Format status badge
                if status == 'OPEN':
                    status_badge = '<span style="background:#dbeafe;color:#1d4ed8;padding:2px 6px;border-radius:4px;font-size:10px;">OPEN</span>'
                elif exit_reason == 'STOP_LOSS':
                    status_badge = '<span style="background:#fee2e2;color:#991b1b;padding:2px 6px;border-radius:4px;font-size:10px;">SL</span>'
                elif exit_reason == 'TAKE_PROFIT':
                    status_badge = '<span style="background:#dcfce7;color:#166534;padding:2px 6px;border-radius:4px;font-size:10px;">TP</span>'
                else:
                    status_badge = '<span style="background:#e2e8f0;color:#475569;padding:2px 6px;border-radius:4px;font-size:10px;">CLOSED</span>'
                
                # Format PnL
                if pnl is not None:
                    pnl_color = '#16a34a' if pnl >= 0 else '#dc2626'
                    pnl_str = f'<span style="color:{pnl_color};font-weight:bold;">{pnl:+.2f}€</span>'
                else:
                    pnl_str = '-'

                html_sections += f"""
                <tr>
                    <td style="color:#64748b; font-size:11px;">{date_str}</td>
                    <td style="font-weight:bold;">{pair}</td>
                    <td style="text-align:center;"><span class="badge {direction}">{direction}</span></td>
                    <td style="text-align:center;">{status_badge}</td>
                    <td style="font-size:11px; color:#475569;">{ai_reason_short}</td>
                    <td style="text-align:right;">{pnl_str}</td>
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
            .empire-table td {{ padding: 12px; border-bottom: 1px solid #f1f5f9; font-size: 13px; }}
            .badge {{ padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }}
            .badge.LONG {{ background: #dcfce7; color: #166534; }}
            .badge.SHORT {{ background: #fee2e2; color: #991b1b; }}
        </style></head>
        <body>
            <div class="container">
                <div class="header"><h1>🏛️ EMPIRE GLOBAL STATUS</h1></div>
                <div style="padding: 10px;">{html_sections}</div>
                <div style="padding: 20px; font-size: 10px; color: #94a3b8; text-align: center;">Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
            </div>
        </body></html>
        """
        
        ses.send_email(
            Source=RECIPIENT,
            Destination={'ToAddresses': [RECIPIENT]},
            Message={'Subject': {'Data': f"🏛️ Empire Global: {len(open_trades)} Open Positions"}, 'Body': {'Html': {'Data': html_body}}}
        )
        return {"status": "SUCCESS"}
    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "ERROR"}
