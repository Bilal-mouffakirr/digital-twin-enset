import streamlit as st
import paho.mqtt.client as mqtt
import pandas as pd
import numpy as np
import time
import plotly.express as px

# --- 1. إعدادات السحاب (Cloud Settings) ---
PREFIX = "enset/bilal/pv_twin/"
BROKER = "broker.hivemq.com"
TOPICS_LIST = ["inv/p_active", "pv/puissance", "dc/p_boost", "inv/tension", "pv/tension", "dc/tension"]
FULL_TOPICS = [PREFIX + t for t in TOPICS_LIST]

# --- 2. الصندوق العالمي (Shared Resource Storage) ---
# استعملنا دالة مُزينة بـ @st.cache_resource لخلق مخزن مشترك
@st.cache_resource
def get_shared_data():
    return {
        "store": { "P_inv": 0.0, "P_pv": 0.0, "P_dc": 0.0, "V_inv": 0.0, "V_pv": 0.0, "V_dc": 0.0 },
        "history": []
    }

# جلب المراجع للمخازن المشتركة
shared_data = get_shared_data()
data_store = shared_data["store"]
history_list = shared_data["history"]

# --- 3. إعداد MQTT (Thread-Safe) ---
def on_message(client, userdata, message):
    try:
        val = float(message.payload.decode())
        topic = message.topic
        mapping = {
            FULL_TOPICS[0]: "P_inv", FULL_TOPICS[1]: "P_pv", FULL_TOPICS[2]: "P_dc",
            FULL_TOPICS[3]: "V_inv", FULL_TOPICS[4]: "V_pv", FULL_TOPICS[5]: "V_dc"
        }
        if topic in mapping:
            # تحديث المخزن المشترك مباشرة
            data_store[mapping[topic]] = val
    except:
        pass

@st.cache_resource
def start_mqtt_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="Dashboard_Bilal_Cloud_Final")
    client.on_message = on_message
    client.connect(BROKER, 1883, 60)
    for t in FULL_TOPICS:
        client.subscribe(t)
    client.loop_start()
    return client

mqtt_client = start_mqtt_client()

# --- 4. واجهة العرض (UI) ---
st.set_page_config(page_title="Digital Twin PV - ENSET", layout="wide")
st.title("☀️ Digital Twin ENSET: Cloud Monitoring")

placeholder = st.empty()

while True:
    # أخذ نسخة من البيانات الحالية للرسم
    current = data_store.copy()
    
    # إضافة السطر الجديد للتاريخ
    history_list.append(current)
    if len(history_list) > 50:
        history_list.pop(0)
    
    # تحويل التاريخ لـ DataFrame
    df = pd.DataFrame(history_list).astype(float)

    with placeholder.container():
        if current["P_pv"] == 0 and current["V_inv"] == 0:
            st.warning("⏳ En attente de données du Cloud...")
            st.write("Topics écoutés :", FULL_TOPICS)
        else:
            # عرض الأرقام (Metrics)
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Puissance PV", f"{current['P_pv']:.1f} W")
            with c2: st.metric("Tension Onduleur", f"{current['V_inv']:.1f} V")
            with c3: 
                v_rms = np.sqrt(np.mean(df['V_inv']**2)) if not df.empty else 0
                st.metric("V_inv (RMS)", f"{v_rms:.2f} V")

            # المبيانات التفاعلية (Plotly)
            st.plotly_chart(px.line(df, y=["P_pv", "P_inv"], title="Puissances (W)", template="plotly_dark"), use_container_width=True)
            st.plotly_chart(px.line(df, y=["V_pv", "V_inv"], title="Tensions (V)", template="plotly_dark"), use_container_width=True)

    time.sleep(0.5)
