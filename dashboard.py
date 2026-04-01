import streamlit as st
import paho.mqtt.client as mqtt
import pandas as pd
import numpy as np
import time
import plotly.express as px

# --- 1. إعدادات السحاب ---
PREFIX = "enset/bilal/pv_twin/"
BROKER = "broker.hivemq.com"
TOPICS_LIST = [
    "inv/p_active", "pv/puissance", "dc/p_boost",
    "inv/tension", "pv/tension", "dc/tension"
]
FULL_TOPICS = [PREFIX + t for t in TOPICS_LIST]

# --- 2. الصندوق العالمي (Thread-Safe Storage) ---
# هاد الصندوق هو لي غايوصل الداتا بين MQTT والواجهة
if 'data_store' not in st.cache_resource():
    st.cache_resource.data_store = {
        "P_inv": 0.0, "P_pv": 0.0, "P_dc": 0.0, 
        "V_inv": 0.0, "V_pv": 0.0, "V_dc": 0.0
    }
if 'history_list' not in st.cache_resource():
    st.cache_resource.history_list = []

data_store = st.cache_resource.data_store

# --- 3. إعداد MQTT ---
def on_message(client, userdata, message):
    try:
        val = float(message.payload.decode())
        topic = message.topic
        # تحويل العنوان لسمية المتغير
        # enset/bilal/pv_twin/inv/p_active -> P_inv
        mapping = {
            FULL_TOPICS[0]: "P_inv", FULL_TOPICS[1]: "P_pv", FULL_TOPICS[2]: "P_dc",
            FULL_TOPICS[3]: "V_inv", FULL_TOPICS[4]: "V_pv", FULL_TOPICS[5]: "V_dc"
        }
        if topic in mapping:
            # تحديث الصندوق العالمي مباشرة
            data_store[mapping[topic]] = val
    except Exception as e:
        pass

@st.cache_resource
def start_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="Dashboard_Bilal_Final")
    client.on_message = on_message
    client.connect(BROKER, 1883, 60)
    for t in FULL_TOPICS:
        client.subscribe(t)
    client.loop_start()
    return client

mqtt_client = start_mqtt()

# --- 4. واجهة العرض ---
st.set_page_config(page_title="Digital Twin PV - ENSET", layout="wide")
st.title("☀️ Digital Twin ENSET: Cloud Monitoring")

placeholder = st.empty()

while True:
    # أخذ نسخة من البيانات من الصندوق العالمي
    current = data_store.copy()
    
    # تحديث التاريخ
    st.cache_resource.history_list.append(current)
    if len(st.cache_resource.history_list) > 50:
        st.cache_resource.history_list.pop(0)
    
    df = pd.DataFrame(st.cache_resource.history_list).astype(float)

    with placeholder.container():
        # فحص الداتا (DEBUG)
        if current["P_pv"] == 0 and current["V_inv"] == 0:
            st.warning(f"⏳ En attente... Listening on: {FULL_TOPICS[1]}")
            st.write("Dernières valeurs reçues (Store):", current)
        else:
            # العرض الاحترافي
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Puissance PV", f"{current['P_pv']:.1f} W")
            with c2: st.metric("Tension Onduleur", f"{current['V_inv']:.1f} V")
            with c3: 
                v_rms = np.sqrt(np.mean(df['V_inv']**2)) if not df.empty else 0
                st.metric("V_inv (RMS)", f"{v_rms:.2f} V")

            # المبيانات
            st.plotly_chart(px.line(df, y=["P_pv", "P_inv"], title="Puissances (W)", template="plotly_dark"), use_container_width=True)
            st.plotly_chart(px.line(df, y=["V_pv", "V_inv"], title="Tensions (V)", template="plotly_dark"), use_container_width=True)

    time.sleep(0.5)
