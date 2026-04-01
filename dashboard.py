import streamlit as st
import paho.mqtt.client as mqtt
import pandas as pd
import numpy as np
import time
import plotly.express as px
import warnings

# إخفاء التحذيرات الجمالية
warnings.simplefilter(action='ignore', category=FutureWarning)

# --- 1. إعدادات الواجهة (UI Config) ---
st.set_page_config(page_title="Digital Twin PV - ENSET", layout="wide")

st.markdown("""
    <style>
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #3d4466; }
    .main { background-color: #0e1117; }
    </style>
    """, unsafe_allow_html=True)

st.title("☀️ Digital Twin ENSET: Cloud Monitoring Pro")

# --- 2. إعدادات السحاب (Cloud MQTT Config) ---
PREFIX = "enset/bilal/pv_twin/"
BROKER = "broker.hivemq.com"
TOPICS_LIST = ["inv/p_active", "pv/puissance", "dc/p_boost", "inv/tension", "pv/tension", "dc/tension"]
FULL_TOPICS = [PREFIX + t for t in TOPICS_LIST]

# --- 3. المخزن العالمي المشترك (Global Shared Storage) ---
# هاد الدالة كتدير لينا "صندوق" كيشوفوه قاع الأجزاء ديال الكود بلا بلوكاج
@st.cache_resource
def get_global_store():
    return {
        "store": { "P_inv": 0.0, "P_pv": 0.0, "P_dc": 0.0, "V_inv": 0.0, "V_pv": 0.0, "V_dc": 0.0 },
        "history": []
    }

global_data = get_global_store()
data_store = global_data["store"]
history_list = global_data["history"]

# --- 4. إعداد MQTT (Thread-Safe Callback) ---
def on_message(client, userdata, message):
    try:
        val = float(message.payload.decode())
        topic = message.topic
        
        # خريطة الربط بين العنوان والمتغير
        mapping = {
            FULL_TOPICS[0]: "P_inv", FULL_TOPICS[1]: "P_pv", FULL_TOPICS[2]: "P_dc",
            FULL_TOPICS[3]: "V_inv", FULL_TOPICS[4]: "V_pv", FULL_TOPICS[5]: "V_dc"
        }
        
        if topic in mapping:
            # تحديث الصندوق العالمي مباشرة
            data_store[mapping[topic]] = val
    except:
        pass

@st.cache_resource
def start_mqtt_service():
    # ID فريد باش ما يوقعش تصادم بين اللوكال والسحاب
    unique_id = f"Dashboard_Bilal_{int(time.time())}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=unique_id)
    client.on_message = on_message
    client.connect(BROKER, 1883, 60)
    for t in FULL_TOPICS:
        client.subscribe(t)
    client.loop_start()
    return client

# تشغيل خدمة الاستقبال فـ الخلفية
mqtt_service = start_mqtt_service()

# --- 5. حلقة العرض (Display Loop) ---
placeholder = st.empty()

while True:
    # 1. أخذ نسخة من الداتا الحالية (Snapshot)
    current_vals = data_store.copy()
    
    # 2. تحديث التاريخ للمبيانات
    history_list.append(current_vals)
    if len(history_list) > 50:
        history_list.pop(0)
    
    # تحويل البيانات لـ DataFrame للأرقام والمبيانات
    df = pd.DataFrame(history_list).astype(float)

    with placeholder.container():
        # حالة الانتظار (إلا كانت الداتا باقة أصفار)
        if current_vals["P_pv"] == 0 and current_vals["V_inv"] == 0:
            st.warning("⏳ En attente de données du Cloud (Vérifiez votre Passerelle)...")
            st.info(f"📡 Listening on Prefix: {PREFIX}")
        else:
            # --- مبيانات رقمية (Metrics) ---
            m1, m2, m3 = st.columns(3)
            with m1: st.metric("Puissance PV (DC)", f"{current_vals['P_pv']:.1f} W")
            with m2: st.metric("Tension Onduleur (AC)", f"{current_vals['V_inv']:.1f} V")
            with m3: 
                # حساب القيمة الفعالة (RMS) للتوتر
                # $V_{rms} = \sqrt{\frac{1}{N} \sum_{i=1}^{N} V_i^2}$
                v_rms = np.sqrt(np.mean(df['V_inv']**2)) if not df.empty else 0
                st.metric("V_inv (RMS)", f"{v_rms:.2f} V")

            st.markdown("---")
            
            # --- مبيانات Plotly الاحترافية ---
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                fig_p = px.line(df, y=["P_pv", "P_inv"], 
                               title="📊 Analyse des Puissances (Watts)",
                               template="plotly_dark",
                               color_discrete_map={"P_pv": "#00d1b2", "P_inv": "#ff3860"})
                fig_p.update_layout(height=400, margin=dict(l=0, r=0, t=40, b=0))
                st.plotly_chart(fig_p, use_container_width=True)

            with chart_col2:
                fig_v = px.line(df, y=["V_pv", "V_inv"], 
                               title="⚡ Stabilité des Tensions (Volts)",
                               template="plotly_dark",
                               color_discrete_map={"V_pv": "#FFDD57", "V_inv": "#3273DC"})
                fig_v.update_layout(height=400, margin=dict(l=0, r=0, t=40, b=0))
                st.plotly_chart(fig_v, use_container_width=True)

    time.sleep(0.5) # تحديث الشاشة كل نصف ثانية
