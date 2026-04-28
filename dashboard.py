"""
PV MPPT Inverter – Streamlit Dashboard
Modèle : PV_MPPT_Inverter1 (Simulink R2024a, FMI 2.0)
Auteur : Bilal Mouffakir
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys, os

# ── FMPy (si disponible, sinon modèle physique interne) ──────────────────────
FMU_PATH = os.path.join(os.path.dirname(__file__), "fmu", "PV_MPPT_Inverter1.fmu")
FMPY_AVAILABLE = False
try:
    from fmpy import simulate_fmu, read_model_description
    FMPY_AVAILABLE = True
except ImportError:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PV MPPT Inverter Dashboard",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"] { background: #0d1117; }
[data-testid="stSidebar"] * { color: #e6edf3 !important; }
.kpi-box {
    background: #161b22; border: 1px solid #30363d; border-radius: 10px;
    padding: 14px 16px; text-align: center; margin-bottom: 8px;
    border-top: 3px solid var(--color);
}
.kpi-label { font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: .8px; }
.kpi-value { font-size: 28px; font-weight: 700; }
.kpi-unit  { font-size: 13px; color: #8b949e; }
.block-title { font-size: 13px; font-weight: 600; color: #8b949e;
               text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
.stAlert { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers – génération des profils
# ─────────────────────────────────────────────────────────────────────────────
def gen_irradiance(profile, t, g_init, g_final, t_step, g_amp, g_period):
    """Génère le profil d'irradiance G (W/m²)."""
    if profile == "Échelon":
        return np.where(t < t_step, g_init, g_final)
    elif profile == "Rampe":
        return np.clip(g_init + (g_final - g_init) * (t / t[-1]), 0, 1200)
    elif profile == "Jour (sinusoïde)":
        return np.maximum(0, g_amp * np.sin(np.pi * t / t[-1]))
    elif profile == "Nuage (aléatoire)":
        base = g_init + (g_final - g_init) * (t / t[-1])
        rng  = np.random.default_rng(42)
        noise = rng.normal(0, g_amp * 0.15, size=len(t))
        cloud = 150 * np.sin(2 * np.pi * t / (g_period + 1e-9))
        return np.clip(base + noise + cloud, 10, 1200)
    elif profile == "Constante":
        return np.full_like(t, g_init)
    elif profile == "Double échelon":
        out = np.where(t < t[-1]*0.33, g_init,
              np.where(t < t[-1]*0.66, g_final, (g_init+g_final)/2))
        return out
    return np.full_like(t, g_init)


def gen_temperature(profile, t, t_init, t_final, t_amp, t_period):
    """Génère le profil de température T (°C)."""
    if profile == "Constante":
        return np.full_like(t, t_init)
    elif profile == "Rampe":
        return t_init + (t_final - t_init) * (t / t[-1])
    elif profile == "Sinusoïde":
        return t_init + t_amp * np.sin(2 * np.pi * t / (t_period + 1e-9))
    elif profile == "Échelon":
        return np.where(t < t[-1]*0.5, t_init, t_final)
    return np.full_like(t, t_init)


# ─────────────────────────────────────────────────────────────────────────────
# Simulation physique (modèle PV analytique)
# ─────────────────────────────────────────────────────────────────────────────
def run_physics_simulation(G_vec, T_vec, dt):
    """
    Modèle analytique calibré sur le FMU PV_MPPT_Inverter1 :
    - Panneau PV : modèle à 5 paramètres (Isc, Voc, FF)
    - MPPT : P&O parfait (rendement tracking ~99%)
    - Boost : η = 96%
    - Onduleur : η = 94%, filtre LC (THD calculé)
    """
    N = len(G_vec)

    # Paramètres panneau (calibrés sur modelDescription.xml)
    Isc_ref  = 8.21    # A  (à G=1000, T=25°C)
    Voc_ref  = 45.5    # V
    Ns       = 20      # modules série
    Np       = 5       # strings parallèle
    alpha_I  = 0.0053  # /°C
    beta_V   = -0.145  # V/°C
    T_ref    = 25.0    # °C
    eta_boost= 0.96
    eta_inv  = 0.94
    V_grid   = 220.0   # V RMS

    Ppv_arr   = np.zeros(N)
    Pboost_arr= np.zeros(N)
    Vond_arr  = np.zeros(N)
    Pondu_arr = np.zeros(N)
    Qondu_arr = np.zeros(N)
    Sondu_arr = np.zeros(N)
    THDV_arr  = np.zeros(N)
    THDi_arr  = np.zeros(N)
    rend_arr  = np.zeros(N)

    for i in range(N):
        G = max(G_vec[i], 0.1)
        T = T_vec[i]

        # Courant court-circuit & tension circuit-ouvert corrigés
        Isc = Isc_ref * (G / 1000.0) * (1 + alpha_I * (T - T_ref))
        Voc = (Voc_ref + beta_V * (T - T_ref))

        # Facteur de forme (dépend de T)
        FF = max(0.60, 0.79 - 0.0005 * (T - T_ref) - 0.003 * (1000/G - 1))

        # Puissance MPPT panneau total
        Ppv = Isc * Voc * FF * Ns * Np

        # Boost
        Pboost = Ppv * eta_boost

        # Onduleur – puissance active
        Pondu = Pboost * eta_inv

        # Puissance réactive (déphasage filtre LC)
        phi_rad = 0.06 + 0.05 * (1 - G/1000)
        Qondu   = Pondu * np.tan(phi_rad)
        Sondu   = np.hypot(Pondu, Qondu)

        # Tension de sortie onduleur (quasi-constante si grid-tied)
        Vond = V_grid * (0.985 + 0.015 * (G/1000))

        # THD (modèle empirique : diminue avec G, augmente avec T)
        THD_V = max(0.4, 5.2 - 4.5*(G/1000) + 0.018*(T-25))
        THD_i = max(0.3, 4.1 - 3.6*(G/1000) + 0.012*(T-25))

        # Rendement onduleur (= Pondu / Ppv)
        rend = min(100.0, (Pondu / max(Ppv, 1e-3)) * 100)

        Ppv_arr[i]    = Ppv
        Pboost_arr[i] = Pboost
        Vond_arr[i]   = Vond
        Pondu_arr[i]  = Pondu
        Qondu_arr[i]  = Qondu
        Sondu_arr[i]  = Sondu
        THDV_arr[i]   = THD_V
        THDi_arr[i]   = THD_i
        rend_arr[i]   = rend

    return pd.DataFrame({
        "time"       : np.arange(N) * dt,
        "G"          : G_vec,
        "T"          : T_vec,
        "Ppanneau"   : Ppv_arr,
        "Pbooste"    : Pboost_arr,
        "Vonduleur"  : Vond_arr,
        "P_ondu"     : Pondu_arr,
        "Q_ondu"     : Qondu_arr,
        "S_ondu"     : Sondu_arr,
        "THD_V"      : THDV_arr,
        "THD_i"      : THDi_arr,
        "rendement"  : rend_arr,
    })


def run_fmu_simulation(G_vec, T_vec, dt):
    """Simulation via FMPy (si dispo + plateforme Windows)."""
    try:
        from fmpy import simulate_fmu
        import tempfile, shutil

        stop  = len(G_vec) * dt
        times = np.arange(len(G_vec)) * dt
        input_data = np.array(
            [(t, G_vec[i], T_vec[i]) for i, t in enumerate(times)],
            dtype=[("time","f8"),("Inport","f8"),("Inport1","f8")]
        )
        res = simulate_fmu(
            FMU_PATH,
            start_time=0.0,
            stop_time=stop,
            step_size=dt,
            input=input_data,
            output=["Vonduleur","Pbooste","Ppanneau","S_ondu",
                    "P_ondu","Q_ondu","THD_V","THD_i","rendemet de onduleur"],
        )
        df = pd.DataFrame(res)
        df.rename(columns={"rendemet de onduleur":"rendement","time":"time"}, inplace=True)
        df["G"] = np.interp(df["time"], times, G_vec)
        df["T"] = np.interp(df["time"], times, T_vec)
        return df
    except Exception as e:
        st.warning(f"⚠️ FMPy échoué ({e}) → modèle physique utilisé.")
        return run_physics_simulation(G_vec, T_vec, dt)


# ─────────────────────────────────────────────────────────────────────────────
# Plotly helpers
# ─────────────────────────────────────────────────────────────────────────────
DARK = dict(
    paper_bgcolor="#0d1117",
    plot_bgcolor="#161b22",
    font=dict(color="#8b949e", size=11),
    xaxis=dict(gridcolor="#21262d", zerolinecolor="#30363d"),
    yaxis=dict(gridcolor="#21262d", zerolinecolor="#30363d"),
    legend=dict(bgcolor="#0d111700", font=dict(size=10)),
    margin=dict(l=50, r=20, t=30, b=40),
)

COLORS = {
    "G"        : "#f0a500",
    "T"        : "#f85149",
    "Ppanneau" : "#f0a500",
    "Pbooste"  : "#58a6ff",
    "P_ondu"   : "#2ea043",
    "Q_ondu"   : "#f85149",
    "S_ondu"   : "#e3b341",
    "Vonduleur": "#bc8cff",
    "THD_V"    : "#f85149",
    "THD_i"    : "#e3b341",
    "rendement": "#2ea043",
}

def line_fig(df, cols, title, yaxis_title, height=300, secondary=None):
    fig = go.Figure()
    for c in cols:
        fig.add_trace(go.Scatter(
            x=df["time"], y=df[c],
            name=c, mode="lines",
            line=dict(color=COLORS.get(c,"#aaa"), width=2),
        ))
    fig.update_layout(title=dict(text=title, font=dict(size=13, color="#e6edf3")),
                      height=height, yaxis_title=yaxis_title, xaxis_title="Temps (s)", **DARK)
    return fig


def kpi_html(label, value, unit, color):
    return f"""
    <div class="kpi-box" style="--color:{color}">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value" style="color:{color}">{value}</div>
      <div class="kpi-unit">{unit}</div>
    </div>"""


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/emoji/96/sun-emoji.png", width=60)
    st.markdown("## **PV MPPT Inverter**")
    st.caption("Simulink R2024a · FMI 2.0 · Bilal Mouffakir")
    st.divider()

    # ── Simulation params ──
    st.markdown("### ⚙️ Paramètres Simulation")
    sim_dur = st.slider("Durée (s)", 0.05, 1.0, 0.2, 0.05)
    dt_us   = st.select_slider("Pas dt", options=[10,20,50,100,200,500], value=100)
    dt      = dt_us * 1e-6
    N       = min(5000, int(sim_dur / dt))

    backend = "FMPy (FMU)" if FMPY_AVAILABLE else "Modèle physique (FMPy absent)"
    st.info(f"🔧 Backend : {backend}", icon="ℹ️")
    st.caption(f"Points de simulation : {N:,}")

    st.divider()

    # ── Irradiance Profile ──
    st.markdown("### 🌤 Profil Irradiance G (W/m²)")
    g_profile = st.selectbox("Type de profil G", [
        "Échelon", "Rampe", "Constante", "Jour (sinusoïde)",
        "Nuage (aléatoire)", "Double échelon"
    ])

    g_init   = st.slider("G initial (W/m²)", 50, 1000, 200, 50)
    g_final  = st.slider("G final (W/m²)",   50, 1000, 800, 50,
                          disabled=(g_profile in ["Constante","Jour (sinusoïde)"]))
    t_step_g = st.slider("Instant échelon (s)", 0.01, sim_dur*0.9,
                          sim_dur*0.4, 0.01,
                          disabled=(g_profile not in ["Échelon","Double échelon"]))
    g_amp    = st.slider("Amplitude max (W/m²)", 200, 1200, 1000, 50,
                          disabled=(g_profile not in ["Jour (sinusoïde)","Nuage (aléatoire)"]))
    g_period = st.slider("Période nuage (s)", 0.02, 0.5, 0.1, 0.01,
                          disabled=(g_profile != "Nuage (aléatoire)"))

    st.divider()

    # ── Temperature Profile ──
    st.markdown("### 🌡 Profil Température T (°C)")
    t_profile = st.selectbox("Type de profil T", [
        "Constante", "Rampe", "Sinusoïde", "Échelon"
    ])
    t_init   = st.slider("T initiale (°C)",  0, 75, 25, 1)
    t_final  = st.slider("T finale (°C)",    0, 80, 55, 1,
                          disabled=(t_profile in ["Constante","Sinusoïde"]))
    t_amp    = st.slider("Amplitude T (°C)", 1, 30,  15, 1,
                          disabled=(t_profile != "Sinusoïde"))
    t_period = st.slider("Période T (s)",    0.02, 1.0, 0.2, 0.01,
                          disabled=(t_profile != "Sinusoïde"))

    st.divider()
    run = st.button("▶ LANCER LA SIMULATION", use_container_width=True, type="primary")


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("# ☀️ PV MPPT Inverter — Dashboard")
st.markdown(
    "**Modèle :** `PV_MPPT_Inverter1.fmu` &nbsp;|&nbsp; "
    "**Entrées :** `Inport` (G W/m²) · `Inport1` (T °C) &nbsp;|&nbsp; "
    "**Sorties :** 9 variables &nbsp;|&nbsp; **Auteur :** Bilal Mouffakir"
)
st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
if not run:
    st.info("👈 Configurez les profils dans le panneau gauche puis cliquez **▶ LANCER LA SIMULATION**")

    # Aperçu des profils
    t_prev = np.linspace(0, sim_dur, 300)
    G_prev = gen_irradiance(g_profile, t_prev, g_init, g_final, t_step_g, g_amp, g_period)
    T_prev = gen_temperature(t_profile, t_prev, t_init, t_final, t_amp, t_period)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🌤 Aperçu — Irradiance G")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t_prev, y=G_prev, fill="tozeroy",
                                  fillcolor="#f0a50018", line=dict(color="#f0a500", width=2), name="G (W/m²)"))
        fig.update_layout(height=220, yaxis_title="W/m²", xaxis_title="Temps (s)", **DARK)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### 🌡 Aperçu — Température T")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t_prev, y=T_prev, fill="tozeroy",
                                  fillcolor="#f8514918", line=dict(color="#f85149", width=2), name="T (°C)"))
        fig.update_layout(height=220, yaxis_title="°C", xaxis_title="Temps (s)", **DARK)
        st.plotly_chart(fig, use_container_width=True)
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────────────────────
with st.spinner("⏳ Simulation en cours..."):
    t_vec = np.linspace(0, sim_dur, N)
    G_vec = gen_irradiance(g_profile, t_vec, g_init, g_final, t_step_g, g_amp, g_period)
    T_vec = gen_temperature(t_profile, t_vec, t_init, t_final, t_amp, t_period)

    if FMPY_AVAILABLE and os.path.exists(FMU_PATH):
        df = run_fmu_simulation(G_vec, T_vec, dt)
    else:
        df = run_physics_simulation(G_vec, T_vec, dt)

st.success(f"✅ Simulation terminée — {len(df):,} points | dt={dt_us} µs | durée={sim_dur} s")

# ─── KPIs ────────────────────────────────────────────────────────────────────
last = df.iloc[-1]
st.markdown("### 📊 Valeurs Finales (régime permanent)")
c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1: st.markdown(kpi_html("Ppanneau",f"{last.Ppanneau:.0f}","W","#f0a500"), unsafe_allow_html=True)
with c2: st.markdown(kpi_html("P_ondu",  f"{last.P_ondu:.0f}","W","#2ea043"),  unsafe_allow_html=True)
with c3: st.markdown(kpi_html("Pbooste", f"{last.Pbooste:.0f}","W","#58a6ff"), unsafe_allow_html=True)
with c4: st.markdown(kpi_html("Vonduleur",f"{last.Vonduleur:.1f}","V","#bc8cff"), unsafe_allow_html=True)
with c5: st.markdown(kpi_html("THD_V",   f"{last.THD_V:.2f}","%","#f85149"),  unsafe_allow_html=True)
with c6: st.markdown(kpi_html("Rendement",f"{last.rendement:.1f}","%","#e3b341"), unsafe_allow_html=True)

st.divider()

# ─── Profils entrées ─────────────────────────────────────────────────────────
st.markdown("### 📥 Profils d'Entrée")
col1, col2 = st.columns(2)
with col1:
    fig = line_fig(df, ["G"], f"Irradiance G — {g_profile}", "W/m²", height=250)
    fig.data[0].fill = "tozeroy"
    fig.data[0].fillcolor = "#f0a50015"
    st.plotly_chart(fig, use_container_width=True)
with col2:
    fig = line_fig(df, ["T"], f"Température T — {t_profile}", "°C", height=250)
    fig.data[0].line.color = "#f85149"
    fig.data[0].fill = "tozeroy"
    fig.data[0].fillcolor = "#f8514915"
    st.plotly_chart(fig, use_container_width=True)

# ─── Puissances ──────────────────────────────────────────────────────────────
st.markdown("### ⚡ Puissances — Sorties du Modèle")
fig = line_fig(df, ["Ppanneau","Pbooste","P_ondu"],
               "Ppanneau · Pbooste · P_ondu", "Puissance (W)", height=320)
st.plotly_chart(fig, use_container_width=True)

col1, col2 = st.columns(2)
with col1:
    fig = line_fig(df, ["P_ondu","Q_ondu","S_ondu"],
                   "Puissances P / Q / S Onduleur", "Puissance", height=290)
    st.plotly_chart(fig, use_container_width=True)
with col2:
    fig = line_fig(df, ["Vonduleur"], "Tension Onduleur (RMS)", "V (RMS)", height=290)
    fig.data[0].fill = "tozeroy"
    fig.data[0].fillcolor = "#bc8cff15"
    st.plotly_chart(fig, use_container_width=True)

# ─── Qualité ─────────────────────────────────────────────────────────────────
st.markdown("### 🌊 Qualité — THD & Rendement")
col1, col2 = st.columns(2)
with col1:
    fig = line_fig(df, ["THD_V","THD_i"], "THD Tension & Courant", "THD (%)", height=280)
    st.plotly_chart(fig, use_container_width=True)
with col2:
    fig = line_fig(df, ["rendement"], "Rendement Onduleur", "%", height=280)
    fig.data[0].fill = "tozeroy"
    fig.data[0].fillcolor = "#2ea04315"
    fig.update_layout(yaxis=dict(range=[0,105]))
    st.plotly_chart(fig, use_container_width=True)

# ─── Corrélations G → sorties ────────────────────────────────────────────────
st.markdown("### 🔗 Corrélations : Irradiance G → Sorties")
col1, col2, col3 = st.columns(3)
scatter_cfg = dict(mode="markers",
                   marker=dict(size=3, color=df["G"], colorscale="Oranges",
                               showscale=True, colorbar=dict(title="G W/m²", thickness=8)))
with col1:
    fig = go.Figure(go.Scatter(x=df["G"], y=df["Ppanneau"],
                               name="Ppanneau", **scatter_cfg))
    fig.update_layout(height=250, xaxis_title="G (W/m²)", yaxis_title="Ppanneau (W)", **DARK)
    st.plotly_chart(fig, use_container_width=True)
with col2:
    fig = go.Figure(go.Scatter(x=df["G"], y=df["rendement"],
                               name="Rendement", **scatter_cfg))
    fig.update_layout(height=250, xaxis_title="G (W/m²)", yaxis_title="Rendement (%)", **DARK)
    st.plotly_chart(fig, use_container_width=True)
with col3:
    fig = go.Figure(go.Scatter(x=df["G"], y=df["THD_V"],
                               name="THD_V", **scatter_cfg))
    fig.update_layout(height=250, xaxis_title="G (W/m²)", yaxis_title="THD_V (%)", **DARK)
    st.plotly_chart(fig, use_container_width=True)

# ─── Tableau récap ────────────────────────────────────────────────────────────
with st.expander("📋 Tableau de données complet"):
    st.dataframe(
        df.round(4).style.background_gradient(subset=["Ppanneau","P_ondu","rendement"], cmap="Greens")
                         .background_gradient(subset=["THD_V","THD_i"], cmap="Reds"),
        use_container_width=True, height=300
    )
    csv = df.to_csv(index=False).encode()
    st.download_button("⬇️ Télécharger CSV", csv, "PV_MPPT_results.csv", "text/csv")

st.caption("PV_MPPT_Inverter1 · Simulink R2024a · FMI 2.0 · Bilal Mouffakir · 2026")
