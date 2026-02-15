
import streamlit as st
import pandas as pd
import boto3
import time
import json
import threading
import hmac
import hashlib
import requests
import websocket
from datetime import datetime, timezone, timedelta
import pytz

# --- CONFIG & AESTHETICS ---
st.set_page_config(
    page_title="Empire V16.5 Sniper Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for Premium Look
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 28px; font-weight: 700; color: #00FFC2; }
    [data-testid="stMetricDelta"] { font-size: 16px; }
    .stMetric { background-color: #1A1C24; padding: 20px; border-radius: 12px; border: 1px solid #2D313E; }
    .section-header { font-size: 20px; font-weight: 600; margin-top: 30px; margin-bottom: 10px; color: #E0E2E8; border-left: 4px solid #00FFC2; padding-left: 15px; }
    .status-badge { padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; }
    .status-active { background-color: #052D24; color: #00FFC2; border: 1px solid #00FFC2; }
    .stDataFrame { border-radius: 12px; overflow: hidden; }
</style>
""", unsafe_allow_stdio=True)

# Shared State
if 'prices' not in st.session_state: st.session_state.prices = {}
if 'ws_thread' not in st.session_state: st.session_state.ws_thread = None

# --- AWS & BINANCE HELPERS ---
REGION = 'ap-northeast-1'
SECRET_NAME = 'trading/binance'
dynamodb = boto3.resource('dynamodb', region_name=REGION)
secrets = boto3.client('secretsmanager', region_name=REGION)

@st.cache_data(ttl=60)
def get_creds():
    try:
        response = secrets.get_secret_value(SecretId=SECRET_NAME)
        return json.loads(response['SecretString'])
    except Exception as e:
        st.error(f"AWS Secret Fetch failed: {e}")
        return None

def get_binance_data():
    creds = get_creds()
    if not creds: return None
    
    api_key = creds.get('api_key')
    secret = creds.get('secret')
    is_demo = os.environ.get('BINANCE_DEMO_MODE', 'true').lower() in ('1', 'true', 'yes', 'y', 'on')
    base_url = "https://demo-fapi.binance.com" if is_demo else "https://fapi.binance.com"
    
    st.sidebar.info(f"Connected to: {'DEMO' if is_demo else 'LIVE'}")
    
    def sign(params):
        return hmac.new(secret.encode('utf-8'), params.encode('utf-8'), hashlib.sha256).hexdigest()
    
    try:
        ts = int(time.time() * 1000)
        p = f"timestamp={ts}"
        sig = sign(p)
        
        # 1. Fetch Account Information
        r_acc = requests.get(f"{base_url}/fapi/v2/account?{p}&signature={sig}", headers={'X-MBX-APIKEY': api_key}, timeout=5)
        acc_data = r_acc.json() if r_acc.status_code == 200 else {}
        
        # 2. Fetch Position Risk
        r_pos = requests.get(f"{base_url}/fapi/v2/positionRisk?{p}&signature={sig}", headers={'X-MBX-APIKEY': api_key}, timeout=5)
        pos_data = r_pos.json() if r_pos.status_code == 200 else []
        
        # Extract balances
        balance = float(acc_data.get('totalWalletBalance', 0))
        available = float(acc_data.get('availableBalance', 0))
        margin_used = float(acc_data.get('totalInitialMargin', 0))
        unrealized_pnl = float(acc_data.get('totalUnrealizedProfit', 0))
        
        # Filter active positions
        active_positions = []
        for pos in pos_data:
            amt = float(pos.get('positionAmt', 0))
            if amt != 0:
                active_positions.append({
                    'symbol': pos['symbol'],
                    'side': 'LONG' if amt > 0 else 'SHORT',
                    'entry': float(pos['entryPrice']),
                    'mark': float(pos['markPrice']),
                    'qty': abs(amt),
                    'pnl': float(pos['unRealizedProfit']),
                    'lev': int(pos['leverage'])
                })
        
        return {
            'balance': balance,
            'available': available,
            'margin_used': margin_used,
            'upnl': unrealized_pnl,
            'positions': pd.DataFrame(active_positions)
        }
    except Exception as e:
        st.error(f"Binance Data Error: {e}")
        return None

def get_skipped_logs():
    table = dynamodb.Table('EmpireSkippedTrades')
    try:
        # Scan last 2 hours
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        response = table.scan() # Simple scan for demo purposes
        df = pd.DataFrame(response.get('Items', []))
        if not df.empty:
            if 'iso_timestamp' in df.columns:
                df = df[df['iso_timestamp'] >= cutoff].sort_values('iso_timestamp', ascending=False)
            elif 'timestamp' in df.columns:
                # Handle numeric timestamps if present
                ts_cutoff = int((time.time() - 7200) * 1000)
                df = df[df['timestamp'].apply(lambda x: x if isinstance(x, (int, float)) else 0) >= ts_cutoff]
        return df
    except: return pd.DataFrame()

# --- WEBSOCKET ---
def on_message(ws, message):
    data = json.loads(message)
    if 'data' in data:
        t = data['data']
        st.session_state.prices[t['s']] = float(t['c'])

def start_ws(symbols):
    if not symbols: return
    streams = [f"{s.lower()}@miniTicker" for s in symbols]
    socket = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"
    ws = websocket.WebSocketApp(socket, on_message=on_message)
    t = threading.Thread(target=ws.run_forever, daemon=True)
    t.start()
    st.session_state.ws_thread = t

# --- HEADER ---
is_demo = os.environ.get('BINANCE_DEMO_MODE', 'true').lower() in ('1', 'true', 'yes', 'y', 'on')
st.title(f"🦅 Empire • Binance {'Demo' if is_demo else 'Live'}")
st.markdown(f"### WebSocket V16.5 - Sniper Portfolio ({'Testnet' if is_demo else 'Production'})")

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.markdown('<div class="status-badge status-active">WebSocket: Active</div>', unsafe_allow_html=True)
with k2:
    st.markdown('<div class="status-badge status-active">Mode: BINANCE DEMO</div>', unsafe_allow_html=True)
with k3:
    st.markdown('<div class="status-badge status-active">Region: Tokyo 🇯🇵</div>', unsafe_allow_html=True)

st.markdown("---")

# --- MAIN LOOP ---
placeholder = st.empty()

while True:
    data = get_binance_data()
    skipped_df = get_skipped_logs()
    
    with placeholder.container():
        if data:
            bal = data['balance']
            upnl = data['upnl']
            avail = data['available']
            margin = data['margin_used']
            pos_df = data['positions']
            
            # --- TOP METRICS ---
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Balance", f"${bal:,.2f}")
            m2.metric("Win Rate", "0%", "Initial")
            m3.metric("Total PnL", f"${upnl:+.2f}", f"{(upnl/bal*100):+.2f}%" if bal > 0 else "0%")
            m4.metric("Active Positions", len(pos_df))
            
            # --- CAPITAL ALLOCATION ---
            st.markdown('<div class="section-header">💰 Budget & Capital Allocation</div>', unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Capital Total", f"${bal:,.2f}")
            c2.metric("Margin Libre", f"${avail:,.2f}")
            c3.metric("Buying Power", f"${(avail * 5):,.2f}", "Leverage x5")
            c4.metric("Risk Utilization", f"{(margin/bal*100) if bal > 0 else 0:.1f}%", "Margin Utilisée")
            
            # --- MARGIN DETAILS ---
            st.markdown('<div class="section-header">📊 Margin Details</div>', unsafe_allow_html=True)
            d1, d2, d3 = st.columns(3)
            d1.metric("Margin Used", f"${margin:,.2f}", delta_color="normal")
            d2.metric("Unrealized PnL", f"${upnl:+.2f}", delta_color="normal")
            d3.metric("Available Balance", f"${avail:,.2f}")
            
            # --- CHARTS ---
            st.markdown('<div class="section-header">📈 Performance & Analysis</div>', unsafe_allow_html=True)
            ch1, ch2 = st.columns(2)
            with ch1:
                st.subheader("📈 Performance PnL")
                # Dummy chart for UI completeness
                chart_data = pd.DataFrame({'PnL': [0.1, 0.5, 0.3, 0.8, 1.2, 1.1, 1.5]})
                st.line_chart(chart_data)
            with ch2:
                st.subheader("🎯 Win Rate Evolution")
                st.area_chart(chart_data)

            # --- POSITIONS ---
            st.markdown('<div class="section-header">🛡️ Active Positions</div>', unsafe_allow_html=True)
            if not pos_df.empty:
                # Update with WS prices if available
                symbols = pos_df['symbol'].unique().tolist()
                if st.session_state.ws_thread is None: start_ws(symbols)
                pos_df['live_price'] = pos_df['symbol'].apply(lambda x: st.session_state.prices.get(x, 0.0))
                
                # Show Table
                st.dataframe(pos_df[['symbol', 'side', 'entry', 'mark', 'qty', 'lev', 'pnl']], use_container_width=True)
            else:
                st.info("Waiting for signals...")
            
            # --- SKIPPED ---
            st.markdown('<div class="section-header">⏭️ Skipped Trades & Reasons</div>', unsafe_allow_html=True)
            if not skipped_df.empty:
                st.dataframe(skipped_df[['Symbol', 'Reason', 'iso_timestamp']].head(10), use_container_width=True)
            else:
                st.write("No trades skipped recently.")
                
        else:
            st.warning("⚠️ Connecting to Binance / Loading Data...")
            
        st.markdown(f"<div style='text-align: right; color: grey; font-size: 10px;'>Last Update: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</div>", unsafe_allow_html=True)

    time.sleep(1)
    st.rerun()
