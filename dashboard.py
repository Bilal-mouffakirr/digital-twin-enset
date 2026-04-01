import streamlit as st
import paho.mqtt.client as mqtt
import pandas as pd
import numpy as np
import time
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

# ============================================================
# 1. إعدادات الواجهة
# ============================================================
st.set_page_config(page_title="Digital Twin PV - ENSET", layout="wide", page_icon="☀️")

st.markdown("""
    <style>
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #3d4466; }
    .main { background-color: #0e1117; }
    [data-testid="stSidebar"] { background-color: #1a1d2e; border-right: 1px solid #3d4466; }
    .sidebar-logo { text-align: center; padding: 20px 0; }
    .sidebar-logo h2 { color: #00d1b2; font-size: 1.4rem; margin: 0; }
    .sidebar-logo p  { color: #aaa; font-size: 0.8rem; margin: 0; }
    </style>
    """, unsafe_allow_html=True)

# ============================================================
# 2. إعدادات MQTT
# ============================================================
PREFIX      = "enset/bilal/pv_twin/"
BROKER      = "broker.hivemq.com"
TOPICS_LIST = ["inv/p_active", "pv/puissance", "dc/p_boost",
               "inv/tension",  "pv/tension",   "dc/tension",
               "pv/courant"]                      # ← زدنا تيار PV للـ MPPT
FULL_TOPICS = [PREFIX + t for t in TOPICS_LIST]

# ============================================================
# 3. المخزن العالمي
# ============================================================
@st.cache_resource
def get_global_store():
    return {
        "store": {
            "P_inv": 0.0, "P_pv": 0.0, "P_dc": 0.0,
            "V_inv": 0.0, "V_pv": 0.0, "V_dc": 0.0,
            "I_pv":  0.0
        },
        "history": [],
        "connected": False,
        "last_error": ""
    }

global_data  = get_global_store()
data_store   = global_data["store"]
history_list = global_data["history"]

# ============================================================
# 4. إعداد MQTT مع معالجة الأخطاء
# ============================================================
def on_connect(client, userdata, flags, reason_code, properties=None):
    if hasattr(reason_code, 'value'):
        ok = reason_code.value == 0
    else:
        ok = reason_code == 0
    global_data["connected"] = ok
    if not ok:
        global_data["last_error"] = f"Connection failed: {reason_code}"

def on_disconnect(client, userdata, disconnect_flags, reason_code=None, properties=None):
    global_data["connected"] = False

def on_message(client, userdata, message):
    try:
        val   = float(message.payload.decode())
        topic = message.topic
        mapping = {
            FULL_TOPICS[0]: "P_inv", FULL_TOPICS[1]: "P_pv",
            FULL_TOPICS[2]: "P_dc",  FULL_TOPICS[3]: "V_inv",
            FULL_TOPICS[4]: "V_pv",  FULL_TOPICS[5]: "V_dc",
            FULL_TOPICS[6]: "I_pv"
        }
        if topic in mapping:
            data_store[mapping[topic]] = val
    except Exception:
        pass

@st.cache_resource
def start_mqtt_service():
    try:
        unique_id = f"Dashboard_Bilal_{int(time.time())}"
        client    = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=unique_id)
        client.on_connect    = on_connect
        client.on_disconnect = on_disconnect
        client.on_message    = on_message
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
# 5. توليد منحنى P-V الفيزيائي (Théorique)
#    نموذج صف واحد: I = Isc - Io*(exp((V+I*Rs)/(Vt)) - 1)
#    نستعمل تقريب مبسط كافي للـ Soutenance
# ============================================================
def generate_pv_curve(V_pv_current, I_pv_current, Isc=8.5, Voc=37.0, Impp=7.9, Vmpp=30.0):
    """
    يرجع (V_arr, P_arr, V_mpp, P_mpp)
    يحسب MPP من المعطيات المرسلة من Simulink إلا توفرو,
    وإلا يستعمل القيم الافتراضية.
    """
    # إذا عندنا بيانات حقيقية نستعملهم للـ MPP الحقيقي
    if V_pv_current > 1 and I_pv_current > 0.1:
        V_mpp = V_pv_current
        P_mpp = V_pv_current * I_pv_current
    else:
        V_mpp = Vmpp
        P_mpp = Impp * Vmpp

    # منحنى نظري مبسط
    V_arr = np.linspace(0, Voc, 300)
    # تقريب: I(V) = Isc * (1 - exp((V - Voc) / (Voc - Vmpp) * 3))
    k     = 3.0 / (Voc - Vmpp + 1e-6)
    I_arr = np.clip(Isc * (1 - np.exp(k * (V_arr - Voc))), 0, Isc)
    P_arr = V_arr * I_arr

    return V_arr, P_arr, V_mpp, P_mpp

# ============================================================
# 6. Sidebar
# ============================================================
with st.sidebar:
    # --- لوغو ENSET ---
    st.markdown("""
    <div class="sidebar-logo">
        <div style="font-size:3rem;">☀️</div>
        <h2>ENSET Mohammedia</h2>
        <p>Digital Twin — PV System</p>
        <p style="color:#00d1b2; font-size:0.75rem; margin-top:8px;">Bilal · 2025</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # --- حالة الاتصال ---
    st.subheader("📡 Connexion MQTT")
    conn_status = global_data.get("connected", False)
    if conn_status:
        st.success("✅ Broker connecté")
    else:
        st.error("🔴 Broker déconnecté")
    st.caption(f"Broker: `{BROKER}`")
    st.caption(f"Prefix: `{PREFIX}`")

    st.markdown("---")

    # --- زر التحميل ---
    st.subheader("📂 Export des données")

    if len(history_list) > 0:
        df_export = pd.DataFrame(history_list).astype(float)
        df_export.insert(0, "Sample", range(1, len(df_export) + 1))

        csv_buf = StringIO()
        df_export.to_csv(csv_buf, index=False, sep=";", decimal=",")  # format Excel FR

        st.download_button(
            label="⬇️ Télécharger CSV (Excel)",
            data=csv_buf.getvalue().encode("utf-8-sig"),  # BOM pour Excel FR
            file_name="digital_twin_pv_data.csv",
            mime="text/csv",
            use_container_width=True
        )
        st.caption(f"📊 {len(history_list)} échantillons enregistrés")
    else:
        st.info("Aucune donnée encore reçue.")

    st.markdown("---")

    # --- معلومات إضافية ---
    st.subheader("⚙️ Paramètres")
    st.caption(f"Rafraîchissement : 500 ms")
    st.caption(f"Historique max   : 50 pts")
    if global_data["last_error"]:
        st.warning(f"⚠️ {global_data['last_error']}")

# ============================================================
# 7. حلقة العرض الرئيسية — مع try/except شاملة
#    => ما عادش كيطيح الـ red error
# ============================================================
st.title("☀️ Digital Twin ENSET: Cloud Monitoring Pro")
placeholder = st.empty()

while True:
    try:
        # --- Snapshot ---
        current_vals = data_store.copy()
        history_list.append(current_vals.copy())
        if len(history_list) > 50:
            history_list.pop(0)

        df = pd.DataFrame(history_list).astype(float)

        with placeholder.container():

            # === حالة الانتظار ===
            if current_vals["P_pv"] == 0 and current_vals["V_inv"] == 0:
                st.warning("⏳ En attente de données... Vérifiez votre Gateway Simulink/Python.")
                st.info(f"📡 Topics surveillés sous: `{PREFIX}`")
                time.sleep(0.5)
                continue

            # =========================================================
            # Row 1 — Métriques
            # =========================================================
            m1, m2, m3, m4 = st.columns(4)
            v_rms = float(np.sqrt(np.mean(df['V_inv']**2))) if len(df) > 0 else 0.0
            eff   = (current_vals['P_inv'] / current_vals['P_pv'] * 100) if current_vals['P_pv'] > 0 else 0.0

            with m1: st.metric("⚡ Puissance PV",       f"{current_vals['P_pv']:.1f} W")
            with m2: st.metric("🔌 Puissance Onduleur", f"{current_vals['P_inv']:.1f} W")
            with m3: st.metric("📈 V_inv RMS",          f"{v_rms:.2f} V")
            with m4: st.metric("🎯 Rendement estimé",   f"{eff:.1f} %")

            st.markdown("---")

            # =========================================================
            # Row 2 — Courbes Puissances + Tensions
            # =========================================================
            col1, col2 = st.columns(2)

            with col1:
                fig_p = px.line(
                    df, y=["P_pv", "P_inv"],
                    title="📊 Analyse des Puissances (W)",
                    template="plotly_dark",
                    color_discrete_map={"P_pv": "#00d1b2", "P_inv": "#ff3860"}
                )
                fig_p.update_layout(
                    height=350, margin=dict(l=0, r=0, t=40, b=0),
                    xaxis_title="Échantillon", yaxis_title="Puissance (W)"
                )
                st.plotly_chart(fig_p, use_container_width=True)

            with col2:
                fig_v = px.line(
                    df, y=["V_pv", "V_inv"],
                    title="⚡ Stabilité des Tensions (V)",
                    template="plotly_dark",
                    color_discrete_map={"V_pv": "#FFDD57", "V_inv": "#3273DC"}
                )
                fig_v.update_layout(
                    height=350, margin=dict(l=0, r=0, t=40, b=0),
                    xaxis_title="Échantillon", yaxis_title="Tension (V)"
                )
                st.plotly_chart(fig_v, use_container_width=True)

            st.markdown("---")

            # =========================================================
            # Row 3 — Courbe MPPT  P = f(V)   ← الجديدة
            # =========================================================
            st.subheader("🎯 Suivi du Point de Puissance Maximale (MPPT)")
            mppt_col1, mppt_col2 = st.columns([2, 1])

            V_now = current_vals["V_pv"]
            I_now = current_vals["I_pv"]
            P_now = V_now * I_now if I_now > 0.1 else current_vals["P_pv"]

            V_arr, P_arr, V_mpp_th, P_mpp_th = generate_pv_curve(V_now, I_now)

            with mppt_col1:
                fig_mppt = go.Figure()

                # المنحنى النظري
                fig_mppt.add_trace(go.Scatter(
                    x=V_arr, y=P_arr,
                    mode='lines',
                    name='Courbe P-V (théorique)',
                    line=dict(color='#00d1b2', width=2.5)
                ))

                # نقطة MPP النظرية
                fig_mppt.add_trace(go.Scatter(
                    x=[V_mpp_th], y=[P_mpp_th],
                    mode='markers',
                    name='P_MPP théorique',
                    marker=dict(color='#FFDD57', size=12, symbol='star')
                ))

                # النقطة الحمراء — موقع الـ Controller الحالي
                fig_mppt.add_trace(go.Scatter(
                    x=[V_now], y=[P_now],
                    mode='markers+text',
                    name='Point de fonctionnement',
                    marker=dict(color='#ff3860', size=16, symbol='circle',
                                line=dict(color='white', width=2)),
                    text=[f"  ({V_now:.1f}V, {P_now:.1f}W)"],
                    textposition='top right',
                    textfont=dict(color='white', size=11)
                ))

                # خط عمودي من المحور X للنقطة
                fig_mppt.add_shape(
                    type="line",
                    x0=V_now, x1=V_now, y0=0, y1=P_now,
                    line=dict(color="#ff3860", dash="dot", width=1.5)
                )

                fig_mppt.update_layout(
                    title="Caractéristique P = f(V) — Panneau PV",
                    template="plotly_dark",
                    height=400,
                    margin=dict(l=0, r=0, t=50, b=0),
                    xaxis_title="Tension V_pv (V)",
                    yaxis_title="Puissance P (W)",
                    legend=dict(
                        orientation="h",
                        yanchor="bottom", y=1.02,
                        xanchor="right",  x=1
                    )
                )
                st.plotly_chart(fig_mppt, use_container_width=True)

            with mppt_col2:
                # بطاقة معلومات MPPT
                delta_p = P_now - P_mpp_th
                delta_v = V_now - V_mpp_th
                tracking_err = abs(delta_p / P_mpp_th * 100) if P_mpp_th > 0 else 0.0

                st.metric("📍 V actuel",         f"{V_now:.2f} V",
                          delta=f"{delta_v:+.2f} V vs MPP")
                st.metric("⚡ P actuelle",        f"{P_now:.1f} W",
                          delta=f"{delta_p:+.1f} W vs MPP")
                st.metric("🎯 Erreur tracking",   f"{tracking_err:.2f} %",
                          delta_color="inverse")

                st.markdown("---")
                if tracking_err < 2.0:
                    st.success("✅ MPPT bien suivi !")
                elif tracking_err < 10.0:
                    st.warning("⚠️ Suivi acceptable")
                else:
                    st.error("❌ Point loin du MPP")

                st.caption("⭐ = P_MPP théorique\n🔴 = Point réel")

    except Exception as e:
        pass

    time.sleep(0.5)
