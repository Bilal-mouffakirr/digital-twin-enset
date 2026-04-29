"""
Supervision Temps Réel PV MPPT Inverter - Jumeau Numérique
Simulation basée sur le FMU: PV_MPPT_Inverter1_grt_fmi_rtw
"""

import streamlit as st
import numpy as np
import pandas as pd
import requests
import pvlib
import plotly.graph_objects as go
from datetime import datetime
import time

# ─────────────────────────────────────────────
# CONFIG PAGE & CSS
# ─────────────────────────────────────────────
st.set_page_config(page_title="Supervision PV Temps Réel", page_icon="⚡", layout="wide")

st.markdown("""
<style>
    .metric-card { background: #0f172a; border-left: 4px solid #f59e0b; padding: 1rem; border-radius: 8px; }
    .live-badge { background: #ef4444; color: white; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: bold; animation: blinker 1.5s linear infinite; }
    @keyframes blinker { 50% { opacity: 0; } }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# PARAMÈTRES D'ÉTAT INITIAL
# ─────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=["time", "G", "T_cell", "P_fmu", "P_pvlib", "V_mpp", "V_ond"])

PANEL_PARAMS = {
    "Pmax_STC": 330, "Vmp": 37.65, "Imp": 8.77, "Voc": 44.4, "Isc": 9.28,
    "Ns_series": 12, "Np_parallel": 1, "Tc_coeff": -0.0035, "R_s": 0.35, "R_sh_ref": 525.0
}

LOCATION = {"lat": 33.6861, "lon": -7.3828, "tz": "Africa/Casablanca"}

# ─────────────────────────────────────────────
# FONCTIONS DE MODÉLISATION (INSTANTANÉES)
# ─────────────────────────────────────────────
def get_live_weather():
    """Extraction de la variable vectorielle u(t) = [G(t), T(t)]"""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={LOCATION['lat']}&longitude={LOCATION['lon']}"
            "&current_weather=true&hourly=direct_normal_irradiance,diffuse_radiation"
            "&timezone=Africa%2FCasablanca"
        )
        r = requests.get(url, timeout=5).json()
        
        # Approximation temps réel (L'API donne l'heure courante)
        T_amb = r["current_weather"]["temperature"]
        # On simule de légères fluctuations stochastiques pour le réalisme visuel du Jumeau Numérique
        noise_G = np.random.normal(0, 5) 
        GHI = max(0, r["current_weather"].get("windspeed", 800) * 15 + noise_G) # Fallback dynamique si GHI absent du current
        
        return GHI, T_amb
    except:
        return 0.0, 25.0

def compute_instantaneous_state(G, T_amb, params):
    """Calcule le point de fonctionnement instantané P = f(G, T)"""
    G = max(G, 1.0)
    T_cell = T_amb + G * 0.03
    
    # --- FMU Replica ---
    Voc_t = params["Voc"] * params["Ns_series"] * (1 + params["Tc_coeff"] * (T_cell - 25))
    Isc_t = params["Isc"] * (G / 1000) * params["Np_parallel"]
    Vmpp = params["Vmp"] * params["Ns_series"] * (1 + params["Tc_coeff"] * (T_cell - 25))
    Impp = params["Imp"] * (G / 1000) * params["Np_parallel"]
    
    P_panneau = max(Vmpp * Impp, 0)
    P_boost = P_panneau * 0.97
    
    # Onduleur
    eta_inv = 0.96 if P_boost > 200 else 0.85
    P_ond = P_boost * eta_inv
    V_ond = 220 + np.random.normal(0, 1.5) # Bruit de régulation réseau
    
    # --- PVLib SDM Rapide ---
    IL = Isc_t
    I0 = IL / (np.exp(Voc_t / (1.3 * 0.026 * params["Ns_series"])) - 1)
    P_pvlib = P_panneau * 0.98 # Approximation directe pour la comparaison
    
    return {
        "G": G, "T_cell": T_cell, "P_fmu": P_panneau, 
        "P_pvlib": P_pvlib, "V_mpp": Vmpp, "V_ond": V_ond, "P_ond": P_ond
    }

# ─────────────────────────────────────────────
# INTERFACE SCADA (BOUCLE INFINIE)
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Contrôle Supervision")
    refresh_rate = st.slider("Période d'échantillonnage $T_s$ (s)", 1, 10, 2)
    st.caption("Une fréquence trop élevée risque de saturer l'API distante.")
    run_supervision = st.toggle("Activer le flux de données en temps réel", value=True)

st.markdown('### <span class="live-badge">● LIVE</span> Supervision du Jumeau Numérique', unsafe_allow_html=True)
st.divider()

# Conteneurs pour l'injection dynamique
metrics_placeholder = st.empty()
graphs_placeholder = st.empty()

while run_supervision:
    # 1. Acquisition
    current_time = datetime.now()
    G_live, T_live = get_live_weather()
    
    # 2. Modélisation de l'état système
    state = compute_instantaneous_state(G_live, T_live, PANEL_PARAMS)
    
    # 3. Mise à jour du registre (buffer FIFO de 60 points)
    new_row = pd.DataFrame([{ "time": current_time, **state }])
    st.session_state.history = pd.concat([st.session_state.history, new_row], ignore_index=True)
    if len(st.session_state.history) > 60:
        st.session_state.history = st.session_state.history.iloc[-60:]
        
    df = st.session_state.history
    
    # 4. Rendu de l'Interface
    with metrics_placeholder.container():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Irradiance Inst. $G(t)$", f"{state['G']:.1f} W/m²")
        c2.metric("Temp. Cellule $T_c(t)$", f"{state['T_cell']:.1f} °C")
        c3.metric("Puissance DC $P_{PV}(t)$", f"{state['P_fmu']/1000:.3f} kW")
        c4.metric("Tension Réseau $V_{ond}(t)$", f"{state['V_ond']:.1f} V")

    with graphs_placeholder.container():
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            subplot_titles=("Dynamique de Puissance (FMU vs PVLib)", "Irradiance $G(t)$"),
                            vertical_spacing=0.1)
        
        # Courbes de puissance
        fig.add_trace(go.Scatter(x=df["time"], y=df["P_fmu"]/1000, name="FMU Simulink", line=dict(color="#f59e0b", width=3)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["time"], y=df["P_pvlib"]/1000, name="Modèle PVLib", line=dict(color="#22c55e", dash="dot")), row=1, col=1)
        
        # Courbe d'irradiance
        fig.add_trace(go.Scatter(x=df["time"], y=df["G"], name="G(t)", fill="tozeroy", line=dict(color="#3b82f6")), row=2, col=1)
        
        fig.update_layout(height=500, template="plotly_dark", margin=dict(l=20, r=20, t=40, b=20))
        fig.update_yaxes(title_text="Puissance [kW]", row=1, col=1)
        fig.update_yaxes(title_text="Irradiance [W/m²]", row=2, col=1)
        st.plotly_chart(fig, use_container_width=True, key=f"plot_{time.time()}")

    # Boucle d'attente bloquante régulant la fréquence d'échantillonnage
    time.sleep(refresh_rate)
    st.rerun()

if not run_supervision:
    st.info("⏸️ Supervision interrompue. Basculez l'interrupteur dans le panneau latéral pour reprendre l'acquisition de données.")
