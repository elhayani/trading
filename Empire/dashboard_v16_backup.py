
import streamlit as st
import pandas as pd
import boto3
import time
import json
import threading
import websocket
from datetime import datetime, timedelta
import pytz

# Config
st.set_page_config(
    page_title="Empire V16 Sniper (Live)",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Shared State for WebSocket Data
if 'prices' not in st.session_state:
    st.session_state.prices = {}
if 'ws_thread' not in st.session_state:
    st.session_state.ws_thread = None

# --- WEBSOCKET CLIENT (Background) ---
def on_message(ws, message):
    data = json.loads(message)
    # data format: {'s': 'BTCUSDT', 'c': '65000.50'} for mini-ticker
    if 'data' in data:
        ticker = data['data']
        symbol = ticker['s']
        price = float(ticker['c'])
        st.session_state.prices[symbol] = price

def on_error(ws, error):
    pass # Silent fail to keep UI clean

def start_websocket(symbols):
    """Start Binance WebSocket for given symbols"""
    if not symbols: return
    
    streams = [f"{s.lower().replace('/','').replace(':usdt','')}@miniTicker" for s in symbols]
    socket = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"
    
    ws = websocket.WebSocketApp(socket, on_message=on_message, on_error=on_error)
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()
    st.session_state.ws_thread = wst

# --- AWS & DATA ---
REGION = 'ap-northeast-1'
dynamodb = boto3.resource('dynamodb', region_name=REGION)
logs = boto3.client('logs', region_name=REGION)

def get_open_positions():
    table = dynamodb.Table('V4TradingState')
    try:
        response = table.scan(FilterExpression=boto3.dynamodb.conditions.Attr('status').eq('OPEN'))
        items = response.get('Items', [])
        return pd.DataFrame(items)
    except: return pd.DataFrame()

def get_skipped_trades_last_hour():
    """Récupère les trades SKIPPED de la dernière heure"""
    table = dynamodb.Table('EmpireSkippedTrades')
    try:
        # Calculer timestamp d'il y a 1 heure en UTC (DynamoDB stocke en UTC)
        utc_now = datetime.now(pytz.UTC)
        one_hour_ago = (utc_now - timedelta(hours=1)).isoformat().replace('+00:00', '+00:00')
        
        response = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('timestamp').gte(one_hour_ago)
        )
        items = response.get('Items', [])
        return pd.DataFrame(items)
    except: 
        return pd.DataFrame()

# --- LAYOUT ---
st.title("🦅 EMPIRE V16 • SNIPER LIVE (TOKYO 🇯🇵)")

# Auto-refresh placeholder
placeholder = st.empty()

while True:
    with placeholder.container():
        # Fetch Data
        positions = get_open_positions()
        skipped = get_skipped_trades_last_hour()
        
        # Start WebSocket if needed
        if not positions.empty:
            symbols = positions['symbol'].unique().tolist()
            # Basic logic: restart WS if symbols change (not implemented fully for brevity, just keeping it running)
            if st.session_state.ws_thread is None:
                start_websocket(symbols)
        
        # Calculate Live KPIs
        total_pnl = 0.0
        active_count = len(positions)
        
        if not positions.empty:
            current_prices = st.session_state.prices
            
            # Recalculate Live PnL
            positions['current_price'] = positions['symbol'].apply(
                lambda s: current_prices.get(s.replace('/','').replace(':USDT','').replace(':',''), 0.0)
            )
            
            # Calculate PnL for rows with price
            for idx, row in positions.iterrows():
                cp = row['current_price']
                if cp > 0:
                    entry = float(row['entry_price'])
                    qty = float(row['quantity'])
                    direction = row['direction']
                    
                    if direction == 'LONG':
                        pnl = (cp - entry) * qty
                    else:
                        pnl = (entry - cp) * qty
                    
                    positions.at[idx, 'pnl_live'] = pnl
                    total_pnl += pnl
                else:
                    positions.at[idx, 'pnl_live'] = 0.0

        # Display Metrics
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Active Trades", active_count)
        k2.metric("Live PnL (USDT)", f"${total_pnl:+.2f}", delta_color="normal")
        k3.metric("Skipped (1h)", len(skipped), delta_color="inverse")
        k4.metric("Scanner", "🟢 ACTIVE" if active_count == 0 else "🟡 BUSY")
        
        # Display Table
        if not positions.empty:
            view = positions[['symbol', 'direction', 'entry_price', 'current_price', 'pnl_live']].copy()
            st.dataframe(view, use_container_width=True, hide_index=True)
        else:
            st.info("Scanner Active... Waiting for targets.")

        # Skipped Trades Section
        if not skipped.empty:
            with st.expander(f"⏭️ Skipped Trades (Last Hour: {len(skipped)})", expanded=True):
                # Formater les données pour l'affichage
                skipped_view = skipped.copy()
                if 'timestamp' in skipped_view.columns:
                    # Les timestamps sont en format ISO string
                    skipped_view['time'] = pd.to_datetime(skipped_view['timestamp']).dt.strftime('%H:%M:%S')
                
                # Colonnes à afficher
                display_cols = ['time', 'Symbol', 'Reason']
                available_cols = [col for col in display_cols if col in skipped_view.columns]
                
                if available_cols:
                    st.dataframe(
                        skipped_view[available_cols].sort_values('time', ascending=False), 
                        use_container_width=True, 
                        hide_index=True
                    )
                else:
                    st.write(skipped_view)  # Fallback: afficher tout
        else:
            with st.expander("⏭️ Skipped Trades (Last Hour: 0)", expanded=True):
                st.info("No skipped trades in the last hour")

        # Logs Section
        with st.expander("☁️ CloudWatch Stream", expanded=True):
             # Fetch logs logic here (simplified)
             pass 

    time.sleep(1) # Live update frequency
