import streamlit as st
import paho.mqtt.client as mqtt
import pandas as pd
import numpy as np
import time
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- 1. إعدادات الصفحة والستايل ---
st.set_page_config(page_title="Digital Twin PV - ENSET Cloud", layout="wide")

st.markdown("""
    <style>
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #3d4466; }
    .stSidebar { background-color: #0e1117; border-right: 1px solid #3d4466; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. إعدادات السحاب (Cloud Settings) ---
PREFIX = "enset/bilal/pv_twin/"
BROKER = "broker.hivemq.com"
TOPICS_LIST = ["inv/p_active", "pv/puissance", "dc/p_boost", "inv/tension", "pv/tension", "dc/tension"]
FULL_TOPICS = [PREFIX + t for t in TOPICS_LIST]

# --- 3. الصندوق العالمي المشترك (Persistent Memory) ---
@st.cache_resource
def get_shared_resources():
    return {
        "store": { "P_inv": 0.0, "P_pv": 0.0, "P_dc": 0.0, "V_inv": 0.0, "V_pv": 0.0, "V_dc": 0.0 },
        "history": [] # غانخليو التاريخ يكبر بلا ليميت كبيرة باش مايتمسحش
    }

shared = get_shared_resources()
data_store = shared["store"]
history_list = shared["history"]

# --- 4. إعداد MQTT (Thread-Safe) ---
def on_message(client, userdata, message):
    try:
        val = float(message.payload.decode())
        topic = message.topic
        mapping = {
            FULL_TOPICS[0]: "P_inv", FULL_TOPICS[1]: "P_pv", FULL_TOPICS[2]: "P_dc",
            FULL_TOPICS[3]: "V_inv", FULL_TOPICS[4]: "V_pv", FULL_TOPICS[5]: "V_dc"
        }
        if topic in mapping:
            data_store[mapping[topic]] = val
    except:
        pass

@st.cache_resource
def start_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"Bilal_Final_UI_{int(time.time())}")
    client.on_message = on_message
    client.connect(BROKER, 1883, 60)
    for t in FULL_TOPICS: client.subscribe(t)
    client.loop_start()
    return client

mqtt_client = start_mqtt()

# --- 5. الشريط الجانبي (Sidebar & Control Panel) ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/d/d1/Logo_ENSET_Mohammedia.png/220px-Logo_ENSET_Mohammedia.png", width=150)
    st.title("🎛️ Control Panel")
    st.info(f"📍 User: Bilal Mouffakir\n🎓 Project: Digital Twin PV")
    
    st.markdown("---")
    st.subheader("📥 Export Data")
    if len(history_list) > 0:
        df_export = pd.DataFrame(history_list)
        csv = df_export.to_csv(index=False).encode('utf-8')
        st.download_button(label="💾 Download Simulation CSV", data=csv, file_name=f"sim_pv_{datetime.now().strftime('%H%M%S')}.csv", mime='text/csv')
    
    if st.button("🗑️ Clear History"):
        history_list.clear()
        st.rerun()

# --- 6. حلقة العرض (Main Interface) ---
st.title("☀️ Monitoring Temps Réel - Digital Twin PV")
placeholder = st.empty()

try:
    while True:
        current = data_store.copy()
        history_list.append(current)
        
        # تحكم فـ حجم التاريخ (مثلاً 500 نقطة باش يبقى المنظر زوين ومايتقالش)
        if len(history_list) > 500:
            history_list.pop(0)
            
        df = pd.DataFrame(history_list).astype(float)

        with placeholder.container():
            # أرقام الحالة
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("Puissance PV", f"{current['P_pv']:.1f} W")
            with c2: st.metric("Tension Inv (AC)", f"{abs(current['V_inv']):.1f} V")
            with c3: 
                v_rms = np.sqrt(np.mean(df['V_inv']**2)) if not df.empty else 0
                st.metric("V_inv (RMS)", f"{v_rms:.2f} V")
            with c4:
                rendement = (current['P_inv']/current['P_pv']*100) if current['P_pv'] > 10 else 0
                st.metric("Rendement η", f"{rendement:.1f} %")

            # --- مبيانات التاريخ ---
            st.markdown("---")
            col_plots = st.columns(2)
            with col_plots[0]:
                st.plotly_chart(px.line(df, y=["P_pv", "P_inv"], title="📊 Puissances (W)", template="plotly_dark", color_discrete_sequence=["#00d1b2", "#ff3860"]), use_container_width=True)
            with col_plots[1]:
                st.plotly_chart(px.line(df, y=["V_pv", "V_inv"], title="⚡ Tensions (V)", template="plotly_dark", color_discrete_sequence=["#FFDD57", "#3273DC"]), use_container_width=True)

            # --- مبيان MPPT: P = f(V) ---
            st.markdown("---")
            st.subheader("🎯 Tracking du Point de Puissance Maximale (MPPT)")
            
            # رسم منحنى PV (History) + النقطة اللحظية (Red Dot)
            fig_mppt = go.Figure()
            # المنحنى التاريخي
            fig_mppt.add_trace(go.Scatter(x=df['V_pv'], y=df['P_pv'], mode='lines', name='Courbe P-V', line=dict(color='#00d1b2', width=1)))
            # النقطة الحمراء اللحظية
            fig_mppt.add_trace(go.Scatter(x=[current['V_pv']], y=[current['P_pv']], mode='markers', name='Point Actuel', marker=dict(color='red', size=15, symbol='circle')))
            
            fig_mppt.update_layout(title="Caractéristique P = f(V)", xaxis_title="Tension PV (V)", yaxis_title="Puissance PV (W)", template="plotly_dark", height=450)
            st.plotly_chart(fig_mppt, use_container_width=True)

        time.sleep(0.5)

except Exception as e:
    # هاد الجزء كيهنيك من داك الميساج الأحمر فاش كتوقع شي حاجة
    st.error("🔄 Reconnexion au flux de données...")
    time.sleep(2)
    st.rerun()
