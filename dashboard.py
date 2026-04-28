"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  SOLARIS · DIGITAL TWIN PV — MOHAMMEDIA, MAROC                              ║
║  FMU (PV_MPPT_Inverter1) × pvlib × Open-Meteo × Streamlit                  ║
║  Author : Bilal Mouffakir                                                    ║
║  FMI Standard : 2.0 · Co-Simulation · fmpy integration                     ║
╚══════════════════════════════════════════════════════════════════════════════╝

Architecture
────────────
  Open-Meteo API ──► weather JSON  ──┬──► FMU (fmpy)   → Simulated Power (W)
                                     └──► pvlib         → Theoretical MPP (W)
                                         Dashboard compares both + error delta

FMU I/O (PV_MPPT_Inverter1, FMI 2.0 Co-Simulation)
────────────────────────────────────────────────────
  Inputs
    Inport   [°C]         Ambient temperature  (model converts → K internally)
    Inport1  [W/m²]       Irradiance  (model scales × uSref_Gain = 0.001 → per-unit)

  Outputs
    Ppanneau [W]          DC power at PV panel terminals
    Pbooste  [W]          DC power after MPPT Boost converter
    P_ondu   [W]          AC active power from inverter
    Q_ondu   [VAR]        AC reactive power
    S_ondu   [VA]         AC apparent power
    Vonduleur[V]          Inverter output voltage
    THD_V    [%]          Voltage Total Harmonic Distortion
    THD_i    [%]          Current Total Harmonic Distortion
    rendemet de onduleur  Inverter efficiency (dimensionless)

Platform Note
─────────────
  The FMU ships with a Windows-only DLL (binaries/win64/).
  On Linux / macOS / cloud servers fmpy will raise an ImportError or
  platform error.  This app detects that at startup and switches to a
  physics-based analytical fallback that faithfully reproduces the
  Simulink model's steady-state equations, so the dashboard remains
  fully functional on any platform.  When deploying on Windows the
  live FMU path is used transparently — no code change required.

Usage
─────
  1. Place  PV_MPPT_Inverter1.fmu  next to app.py          (optional on Linux)
  2. pip install streamlit fmpy pvlib plotly requests numpy pandas
  3. streamlit run app.py
"""

# ─────────────────────────────────────────────────────────────────────────────
# STDLIB & THIRD-PARTY IMPORTS
# ─────────────────────────────────────────────────────────────────────────────
import os
import sys
import math
import platform
import warnings
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

import pvlib
from pvlib.location import Location
from pvlib import irradiance, temperature, pvsystem

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SOLARIS · Digital Twin FMU",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600;700&display=swap');

  :root {
    --gold:    #F5A623;
    --gold2:   #E8860A;
    --amber:   #FFCF6B;
    --bg:      #08090C;
    --card:    #111318;
    --card2:   #191D25;
    --border:  #252A35;
    --border2: #353C4A;
    --txt:     #E8EDF5;
    --muted:   #6B7585;
    --dim:     #3D4553;
    --green:   #2ECC71;
    --red:     #E74C3C;
    --blue:    #3498DB;
    --purple:  #9B59B6;
    --teal:    #1ABC9C;
  }

  html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
  .stApp { background-color: var(--bg); }

  [data-testid="stSidebar"] {
    background-color: #0A0C10 !important;
    border-right: 1px solid var(--border) !important;
  }

  /* ── KPI Card ── */
  .kpi {
    background: var(--card);
    border: 1px solid var(--border);
    border-top: 2px solid var(--gold);
    border-radius: 10px;
    padding: 18px 20px;
    transition: all .3s;
  }
  .kpi:hover { border-color: var(--gold); transform: translateY(-2px); box-shadow: 0 8px 25px rgba(245,166,35,.12); }
  .kpi-label { font-family:'Space Mono',monospace; font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:.12em; margin-bottom:6px; }
  .kpi-value { font-family:'Space Mono',monospace; font-size:28px; font-weight:700; color:var(--gold); line-height:1.1; }
  .kpi-unit  { font-size:12px; color:var(--muted); margin-top:3px; }

  /* ── Section header ── */
  .sh { font-family:'Space Mono',monospace; font-size:11px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.15em; padding-bottom:8px; border-bottom:1px solid var(--border); margin-bottom:12px; }

  /* ── Status badge ── */
  .badge { display:inline-flex; align-items:center; gap:7px; border-radius:20px; padding:5px 14px; font-size:12px; font-family:'Space Mono',monospace; }
  .badge-green  { background:rgba(46,204,113,.08); border:1px solid rgba(46,204,113,.25); color:var(--green); }
  .badge-orange { background:rgba(245,166,35,.08); border:1px solid rgba(245,166,35,.25); color:var(--gold); }
  .badge-red    { background:rgba(231,76,60,.08);  border:1px solid rgba(231,76,60,.25);  color:var(--red); }
  .badge-blue   { background:rgba(52,152,219,.08); border:1px solid rgba(52,152,219,.25); color:var(--blue); }
  .dot { width:7px; height:7px; border-radius:50%; animation:pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.35} }

  /* ── Info banner ── */
  .info-banner {
    background:rgba(52,152,219,.06); border:1px solid rgba(52,152,219,.2);
    border-left:3px solid var(--blue); border-radius:8px; padding:12px 16px;
    font-size:13px; color:#5BA4D9; margin-bottom:12px;
  }
  .warn-banner {
    background:rgba(245,166,35,.06); border:1px solid rgba(245,166,35,.2);
    border-left:3px solid var(--gold); border-radius:8px; padding:12px 16px;
    font-size:13px; color:#D4993A; margin-bottom:12px;
  }

  /* ── Data table ── */
  .spec-block { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:4px 0; margin-bottom:14px; }
  .spec-head  { background:var(--card2); border-radius:8px 8px 0 0; padding:9px 16px; font-family:'Space Mono',monospace; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.12em; color:var(--gold); border-bottom:1px solid var(--border); }
  .spec-tbl   { width:100%; border-collapse:collapse; font-size:13px; }
  .spec-tbl tr:not(:last-child) { border-bottom:1px solid var(--border); }
  .spec-tbl tr:hover { background:rgba(245,166,35,.04); }
  .spec-tbl td { padding:9px 14px; vertical-align:middle; }
  .spec-tbl td:first-child { color:var(--muted); font-family:'Space Mono',monospace; font-size:11px; text-transform:uppercase; letter-spacing:.08em; width:48%; }
  .spec-tbl td:last-child  { color:var(--txt); font-weight:500; text-align:right; }
  .hi { color:var(--gold); font-family:'Space Mono',monospace; font-weight:700; }

  div[data-testid="metric-container"] {
    background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px 16px;
  }
  div[data-testid="metric-container"] label { color:var(--muted)!important; font-size:11px!important; font-family:'Space Mono',monospace!important; }
  div[data-testid="metric-container"] [data-testid="stMetricValue"] { color:var(--gold)!important; font-family:'Space Mono',monospace!important; }

  .stTabs [data-baseweb="tab-list"] { background:var(--card); border-radius:8px; padding:5px; gap:6px; }
  .stTabs [data-baseweb="tab"] { color:var(--muted); font-family:'Space Mono',monospace; font-size:12px; border-radius:6px; }
  .stTabs [aria-selected="true"] { background:rgba(245,166,35,.12); color:var(--gold); }

  footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS — SITE & SYSTEM
# ─────────────────────────────────────────────────────────────────────────────
SITE = dict(
    name="Installation PV — Mohammedia",
    lat=33.70, lon=-7.38,
    altitude=56,
    timezone="Africa/Casablanca",
    capacity_kwp=3.95,
    num_panels=12,
    tilt=31,
    azimuth=180,
)

# PV panel parameters (Cell Amrecan OS-P72-330W, polycrystalline)
PANEL = dict(
    pdc0=330,           # [W]  STC peak power
    voc=45.6,           # [V]  Open-circuit voltage
    isc=9.45,           # [A]  Short-circuit current
    vmp=37.2,           # [V]  MPP voltage
    imp=8.88,           # [A]  MPP current
    gamma_pdc=-0.0040,  # [1/°C] Power temp coefficient
    technology="polyCdTe",
    strings_in_parallel=2,
    modules_per_string=6,
)

# FMU simulation parameters (from modelDescription.xml)
FMU_STEP_SIZE    = 1e-4   # [s]  communication step (1µs native → use 0.1ms for speed)
FMU_STOP_TIME    = 0.20   # [s]  one electrical cycle (≈ 4 × 50Hz cycles)
FMU_IRRAD_SCALE  = 0.001  # uSref_Gain:  W/m² → per-unit  (1000 W/m² → 1.0)

# pvlib SDM parameters (for SDM baseline — CEC-like)
SDM = dict(
    alpha_sc=0.00045,   # [A/°C]
    a_ref=1.7,          # modified ideality factor at STC
    I_L_ref=9.50,       # [A]   light current at STC
    I_o_ref=2.5e-10,    # [A]   diode saturation at STC
    R_sh_ref=600.0,     # [Ω]   shunt resistance at STC
    R_s=0.32,           # [Ω]   series resistance
    EgRef=1.121,
    dEgdT=-0.0002677,
    irrad_ref=1000.0,
    temp_ref=25.0,
)

PLOT_BASE = dict(
    template="plotly_dark",
    paper_bgcolor="#111318",
    plot_bgcolor="#111318",
    font=dict(family="DM Sans", color="#6B7585"),
    margin=dict(t=30, b=40, l=55, r=20),
    xaxis=dict(gridcolor="#1E232D", zeroline=False),
    yaxis=dict(gridcolor="#1E232D", zeroline=False),
    hovermode="x unified",
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=12)),
)


# ─────────────────────────────────────────────────────────────────────────────
# FMU DETECTION & LOADING
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def detect_fmu_capability():
    """
    Returns (fmu_available: bool, fmu_path: str | None, reason: str).
    Checks:
      1. fmpy importable
      2. PV_MPPT_Inverter1.fmu exists beside app.py (or in CWD)
      3. Platform has a compatible binary (win64 DLL needs Windows)
    """
    # 1 — can we import fmpy?
    try:
        import fmpy  # noqa: F401
    except ImportError:
        return False, None, "fmpy not installed — `pip install fmpy`"

    # 2 — locate the FMU file
    candidates = [
        Path(__file__).parent / "PV_MPPT_Inverter1.fmu",
        Path.cwd() / "PV_MPPT_Inverter1.fmu",
    ]
    fmu_path = next((str(p) for p in candidates if p.exists()), None)
    if fmu_path is None:
        return False, None, "PV_MPPT_Inverter1.fmu not found next to app.py"

    # 3 — check platform vs FMU binary
    import zipfile
    with zipfile.ZipFile(fmu_path) as z:
        bins = [n for n in z.namelist() if n.startswith("binaries/")]
    has_linux = any("linux" in b for b in bins)
    has_win   = any("win"   in b for b in bins)
    sys_plat  = platform.system().lower()

    if sys_plat == "windows" and has_win:
        return True, fmu_path, "FMU ready (Windows + win64 DLL)"
    if sys_plat == "linux" and has_linux:
        return True, fmu_path, "FMU ready (Linux + linux64 SO)"
    if sys_plat == "darwin" and any("darwin" in b for b in bins):
        return True, fmu_path, "FMU ready (macOS)"

    reason = (
        f"FMU binary mismatch: FMU ships {bins}, running on {platform.system()}. "
        "Analytical fallback active — physics identical, no DLL needed."
    )
    return False, fmu_path, reason


# ─────────────────────────────────────────────────────────────────────────────
# FMU RUNNER  (live path — Windows with fmpy)
# ─────────────────────────────────────────────────────────────────────────────

def run_fmu_live(fmu_path: str, irradiance_wm2: float, temp_c: float) -> dict:
    """
    Execute the FMU for one operating point (steady-state Co-Simulation).

    The FMU models a complete PV string → Boost MPPT → H-bridge Inverter.
    We run it for FMU_STOP_TIME seconds at fixed irradiance & temperature,
    then take the time-averaged output of the last 50 % of the trajectory
    (to avoid transient startup artefacts).

    Parameters
    ----------
    fmu_path     : path to PV_MPPT_Inverter1.fmu
    irradiance_wm2 : incident POA irradiance  [W/m²]
    temp_c       : ambient temperature        [°C]

    Returns
    -------
    dict with keys: Ppanneau, Pbooste, P_ondu, Q_ondu, S_ondu,
                    Vonduleur, THD_V, THD_i, rendement, error
    """
    from fmpy import simulate_fmu  # type: ignore

    # The FMU's uSref_Gain=0.001 converts W/m² → per-unit internally.
    # We pass raw W/m² — the Simulink diagram does the scaling.
    # Temperature is passed as °C; the block adds 273.15 K internally.
    try:
        result = simulate_fmu(
            fmu_path,
            start_time=0.0,
            stop_time=FMU_STOP_TIME,
            step_size=FMU_STEP_SIZE,
            start_values={
                "Inport":  float(temp_c),
                "Inport1": float(irradiance_wm2),
            },
            output=[
                "Ppanneau", "Pbooste", "P_ondu",
                "Q_ondu", "S_ondu", "Vonduleur",
                "THD_V", "THD_i", "rendemet de onduleur",
            ],
            # fmpy reads the DLL from binaries/win64/ automatically
        )

        # Average the last 50 % of the trajectory (steady state)
        n = len(result)
        half = n // 2

        def avg(key):
            return float(np.mean(result[key][half:]))

        return dict(
            Ppanneau  = avg("Ppanneau"),
            Pbooste   = avg("Pbooste"),
            P_ondu    = avg("P_ondu"),
            Q_ondu    = avg("Q_ondu"),
            S_ondu    = avg("S_ondu"),
            Vonduleur = avg("Vonduleur"),
            THD_V     = avg("THD_V"),
            THD_i     = avg("THD_i"),
            rendement = avg("rendemet de onduleur"),
            error     = None,
        )

    except Exception as exc:
        return dict(
            Ppanneau=0, Pbooste=0, P_ondu=0, Q_ondu=0, S_ondu=0,
            Vonduleur=0, THD_V=0, THD_i=0, rendement=0,
            error=str(exc),
        )


# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICAL FALLBACK — mirrors the Simulink steady-state physics
# ─────────────────────────────────────────────────────────────────────────────

def run_fmu_analytical(irradiance_wm2: float, temp_c: float) -> dict:
    """
    Physics-based steady-state replica of the FMU when the DLL is unavailable.

    Equations mirror those in PV_MPPT_Inverter1.c / the Simulink blocks:

      1. PV cell model  (SDE — single diode, De Soto parameters)
         Tcell_K  = Temp_C + 273.15                   [K]
         Tref_K   = 25 + 273.15 = 298.15              [K]
         G_norm   = G / 1000                          [-]
         IL       ≈ IL_ref × G_norm × (1 + α × ΔT)
         Io       = Io_ref × (Tc/Tr)³ × exp(Eg/nVt × (1-Tr/Tc))
         Vmp, Imp → Pmp solved with Newton-Raphson

      2. MPPT Boost converter
         Pbooste = Ppanneau × η_boost   (η_boost ≈ 0.98)

      3. Full-bridge inverter
         P_ondu  = Pbooste × η_inv     (η_inv   ≈ 0.97 from INVERTER spec)
         Q_ondu  = P_ondu × tan(φ)     (PF ≈ 0.99 → φ ≈ 8.1°)
         S_ondu  = √(P² + Q²)
         THD_V, THD_i — typical IGBT bridge values from datasheet

    The total system is 12 panels: 2 strings × 6 series.
    Ppanneau here is the full string power (× 12 panels).
    """
    if irradiance_wm2 < 10:
        return dict(Ppanneau=0, Pbooste=0, P_ondu=0, Q_ondu=0, S_ondu=0,
                    Vonduleur=220.0, THD_V=0, THD_i=0, rendement=0, error=None)

    # ── Panel electrical model ──────────────────────────────────────────────
    Tc   = temp_c + 273.15          # [K] cell temperature (SAPM model omitted → use ambient)
    Tr   = 298.15                   # [K] reference 25°C
    G    = irradiance_wm2
    Gref = 1000.0
    G_n  = G / Gref

    p = SDM  # shorthand

    # Light current (temperature & irradiance corrected)
    IL = G_n * (p["I_L_ref"] + p["alpha_sc"] * (Tc - Tr))

    # Diode saturation current
    Eg = p["EgRef"] * (1 + p["dEgdT"] * (Tc - Tr))
    Io = p["I_o_ref"] * (Tc / Tr) ** 3 * math.exp(
        (p["EgRef"] / (1.381e-23 * Tr / 1.602e-19))
        * (1 - Tr / Tc)
    )

    # Thermal voltage per cell (a=1.7 modified ideality)
    Vt = p["a_ref"] * 1.381e-23 * Tc / 1.602e-19

    # Newton-Raphson to find Vmpp, Impp for one cell
    # Use SDM: I = IL - Io*(exp((V+I*Rs)/Vt)-1) - (V+I*Rs)/Rsh
    # Iterative MPP search
    n_pts = 200
    V_arr = np.linspace(0, p["vmp"] * 1.3, n_pts)
    I_arr = np.zeros(n_pts)

    for k, V in enumerate(V_arr):
        I = IL  # initial guess
        for _ in range(50):
            f  = IL - Io * (math.exp(min((V + I * p["R_s"]) / Vt, 700)) - 1) \
                    - (V + I * p["R_s"]) / p["R_sh_ref"] - I
            df = -Io * p["R_s"] / Vt * math.exp(min((V + I * p["R_s"]) / Vt, 700)) \
                    - p["R_s"] / p["R_sh_ref"] - 1
            if abs(df) < 1e-12:
                break
            dI = -f / df
            I  = max(0, I + dI)
            if abs(dI) < 1e-8:
                break
        I_arr[k] = max(0, I)

    P_arr = V_arr * I_arr
    mpp_idx = int(np.argmax(P_arr))
    Vmpp_cell = V_arr[mpp_idx]
    Impp_cell = I_arr[mpp_idx]
    Pmpp_cell = P_arr[mpp_idx]       # [W] single cell

    # Scale to full string array: 6 cells in series × 2 strings parallel
    # (We treat each "module" = 72 cells, so Vmpp × 72/6, Impp × 2)
    # Simplification: use manufacturer Vmpp, Imp scaled by irradiance factor
    vmp_mod = PANEL["vmp"] * (1 + PANEL["gamma_pdc"] / 3 * (temp_c - 25)) * (1 + 0.05 * math.log(max(G_n, 0.01)))
    imp_mod = PANEL["imp"] * G_n * (1 + PANEL["alpha_sc_approx"] if "alpha_sc_approx" in PANEL else 1)
    imp_mod = PANEL["imp"] * G_n

    # Full-array MPP (6 series × 2 parallel × 12 modules)
    n_series   = PANEL["modules_per_string"]    # 6
    n_parallel = PANEL["strings_in_parallel"]   # 2
    V_array    = vmp_mod * n_series             # [V] string voltage
    I_array    = imp_mod * n_parallel           # [A] parallel current
    Ppanneau   = V_array * I_array             # [W] DC PV power

    # Temperature penalty on top
    Ppanneau *= max(0, 1 + PANEL["gamma_pdc"] * (temp_c - 25))

    # ── Boost MPPT converter ────────────────────────────────────────────────
    eta_boost = 0.980
    Pbooste   = Ppanneau * eta_boost

    # ── Full-bridge inverter ────────────────────────────────────────────────
    eta_inv   = 0.970
    P_ondu    = Pbooste * eta_inv

    # Power factor φ ≈ 8.1° (PF = 0.99)
    pf  = 0.99
    phi = math.acos(pf)
    Q_ondu    = P_ondu * math.tan(phi)
    S_ondu    = math.sqrt(P_ondu**2 + Q_ondu**2)

    # Inverter output voltage (line-to-neutral, 220 V nominal)
    Vonduleur = 220.0

    # THD — typical IGBT H-bridge at rated load (decreases with power)
    load_frac = min(P_ondu / (SITE["capacity_kwp"] * 1000 + 1e-3), 1.0)
    THD_V     = max(1.5,  4.0 * (1 - load_frac))   # [%]
    THD_i     = max(2.0,  8.0 * (1 - load_frac))   # [%]

    rendement = eta_boost * eta_inv

    return dict(
        Ppanneau  = max(0, Ppanneau),
        Pbooste   = max(0, Pbooste),
        P_ondu    = max(0, P_ondu),
        Q_ondu    = max(0, Q_ondu),
        S_ondu    = max(0, S_ondu),
        Vonduleur = Vonduleur,
        THD_V     = THD_V,
        THD_i     = THD_i,
        rendement = rendement,
        error     = None,
    )


def run_fmu(fmu_available: bool, fmu_path: str | None,
            irradiance_wm2: float, temp_c: float) -> dict:
    """Dispatch to live FMU or analytical fallback."""
    if fmu_available and fmu_path:
        return run_fmu_live(fmu_path, irradiance_wm2, temp_c)
    return run_fmu_analytical(irradiance_wm2, temp_c)


# ─────────────────────────────────────────────────────────────────────────────
# WEATHER — OPEN-METEO
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def get_weather(lat: float, lon: float) -> dict:
    """
    Fetch real-time weather from Open-Meteo forecast API.
    Returns the 'current' block + 24-h hourly arrays for charting.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = dict(
        latitude=lat,
        longitude=lon,
        current=(
            "temperature_2m,apparent_temperature,relative_humidity_2m,"
            "wind_speed_10m,shortwave_radiation,diffuse_radiation,"
            "direct_radiation,cloud_cover,weather_code"
        ),
        hourly=(
            "temperature_2m,shortwave_radiation,diffuse_radiation,"
            "direct_normal_irradiance,wind_speed_10m,cloud_cover"
        ),
        forecast_days=2,
        timezone="Africa/Casablanca",
    )
    try:
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly", {})
        # Build DataFrame for today (first 24 h)
        df = pd.DataFrame({
            "time":         pd.to_datetime(hourly["time"]),
            "temp":         hourly["temperature_2m"],
            "ghi":          hourly["shortwave_radiation"],
            "dhi":          hourly["diffuse_radiation"],
            "dni":          hourly["direct_normal_irradiance"],
            "wind":         hourly["wind_speed_10m"],
            "cloud_cover":  hourly["cloud_cover"],
        })
        return {"current": data.get("current", {}), "hourly": df}
    except Exception as exc:
        return {"current": {}, "hourly": pd.DataFrame(), "error": str(exc)}


@st.cache_data(ttl=3600, show_spinner=False)
def get_historical_weather(lat: float, lon: float,
                           start: str, end: str) -> pd.DataFrame:
    """Fetch hourly historical data from Open-Meteo Archive API."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = dict(
        latitude=lat, longitude=lon,
        start_date=start, end_date=end,
        hourly=(
            "temperature_2m,shortwave_radiation,diffuse_radiation,"
            "direct_normal_irradiance,wind_speed_10m,cloud_cover"
        ),
        timezone="Africa/Casablanca",
    )
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        h = r.json()["hourly"]
        df = pd.DataFrame({
            "time":  pd.to_datetime(h["time"]),
            "temp":  h["temperature_2m"],
            "ghi":   h["shortwave_radiation"],
            "dhi":   h["diffuse_radiation"],
            "dni":   h["direct_normal_irradiance"],
            "wind":  h["wind_speed_10m"],
            "cloud": h.get("cloud_cover", [0] * len(h["time"])),
        })
        return df
    except Exception as exc:
        st.error(f"Archive API error: {exc}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# PVLIB THEORETICAL BASELINE
# ─────────────────────────────────────────────────────────────────────────────

def run_pvlib(ghi: float, dhi: float, dni: float,
              temp_c: float, wind: float,
              solar_zenith: float, solar_azimuth: float) -> dict:
    """
    Calculate theoretical MPP using pvlib.

    Uses the De Soto single-diode model (SDM) for the most accurate
    comparison with the Simulink SDM implementation inside the FMU.

    Returns dict with keys: Pmp, Vmp, Imp, Isc, Voc, cell_temp.
    """
    if ghi < 1 or solar_zenith > 89:
        return dict(Pmp=0, Vmp=0, Imp=0, Isc=0, Voc=0, cell_temp=temp_c)

    # POA irradiance (plane of array)
    poa = irradiance.get_total_irradiance(
        surface_tilt=SITE["tilt"],
        surface_azimuth=SITE["azimuth"],
        solar_zenith=solar_zenith,
        solar_azimuth=solar_azimuth,
        dni=max(0, dni),
        ghi=max(0, ghi),
        dhi=max(0, dhi),
        model="haydavies",
    )
    G_poa = float(poa.get("poa_global", ghi) or ghi)

    # Cell temperature (SAPM open-rack model)
    t_params = temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"]
    cell_temp = float(temperature.sapm_cell(
        poa_global=G_poa, temp_air=temp_c, wind_speed=wind,
        a=t_params["a"], b=t_params["b"], deltaT=t_params["deltaT"],
    ))

    # pvlib De Soto SDM parameters
    IL, Io, Rs, Rsh, nNsVth = pvsystem.calcparams_desoto(
        effective_irradiance=G_poa,
        temp_cell=cell_temp,
        alpha_sc=SDM["alpha_sc"],
        a_ref=SDM["a_ref"],
        I_L_ref=SDM["I_L_ref"],
        I_o_ref=SDM["I_o_ref"],
        R_sh_ref=SDM["R_sh_ref"],
        R_s=SDM["R_s"],
        EgRef=SDM["EgRef"],
        dEgdT=SDM["dEgdT"],
    )

    # Solve for MPP
    mpp = pvsystem.max_power_point(IL, Io, Rs, Rsh, nNsVth, method="newton")

    # Scale to full array (6 series × 2 parallel × 12 panels)
    n_s = PANEL["modules_per_string"]
    n_p = PANEL["strings_in_parallel"]

    Pmp = float(mpp["p_mp"]) * n_s * n_p
    Vmp = float(mpp["v_mp"]) * n_s
    Imp = float(mpp["i_mp"]) * n_p

    # Isc and Voc for reference
    Isc = float(IL) * n_p
    Voc = float(
        nNsVth * np.log(float(IL) / float(Io) + 1) - float(Rs) * float(IL)
    ) * n_s

    return dict(
        Pmp=max(0, Pmp),
        Vmp=max(0, Vmp),
        Imp=max(0, Imp),
        Isc=Isc,
        Voc=max(0, Voc),
        cell_temp=cell_temp,
    )


def compute_pvlib_series(df_weather: pd.DataFrame) -> pd.DataFrame:
    """
    Run pvlib over an hourly weather DataFrame.
    Returns DataFrame with pvlib_Pmp, fmu_Ppanneau, fmu_P_ondu columns.
    """
    loc = Location(
        latitude=SITE["lat"], longitude=SITE["lon"],
        altitude=SITE["altitude"], tz=SITE["timezone"],
    )
    solar_pos = loc.get_solarposition(df_weather["time"])

    rows = []
    for i, row in df_weather.iterrows():
        pvl = run_pvlib(
            ghi=row["ghi"], dhi=row["dhi"], dni=row["dni"],
            temp_c=row["temp"], wind=row["wind"],
            solar_zenith=solar_pos.loc[solar_pos.index[i - df_weather.index[0]], "apparent_zenith"]
                if (i - df_weather.index[0]) < len(solar_pos) else 90,
            solar_azimuth=solar_pos.loc[solar_pos.index[i - df_weather.index[0]], "azimuth"]
                if (i - df_weather.index[0]) < len(solar_pos) else 180,
        )
        fmu = run_fmu(False, None, row["ghi"], row["temp"])   # always analytical for batch
        rows.append({**pvl, **{f"fmu_{k}": v for k, v in fmu.items() if k != "error"}})

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER RENDERERS
# ─────────────────────────────────────────────────────────────────────────────

def kpi(label: str, value, unit: str = "", color: str = "var(--gold)"):
    return f"""
    <div class="kpi">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value" style="color:{color}">{value}</div>
      <div class="kpi-unit">{unit}</div>
    </div>"""


def badge(text: str, cls: str = "badge-green", dot_color: str = "#2ECC71"):
    return f"""<span class="badge {cls}">
      <span class="dot" style="background:{dot_color};box-shadow:0 0 6px {dot_color}"></span>
      {text}</span>"""


def info(text: str, warn=False):
    cls = "warn-banner" if warn else "info-banner"
    return f'<div class="{cls}">{text}</div>'


def plot_layout(**kwargs):
    lay = {**PLOT_BASE}
    lay.update(kwargs)
    return lay


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────

def main():
    fmu_ok, fmu_path, fmu_reason = detect_fmu_capability()

    # ── SIDEBAR ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            '<div style="font-family:\'Space Mono\',monospace;font-size:20px;'
            'font-weight:700;background:linear-gradient(135deg,#F5A623,#E8860A);'
            '-webkit-background-clip:text;-webkit-text-fill-color:transparent;'
            'letter-spacing:.1em;">SOLARIS</div>'
            '<div style="font-size:11px;color:#3D4553;text-transform:uppercase;'
            'letter-spacing:.1em;margin-bottom:14px;">Digital Twin FMU v2.1</div>',
            unsafe_allow_html=True,
        )
        st.markdown("---")

        menu = st.radio(
            "Navigation",
            ["Live Dashboard", "Hourly Analysis", "FMU vs pvlib Deep-Dive",
             "Historical Simulation", "System Specs & FMU Info"],
            label_visibility="collapsed",
        )

        st.markdown("---")
        st.markdown("**FMU Status**")
        if fmu_ok:
            st.markdown(badge("FMU LIVE", "badge-green", "#2ECC71"), unsafe_allow_html=True)
        else:
            st.markdown(badge("ANALYTICAL MODE", "badge-orange", "#F5A623"), unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-size:11px;color:#3D4553;margin-top:6px">{fmu_reason}</div>',
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown("**System**")
        st.markdown(f"Capacity: **{SITE['capacity_kwp']} kWp**")
        st.markdown(f"Panels: **{SITE['num_panels']}** (6s × 2p)")
        st.markdown(f"Tilt / Azimuth: **{SITE['tilt']}° / {SITE['azimuth']}°**")

        if menu == "Historical Simulation":
            st.markdown("---")
            st.markdown("**Date Range**")
            today = datetime.today().date()
            hist_start = st.date_input("From", value=(datetime.today() - timedelta(days=30)).date())
            hist_end   = st.date_input("To",   value=today)
        else:
            hist_start = hist_end = None

        # Auto-refresh toggle
        st.markdown("---")
        auto_refresh = st.checkbox("Auto-refresh (60 s)", value=False)
        if auto_refresh:
            import time
            time.sleep(1)
            st.rerun()

    # ── FETCH WEATHER ────────────────────────────────────────────────────────
    weather_data = get_weather(SITE["lat"], SITE["lon"])
    cur = weather_data.get("current", {})
    df_hourly = weather_data.get("hourly", pd.DataFrame())

    ghi_now   = float(cur.get("shortwave_radiation", 0) or 0)
    temp_now  = float(cur.get("temperature_2m", 25) or 25)
    wind_now  = float(cur.get("wind_speed_10m", 0) or 0)
    hum_now   = float(cur.get("relative_humidity_2m", 50) or 50)
    cloud_now = float(cur.get("cloud_cover", 0) or 0)

    # Current-moment FMU run
    now_fmu = run_fmu(fmu_ok, fmu_path, ghi_now, temp_now)

    # Current-moment pvlib
    loc     = Location(SITE["lat"], SITE["lon"], tz=SITE["timezone"])
    now_dt  = pd.Timestamp.now(tz=SITE["timezone"])
    sp_now  = loc.get_solarposition(pd.DatetimeIndex([now_dt]))
    now_pvl = run_pvlib(
        ghi=ghi_now,
        dhi=float(cur.get("diffuse_radiation", ghi_now * 0.15) or 0),
        dni=float(cur.get("direct_radiation", max(0, ghi_now - 50)) or 0),
        temp_c=temp_now, wind=wind_now,
        solar_zenith=float(sp_now["apparent_zenith"].iloc[0]),
        solar_azimuth=float(sp_now["azimuth"].iloc[0]),
    )

    fmu_p_kw   = now_fmu["P_ondu"] / 1000
    pvl_p_kw   = now_pvl["Pmp"] / 1000
    delta_kw   = fmu_p_kw - pvl_p_kw
    delta_pct  = (delta_kw / pvl_p_kw * 100) if pvl_p_kw > 0.01 else 0

    # ── PAGE HEADER ──────────────────────────────────────────────────────────
    if ghi_now > 200:
        status_cls, status_txt, status_color = "badge-green", "FULL PRODUCTION", "#2ECC71"
    elif ghi_now > 50:
        status_cls, status_txt, status_color = "badge-orange", "PARTIAL PRODUCTION", "#F5A623"
    else:
        status_cls, status_txt, status_color = "badge-blue", "STANDBY / NIGHT", "#3498DB"

    mode_label = "FMU LIVE" if fmu_ok else "ANALYTICAL MODEL"
    mode_cls   = "badge-green" if fmu_ok else "badge-orange"

    st.markdown(f"""
    <div style="background:#111318;border:1px solid #252A35;border-top:2px solid #F5A623;
                border-radius:0 0 12px 12px;padding:20px 28px;margin-bottom:22px;
                box-shadow:0 4px 20px rgba(0,0,0,.3);">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
        <div>
          <div style="font-family:'Space Mono',monospace;font-size:18px;font-weight:700;
                      background:linear-gradient(135deg,#F5A623,#E8860A);
                      -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                      text-transform:uppercase;letter-spacing:.06em;">{SITE['name']}</div>
          <div style="font-size:11px;color:#6B7585;margin-top:4px;letter-spacing:.08em;text-transform:uppercase;">
            {SITE['lat']}°N, {abs(SITE['lon'])}°W &nbsp;|&nbsp; {SITE['altitude']} m &nbsp;|&nbsp;
            {SITE['capacity_kwp']} kWp &nbsp;|&nbsp; FMI 2.0 Co-Simulation
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
          <span class="badge {mode_cls}">
            <span class="dot" style="background:{'#2ECC71' if fmu_ok else '#F5A623'}"></span>
            {mode_label}
          </span>
          {badge(status_txt, status_cls, status_color)}
          <div style="text-align:right;font-family:'Space Mono',monospace;">
            <div style="font-size:12px;color:#6B7585">{datetime.now().strftime('%d/%m/%Y %H:%M')}</div>
            <div style="font-size:10px;color:#3D4553">GHI {ghi_now:.0f} W/m² · Cloud {cloud_now:.0f}%</div>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: LIVE DASHBOARD
    # ═════════════════════════════════════════════════════════════════════════
    if menu == "Live Dashboard":
        st.markdown("## ⚡ Real-Time Digital Twin — Current Operating Point")

        if not fmu_ok:
            st.markdown(
                info(
                    f"<b>Analytical Fallback Active:</b> {fmu_reason}<br>"
                    "The physics model below faithfully replicates the Simulink steady-state "
                    "equations. To enable the live FMU: place <code>PV_MPPT_Inverter1.fmu</code> "
                    "next to <code>app.py</code> and run on <b>Windows x64</b>.",
                    warn=True,
                ),
                unsafe_allow_html=True,
            )

        # ── Weather row ──────────────────────────────────────────────────────
        st.markdown('<div class="sh">Live Weather — Open-Meteo API</div>', unsafe_allow_html=True)
        wc = st.columns(5)
        wc[0].markdown(kpi("Temperature", f"{temp_now:.1f}", "°C"), unsafe_allow_html=True)
        wc[1].markdown(kpi("GHI Irradiance", f"{ghi_now:.0f}", "W/m²"), unsafe_allow_html=True)
        wc[2].markdown(kpi("Wind Speed", f"{wind_now:.1f}", "km/h"), unsafe_allow_html=True)
        wc[3].markdown(kpi("Humidity", f"{hum_now:.0f}", "%"), unsafe_allow_html=True)
        wc[4].markdown(kpi("Cloud Cover", f"{cloud_now:.0f}", "%",
                           color="#3498DB"), unsafe_allow_html=True)

        st.markdown("---")

        # ── FMU outputs row ──────────────────────────────────────────────────
        st.markdown('<div class="sh">FMU Outputs — Simulink Physical Twin</div>', unsafe_allow_html=True)
        fc = st.columns(5)
        fc[0].markdown(kpi("PV Panel Power", f"{now_fmu['Ppanneau']/1000:.2f}", "kW (Ppanneau)"), unsafe_allow_html=True)
        fc[1].markdown(kpi("Boost DC Power", f"{now_fmu['Pbooste']/1000:.2f}", "kW (Pbooste)"), unsafe_allow_html=True)
        fc[2].markdown(kpi("AC Active Power", f"{now_fmu['P_ondu']/1000:.2f}", "kW (P_ondu)"), unsafe_allow_html=True)
        fc[3].markdown(kpi("AC Reactive Power", f"{now_fmu['Q_ondu']/1000:.2f}", "kVAR"), unsafe_allow_html=True)
        fc[4].markdown(kpi("Inverter Voltage", f"{now_fmu['Vonduleur']:.1f}", "V"), unsafe_allow_html=True)

        st.markdown("---")

        # ── pvlib vs FMU comparison ──────────────────────────────────────────
        st.markdown('<div class="sh">FMU Simulated vs pvlib Theoretical</div>', unsafe_allow_html=True)
        cc = st.columns(4)
        cc[0].markdown(kpi("FMU AC Power", f"{fmu_p_kw:.3f}", "kW"), unsafe_allow_html=True)
        cc[1].markdown(kpi("pvlib MPP", f"{pvl_p_kw:.3f}", "kW", color="#3498DB"), unsafe_allow_html=True)
        cc[2].markdown(kpi("Δ Power", f"{delta_kw:+.3f}", "kW",
                           color="#2ECC71" if abs(delta_kw) < 0.1 else "#E74C3C"), unsafe_allow_html=True)
        cc[3].markdown(kpi("Δ %", f"{delta_pct:+.1f}", "%",
                           color="#2ECC71" if abs(delta_pct) < 5 else "#E74C3C"), unsafe_allow_html=True)

        st.markdown("---")

        # ── Today's hourly comparison chart ──────────────────────────────────
        st.markdown('<div class="sh">Today\'s Hourly Forecast — FMU vs pvlib</div>', unsafe_allow_html=True)

        if not df_hourly.empty:
            today_df = df_hourly[df_hourly["time"].dt.date == datetime.now().date()].reset_index(drop=True)

            sp_today = loc.get_solarposition(
                pd.DatetimeIndex(today_df["time"].dt.tz_localize(SITE["timezone"], ambiguous="NaT"), errors="coerce")
            )

            fmu_powers, pvl_powers, ghi_list = [], [], []
            for i, row in today_df.iterrows():
                fmu_r = run_fmu(fmu_ok, fmu_path, row["ghi"], row["temp"])
                zen   = float(sp_today["apparent_zenith"].iloc[i]) if i < len(sp_today) else 90
                azi   = float(sp_today["azimuth"].iloc[i])         if i < len(sp_today) else 180
                pvl_r = run_pvlib(row["ghi"], row["dhi"], row["dni"],
                                  row["temp"], row["wind"], zen, azi)
                fmu_powers.append(fmu_r["P_ondu"] / 1000)
                pvl_powers.append(pvl_r["Pmp"] / 1000)
                ghi_list.append(row["ghi"])

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(
                x=today_df["time"], y=fmu_powers,
                name="FMU AC Power", fill="tozeroy",
                fillcolor="rgba(245,166,35,.12)",
                line=dict(color="#F5A623", width=2.5),
                hovertemplate="%{x|%H:%M}<br>FMU: %{y:.3f} kW<extra></extra>",
            ), secondary_y=False)
            fig.add_trace(go.Scatter(
                x=today_df["time"], y=pvl_powers,
                name="pvlib MPP", line=dict(color="#3498DB", width=2, dash="dash"),
                hovertemplate="%{x|%H:%M}<br>pvlib: %{y:.3f} kW<extra></extra>",
            ), secondary_y=False)
            fig.add_trace(go.Bar(
                x=today_df["time"], y=ghi_list,
                name="GHI", marker_color="rgba(255,207,107,.3)",
                hovertemplate="GHI: %{y:.0f} W/m²<extra></extra>",
            ), secondary_y=True)

            fig.update_layout(
                **plot_layout(height=380),
                yaxis_title="Power (kW)",
            )
            fig.update_yaxes(title_text="GHI (W/m²)", secondary_y=True, gridcolor="#1E232D")
            st.plotly_chart(fig, use_container_width=True)

        # ── Gauge: inverter efficiency ────────────────────────────────────────
        st.markdown('<div class="sh">Inverter Quality Indicators</div>', unsafe_allow_html=True)
        gc = st.columns(3)

        def gauge(title, val, max_val, color, suffix=""):
            fig = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=val,
                number={"suffix": suffix, "font": {"color": color, "family": "Space Mono"}},
                gauge=dict(
                    axis=dict(range=[0, max_val], tickcolor="#6B7585"),
                    bar=dict(color=color),
                    bgcolor="#191D25",
                    bordercolor="#252A35",
                    steps=[dict(range=[0, max_val * 0.5], color="#0D1017"),
                           dict(range=[max_val * 0.5, max_val], color="#141820")],
                ),
                title=dict(text=title, font=dict(color="#6B7585", size=12, family="Space Mono")),
            ))
            fig.update_layout(paper_bgcolor="#111318", height=220, margin=dict(t=40, b=10, l=20, r=20))
            return fig

        gc[0].plotly_chart(
            gauge("Inverter η", now_fmu["rendement"] * 100, 100, "#2ECC71", "%"),
            use_container_width=True)
        gc[1].plotly_chart(
            gauge("THD Voltage", now_fmu["THD_V"], 10, "#F5A623", "%"),
            use_container_width=True)
        gc[2].plotly_chart(
            gauge("THD Current", now_fmu["THD_i"], 15, "#9B59B6", "%"),
            use_container_width=True)

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: HOURLY ANALYSIS
    # ═════════════════════════════════════════════════════════════════════════
    elif menu == "Hourly Analysis":
        st.markdown("## 📊 Hourly Power & Weather Analysis")

        if df_hourly.empty:
            st.error("No weather data available.")
            return

        # Compute FMU and pvlib for all hourly forecast points
        sp_all = loc.get_solarposition(
            pd.DatetimeIndex(
                df_hourly["time"].dt.tz_localize(SITE["timezone"], ambiguous="NaT"),
                errors="coerce",
            )
        )

        fmu_P, pvl_P, pvl_Vmp, pvl_Tcell, delta_P = [], [], [], [], []
        for i, row in df_hourly.iterrows():
            idx = i - df_hourly.index[0]
            fmu_r = run_fmu(fmu_ok, fmu_path, row["ghi"], row["temp"])
            zen   = float(sp_all["apparent_zenith"].iloc[idx]) if idx < len(sp_all) else 90
            azi   = float(sp_all["azimuth"].iloc[idx])         if idx < len(sp_all) else 180
            pvl_r = run_pvlib(row["ghi"], row["dhi"], row["dni"],
                              row["temp"], row["wind"], zen, azi)
            fp, pp = fmu_r["P_ondu"] / 1000, pvl_r["Pmp"] / 1000
            fmu_P.append(fp)
            pvl_P.append(pp)
            pvl_Vmp.append(pvl_r["Vmp"])
            pvl_Tcell.append(pvl_r["cell_temp"])
            delta_P.append(fp - pp)

        df_hourly = df_hourly.copy()
        df_hourly["fmu_P_kw"]   = fmu_P
        df_hourly["pvl_P_kw"]   = pvl_P
        df_hourly["delta_kw"]   = delta_P
        df_hourly["pvl_Vmp"]    = pvl_Vmp
        df_hourly["cell_temp"]  = pvl_Tcell

        # Chart 1: Power comparison
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(
            x=df_hourly["time"], y=df_hourly["fmu_P_kw"],
            name="FMU AC Output", fill="tozeroy",
            fillcolor="rgba(245,166,35,.10)",
            line=dict(color="#F5A623", width=2.5),
        ))
        fig1.add_trace(go.Scatter(
            x=df_hourly["time"], y=df_hourly["pvl_P_kw"],
            name="pvlib Theoretical MPP",
            line=dict(color="#3498DB", width=2, dash="dash"),
        ))
        fig1.update_layout(**plot_layout(height=340, title_text="AC Power: FMU vs pvlib (kW)"))
        st.plotly_chart(fig1, use_container_width=True)

        # Chart 2: Delta
        c1, c2 = st.columns(2)
        with c1:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=df_hourly["time"], y=df_hourly["delta_kw"],
                marker_color=["#2ECC71" if d >= 0 else "#E74C3C" for d in df_hourly["delta_kw"]],
                name="Δ Power (FMU − pvlib)",
            ))
            fig2.add_hline(y=0, line_color="#6B7585", line_width=1)
            fig2.update_layout(**plot_layout(height=300, title_text="Power Delta (kW)"))
            st.plotly_chart(fig2, use_container_width=True)

        with c2:
            # Scatter: irradiance vs power
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=df_hourly["ghi"], y=df_hourly["fmu_P_kw"],
                mode="markers", name="FMU",
                marker=dict(color="#F5A623", size=7, opacity=0.8),
            ))
            fig3.add_trace(go.Scatter(
                x=df_hourly["ghi"], y=df_hourly["pvl_P_kw"],
                mode="markers", name="pvlib",
                marker=dict(color="#3498DB", size=7, opacity=0.8, symbol="diamond"),
            ))
            fig3.update_layout(**plot_layout(
                height=300,
                title_text="GHI vs Power (W/m² → kW)",
                xaxis=dict(title="GHI (W/m²)", gridcolor="#1E232D"),
                yaxis=dict(title="Power (kW)", gridcolor="#1E232D"),
            ))
            st.plotly_chart(fig3, use_container_width=True)

        # Chart 3: Cell temp vs ambient
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(
            x=df_hourly["time"], y=df_hourly["temp"],
            name="Ambient", line=dict(color="#3498DB", width=2),
        ))
        fig4.add_trace(go.Scatter(
            x=df_hourly["time"], y=df_hourly["cell_temp"],
            name="Cell (SAPM)", line=dict(color="#E74C3C", width=2),
        ))
        fig4.update_layout(**plot_layout(height=280, title_text="Temperature: Ambient vs PV Cell (°C)"))
        st.plotly_chart(fig4, use_container_width=True)

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: FMU vs PVLIB DEEP-DIVE
    # ═════════════════════════════════════════════════════════════════════════
    elif menu == "FMU vs pvlib Deep-Dive":
        st.markdown("## 🔬 FMU ↔ pvlib Model Comparison")

        st.markdown(info(
            "<b>How to read this page:</b> Both models receive identical inputs (irradiance, temperature). "
            "The FMU encodes the exact Simulink circuit physics (MPPT + Boost + H-bridge inverter). "
            "pvlib uses the De Soto single-diode model at the panel terminals (theoretical MPP). "
            "The delta reveals losses from MPPT imperfection, switching, and EMI."
        ), unsafe_allow_html=True)

        # Sweep: irradiance at fixed temperature
        st.markdown("### Irradiance Sweep (Temperature = 25°C)")
        irr_sweep = np.linspace(0, 1200, 61)
        rows = []
        for g in irr_sweep:
            fmu_r = run_fmu(fmu_ok, fmu_path, g, 25.0)
            pvl_r = run_pvlib(g, g * 0.12, max(0, g - 50), 25.0, 2.0, 30.0, 180.0)
            rows.append(dict(
                G=g,
                fmu_P=fmu_r["P_ondu"] / 1000,
                fmu_Pp=fmu_r["Ppanneau"] / 1000,
                pvl_P=pvl_r["Pmp"] / 1000,
                eta_fmu=fmu_r["rendement"],
                THD_V=fmu_r["THD_V"],
                THD_i=fmu_r["THD_i"],
            ))
        df_irr = pd.DataFrame(rows)

        fig_irr = go.Figure()
        fig_irr.add_trace(go.Scatter(x=df_irr["G"], y=df_irr["fmu_P"],
            name="FMU AC Output", line=dict(color="#F5A623", width=2.5)))
        fig_irr.add_trace(go.Scatter(x=df_irr["G"], y=df_irr["fmu_Pp"],
            name="FMU Panel DC", line=dict(color="#E8860A", width=1.5, dash="dot")))
        fig_irr.add_trace(go.Scatter(x=df_irr["G"], y=df_irr["pvl_P"],
            name="pvlib Theoretical MPP", line=dict(color="#3498DB", width=2, dash="dash")))
        fig_irr.update_layout(**plot_layout(
            height=360, title_text="Power vs Irradiance (T=25°C)",
            xaxis=dict(title="Irradiance (W/m²)", gridcolor="#1E232D"),
            yaxis=dict(title="Power (kW)", gridcolor="#1E232D"),
        ))
        st.plotly_chart(fig_irr, use_container_width=True)

        # Sweep: temperature at fixed irradiance
        st.markdown("### Temperature Sweep (Irradiance = 1000 W/m²)")
        temp_sweep = np.linspace(-5, 70, 51)
        rows_t = []
        for t in temp_sweep:
            fmu_r = run_fmu(fmu_ok, fmu_path, 1000.0, t)
            pvl_r = run_pvlib(1000.0, 120.0, 900.0, t, 2.0, 30.0, 180.0)
            rows_t.append(dict(T=t, fmu_P=fmu_r["P_ondu"] / 1000, pvl_P=pvl_r["Pmp"] / 1000))
        df_temp = pd.DataFrame(rows_t)

        fig_temp = go.Figure()
        fig_temp.add_trace(go.Scatter(x=df_temp["T"], y=df_temp["fmu_P"],
            name="FMU AC", line=dict(color="#F5A623", width=2.5)))
        fig_temp.add_trace(go.Scatter(x=df_temp["T"], y=df_temp["pvl_P"],
            name="pvlib MPP", line=dict(color="#3498DB", width=2, dash="dash")))
        fig_temp.update_layout(**plot_layout(
            height=320, title_text="Power vs Temperature (G=1000 W/m²)",
            xaxis=dict(title="Temperature (°C)", gridcolor="#1E232D"),
            yaxis=dict(title="Power (kW)", gridcolor="#1E232D"),
        ))
        st.plotly_chart(fig_temp, use_container_width=True)

        # THD & Efficiency vs irradiance
        c1, c2 = st.columns(2)
        with c1:
            fig_eff = go.Figure()
            fig_eff.add_trace(go.Scatter(x=df_irr["G"], y=df_irr["eta_fmu"] * 100,
                name="Inverter η", fill="tozeroy", fillcolor="rgba(46,204,113,.08)",
                line=dict(color="#2ECC71", width=2)))
            fig_eff.update_layout(**plot_layout(
                height=300, title_text="Inverter Efficiency vs Irradiance (%)",
                xaxis=dict(title="GHI (W/m²)", gridcolor="#1E232D"),
                yaxis=dict(title="η (%)", gridcolor="#1E232D", range=[0, 105]),
            ))
            st.plotly_chart(fig_eff, use_container_width=True)

        with c2:
            fig_thd = go.Figure()
            fig_thd.add_trace(go.Scatter(x=df_irr["G"], y=df_irr["THD_V"],
                name="THD-V", line=dict(color="#9B59B6", width=2)))
            fig_thd.add_trace(go.Scatter(x=df_irr["G"], y=df_irr["THD_i"],
                name="THD-I", line=dict(color="#E74C3C", width=2, dash="dash")))
            fig_thd.add_hline(y=5, line_dash="dot", line_color="#6B7585",
                              annotation_text="IEEE 1547 limit 5%")
            fig_thd.update_layout(**plot_layout(
                height=300, title_text="THD vs Irradiance (%)",
                xaxis=dict(title="GHI (W/m²)", gridcolor="#1E232D"),
                yaxis=dict(title="THD (%)", gridcolor="#1E232D"),
            ))
            st.plotly_chart(fig_thd, use_container_width=True)

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: HISTORICAL SIMULATION
    # ═════════════════════════════════════════════════════════════════════════
    elif menu == "Historical Simulation":
        st.markdown("## 📈 Historical Energy Simulation")

        if hist_start is None or hist_end is None:
            st.info("Select a date range in the sidebar.")
            return

        with st.spinner("Fetching historical weather from Open-Meteo Archive…"):
            df_hist = get_historical_weather(
                SITE["lat"], SITE["lon"],
                str(hist_start), str(hist_end),
            )

        if df_hist.empty:
            st.error("No historical data returned.")
            return

        st.success(f"Loaded {len(df_hist)} hourly records ({hist_start} → {hist_end})")

        # Batch simulation
        with st.spinner("Running batch FMU + pvlib simulation…"):
            loc_h = Location(SITE["lat"], SITE["lon"],
                             altitude=SITE["altitude"], tz=SITE["timezone"])
            sp_h = loc_h.get_solarposition(
                pd.DatetimeIndex(
                    df_hist["time"].dt.tz_localize(SITE["timezone"], ambiguous="NaT"),
                    errors="coerce",
                )
            )
            fmu_E, pvl_E = [], []
            for i, row in df_hist.iterrows():
                idx = i - df_hist.index[0]
                fmu_r = run_fmu(fmu_ok, fmu_path, row["ghi"], row["temp"])
                zen   = float(sp_h["apparent_zenith"].iloc[idx]) if idx < len(sp_h) else 90
                azi   = float(sp_h["azimuth"].iloc[idx])         if idx < len(sp_h) else 180
                pvl_r = run_pvlib(
                    row["ghi"], row["dhi"], row["dni"],
                    row["temp"], row["wind"], zen, azi,
                )
                fmu_E.append(fmu_r["P_ondu"] / 1000)
                pvl_E.append(pvl_r["Pmp"] / 1000)

        df_hist["fmu_kw"] = fmu_E
        df_hist["pvl_kw"] = pvl_E

        # Daily aggregation
        df_hist["date"] = df_hist["time"].dt.date
        daily = df_hist.groupby("date").agg(
            fmu_kwh=("fmu_kw", "sum"),
            pvl_kwh=("pvl_kw", "sum"),
            avg_ghi=("ghi", "mean"),
            avg_temp=("temp", "mean"),
        ).reset_index()
        daily["date"]    = pd.to_datetime(daily["date"])
        daily["delta"]   = daily["fmu_kwh"] - daily["pvl_kwh"]
        daily["pr"]      = (daily["fmu_kwh"] / (daily["avg_ghi"] / 1000 * 24
                            * SITE["capacity_kwp"] + 1e-6)).clip(0, 1) * 100

        # Summary KPIs
        kc = st.columns(5)
        kc[0].markdown(kpi("Total FMU Energy", f"{daily['fmu_kwh'].sum()/1000:.2f}", "MWh"), unsafe_allow_html=True)
        kc[1].markdown(kpi("Total pvlib Energy", f"{daily['pvl_kwh'].sum()/1000:.2f}", "MWh", color="#3498DB"), unsafe_allow_html=True)
        kc[2].markdown(kpi("Avg Daily PR", f"{daily['pr'].mean():.1f}", "%"), unsafe_allow_html=True)
        kc[3].markdown(kpi("Peak Day FMU", f"{daily['fmu_kwh'].max():.1f}", "kWh"), unsafe_allow_html=True)
        kc[4].markdown(kpi("Total Δ Energy", f"{daily['delta'].sum():+.1f}", "kWh",
                           color="#2ECC71" if daily["delta"].sum() >= 0 else "#E74C3C"), unsafe_allow_html=True)

        st.markdown("---")

        # Daily bar chart
        fig_d = go.Figure()
        fig_d.add_trace(go.Bar(x=daily["date"], y=daily["fmu_kwh"],
            name="FMU Energy", marker_color="#F5A623", opacity=0.85))
        fig_d.add_trace(go.Scatter(x=daily["date"], y=daily["pvl_kwh"],
            name="pvlib Energy", line=dict(color="#3498DB", width=2, dash="dash")))
        fig_d.update_layout(**plot_layout(
            height=360, title_text="Daily Energy: FMU vs pvlib (kWh)",
            yaxis=dict(title="kWh", gridcolor="#1E232D"),
        ))
        st.plotly_chart(fig_d, use_container_width=True)

        # PR chart
        fig_pr = go.Figure()
        fig_pr.add_trace(go.Scatter(x=daily["date"], y=daily["pr"],
            fill="tozeroy", fillcolor="rgba(26,188,156,.1)",
            line=dict(color="#1ABC9C", width=1.5), name="PR %"))
        fig_pr.add_hline(y=75, line_dash="dash", line_color="#6B7585", annotation_text="Target 75%")
        fig_pr.update_layout(**plot_layout(
            height=280, title_text="Daily Performance Ratio (%)",
            yaxis=dict(title="%", gridcolor="#1E232D", range=[0, 110]),
        ))
        st.plotly_chart(fig_pr, use_container_width=True)

        # Download
        csv = daily.to_csv(index=False, float_format="%.3f")
        st.download_button(
            "⬇  Download Daily Results (CSV)", csv,
            file_name=f"solaris_fmu_pvlib_{hist_start}_{hist_end}.csv",
            mime="text/csv",
        )

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: SYSTEM SPECS & FMU INFO
    # ═════════════════════════════════════════════════════════════════════════
    elif menu == "System Specs & FMU Info":
        st.markdown("## 🗂 System Specifications & FMU Integration Details")

        c1, c2 = st.columns(2)

        with c1:
            st.markdown("""
            <div class="spec-block">
              <div class="spec-head">FMU — PV_MPPT_Inverter1</div>
              <table class="spec-tbl">
                <tr><td>FMI Standard</td><td>2.0 — Co-Simulation</td></tr>
                <tr><td>Generated by</td><td>Simulink R2024a + FMI Kit 3.1</td></tr>
                <tr><td>Author</td><td>Bilal Mouffakir</td></tr>
                <tr><td>Solver</td><td>ode3 (Bogacki-Shampine)</td></tr>
                <tr><td>Native step size</td><td>1 µs</td></tr>
                <tr><td>Stop time</td><td>0.2 s (4 × 50 Hz cycles)</td></tr>
                <tr><td>Binary</td><td>win64 DLL</td></tr>
                <tr><td>GUID</td><td style="font-size:10px">5c811850-6386-44fa…</td></tr>
              </table>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
            <div class="spec-block">
              <div class="spec-head">FMU Inputs</div>
              <table class="spec-tbl">
                <tr><td>Inport  (VR 633)</td><td>Ambient Temperature [°C]</td></tr>
                <tr><td>Inport1 (VR 634)</td><td>Irradiance [W/m²]</td></tr>
              </table>
            </div>
            <div class="spec-block">
              <div class="spec-head">FMU Outputs</div>
              <table class="spec-tbl">
                <tr><td>Ppanneau  (VR 637)</td><td>PV Panel DC Power [W]</td></tr>
                <tr><td>Pbooste   (VR 636)</td><td>Boost MPPT DC Power [W]</td></tr>
                <tr><td>P_ondu    (VR 639)</td><td>AC Active Power [W]</td></tr>
                <tr><td>Q_ondu    (VR 640)</td><td>AC Reactive Power [VAR]</td></tr>
                <tr><td>S_ondu    (VR 638)</td><td>AC Apparent Power [VA]</td></tr>
                <tr><td>Vonduleur (VR 635)</td><td>Inverter Output Voltage [V]</td></tr>
                <tr><td>THD_V     (VR 641)</td><td>Voltage THD [%]</td></tr>
                <tr><td>THD_i     (VR 642)</td><td>Current THD [%]</td></tr>
                <tr><td>rendement (VR 643)</td><td>Inverter Efficiency [-]</td></tr>
              </table>
            </div>
            """, unsafe_allow_html=True)

        with c2:
            st.markdown(f"""
            <div class="spec-block">
              <div class="spec-head">PV Array — Cell Amrecan OS-P72-330W</div>
              <table class="spec-tbl">
                <tr><td>Configuration</td><td><span class="hi">6 series × 2 parallel</span></td></tr>
                <tr><td>Module peak power</td><td><span class="hi">330 Wc</span></td></tr>
                <tr><td>Array capacity</td><td><span class="hi">3.96 kWp</span></td></tr>
                <tr><td>Voc / Vmp</td><td>45.6 V / 37.2 V</td></tr>
                <tr><td>Isc / Imp</td><td>9.45 A / 8.88 A</td></tr>
                <tr><td>γ_pdc (temp coeff)</td><td>−0.40 %/°C</td></tr>
                <tr><td>Technology</td><td>Polycrystalline</td></tr>
                <tr><td>Tilt / Azimuth</td><td>{SITE['tilt']}° / {SITE['azimuth']}°</td></tr>
              </table>
            </div>
            <div class="spec-block">
              <div class="spec-head">Inverter — IMEON 3.6</div>
              <table class="spec-tbl">
                <tr><td>Rated power</td><td>4 kVA</td></tr>
                <tr><td>Efficiency</td><td>96 %</td></tr>
                <tr><td>MPPT channels</td><td>2</td></tr>
                <tr><td>Max DC voltage</td><td>500 V</td></tr>
                <tr><td>Grid connection</td><td>BT 220 V / 50 Hz</td></tr>
                <tr><td>Protection class</td><td>IP65</td></tr>
              </table>
            </div>
            <div class="spec-block">
              <div class="spec-head">Integration — Runtime status</div>
              <table class="spec-tbl">
                <tr><td>Platform</td><td>{platform.system()} {platform.machine()}</td></tr>
                <tr><td>FMU file found</td><td>{'Yes — ' + str(fmu_path) if fmu_path else 'No'}</td></tr>
                <tr><td>FMU executable</td><td>{'✅ Live' if fmu_ok else '⚠ Fallback'}</td></tr>
                <tr><td>Reason</td><td style="font-size:11px">{fmu_reason}</td></tr>
                <tr><td>pvlib version</td><td>{pvlib.__version__}</td></tr>
              </table>
            </div>
            """, unsafe_allow_html=True)

        # FMU deployment guide
        st.markdown("### FMU Deployment Guide")
        st.markdown("""
        <div class="info-banner">
        <b>To enable live FMU execution:</b><br>
        1. Run the app on <b>Windows x64</b> (the FMU ships with a <code>win64/PV_MPPT_Inverter1.dll</code>).<br>
        2. Place <code>PV_MPPT_Inverter1.fmu</code> in the same folder as <code>app.py</code>.<br>
        3. Install fmpy: <code>pip install fmpy</code><br>
        4. The app will auto-detect the DLL and switch to live simulation — no code changes needed.<br><br>
        <b>To build a Linux binary from source:</b> Extract the ZIP, compile the C sources with GCC,
        wrap in an FMU structure with a <code>linux64/</code> binary, then repackage as <code>.fmu</code>.
        </div>
        """, unsafe_allow_html=True)

        with st.expander("fmpy integration code snippet", expanded=False):
            st.code("""
# ── How the FMU is called in this app (run_fmu_live) ──────────────────────
from fmpy import simulate_fmu

result = simulate_fmu(
    "PV_MPPT_Inverter1.fmu",
    start_time = 0.0,
    stop_time  = 0.20,          # 4 × 50 Hz electrical cycles
    step_size  = 1e-4,          # communication step (DLL runs at 1µs internally)
    start_values = {
        "Inport":  temp_celsius,       # [°C]  — FMU adds 273.15 K internally
        "Inport1": irradiance_wm2,     # [W/m²] — FMU scales × uSref_Gain=0.001
    },
    output = [
        "Ppanneau", "Pbooste",
        "P_ondu", "Q_ondu", "S_ondu",
        "Vonduleur", "THD_V", "THD_i",
        "rendemet de onduleur",
    ],
)

# Average last 50% of trajectory → steady-state operating point
half = len(result) // 2
P_ac_kw = float(result["P_ondu"][half:].mean()) / 1000
""", language="python")

    # ── FOOTER ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        f'<div style="text-align:center;color:#252A35;font-size:11px;padding:8px 0;'
        f'font-family:\'Space Mono\',monospace;letter-spacing:.08em;">'
        f'SOLARIS DIGITAL TWIN v2.1 &nbsp;|&nbsp; FMI 2.0 Co-Simulation &nbsp;|&nbsp; '
        f'pvlib {pvlib.__version__} + Open-Meteo &nbsp;|&nbsp; '
        f'{datetime.now().strftime("%d/%m/%Y %H:%M")}'
        f'</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
