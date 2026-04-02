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
# 1. 
# ============================================================
st.set_page_config(page_title="Digital Twin PV - ENSET", layout="wide", page_icon="https://www.startpage.com/av/proxy-image?piurl=https%3A%2F%2Ftse3.mm.bing.net%2Fth%2Fid%2FOIP._SKHTtj-78Un4eybBA2wkQHaHa%3Fpid%3DApi&sp=1775076847Tb1a92041ca968dd0518d99783a819921ac64735d498fc70eabc66865c2ec68be")

st.markdown("""
    <style>
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #3d4466; }
    .main { background-color: #0e1117; }
    [data-testid="stSidebar"] { background-color: #1a1d2e; border-right: 1px solid #3d4466; }
    </style>
    """, unsafe_allow_html=True)

# ============================================================
# 2.  MQTT — 10 topics
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
# 3. 
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

def on_disconnect(client, userdata, disconnect_flags, reason_code=None, properties=None):
    global_data["connected"] = False

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
        uid    = f"Dashboard_Bilal_{int(time.time())}"
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=uid)
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
# 5. Sidebar
# ============================================================
#  python
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding:20px 0;">
       <div style="font-size:3rem;">
          <img 
            src="th.jpg"
            alt="ENSET"
            style="width:9rem; height:9rem;"
             >
        </div>
        <h2 style="color:#00d1b2; font-size:1.4rem; margin:0;">ENSET Mohammedia</h2>
        <p style="color:#aaa; font-size:0.8rem; margin:0;">Digital Twin — PV System</p>
        <p style="color:#00d1b2; font-size:0.75rem; margin-top:8px;"> 2025/2026 </p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("📡 Connexion MQTT")
    if global_data.get("connected", False):
        st.success("✅ Broker connecté")
    else:
        st.error("🔴 Broker déconnecté")
    st.caption(f"Broker: `{BROKER}`")
    st.caption(f"Prefix: `{PREFIX}`")

    st.markdown("---")
    st.subheader("📂 Export des données")

    if len(history_list) > 0:
        df_export = pd.DataFrame(history_list).astype(float)
        df_export.insert(0, "Sample", range(1, len(df_export) + 1))
        csv_buf = StringIO()
        df_export.to_csv(csv_buf, index=False, sep=";", decimal=",")
        st.download_button(
            label="⬇️ Télécharger CSV (Excel)",
            data=csv_buf.getvalue().encode("utf-8-sig"),
            file_name="digital_twin_pv_data.csv",
            mime="text/csv",
            use_container_width=True
        )
        st.caption(f"📊 {len(history_list)} échantillons enregistrés")
    else:
        st.info("Aucune donnée encore reçue.")

    st.markdown("---")
    st.subheader("⚙️ Paramètres")
    st.caption(f"Rafraîchissement : {time_sleep} s")
    st.caption("Historique max   : 50 pts")
    if global_data["last_error"]:
        st.warning(f"⚠️ {global_data['last_error']}")

# ============================================================
# 6. Boucle principale
# ============================================================
st.title("Digital Twin ENSET: Cloud Monitoring Pro")
placeholder = st.empty()

while True:
    try:
        current_vals = data_store.copy()
        history_list.append(current_vals.copy())
        if len(history_list) > 50:
            history_list.pop(0)

        df = pd.DataFrame(history_list).astype(float)

        with placeholder.container():

            # ── Attente données ──────────────────────────────────
            if current_vals["P_pv"] == 0 and current_vals["V_inv"] == 0:
                st.warning("⏳ En attente de données... Vérifiez votre Gateway.")
                st.info(f"📡Topics surveillés sous: `{PREFIX}`")
                time.sleep(0.5)
                continue

            # ========================================================
            # ROW 1 — Métriques Puissances + Tensions
            # ========================================================
            # ========================================================
            # ROW 1 — Les Puissances (3 Columns)
            # ========================================================
            st.subheader("⚡ Puissances — Valeurs instantanées")
            r1_c1, r1_c2, r1_c3 = st.columns(3)
            
            # الحسابات (كتبقى هي هي)
            v_rms = float(np.sqrt(np.mean(df['V_inv']**2))) if len(df) > 0 else 0.0
            eff   = (current_vals['P_inv'] / current_vals['P_pv'] * 100) if current_vals['P_pv'] > 0 else 0.0
            
            with r1_c1: st.metric("P_PV",       f"{current_vals['P_pv']:.1f} W")
            with r1_c2: st.metric("P_Boost DC", f"{current_vals['P_dc']:.1f} W")
            with r1_c3: st.metric("P_Onduleur", f"{current_vals['P_inv']:.1f} W")
            
            st.markdown(" ") # سطر خاوي خفيف للتنفس
            
            # ========================================================
            # ROW 2 — Tensions & Performance (3 Columns)
            # ========================================================
            st.subheader("Tensions & Performance")
            r2_c1, r2_c2, r2_c3 = st.columns(3)
            
            with r2_c1: st.metric("V_inv RMS",   f"{v_rms:.2f} V")
            with r2_c2: st.metric("V_PV",        f"{current_vals['V_pv']:.1f} V")
            with r2_c3: st.metric("Rendement",   f"{eff:.1f} %")
            
            st.markdown("---") # فاصل بين الأرقام والمبيانات
            #=================================================
            # ROW 2 — Puissance Apparente S + Réactive Q + FP
            # ========================================================
            st.subheader("Puissances Apparente & Réactive")
            s1, s2, s3, s4 = st.columns(4)

            S_val = current_vals['S']
            Q_val = current_vals['Q']
            P_val = current_vals['P_inv']
            fp    = (P_val / S_val) if S_val > 0.1 else 0.0

            with s1: st.metric("🔵 S — Apparente",         f"{S_val:.1f} VA")
            with s2: st.metric("🟠 Q — Réactive",          f"{Q_val:.1f} VAR")
            with s3: st.metric("🟢 P — Active",            f"{P_val:.1f} W")
            with s4: st.metric("📊 Facteur de Puissance",  f"{fp:.3f}")

            st.markdown("---")

            # ========================================================
            # ROW 3 — THD
            # ========================================================
            st.subheader("Distorsion Harmonique Totale (THD)")
            t1, t2, t3 = st.columns(3)

            thd_v = current_vals['THD_V']
            thd_i = current_vals['THD_I']

            with t1:
                st.metric("THD_V — Tension onduleur", f"{thd_v:.2f} %")
                if thd_v < 5:
                    st.success("✅ < 5% — Conforme IEC")
                elif thd_v < 8:
                    st.warning("⚠️ Légèrement élevé")
                else:
                    st.error("❌ Hors norme")

            with t2:
                st.metric("THD_I — Courant onduleur", f"{thd_i:.2f} %")
                if thd_i < 5:
                    st.success("✅ < 5% — Conforme IEC")
                elif thd_i < 8:
                    st.warning("⚠️ Légèrement élevé")
                else:
                    st.error("❌ Hors norme")

            with t3:
                fig_thd = go.Figure(go.Bar(
                    x=["THD_V (%)", "THD_I (%)"],
                    y=[thd_v, thd_i],
                    marker_color=["#3273DC", "#ff3860"],
                    text=[f"{thd_v:.2f}%", f"{thd_i:.2f}%"],
                    textposition='outside'
                ))
                fig_thd.add_hline(
                    y=5, line_dash="dash", line_color="#FFDD57", line_width=2,
                    annotation_text="Norme 5%", annotation_position="right"
                )
                fig_thd.update_layout(
                    template="plotly_dark", height=230,
                    margin=dict(l=0, r=20, t=10, b=0),
                    yaxis_title="THD (%)", showlegend=False
                )
                st.plotly_chart(fig_thd, use_container_width=True, key="chart_thd_bar")

            st.markdown("---")

            # ========================================================
            # ROW 4 — Courbes Puissances (3 courbes séparées)
            # ========================================================
            st.subheader("Évolution des Puissances Actives")
            pc1, pc2, pc3 = st.columns(3)

            def make_area_chart(y_data, color, fill_color, title):
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    y=y_data, mode='lines', fill='tozeroy',
                    line=dict(color=color, width=2),
                    fillcolor=fill_color
                ))
                fig.update_layout(
                    title=title, template="plotly_dark", height=280,
                    margin=dict(l=0, r=0, t=40, b=0),
                    showlegend=False,
                    yaxis_title="W", xaxis_title="Échantillon"
                )
                return fig

            with pc1:
                st.plotly_chart(
                    make_area_chart(df['P_pv'],  '#00d1b2', 'rgba(0,209,178,0.15)', 'Puissance PV (W)'),
                    use_container_width=True, key="chart_p_pv"
                )
            with pc2:
                st.plotly_chart(
                    make_area_chart(df['P_dc'],  '#FFDD57', 'rgba(255,221,87,0.15)', 'Puissance Boost DC (W)'),
                    use_container_width=True, key="chart_p_dc"
                )
            with pc3:
                st.plotly_chart(
                    make_area_chart(df['P_inv'], '#ff3860', 'rgba(255,56,96,0.15)',  'Puissance Onduleur AC (W)'),
                    use_container_width=True, key="chart_p_inv"
                )

            st.markdown("---")

            # ========================================================
            # ROW 5 — Courbes Tensions (3 courbes séparées)
            # ========================================================
            st.subheader("Évolution des Tensions")
            vc1, vc2, vc3 = st.columns(3)

            def make_line_chart(y_data, color, title, y_label="V"):
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    y=y_data, mode='lines',
                    line=dict(color=color, width=2)
                ))
                fig.update_layout(
                    title=title, template="plotly_dark", height=260,
                    margin=dict(l=0, r=0, t=40, b=0),
                    showlegend=False,
                    yaxis_title=y_label, xaxis_title="Échantillon"
                )
                return fig

            with vc1:
                st.plotly_chart(
                    make_line_chart(df['V_pv'], '#00d1b2', 'Tension PV (V)'),
                    use_container_width=True, key="chart_v_pv"
                )
            with vc2:
                st.plotly_chart(
                    make_line_chart(df['V_dc'], '#FFDD57', 'Tension Bus DC (V)'),
                    use_container_width=True, key="chart_v_dc"
                )
            with vc3:
                st.plotly_chart(
                    make_line_chart(df['V_inv'], '#3273DC', 'Tension Onduleur AC (V)'),
                    use_container_width=True, key="chart_v_ac"
                )

    except Exception as e:
        pass

    time.sleep(time_sleep)
