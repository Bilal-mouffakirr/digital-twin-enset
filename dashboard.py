"""
app.py — PV Digital Twin Dashboard
Installation: ENSET Mohammedia SSDIA | 12 × 330W | IMEON 3.6
"""

import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import time

from utils.pv_model import computePV, INSTALLATION
from utils.openmeteo import fetch_openmeteo

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PV Digital Twin — ENSET Mohammedia",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS personnalisé ──────────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #020817; }
  [data-testid="stSidebar"]          { background: #0f172a; }
  .main .block-container             { padding-top: 1.5rem; }

  .kpi-card {
    background: #0f172a;
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 8px;
  }
  .kpi-value { font-size: 28px; font-weight: 800; font-family: monospace; }
  .kpi-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .07em; }
  .kpi-sub   { font-size: 11px; color: #334155; margin-top: 3px; }

  .status-live   { color: #22c55e; font-weight: 700; }
  .status-error  { color: #ef4444; font-weight: 700; }
  .status-load   { color: #f59e0b; font-weight: 700; }

  h1, h2, h3 { color: #f1f5f9 !important; }
  p, label    { color: #94a3b8 !important; }
</style>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ☀️ PV Digital Twin")
    st.markdown("**ENSET Mohammedia — SSDIA**")
    st.divider()

    st.markdown("### ⚙️ Paramètres installation")
    inst = INSTALLATION
    st.markdown(f"""
    | Paramètre | Valeur |
    |-----------|--------|
    | Panneaux  | 12 × 330 Wc |
    | Pmax STC  | **3 960 Wc** |
    | Onduleur  | IMEON 3.6 |
    | Config    | 12S × 1P |
    | Vmp champ | 451.8 V |
    | Site      | Mohammedia |
    | Azimut    | Sud 0° |
    | Inclinaison | **31°** |
    """)

    st.divider()
    refresh_rate = st.slider("🔄 Refresh (secondes)", 30, 300, 60, 10)
    auto_refresh  = st.toggle("Auto-refresh", value=True)

    st.divider()
    st.markdown("### 🔌 ESP32 (à venir)")
    mqtt_broker = st.text_input("MQTT Broker IP", placeholder="192.168.1.x", disabled=True)
    st.caption("Sera activé quand les capteurs seront installés")


# ── Header ────────────────────────────────────────────────────────────────────
col_title, col_status = st.columns([3, 1])
with col_title:
    st.markdown("# ☀️ PV Digital Twin — ENSET Mohammedia")
    st.caption("Labo SSDIA · Supervision temps réel · Modèle MATLAB/MPPT")
with col_status:
    status_placeholder = st.empty()


# ── Fetch data ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def get_meteo_data():
    return fetch_openmeteo()


with st.spinner("Récupération données Open-Meteo..."):
    try:
        meteo = get_meteo_data()
        T_now = meteo["current"]["temperature_2m"]
        G_now = meteo["current"]["shortwave_radiation"] or 0.0
        status_placeholder.markdown('<p class="status-live">🟢 LIVE</p>', unsafe_allow_html=True)
    except Exception as e:
        T_now, G_now = 28.0, 600.0
        st.warning(f"⚠️ Open-Meteo inaccessible — données simulées | {e}")
        meteo = None
        status_placeholder.markdown('<p class="status-error">🔴 ERREUR API</p>', unsafe_allow_html=True)


pv = computePV(G_now, T_now)
Pmax_field = INSTALLATION["field"]["Pmax_field"]
PR = (pv["P_field"] / Pmax_field * 100) if Pmax_field else 0

# ── KPI Row ───────────────────────────────────────────────────────────────────
st.divider()
c1, c2, c3, c4, c5, c6 = st.columns(6)

def kpi(col, label, value, unit, color, sub=""):
    col.markdown(f"""
    <div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value" style="color:{color}">{value}<span style="font-size:13px;color:#64748b;margin-left:4px">{unit}</span></div>
      <div class="kpi-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)

kpi(c1, "Puissance PV",  f"{pv['P_field']:.0f}",  "W",    "#f59e0b", f"PR: {PR:.1f}%")
kpi(c2, "Irradiation",   f"{G_now:.0f}",           "W/m²", "#38bdf8", "STC: 1000 W/m²")
kpi(c3, "Température",   f"{T_now:.1f}",           "°C",   "#fb923c", f"Tc cellule: {pv['Tc']:.1f}°C")
kpi(c4, "Tension Vmp",   f"{pv['Vmp']:.1f}",       "V",    "#a78bfa", f"Voc: {pv['Voc']:.1f} V")
kpi(c5, "Courant Imp",   f"{pv['Imp']:.2f}",       "A",    "#34d399", f"Isc: {pv['Isc']:.2f} A")
kpi(c6, "Efficacité η",  f"{pv['eta']:.2f}",       "%",    "#22c55e", f"Réf: 17%")

st.divider()

# ── Gauges row ────────────────────────────────────────────────────────────────
def make_gauge(value, max_val, title, unit, color):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": f" {unit}", "font": {"color": "#f1f5f9", "size": 18}},
        title={"text": title, "font": {"color": "#64748b", "size": 12}},
        gauge={
            "axis": {"range": [0, max_val], "tickcolor": "#334155"},
            "bar":  {"color": color},
            "bgcolor": "#1e293b",
            "bordercolor": "#0f172a",
            "steps": [{"range": [0, max_val], "color": "#0f172a"}],
            "threshold": {
                "line": {"color": color, "width": 2},
                "thickness": 0.75,
                "value": value,
            },
        },
    ))
    fig.update_layout(
        height=180, margin=dict(t=40, b=10, l=20, r=20),
        paper_bgcolor="#0f172a", font_color="#f1f5f9",
    )
    return fig

g1, g2, g3, g4, g5 = st.columns(5)
g1.plotly_chart(make_gauge(G_now,           1200, "Irradiation",  "W/m²", "#fbbf24"), use_container_width=True)
g2.plotly_chart(make_gauge(T_now,           50,   "Température",  "°C",   "#fb923c"), use_container_width=True)
g3.plotly_chart(make_gauge(pv["P_field"],   3960, "Puissance PV", "W",    "#22c55e"), use_container_width=True)
g4.plotly_chart(make_gauge(pv["Vmp"],       500,  "Tension Vmp",  "V",    "#38bdf8"), use_container_width=True)
g5.plotly_chart(make_gauge(pv["Imp"],       12,   "Courant Imp",  "A",    "#34d399"), use_container_width=True)

st.divider()

# ── Hourly charts ─────────────────────────────────────────────────────────────
if meteo:
    hrs  = meteo["hourly"]
    times = [t.split("T")[1][:5] for t in hrs["time"]]

    df_hourly = pd.DataFrame({
        "Heure":       times,
        "Température": hrs["temperature_2m"],
        "Radiation":   hrs["shortwave_radiation"],
    })

    # Compute PV power for each hour
    df_hourly["Puissance"] = df_hourly.apply(
        lambda r: computePV(r["Radiation"] or 0, r["Température"])["P_field"], axis=1
    )

    col_left, col_right = st.columns(2)

    # Chart 1 — Puissance PV
    with col_left:
        fig_pv = go.Figure()
        fig_pv.add_trace(go.Scatter(
            x=df_hourly["Heure"], y=df_hourly["Puissance"],
            fill="tozeroy", fillcolor="rgba(34,197,94,0.15)",
            line=dict(color="#22c55e", width=2),
            name="Puissance PV (W)"
        ))
        fig_pv.update_layout(
            title="⚡ Puissance PV simulée — aujourd'hui",
            paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
            font_color="#94a3b8", height=280,
            margin=dict(t=40, b=30, l=50, r=20),
            xaxis=dict(gridcolor="#1e293b", tickfont=dict(size=10)),
            yaxis=dict(gridcolor="#1e293b", title="W"),
        )
        st.plotly_chart(fig_pv, use_container_width=True)

    # Chart 2 — Irradiation
    with col_right:
        fig_rad = go.Figure()
        fig_rad.add_trace(go.Scatter(
            x=df_hourly["Heure"], y=df_hourly["Radiation"],
            fill="tozeroy", fillcolor="rgba(251,191,36,0.15)",
            line=dict(color="#fbbf24", width=2),
            name="Irradiation (W/m²)"
        ))
        fig_rad.update_layout(
            title="☀️ Irradiation solaire — aujourd'hui",
            paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
            font_color="#94a3b8", height=280,
            margin=dict(t=40, b=30, l=50, r=20),
            xaxis=dict(gridcolor="#1e293b", tickfont=dict(size=10)),
            yaxis=dict(gridcolor="#1e293b", title="W/m²"),
        )
        st.plotly_chart(fig_rad, use_container_width=True)

    col_left2, col_right2 = st.columns(2)

    # Chart 3 — Température
    with col_left2:
        fig_t = go.Figure()
        fig_t.add_trace(go.Scatter(
            x=df_hourly["Heure"], y=df_hourly["Température"],
            fill="tozeroy", fillcolor="rgba(251,146,60,0.15)",
            line=dict(color="#fb923c", width=2),
            name="Température (°C)"
        ))
        fig_t.update_layout(
            title="🌡️ Température ambiante — aujourd'hui",
            paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
            font_color="#94a3b8", height=280,
            margin=dict(t=40, b=30, l=50, r=20),
            xaxis=dict(gridcolor="#1e293b", tickfont=dict(size=10)),
            yaxis=dict(gridcolor="#1e293b", title="°C"),
        )
        st.plotly_chart(fig_t, use_container_width=True)

    # Chart 4 — Énergie cumulée
    with col_right2:
        df_hourly["Energie_cum"] = df_hourly["Puissance"].cumsum() / 1000  # kWh
        fig_e = go.Figure()
        fig_e.add_trace(go.Scatter(
            x=df_hourly["Heure"], y=df_hourly["Energie_cum"],
            fill="tozeroy", fillcolor="rgba(167,139,250,0.15)",
            line=dict(color="#a78bfa", width=2),
            name="Énergie cumulée (kWh)"
        ))
        fig_e.update_layout(
            title="🔋 Énergie cumulée — aujourd'hui",
            paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
            font_color="#94a3b8", height=280,
            margin=dict(t=40, b=30, l=50, r=20),
            xaxis=dict(gridcolor="#1e293b", tickfont=dict(size=10)),
            yaxis=dict(gridcolor="#1e293b", title="kWh"),
        )
        st.plotly_chart(fig_e, use_container_width=True)

    # ── Tableau de données ────────────────────────────────────────────────────
    st.divider()
    with st.expander("📋 Voir les données horaires complètes"):
        st.dataframe(
            df_hourly.rename(columns={
                "Heure": "Heure",
                "Température": "T_amb (°C)",
                "Radiation": "G (W/m²)",
                "Puissance": "P_PV (W)",
                "Energie_cum": "E_cumulée (kWh)",
            }).style.format({
                "T_amb (°C)": "{:.1f}",
                "G (W/m²)":   "{:.0f}",
                "P_PV (W)":   "{:.1f}",
                "E_cumulée (kWh)": "{:.3f}",
            }),
            use_container_width=True, hide_index=True
        )
        csv = df_hourly.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Télécharger CSV", csv, "pv_data.csv", "text/csv")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    f"🕐 Dernière mise à jour: {datetime.now().strftime('%H:%M:%S')} · "
    "Source: Open-Meteo API (Mohammedia 33.69°N, 7.38°W) · "
    "Modèle: P = Pmax×(1+β(Tc−Tref))×G/Gstc · ENSET Mohammedia SSDIA 2024"
)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if auto_refresh:
    time.sleep(refresh_rate)
    st.cache_data.clear()
    st.rerun()
