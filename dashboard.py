"""
PV MPPT Inverter Dashboard - ENSET Mohammedia
Real-time supervision avec Open-Meteo + FMU replica + PVLib
"""

import streamlit as st
import numpy as np
import pandas as pd
import requests
import pvlib
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="PV MPPT – Supervision Temps Réel",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    .main-header {
        font-size: 1.8rem; font-weight: 700;
        background: linear-gradient(135deg, #f59e0b, #ef4444);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    div[data-testid="stMetricValue"] > div { font-size: 1.4rem !important; font-weight: 800 !important; }
    .live-badge {
        display: inline-block;
        background: #22c55e; color: #000;
        font-size: 0.7rem; font-weight: 800;
        padding: 2px 10px; border-radius: 20px;
        animation: blink 1.5s infinite;
    }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.5} }
    .stAlert { font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
LOCATION = dict(lat=33.6861, lon=-7.3828, altitude=27, tz="Africa/Casablanca", name="Mohammedia, Maroc")

PANEL = dict(
    Pmax=330, Vmp=37.65, Imp=8.77, Voc=44.4, Isc=9.28,
    Ns=12, Np=1, Tc_coeff=-0.0035,
    R_s=0.35, R_sh_ref=525.0, P_rated=3960,
    alpha_sc=0.004539, a_ref=1.5, I_L_ref=9.28,
    I_o_ref=2.2e-10, Adjust=8.7, gamma_r=-0.35,
    tilt=31, azimuth=180,
)

REFRESH_INTERVALS = {"2s": 2, "5s": 5, "10s": 10, "30s": 30}

# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=[
        "time", "G", "Tamb", "Tcell", "wind",
        "Ppanneau", "Vmpp", "Impp", "Pbooste",
        "P_ondu", "S_ondu", "Q_ondu", "THD_V", "THD_i", "eta",
        "P_pvlib",
    ])
if "weather_cache" not in st.session_state:
    st.session_state.weather_cache = None
if "last_api_fetch" not in st.session_state:
    st.session_state.last_api_fetch = 0
if "tick" not in st.session_state:
    st.session_state.tick = 0

HIST_MAX = 120  # keep last 120 points

# ─────────────────────────────────────────────
# OPEN-METEO FETCH  (cache 3 min)
# ─────────────────────────────────────────────
def fetch_openmeteo():
    now = datetime.now()
    # Only re-fetch if cache is older than 3 min
    age = time.time() - st.session_state.last_api_fetch
    if st.session_state.weather_cache is not None and age < 180:
        return st.session_state.weather_cache, False  # (data, is_fresh)

    end_d = now.strftime("%Y-%m-%d")
    start_d = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LOCATION['lat']}&longitude={LOCATION['lon']}"
        "&hourly=shortwave_radiation,diffuse_radiation,"
        "direct_normal_irradiance,temperature_2m,windspeed_10m"
        f"&start_date={start_d}&end_date={end_d}"
        "&timezone=Africa%2FCasablanca"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        h = r.json()["hourly"]
        df = pd.DataFrame({
            "time": pd.to_datetime(h["time"]),
            "GHI": h["shortwave_radiation"],
            "DHI": h["diffuse_radiation"],
            "DNI": h["direct_normal_irradiance"],
            "Tamb": h["temperature_2m"],
            "wind": h["windspeed_10m"],
        }).set_index("time").dropna()
        st.session_state.weather_cache = df
        st.session_state.last_api_fetch = time.time()
        return df, True
    except Exception as e:
        return st.session_state.weather_cache, False


def get_current_conditions(df):
    """Get nearest hourly row to now."""
    if df is None or df.empty:
        return None
    now = pd.Timestamp.now(tz=LOCATION["tz"]).tz_localize(None)
    idx = (df.index - now).abs().argmin()
    row = df.iloc[idx]
    return {
        "G": max(float(row["GHI"]), 0),
        "DHI": max(float(row["DHI"]), 0),
        "DNI": max(float(row["DNI"]), 0),
        "Tamb": float(row["Tamb"]),
        "wind": max(float(row["wind"]), 0.5),
    }


# ─────────────────────────────────────────────
# FMU SIMULATION (Python replica)
# ─────────────────────────────────────────────
def sim_fmu(G, Tamb, wind, tick=0):
    G = max(G, 0)
    # Sub-hour variation noise (realistic)
    noise = 1 + 0.012 * np.sin(tick * 0.31) + 0.006 * np.sin(tick * 0.73)
    G = max(G * noise, 0)

    Tcell = max(Tamb + G * 0.03 - wind * 0.5, Tamb)
    dT = Tcell - 25

    Vmpp = PANEL["Vmp"] * PANEL["Ns"] * (1 + PANEL["Tc_coeff"] * dT)
    Impp = PANEL["Imp"] * (G / 1000) * PANEL["Np"]
    Ppanneau = max(Vmpp * Impp, 0)
    Pbooste = Ppanneau * 0.97

    ratio = min(Pbooste / PANEL["P_rated"], 1.0)
    if ratio < 0.05:
        eta_inv = 0.0
    elif ratio < 0.2:
        eta_inv = 0.90 + 0.07 * (ratio / 0.2)
    elif ratio < 0.5:
        eta_inv = 0.96 + 0.01 * ((ratio - 0.2) / 0.3)
    else:
        eta_inv = 0.97 - 0.005 * ((ratio - 0.5) / 0.5)

    P_ondu = Pbooste * eta_inv
    cos_phi = 0.99
    S_ondu = P_ondu / cos_phi if cos_phi > 0 else P_ondu
    Q_ondu = S_ondu * np.sqrt(1 - cos_phi**2)
    THD_V = (0.015 + 0.005 * (1 - ratio)) * 100
    THD_i = (0.025 + 0.015 * (1 - ratio)) * 100

    return {
        "G": G, "Tamb": Tamb, "Tcell": Tcell, "wind": wind,
        "Ppanneau": Ppanneau, "Vmpp": Vmpp, "Impp": Impp,
        "Pbooste": Pbooste, "P_ondu": P_ondu,
        "S_ondu": S_ondu, "Q_ondu": Q_ondu,
        "THD_V": THD_V, "THD_i": THD_i,
        "eta": eta_inv * 100,
    }


# ─────────────────────────────────────────────
# PVLIB SIMULATION
# ─────────────────────────────────────────────
def sim_pvlib(conditions, weather_df):
    if weather_df is None or weather_df.empty:
        return 0.0
    try:
        loc = pvlib.location.Location(
            latitude=LOCATION["lat"], longitude=LOCATION["lon"],
            tz=LOCATION["tz"], altitude=LOCATION["altitude"],
        )
        # Use last 1h slice
        times = weather_df.index[-2:]
        solar_pos = loc.get_solarposition(times)
        poa = pvlib.irradiance.get_total_irradiance(
            surface_tilt=PANEL["tilt"], surface_azimuth=PANEL["azimuth"],
            dni=weather_df["DNI"].iloc[-2:],
            ghi=weather_df["GHI"].iloc[-2:],
            dhi=weather_df["DHI"].iloc[-2:],
            solar_zenith=solar_pos["apparent_zenith"],
            solar_azimuth=solar_pos["azimuth"],
        )
        poa_g = poa["poa_global"].fillna(0).clip(lower=0)
        temp_p = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"]
        T_cell = pvlib.temperature.sapm_cell(
            poa_global=poa_g, temp_air=weather_df["Tamb"].iloc[-2:],
            wind_speed=weather_df["wind"].iloc[-2:], **temp_p,
        )
        IL, I0, Rs, Rsh, nNsVth = pvlib.pvsystem.calcparams_cec(
            effective_irradiance=poa_g, temp_cell=T_cell,
            alpha_sc=PANEL["alpha_sc"], a_ref=PANEL["a_ref"],
            I_L_ref=PANEL["I_L_ref"], I_o_ref=PANEL["I_o_ref"],
            R_sh_ref=PANEL["R_sh_ref"], R_s=PANEL["R_s"],
            Adjust=PANEL["Adjust"], EgRef=1.121, dEgdT=-0.0002677,
        )
        mpp = pvlib.pvsystem.max_power_point(IL, I0, Rs, Rsh, nNsVth, method="newton")
        P_pvlib = float(mpp["p_mp"].iloc[-1]) * PANEL["Ns"] * PANEL["Np"]
        return max(P_pvlib, 0)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    st.markdown(f"**📍 {LOCATION['name']}**")
    st.caption(f"Lat {LOCATION['lat']}°N | Lon {LOCATION['lon']}°E")
    st.divider()

    refresh_label = st.select_slider(
        "🔄 Vitesse de rafraîchissement",
        options=list(REFRESH_INTERVALS.keys()), value="5s"
    )
    refresh_sec = REFRESH_INTERVALS[refresh_label]

    st.divider()
    st.markdown("**☀️ Panneau PV**")
    st.caption(f"Pmax={PANEL['Pmax']}W | Vmp={PANEL['Vmp']}V | Config: {PANEL['Ns']}s×{PANEL['Np']}p")
    st.caption(f"Puissance crête: {PANEL['Pmax']*PANEL['Ns']*PANEL['Np']/1000:.2f} kWc")

    st.divider()
    hist_len = st.slider("📊 Points historique affichés", 20, 120, 60)

    st.divider()
    if st.button("🗑️ Reset historique", use_container_width=True):
        st.session_state.history = st.session_state.history.iloc[0:0]
        st.rerun()

    st.divider()
    st.markdown("""
    <div style='font-size:0.72rem;color:#888'>
    <b>FMU:</b> PV_MPPT_Inverter1<br>
    <b>Source:</b> MATLAB/Simulink FMI 2.0<br>
    <b>Météo:</b> Open-Meteo API (live)<br>
    <b>PVLib:</b> SDM-CEC model
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
col_title, col_status = st.columns([3, 1])
with col_title:
    st.markdown('<div class="main-header">☀️ PV MPPT — Supervision Temps Réel</div>', unsafe_allow_html=True)
    st.caption("ENSET Mohammedia | FMU Simulink replica + PVLib | Open-Meteo Mohammedia")
with col_status:
    now_str = datetime.now().strftime("%H:%M:%S")
    age_sec = int(time.time() - st.session_state.last_api_fetch)
    st.markdown(f'<div style="text-align:right;padding-top:10px"><span class="live-badge">● LIVE</span></div>', unsafe_allow_html=True)
    st.caption(f"🕐 {now_str} | API il y a {age_sec}s | Refresh: {refresh_label}")

st.divider()

# ─────────────────────────────────────────────
# FETCH & SIMULATE
# ─────────────────────────────────────────────
weather_df, is_fresh = fetch_openmeteo()
conditions = get_current_conditions(weather_df)

if conditions is None:
    st.error("❌ Impossible de récupérer les données Open-Meteo. Vérifiez la connexion.")
    time.sleep(refresh_sec)
    st.rerun()

if is_fresh:
    st.toast("✅ Données Open-Meteo mises à jour!", icon="📡")

# Run simulations
tick = st.session_state.tick
fmu = sim_fmu(conditions["G"], conditions["Tamb"], conditions["wind"], tick)
pvlib_p = sim_pvlib(conditions, weather_df)
st.session_state.tick += 1

# Append to history
new_row = {"time": datetime.now(), **fmu, "P_pvlib": pvlib_p}
new_df = pd.DataFrame([new_row])
st.session_state.history = pd.concat(
    [st.session_state.history, new_df], ignore_index=True
).tail(HIST_MAX)

hist = st.session_state.history.tail(hist_len)

# ─────────────────────────────────────────────
# KPI CARDS  (instantaneous)
# ─────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)

prev = hist.iloc[-2] if len(hist) >= 2 else None

def delta(key):
    if prev is None: return None
    return float(fmu.get(key, 0)) - float(prev.get(key, 0))

c1.metric("☀️ Irradiance GHI", f"{fmu['G']:.0f} W/m²",
          delta=f"{delta('G'):+.1f}" if prev is not None else None)
c2.metric("🌡️ T Cellule", f"{fmu['Tcell']:.1f} °C",
          delta=f"{delta('Tcell'):+.1f}" if prev is not None else None)
c3.metric("⚡ P Panneau (FMU)", f"{fmu['Ppanneau']:.0f} W",
          delta=f"{delta('Ppanneau'):+.0f}" if prev is not None else None)
c4.metric("🔋 P Onduleur", f"{fmu['P_ondu']:.0f} W",
          delta=f"{delta('P_ondu'):+.0f}" if prev is not None else None)
c5.metric("📐 PVLib DC", f"{pvlib_p:.0f} W",
          delta=f"{fmu['Ppanneau'] - pvlib_p:+.0f} vs FMU")
c6.metric("🏆 η Onduleur", f"{fmu['eta']:.1f} %",
          delta=f"{delta('eta'):+.2f}" if prev is not None else None)

st.divider()

# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📈 Temps Réel", "🔋 Onduleur", "📊 FMU vs PVLib", "📋 Tableau"
])

# ── TAB 1: REAL-TIME IRRADIANCE + POWER ──
with tab1:
    fig = make_subplots(
        rows=2, cols=2, shared_xaxes=False,
        subplot_titles=(
            "Irradiance GHI [W/m²] — Temps Réel",
            "Température Cellule [°C] — Temps Réel",
            "P Panneau FMU [W] — Temps Réel",
            "P Onduleur [W] — Temps Réel",
        ),
        vertical_spacing=0.14, horizontal_spacing=0.08,
    )

    T = hist["time"]

    fig.add_trace(go.Scatter(x=T, y=hist["G"], name="GHI", mode="lines",
        line=dict(color="#f59e0b", width=2),
        fill="tozeroy", fillcolor="rgba(245,158,11,0.15)"), row=1, col=1)

    fig.add_trace(go.Scatter(x=T, y=hist["Tcell"], name="T_cell", mode="lines",
        line=dict(color="#ef4444", width=2),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.1)"), row=1, col=2)

    fig.add_trace(go.Scatter(x=T, y=hist["Ppanneau"], name="P_panneau", mode="lines",
        line=dict(color="#3b82f6", width=2.5),
        fill="tozeroy", fillcolor="rgba(59,130,246,0.15)"), row=2, col=1)

    fig.add_trace(go.Scatter(x=T, y=hist["P_ondu"], name="P_onduleur", mode="lines",
        line=dict(color="#22c55e", width=2.5),
        fill="tozeroy", fillcolor="rgba(34,197,94,0.15)"), row=2, col=2)

    # Mark latest point
    for row, col, key, color in [(1,1,"G","#f59e0b"),(1,2,"Tcell","#ef4444"),(2,1,"Ppanneau","#3b82f6"),(2,2,"P_ondu","#22c55e")]:
        if not hist.empty:
            fig.add_trace(go.Scatter(
                x=[hist["time"].iloc[-1]], y=[hist[key].iloc[-1]],
                mode="markers", marker=dict(color=color, size=10, symbol="circle"),
                showlegend=False, name=""), row=row, col=col)

    fig.update_layout(
        height=450, template="plotly_dark",
        paper_bgcolor="#0f172a", plot_bgcolor="#1e293b",
        showlegend=False,
        margin=dict(l=50, r=20, t=40, b=30),
    )
    fig.update_xaxes(gridcolor="#334155", showgrid=True)
    fig.update_yaxes(gridcolor="#334155", showgrid=True)
    st.plotly_chart(fig, use_container_width=True)

# ── TAB 2: INVERTER OUTPUTS ──
with tab2:
    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("#### 🔋 Puissances P / Q / S")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=hist["time"], y=hist["P_ondu"]/1000,
            name="P active [kW]", line=dict(color="#22c55e", width=2)))
        fig2.add_trace(go.Scatter(x=hist["time"], y=hist["Q_ondu"]/1000,
            name="Q réactive [kVAR]", line=dict(color="#f59e0b", width=1.5)))
        fig2.add_trace(go.Scatter(x=hist["time"], y=hist["S_ondu"]/1000,
            name="S apparente [kVA]", line=dict(color="#3b82f6", width=1.5, dash="dash")))
        fig2.update_layout(height=260, template="plotly_dark",
            paper_bgcolor="#0f172a", plot_bgcolor="#1e293b",
            yaxis_title="kW / kVAR / kVA",
            margin=dict(l=50, r=10, t=20, b=30))
        fig2.update_xaxes(gridcolor="#334155")
        fig2.update_yaxes(gridcolor="#334155")
        st.plotly_chart(fig2, use_container_width=True)

    with col_r:
        st.markdown("#### 📉 THD tension & courant")
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=hist["time"], y=hist["THD_V"],
            name="THD_V [%]", line=dict(color="#ef4444", width=2),
            fill="tozeroy", fillcolor="rgba(239,68,68,0.1)"))
        fig3.add_trace(go.Scatter(x=hist["time"], y=hist["THD_i"],
            name="THD_i [%]", line=dict(color="#f97316", width=1.5, dash="dot")))
        fig3.add_hline(y=5, line_dash="dash", line_color="#64748b",
            annotation_text="Limite IEC 5%", annotation_position="top right")
        fig3.update_layout(height=260, template="plotly_dark",
            paper_bgcolor="#0f172a", plot_bgcolor="#1e293b",
            yaxis_title="THD [%]",
            margin=dict(l=50, r=10, t=20, b=30))
        fig3.update_xaxes(gridcolor="#334155")
        fig3.update_yaxes(gridcolor="#334155")
        st.plotly_chart(fig3, use_container_width=True)

    # Rendement
    st.markdown("#### 🏆 Rendement onduleur [%]")
    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(x=hist["time"], y=hist["eta"],
        name="η [%]", line=dict(color="#a855f7", width=2),
        fill="tozeroy", fillcolor="rgba(168,85,247,0.15)"))
    fig4.add_hline(y=97, line_dash="dash", line_color="#22c55e",
        annotation_text="Cible 97%")
    fig4.update_layout(height=200, template="plotly_dark",
        paper_bgcolor="#0f172a", plot_bgcolor="#1e293b",
        yaxis=dict(range=[0, 102]),
        margin=dict(l=50, r=10, t=10, b=30))
    fig4.update_xaxes(gridcolor="#334155")
    fig4.update_yaxes(gridcolor="#334155")
    st.plotly_chart(fig4, use_container_width=True)

# ── TAB 3: FMU vs PVLIB ──
with tab3:
    st.markdown("#### 📊 Comparaison FMU Simulink vs PVLib (temps réel)")
    fig5 = go.Figure()
    fig5.add_trace(go.Scatter(x=hist["time"], y=hist["Ppanneau"],
        name="FMU Simulink", line=dict(color="#f59e0b", width=2.5)))
    fig5.add_trace(go.Scatter(x=hist["time"], y=hist["P_pvlib"],
        name="PVLib (SDM-CEC)", line=dict(color="#22c55e", width=2, dash="dash")))
    fig5.update_layout(height=300, template="plotly_dark",
        paper_bgcolor="#0f172a", plot_bgcolor="#1e293b",
        yaxis_title="Puissance [W]",
        margin=dict(l=50, r=10, t=20, b=30))
    fig5.update_xaxes(gridcolor="#334155")
    fig5.update_yaxes(gridcolor="#334155")
    st.plotly_chart(fig5, use_container_width=True)

    if len(hist) > 5:
        c1, c2, c3 = st.columns(3)
        valid = hist[hist["P_pvlib"] > 10]
        if not valid.empty:
            corr = valid["Ppanneau"].corr(valid["P_pvlib"])
            rmse = np.sqrt(((valid["Ppanneau"] - valid["P_pvlib"])**2).mean())
            ratio_mean = (valid["Ppanneau"] / valid["P_pvlib"].replace(0, np.nan)).mean()
            c1.metric("📊 Corrélation R", f"{corr:.4f}")
            c2.metric("📉 RMSE", f"{rmse:.1f} W")
            c3.metric("📈 Ratio FMU/PVLib", f"{ratio_mean:.3f}")

# ── TAB 4: TABLE ──
with tab4:
    st.markdown("#### 📋 Historique des mesures simulées")
    display = hist.copy()
    display["time"] = display["time"].dt.strftime("%H:%M:%S")
    display = display.round(3)
    display.columns = [
        "Heure", "G [W/m²]", "Tamb [°C]", "Tcell [°C]", "Vent [m/s]",
        "P_pan [W]", "Vmpp [V]", "Impp [A]", "P_boost [W]",
        "P_ondu [W]", "S [VA]", "Q [VAR]", "THD_V [%]", "THD_i [%]", "η [%]",
        "P_pvlib [W]",
    ]
    st.dataframe(display[::-1], use_container_width=True, height=400)

    col_dl1, col_dl2 = st.columns(2)
    csv = display.to_csv(index=False).encode()
    col_dl1.download_button("⬇️ Télécharger CSV", csv, "pv_data.csv", "text/csv")

# ─────────────────────────────────────────────
# AUTO REFRESH
# ─────────────────────────────────────────────
st.divider()
st.caption(f"🔄 Prochain rafraîchissement dans {refresh_sec}s | Tick #{tick} | Points: {len(st.session_state.history)}")

time.sleep(refresh_sec)
st.rerun()
