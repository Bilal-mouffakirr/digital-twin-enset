import streamlit as st
import paho.mqtt.client as mqtt
import pandas as pd
import numpy as np
import time
import plotly.express as px

# --- 1. إعدادات الصفحة والستايل ---
st.set_page_config(page_title="Digital Twin PV - ENSET Cloud", layout="wide")

st.markdown("""
    <style>
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #3d4466; }
    </style>
    """, unsafe_allow_html=True)

st.title("☀️ Digital Twin PV : Monitoring Cloud (ENSET)")

# --- 2. إعدادات السحاب (Cloud Configuration) ---
# 🔒 البصمة الخاصة بك باش ما تتخلطش الداتا مع ناس خرين
PREFIX = "enset/bilal/pv_twin/"
BROKER = "broker.hivemq.com"

TOPICS = [
    PREFIX + "inv/p_active",  # index 0
    PREFIX + "pv/puissance",  # index 1
    PREFIX + "dc/p_boost",    # index 2
    PREFIX + "inv/tension",   # index 3
    PREFIX + "pv/tension",    # index 4
    PREFIX + "dc/tension"     # index 5
]

# --- 3. إدارة البيانات (State Management) ---
if 'latest_data' not in st.session_state:
    st.session_state.latest_data = {"P_inv": 0.0, "P_pv": 0.0, "P_dc": 0.0, "V_inv": 0.0, "V_pv": 0.0, "V_dc": 0.0}
if 'history' not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=["P_inv", "P_pv", "P_dc", "V_inv", "V_pv", "V_dc"])

# --- 4. إعداد الاتصال بـ MQTT Cloud ---
@st.cache_resource
def get_mqtt_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="Dashboard_ENSET_Cloud_Bilal")
    
    def on_message(client, userdata, message):
        try:
            val = float(message.payload.decode())
            topic = message.topic
            
            # الربط بين الـ Topic والعمود فـ الـ DataFrame
            mapping = {
                TOPICS[0]: "P_inv", TOPICS[1]: "P_pv", TOPICS[2]: "P_dc",
                TOPICS[3]: "V_inv", TOPICS[4]: "V_pv", TOPICS[5]: "V_dc"
            }
            
            if topic in mapping:
                st.session_state.latest_data[mapping[topic]] = val
        except:
            pass

    client.on_message = on_message
    client.connect(BROKER, 1883, 60)
    for t in TOPICS:
        client.subscribe(t)
    client.loop_start()
    return client

# تشغيل الـ Client
mqtt_client = get_mqtt_client()

# --- 5. حلقة العرض (Display Loop) ---
placeholder = st.empty()

while True:
    # تحديث الذاكرة (History)
    new_row = pd.DataFrame([st.session_state.latest_data])
    st.session_state.history = pd.concat([st.session_state.history, new_row], ignore_index=True)
    if len(st.session_state.history) > 50:
        st.session_state.history = st.session_state.history.iloc[1:]
    
    df = st.session_state.history

    with placeholder.container():
        latest = st.session_state.latest_data
        
        if latest["P_pv"] == 0 and latest["V_inv"] == 0:
            st.warning("⏳ En attente de données du Cloud (Vérifiez votre passerelle locale)...")
        else:
            # --- مبيانات رقمية (Metrics) ---
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("Puissance PV (DC)", f"{latest['P_pv']:.1f} W")
            with col2: st.metric("Tension Onduleur (AC)", f"{latest['V_inv']:.1f} V")
            with col3: 
                v_eff = np.sqrt(np.mean(df['V_inv']**2)) if not df['V_inv'].empty else 0
                st.metric("V_inv (RMS)", f"{v_eff:.2f} V")

            st.markdown("---")
            
            # --- مبيانات Plotly الاحترافية ---
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                fig_p = px.line(df, y=["P_pv", "P_inv"], 
                               title="📊 Comparaison des Puissances (Watts)",
                               template="plotly_dark",
                               color_discrete_map={"P_pv": "#00d1b2", "P_inv": "#ff3860"})
                fig_p.update_layout(height=400, margin=dict(l=0, r=0, t=40, b=0))
                st.plotly_chart(fig_p, use_container_width=True)

            with chart_col2:
                fig_v = px.line(df, y=["V_pv", "V_inv"], 
                               title="⚡ Évolution des Tensions (Volts)",
                               template="plotly_dark",
                               color_discrete_map={"V_pv": "#FFDD57", "V_inv": "#3273DC"})
                fig_v.update_layout(height=400, margin=dict(l=0, r=0, t=40, b=0))
                st.plotly_chart(fig_v, use_container_width=True)

    time.sleep(0.5)