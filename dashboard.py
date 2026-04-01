import streamlit as st
import paho.mqtt.client as mqtt
import pandas as pd
import numpy as np
import time
import plotly.graph_objects as go
from io import StringIO
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)
time_sleep = 0.001

# ============================================================
# 1. إعدادات الواجهة
# ============================================================
st.set_page_config(page_title="Digital Twin PV - ENSET", layout="wide", page_icon="☀️")

st.markdown("""
    <style>
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #3d4466; }
    .main { background-color: #0e1117; }
    [data-testid="stSidebar"] { background-color: #1a1d2e; border-right: 1px solid #3d4466; }
    </style>
    """, unsafe_allow_html=True)

# ============================================================
# 2. إعدادات MQTT
# ============================================================
PREFIX = "enset/bilal/pv_twin/"
BROKER = "broker.hivemq.com"

TOPICS_MAP = {
    PREFIX + "inv/p_active":   "P_inv",
    PREFIX + "pv/puissance":   "P_pv",
    PREFIX + "dc/p_boost":     "P_dc",
    PREFIX + "inv/tension":    "V_inv",
    PREFIX + "pv/tension":     "V_pv",
    PREFIX + "dc/tension":     "V_dc",
    PREFIX + "inv/s_apparent": "S",
    PREFIX + "inv/q_reactive": "Q",
    PREFIX + "inv/thd_v":      "THD_V",
    PREFIX + "inv/thd_i":      "THD_I",
}
FULL_TOPICS = list(TOPICS_MAP.keys())

# ============================================================
# 3. المخزن العالمي
# ============================================================
@st.cache_resource
def get_global_store():
    return {
        "store": {k: 0.0 for k in TOPICS_MAP.values()},
        "history": [],
        "connected": False,
        "last_error": ""
    }

global_data  = get_global_store()
data_store   = global_data["store"]
history_list = global_data["history"]

# ============================================================
# 4. MQTT callbacks
# ============================================================
def on_connect(client, userdata, flags, reason_code, properties=None):
    rc = reason_code.value if hasattr(reason_code, 'value') else reason_code
    global_data["connected"] = (rc == 0)

def on_message(client, userdata, message):
    try:
        val = float(message.payload.decode())
        key = TOPICS_MAP.get(message.topic)
        if key:
            data_store[key] = val
    except Exception:
        pass

@st.cache_resource
def start_mqtt_service():
    try:
        uid = f"Dashboard_Bilal_{int(time.time())}"
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=uid)
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(BROKER, 1883, 60)
        for t in FULL_TOPICS:
            client.subscribe(t)
        client.loop_start()
        return client
    except Exception as e:
        global_data["last_error"] = str(e)
        return None

mqtt_service = start_mqtt_service()

# ============================================================
# 5. Sidebar (مع اللوغو والتحميل)
# ============================================================
with st.sidebar:
    # --- إضافة لوغو ENSET ---
    # استعملت رابط مباشر للتصويرة من ويكيبيديا (موثوق)
    logo_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d1/Logo_ENSET_Mohammedia.png/220px-Logo_ENSET_Mohammedia.png"
    st.image(logo_url, width=180)
    
    st.markdown("""
    <div style="text-align:center; padding-bottom:10px;">
        <h2 style="color:#00d1b2; font-size:1.2rem; margin:0;">Génie Électrique</h2>
        <p style="color:#aaa; font-size:0.8rem;">Digital Twin — Bilal M.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📡 Status Connexion")
    if global_data.get("connected", False):
        st.success("✅ Online")
    else:
        st.error("🔴 Offline")

    st.markdown("---")
    st.subheader("📂 Export Data")
    if len(history_list) > 0:
        df_export = pd.DataFrame(history_list).astype(float)
        csv_buf = StringIO()
        df_export.to_csv(csv_buf, index=False, sep=";", decimal=",")
        st.download_button(
            label="⬇️ Download CSV (Excel)",
            data=csv_buf.getvalue().encode("utf-8-sig"),
            file_name="pv_simulation_data.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    if st.button("🗑️ Reset Curves", use_container_width=True):
        history_list.clear()
        st.rerun()

# ============================================================
# 6. Boucle principale (التعديل لضمان بقاء المنحنيات)
# ============================================================
st.title("☀️ Digital Twin ENSET: Cloud Monitoring Pro")
placeholder = st.empty()

while True:
    try:
        current_vals = data_store.copy()
        history_list.append(current_vals.copy())
        
        # زدنا هاد العدد لـ 5000 باش المنحنى ما يتمسحش حتّى تسالي الـ Simulation
        if len(history_list) > 5000:
            history_list.pop(0)

        df = pd.DataFrame(history_list).astype(float)

        with placeholder.container():
            if current_vals["P_pv"] == 0 and current_vals["V_inv"] == 0:
                st.warning("⏳ En attente de données du Cloud...")
                time.sleep(1)
                continue

            # --- Row 1: Metrics ---
            m1, m2, m3, m4 = st.columns(4)
            eff = (current_vals['P_inv'] / current_vals['P_pv'] * 100) if current_vals['P_pv'] > 1 else 0
            with m1: st.metric("🌞 P_PV", f"{current_vals['P_pv']:.1f} W")
            with m2: st.metric("🔌 P_Onduleur", f"{current_vals['P_inv']:.1f} W")
            with m3: st.metric("🎯 Rendement", f"{eff:.1f} %")
            with m4: 
                v_rms = float(np.sqrt(np.mean(df['V_inv']**2))) if len(df) > 0 else 0.0
                st.metric("📈 V_RMS", f"{v_rms:.1f} V")

            # --- Row 2: Charts ---
            st.markdown("---")
            st.subheader("📊 Évolution Temporelle (Simulink Live)")
            
            c1, c2 = st.columns(2)
            with c1:
                fig_p = go.Figure()
                fig_p.add_trace(go.Scatter(y=df['P_pv'], name="P_PV", line=dict(color='#00d1b2')))
                fig_p.add_trace(go.Scatter(y=df['P_inv'], name="P_Inv", line=dict(color='#ff3860')))
                fig_p.update_layout(template="plotly_dark", height=350, title="Puissances (W)")
                st.plotly_chart(fig_p, use_container_width=True)
            
            with c2:
                fig_v = go.Figure()
                fig_v.add_trace(go.Scatter(y=df['V_pv'], name="V_PV", line=dict(color='#FFDD57')))
                fig_v.add_trace(go.Scatter(y=df['V_inv'], name="V_Inv", line=dict(color='#3273DC')))
                fig_v.update_layout(template="plotly_dark", height=350, title="Tensions (V)")
                st.plotly_chart(fig_v, use_container_width=True)

    except Exception:
        pass
    
    time.sleep(0.1)
