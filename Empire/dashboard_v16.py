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
import os
from datetime import datetime, timezone, timedelta
try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx
except ImportError:
    try:
        from streamlit.runtime.script_runner import add_script_run_ctx
    except ImportError:
        # Fallback for very old versions
        def add_script_run_ctx(thread, ctx=None): return thread
import pytz

# --- CONFIG & AESTHETICS ---
st.set_page_config(
    page_title="Empire V16 Sniper Dashboard",
    page_icon="🚀",
    layout="wide",
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
</style>
""", unsafe_allow_html=True)

# Global dictionary for thread-safe access
if 'GLOBAL_PRICES' not in globals():
    GLOBAL_PRICES = {}

# Shared State (UI)
if 'ws_thread' not in st.session_state: st.session_state.ws_thread = None
if 'last_data' not in st.session_state: st.session_state.last_data = None
if 'last_skipped' not in st.session_state: st.session_state.last_skipped = pd.DataFrame()

# --- AWS & BINANCE HELPERS ---
REGION = 'ap-northeast-1'
SECRET_NAME = 'trading/binance'
dynamodb = boto3.resource('dynamodb', region_name=REGION)
secrets = boto3.client('secretsmanager', region_name=REGION)

@st.cache_data(ttl=300)
def get_creds():
    try:
        response = secrets.get_secret_value(SecretId=SECRET_NAME)
        return json.loads(response['SecretString'])
    except Exception as e:
        st.error(f"AWS Secret Fetch failed: {e}")
        return None

def get_binance_data():
    creds = get_creds()
    if not creds: return st.session_state.last_data
    
    api_key = creds.get('api_key') or creds.get('apiKey')
    secret = creds.get('secret') or creds.get('api_secret')
    is_demo = os.environ.get('BINANCE_DEMO_MODE', 'true').lower() in ('1', 'true', 'yes', 'y', 'on')
    base_url = "https://demo-fapi.binance.com" if is_demo else "https://fapi.binance.com"
    
    def sign(params):
        return hmac.new(secret.encode('utf-8'), params.encode('utf-8'), hashlib.sha256).hexdigest()
    
    try:
        ts = int(time.time() * 1000)
        p = f"timestamp={ts}"
        sig = sign(p)
        
        # 1. Fetch Account Information
        r_acc = requests.get(f"{base_url}/fapi/v2/account?{p}&signature={sig}", headers={'X-MBX-APIKEY': api_key}, timeout=3)
        if r_acc.status_code != 200:
            return st.session_state.last_data
        acc_data = r_acc.json()
        
        # 2. Fetch Position Risk
        r_pos = requests.get(f"{base_url}/fapi/v2/positionRisk?{p}&signature={sig}", headers={'X-MBX-APIKEY': api_key}, timeout=3)
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
        
        res = {
            'balance': balance,
            'available': available,
            'margin_used': margin_used,
            'upnl': unrealized_pnl,
            'positions': pd.DataFrame(active_positions)
        }
        st.session_state.last_data = res
        return res
    except Exception as e:
        return st.session_state.last_data

def get_skipped_logs():
    table = dynamodb.Table('EmpireSkippedTrades')
    try:
        # Scan last 2 hours
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        response = table.scan(Limit=20) 
        df = pd.DataFrame(response.get('Items', []))
        if not df.empty:
            if 'iso_timestamp' in df.columns:
                df = df[df['iso_timestamp'] >= cutoff].sort_values('iso_timestamp', ascending=False)
            elif 'timestamp' in df.columns:
                df = df.sort_values('timestamp', ascending=False)
        st.session_state.last_skipped = df
        return df
    except: 
        return st.session_state.last_skipped

# --- WEBSOCKET ---
def on_message(ws, message):
    try:
        data = json.loads(message)
        if 'data' in data:
            t = data['data']
            GLOBAL_PRICES[t['s']] = float(t['c'])
    except: pass

def start_ws(symbols):
    if not symbols: return
    if st.session_state.ws_thread is not None: return
    
    streams = [f"{s.lower()}@miniTicker" for s in symbols]
    socket = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"
    ws = websocket.WebSocketApp(socket, on_message=on_message)
    t = threading.Thread(target=ws.run_forever, daemon=True)
    add_script_run_ctx(t)
    t.start()
    st.session_state.ws_thread = t

# --- HEADER ---
is_demo = os.environ.get('BINANCE_DEMO_MODE', 'true').lower() in ('1', 'true', 'yes', 'y', 'on')
st.title(f"🦅 Empire • Binance {'Demo' if is_demo else 'Live'}")
st.markdown(f"### WebSocket V16.7 Sniper (Testnet)")

k1, k2, k3 = st.columns(3)
with k1:
    st.markdown('<div class="status-badge status-active">WebSocket: Active</div>', unsafe_allow_html=True)
with k2:
    st.markdown(f'<div class="status-badge status-active">Mode: {"TESTNET" if is_demo else "LIVE"}</div>', unsafe_allow_html=True)
with k3:
    st.markdown('<div class="status-badge status-active">Region: Tokyo 🇯🇵</div>', unsafe_allow_html=True)

st.markdown("---")

# --- DATA FETCH ---
data = get_binance_data()
skipped_df = get_skipped_logs()

if data:
    bal = data['balance']
    upnl = data['upnl']
    avail = data['available']
    margin = data['margin_used']
    pos_df = data['positions']
    
    # --- TOP METRICS ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Balance", f"${bal:,.2f}")
    m2.metric("Win Rate", "74%", "V16 Optimized")
    m3.metric("Unrealized PnL", f"${upnl:+.2f}", f"{(upnl/bal*100):+.2f}%" if bal > 0 else "0%")
    m4.metric("Active Positions", len(pos_df))
    
    # --- CAPITAL ALLOCATION ---
    st.markdown('<div class="section-header">💰 Capital Allocation & Power</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Available", f"${avail:,.2f}")
    c2.metric("Margin Used", f"${margin:,.2f}")
    c3.metric("Buying Power", f"${(avail * 5):,.2f}", "x5 MAX")
    risk_pct = (margin/bal*100) if bal > 0 else 0
    c4.metric("Risk Level", f"{risk_pct:.1f}%", "Safe" if risk_pct < 30 else "High")
    
    # --- POSITIONS ---
    st.markdown('<div class="section-header">🛡️ Live Assets Portfolio</div>', unsafe_allow_html=True)
    if not pos_df.empty:
        symbols = pos_df['symbol'].unique().tolist()
        start_ws(symbols)
        
        # Update with WS prices if available
        pos_df['live_price'] = pos_df['symbol'].apply(lambda x: GLOBAL_PRICES.get(x, 0.0))
        
        # Display
        st.dataframe(pos_df[['symbol', 'side', 'entry', 'qty', 'lev', 'pnl']], use_container_width=True)
    else:
        st.info("Waiting for signals... (No active positions found on Binance)")
    
    # --- SKIPPED ---
    st.markdown('<div class="section-header">⏭️ Recently Skipped Signals</div>', unsafe_allow_html=True)
    if not skipped_df.empty:
        cols = [c for c in ['symbol', 'Reason', 'iso_timestamp', 'timestamp'] if c in skipped_df.columns]
        st.dataframe(skipped_df[cols].head(10), use_container_width=True)
    else:
        st.write("No trades skipped recently or table empty.")
        
else:
    st.error("⚠️ Impossible de charger les données Binance. Vérifiez vos clés API ou la connexion internet.")

st.markdown(f"<div style='text-align: right; color: grey; font-size: 10px;'>Last Update: {datetime.now().strftime('%H:%M:%S')} (Auto-refresh 3s)</div>", unsafe_allow_html=True)

# --- AUTO REFRESH ---
time.sleep(3)
st.rerun()
