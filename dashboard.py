"""
╔══════════════════════════════════════════════════════════════════════════════╗
║     Solar PV + MPPT + Inverter  —  Digital Twin Dashboard                  ║
║     Location : Mohammedia, Morocco  (Lat 33.68 / Lon -7.38)                ║
║     Author   : Bilal Mouffakir                                              ║
║     FMU      : PV_MPPT_Inverter1.fmu  (Simulink R2024a / FMI 2.0)         ║
╚══════════════════════════════════════════════════════════════════════════════╝

Architecture
────────────
  1. Weather layer  → Open-Meteo free API (irradiance + temperature)
  2. FMU layer      → fmpy co-simulation  (physics-based Simulink model)
  3. Analytical layer → pvlib SDM model  (industry-standard Python library)
  4. UI layer       → Streamlit with custom CSS / Plotly charts
"""

import os
import time
import math
import requests
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# ── pvlib ──────────────────────────────────────────────────────────────────
import pvlib
from pvlib.location import Location
from pvlib.pvsystem import PVSystem, FixedMount
from pvlib.modelchain import ModelChain

# ── fmpy ───────────────────────────────────────────────────────────────────
try:
    from fmpy import read_model_description, extract
    from fmpy.fmi2 import FMU2Slave
    FMPY_AVAILABLE = True
except ImportError:
    FMPY_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════════════════
# 0.  SITE & PANEL CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

# ── Geographic location ────────────────────────────────────────────────────
LATITUDE  = 33.68
LONGITUDE = -7.38
ALTITUDE  = 28          # metres, Mohammedia sea-level area
TIMEZONE  = "Africa/Casablanca"
TILT      = 30          # panel tilt from horizontal (°)
AZIMUTH   = 180         # panel azimuth: 180 = south-facing

# ── Solar panel datasheet parameters ──────────────────────────────────────
# Inferred from the FMU ModelDescription:
#   • Parameters.IL_module_Value  = 10.2347  A   → Isc at STC
#   • Parameters.alpha_Isc_Gain   = 0.010414 A/°C → temperature coeff of Isc
#   • Parameters.Tref_K_Value     = 298.15   K   → STC reference (25 °C)
# The values below match a generic 400 W monocrystalline panel consistent
# with those FMU parameters.  Adjust if you have an exact datasheet.
PANEL_PARAMS = {
    "pdc0":         400,      # W  – STC peak power
    "v_mp":         37.8,     # V  – MPP voltage  at STC
    "i_mp":         10.58,    # A  – MPP current  at STC
    "v_oc":         46.2,     # V  – Open-circuit voltage
    "i_sc":         10.23,    # A  – Short-circuit current  (matches FMU IL_module_Value)
    "alpha_sc":     0.010414, # A/°C – Temp coeff Isc       (matches FMU alpha_Isc_Gain)
    "beta_oc":      -0.1386,  # V/°C – Temp coeff Voc  (typical -0.3 %/°C × 46.2 V)
    "gamma_pdc":    -0.0037,  # 1/°C – Temp coeff Pmax (typical -0.37 %/°C)
    "cells_in_series": 120,   # typical for 46 V Voc mono panel
}

# Number of modules in the system (scale factor)
N_MODULES_SERIES  = 1
N_MODULES_PARALLEL = 1

# ── FMU variable names (edit here if the model is revised) ────────────────
FMU_INPUT_IRRADIANCE   = "Inport"   # ← swap these two names if needed
FMU_INPUT_TEMPERATURE  = "Inport1"  # ← swap these two names if needed
FMU_OUTPUT_VARS = [
    "Ppanneau",             # DC power from the PV panel (W)
    "P_ondu",               # AC active power from the inverter (W)
    "Vonduleur",            # AC voltage at inverter output (V)
    "rendemet de onduleur", # Inverter efficiency (0–1 or 0–100 %)
]

# ── Open-Meteo endpoint ────────────────────────────────────────────────────
OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LATITUDE}&longitude={LONGITUDE}"
    "&current=temperature_2m,shortwave_radiation"
    "&timezone=auto"
    "&forecast_days=1"
)

# ══════════════════════════════════════════════════════════════════════════════
# 1.  PAGE CONFIG & CUSTOM CSS
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Solar Digital Twin – Mohammedia",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  /* ── Google Fonts ── */
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

  /* ── Root palette ── */
  :root {
    --bg-deep:    #0a0f1e;
    --bg-card:    #111827;
    --bg-card2:   #1a2235;
    --accent:     #f59e0b;
    --accent2:    #10b981;
    --accent3:    #3b82f6;
    --danger:     #ef4444;
    --text:       #f1f5f9;
    --muted:      #94a3b8;
    --border:     rgba(255,255,255,0.08);
  }

  /* ── Base ── */
  html, body, [class*="css"] {
    font-family: 'Space Grotesk', sans-serif;
    background-color: var(--bg-deep) !important;
    color: var(--text) !important;
  }
  .main .block-container { padding: 1.5rem 2rem 3rem; max-width: 1400px; }

  /* ── Header banner ── */
  .banner {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f2027 100%);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
  }
  .banner::before {
    content: '';
    position: absolute; top: -50%; right: -10%;
    width: 400px; height: 400px;
    background: radial-gradient(circle, rgba(245,158,11,0.15) 0%, transparent 70%);
    pointer-events: none;
  }
  .banner h1 { font-size: 2rem; font-weight: 700; margin: 0 0 .4rem;
               background: linear-gradient(90deg, #f59e0b, #fbbf24);
               -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .banner p  { font-size: .95rem; color: var(--muted); margin: 0; }
  .banner .badge {
    display: inline-block; padding: .2rem .7rem; border-radius: 20px;
    background: rgba(245,158,11,0.15); border: 1px solid rgba(245,158,11,0.3);
    color: var(--accent); font-size: .75rem; font-weight: 600;
    margin-right: .4rem; margin-top: .6rem;
  }

  /* ── Metric card ── */
  .metric-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem 1.4rem;
    transition: border-color .2s;
  }
  .metric-card:hover { border-color: rgba(245,158,11,0.35); }
  .metric-label { font-size: .72rem; text-transform: uppercase; letter-spacing: .1em;
                  color: var(--muted); margin-bottom: .3rem; }
  .metric-value { font-family: 'JetBrains Mono', monospace; font-size: 1.8rem;
                  font-weight: 600; line-height: 1.1; }
  .metric-unit  { font-size: .8rem; color: var(--muted); margin-left: .25rem; }
  .metric-delta { font-size: .75rem; margin-top: .3rem; }
  .delta-pos { color: var(--accent2); }
  .delta-neg { color: var(--danger);  }

  /* ── Section title ── */
  .section-title {
    font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .15em;
    color: var(--muted); border-left: 3px solid var(--accent);
    padding-left: .6rem; margin: 1.6rem 0 .8rem;
  }

  /* ── Comparison box ── */
  .compare-box {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px; padding: 1.4rem;
  }
  .compare-box h3 { font-size: .85rem; font-weight: 600; margin: 0 0 .8rem;
                    color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }

  /* ── Error / warning ── */
  .err-box {
    background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3);
    border-radius: 10px; padding: 1rem 1.2rem; color: #fca5a5;
    font-size: .85rem;
  }
  .warn-box {
    background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.3);
    border-radius: 10px; padding: 1rem 1.2rem; color: #fcd34d;
    font-size: .85rem;
  }

  /* ── Plotly chart container ── */
  .js-plotly-plot { border-radius: 12px; overflow: hidden; }

  /* ── Streamlit overrides ── */
  [data-testid="stMetric"]  { background: transparent !important; }
  div[data-testid="column"] { gap: .8rem; }
  .stSpinner > div { border-top-color: var(--accent) !important; }
  footer { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 2.  WEATHER DATA — Open-Meteo API
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=900, show_spinner=False)  # 15-minute cache
def fetch_weather() -> dict:
    """
    Fetch the latest current-hour weather from Open-Meteo (free, no key).
    Returns a dict with keys: temperature_c, irradiance_wm2, timestamp, raw.
    """
    try:
        resp = requests.get(OPEN_METEO_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        current = data["current"]
        return {
            "temperature_c":   float(current["temperature_2m"]),
            "irradiance_wm2":  float(current["shortwave_radiation"]),
            "timestamp":       current["time"],
            "error":           None,
            "raw":             data,
        }
    except Exception as exc:
        return {
            "temperature_c":   25.0,   # safe fallback for STC
            "irradiance_wm2":  1000.0,
            "timestamp":       "N/A",
            "error":           str(exc),
            "raw":             {},
        }


# ══════════════════════════════════════════════════════════════════════════════
# 3.  FMU CO-SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

def run_fmu_simulation(irradiance: float, temperature: float) -> dict:
    """
    Instantiate and step the PV_MPPT_Inverter1.fmu for a short interval,
    then read the output variables.

    FMU inputs
    ──────────
    • Inport  → irradiance  (W/m²)   ← edit FMU_INPUT_IRRADIANCE to swap
    • Inport1 → temperature (°C)     ← edit FMU_INPUT_TEMPERATURE to swap

    FMU outputs extracted
    ─────────────────────
    • Ppanneau             – DC panel power  (W)
    • P_ondu               – AC active power (W)
    • Vonduleur            – AC voltage      (V)
    • rendemet de onduleur – Inverter efficiency
    """
    result = {k: None for k in FMU_OUTPUT_VARS}
    result["error"] = None

    if not FMPY_AVAILABLE:
        result["error"] = "fmpy is not installed."
        return result

    fmu_path = "PV_MPPT_Inverter1.fmu"
    if not os.path.exists(fmu_path):
        result["error"] = (
            f"FMU file '{fmu_path}' not found in the working directory. "
            "Make sure it is deployed alongside app.py."
        )
        return result

    # ── Simulation time settings ───────────────────────────────────────────
    START_TIME  = 0.0
    STOP_TIME   = 0.1     # 100 ms is enough to let the model settle
    STEP_SIZE   = 1e-4    # 0.1 ms per communication step

    fmu = None
    unzip_dir = None
    try:
        # 1. Parse the model description to get value references
        model_desc = read_model_description(fmu_path)
        vrs = {var.name: var.valueReference for var in model_desc.modelVariables}

        # 2. Extract FMU to a temp directory
        unzip_dir = extract(fmu_path)

        # 3. Instantiate the FMU2Slave
        fmu = FMU2Slave(
            guid          = model_desc.guid,
            unzipDirectory= unzip_dir,
            modelIdentifier = model_desc.coSimulation.modelIdentifier,
            instanceName  = "PV_Digital_Twin",
        )

        # 4. Initialise
        fmu.instantiate()
        fmu.setupExperiment(startTime=START_TIME, stopTime=STOP_TIME)
        fmu.enterInitializationMode()

        # 5. Set inputs BEFORE exiting init mode
        fmu.setReal([vrs[FMU_INPUT_IRRADIANCE],  vrs[FMU_INPUT_TEMPERATURE]],
                    [irradiance,                   temperature])

        fmu.exitInitializationMode()

        # 6. Step through time until STOP_TIME
        current_time = START_TIME
        while current_time < STOP_TIME - 1e-9:
            step = min(STEP_SIZE, STOP_TIME - current_time)
            fmu.doStep(currentCommunicationPoint=current_time, communicationStepSize=step)
            current_time += step

        # 7. Read outputs
        for var_name in FMU_OUTPUT_VARS:
            if var_name in vrs:
                val = fmu.getReal([vrs[var_name]])[0]
                result[var_name] = val
            else:
                result[var_name] = None

    except Exception as exc:
        result["error"] = f"FMU simulation failed: {exc}"
    finally:
        # Always clean up to avoid resource leaks
        if fmu is not None:
            try:
                fmu.terminate()
                fmu.freeInstance()
            except Exception:
                pass
        if unzip_dir and os.path.exists(unzip_dir):
            import shutil
            try:
                shutil.rmtree(unzip_dir, ignore_errors=True)
            except Exception:
                pass

    return result


# ══════════════════════════════════════════════════════════════════════════════
# 4.  PVLIB ANALYTICAL SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def build_pvlib_system():
    """
    Build and cache the pvlib Location + PVSystem + ModelChain objects.
    Only instantiated once per Streamlit session.
    """
    location = Location(
        latitude  = LATITUDE,
        longitude = LONGITUDE,
        tz        = TIMEZONE,
        altitude  = ALTITUDE,
        name      = "Mohammedia, Morocco",
    )

    # Use the CEC single-diode model parameters derived from our panel datasheet.
    # pvlib.ivtools.sdm.fit_cec_sam can compute these, but we use the simplified
    # PVWatts DC model (pvwatts_dc) which only needs pdc0 and gamma_pdc.
    # This is the most robust approach when a full CEC database record is absent.
    module_params = {
        "pdc0":      PANEL_PARAMS["pdc0"],
        "gamma_pdc": PANEL_PARAMS["gamma_pdc"],   # Pmax temp coefficient (1/°C)
    }

    inverter_params = {
        "pdc0": PANEL_PARAMS["pdc0"] * N_MODULES_SERIES * N_MODULES_PARALLEL,
        "eta_inv_nom": 0.96,   # Nominal inverter efficiency
        "eta_inv_ref": 0.9637,
    }

    mount  = FixedMount(surface_tilt=TILT, surface_azimuth=AZIMUTH)
    system = PVSystem(
        surface_tilt    = TILT,
        surface_azimuth = AZIMUTH,
        module_parameters       = module_params,
        inverter_parameters     = inverter_params,
        modules_per_string      = N_MODULES_SERIES,
        strings_per_inverter    = N_MODULES_PARALLEL,
        mount                   = mount,
    )

    mc = ModelChain(
        system,
        location,
        dc_model      = "pvwatts",
        ac_model      = "pvwatts",
        aoi_model     = "physical",
        spectral_model= "no_loss",
        losses_model  = "no_loss",
    )

    return location, system, mc


def run_pvlib_simulation(irradiance: float, temperature: float) -> dict:
    """
    Run the pvlib analytical model for a single time point.
    Returns a dict with dc_power_w, cell_temp_c, and optional error.
    """
    result = {"dc_power_w": None, "cell_temp_c": None, "error": None}
    try:
        location, system, mc = build_pvlib_system()

        # Build a single-row DataFrame with the current timestamp
        now_utc = pd.Timestamp.utcnow().tz_convert(TIMEZONE)
        times   = pd.DatetimeIndex([now_utc])

        # ── Effective irradiance on tilted plane ───────────────────────────
        # We only have GHI; decompose it to DNI + DHI using the Erbs model,
        # then use transposition to get POA irradiance.
        solar_pos = location.get_solarposition(times)
        solar_zenith = float(solar_pos["apparent_zenith"].iloc[0])

        ghi = max(irradiance, 0.0)

        # Decompose GHI → DNI, DHI
        if solar_zenith < 90:
            dec = pvlib.irradiance.erbs(ghi, solar_zenith, times)
            dni = float(dec["dni"].iloc[0])
            dhi = float(dec["dhi"].iloc[0])
        else:
            dni = 0.0
            dhi = 0.0

        # Transposition to tilted plane (POA)
        poa = pvlib.irradiance.get_total_irradiance(
            surface_tilt    = TILT,
            surface_azimuth = AZIMUTH,
            solar_zenith    = solar_zenith,
            solar_azimuth   = float(solar_pos["azimuth"].iloc[0]),
            dni = dni, ghi = ghi, dhi = dhi,
        )
        poa_global = float(poa["poa_global"])

        # ── Cell temperature (Faiman model) ───────────────────────────────
        wind_speed = 1.0  # assumed average (m/s) — not in free Open-Meteo tier
        cell_temp = pvlib.temperature.faiman(
            poa_global = poa_global,
            temp_air   = temperature,
            wind_speed = wind_speed,
        )
        result["cell_temp_c"] = float(cell_temp)

        # ── PVWatts DC power ───────────────────────────────────────────────
        # P_dc = pdc0 × (G_eff / 1000) × [1 + gamma_pdc × (T_cell - 25)]
        g_ratio = poa_global / 1000.0
        temp_factor = 1.0 + PANEL_PARAMS["gamma_pdc"] * (cell_temp - 25.0)
        dc_power = PANEL_PARAMS["pdc0"] * N_MODULES_SERIES * N_MODULES_PARALLEL * g_ratio * temp_factor
        result["dc_power_w"] = max(float(dc_power), 0.0)

    except Exception as exc:
        result["error"] = f"pvlib simulation failed: {exc}"

    return result


# ══════════════════════════════════════════════════════════════════════════════
# 5.  PLOTLY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor ="rgba(0,0,0,0)",
    font         = dict(family="Space Grotesk", color="#94a3b8", size=12),
    margin       = dict(l=10, r=10, t=40, b=10),
)


def gauge_chart(value: float, title: str, unit: str,
                min_val: float = 0, max_val: float = 500,
                color: str = "#f59e0b") -> go.Figure:
    """Render a Plotly gauge for a single metric."""
    fig = go.Figure(go.Indicator(
        mode   = "gauge+number",
        value  = value if value is not None else 0,
        title  = {"text": f"{title}<br><span style='font-size:.75rem;color:#94a3b8'>{unit}</span>",
                  "font": {"size": 13}},
        gauge  = {
            "axis" : {"range": [min_val, max_val],
                      "tickcolor": "#334155", "tickfont": {"size": 10}},
            "bar"  : {"color": color, "thickness": 0.25},
            "bgcolor": "#1a2235",
            "bordercolor": "#334155",
            "steps": [
                {"range": [min_val, max_val * 0.33], "color": "#1e293b"},
                {"range": [max_val * 0.33, max_val * 0.66], "color": "#1e3a5f"},
                {"range": [max_val * 0.66, max_val],        "color": "#1e3a2f"},
            ],
            "threshold": {
                "line": {"color": "#f8fafc", "width": 2},
                "thickness": 0.8,
                "value": value if value is not None else 0,
            },
        },
        number = {"suffix": f" {unit}", "font": {"size": 24, "color": color}},
    ))
    fig.update_layout(**PLOTLY_LAYOUT, height=220)
    return fig


def comparison_bar(fmu_val: float | None, pvlib_val: float | None) -> go.Figure:
    """Side-by-side bar comparing FMU DC Power vs pvlib DC Power."""
    fmu_v   = fmu_val   if fmu_val   is not None else 0.0
    pvlib_v = pvlib_val if pvlib_val is not None else 0.0

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name = "FMU (Simulink)",
        x    = ["DC Power"],
        y    = [fmu_v],
        marker_color = "#f59e0b",
        text = [f"{fmu_v:.1f} W"],
        textposition = "outside",
        textfont     = dict(color="#f59e0b", size=13),
        width = 0.3,
    ))
    fig.add_trace(go.Bar(
        name = "pvlib (Analytical)",
        x    = ["DC Power"],
        y    = [pvlib_v],
        marker_color = "#10b981",
        text = [f"{pvlib_v:.1f} W"],
        textposition = "outside",
        textfont     = dict(color="#10b981", size=13),
        width = 0.3,
    ))
    fig.update_layout(
        **PLOTLY_LAYOUT,
        barmode   = "group",
        height    = 280,
        title     = dict(text="DC Power Comparison", font=dict(size=14, color="#f1f5f9")),
        yaxis     = dict(title="Power (W)", gridcolor="#1e293b", zeroline=False),
        xaxis     = dict(showticklabels=False),
        legend    = dict(orientation="h", y=1.15, x=0.5, xanchor="center",
                         font=dict(color="#f1f5f9")),
        bargroupgap = 0.15,
    )
    return fig


def efficiency_donut(efficiency: float | None) -> go.Figure:
    """Donut chart showing inverter efficiency."""
    eff = efficiency if efficiency is not None else 0.0
    # Normalise: if stored as 0–100 keep as-is; if 0–1 scale up
    if eff <= 1.0:
        eff = eff * 100.0
    eff = max(0.0, min(eff, 100.0))

    fig = go.Figure(go.Pie(
        values   = [eff, 100.0 - eff],
        hole     = 0.70,
        labels   = ["Efficiency", ""],
        marker   = dict(colors=["#10b981", "#1e293b"],
                        line=dict(color="#0a0f1e", width=2)),
        showlegend  = False,
        hoverinfo   = "none",
        textinfo    = "none",
    ))
    fig.add_annotation(
        text      = f"<b>{eff:.1f}%</b>",
        x=0.5, y=0.5, showarrow=False,
        font      = dict(size=26, color="#10b981", family="JetBrains Mono"),
    )
    fig.update_layout(**PLOTLY_LAYOUT, height=200,
                      title=dict(text="Inverter Efficiency", font=dict(size=13, color="#f1f5f9")))
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# 6.  STREAMLIT MAIN UI
# ══════════════════════════════════════════════════════════════════════════════

def render_metric_card(label: str, value: str, unit: str = "",
                       delta: str = "", delta_ok: bool = True) -> str:
    delta_class = "delta-pos" if delta_ok else "delta-neg"
    delta_html  = f'<div class="metric-delta {delta_class}">{delta}</div>' if delta else ""
    return f"""
    <div class="metric-card">
      <div class="metric-label">{label}</div>
      <div class="metric-value">{value}<span class="metric-unit">{unit}</span></div>
      {delta_html}
    </div>"""


def main():
    # ── Header ────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="banner">
      <h1>☀️ Solar PV Digital Twin</h1>
      <p>Real-time simulation &amp; comparison dashboard for the PV + MPPT + Inverter
         installation in <strong>Mohammedia, Morocco</strong>.</p>
      <span class="badge">FMI 2.0 Co-Simulation</span>
      <span class="badge">pvlib Analytical</span>
      <span class="badge">Open-Meteo API</span>
      <span class="badge">Lat 33.68 / Lon -7.38</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Refresh / last updated ─────────────────────────────────────────────
    top_col_l, top_col_r = st.columns([3, 1])
    with top_col_r:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # ── 1. Fetch weather ───────────────────────────────────────────────────
    with st.spinner("Fetching real-time weather from Open-Meteo…"):
        weather = fetch_weather()

    irradiance  = weather["irradiance_wm2"]
    temperature = weather["temperature_c"]

    # ── 2. Run simulations in parallel (sequential in Streamlit, but fast) ─
    with st.spinner("Running FMU co-simulation…"):
        fmu_result = run_fmu_simulation(irradiance, temperature)

    with st.spinner("Running pvlib analytical model…"):
        pvlib_result = run_pvlib_simulation(irradiance, temperature)

    # ── SECTION: Weather ──────────────────────────────────────────────────
    st.markdown('<div class="section-title">🌤 Real-time Weather — Mohammedia</div>',
                unsafe_allow_html=True)

    if weather["error"]:
        st.markdown(f'<div class="warn-box">⚠️ Weather API error (using STC fallback): {weather["error"]}</div>',
                    unsafe_allow_html=True)
    else:
        st.caption(f"Last updated: {weather['timestamp']}  (cache TTL: 15 min)")

    w1, w2, w3 = st.columns(3)
    with w1:
        st.markdown(render_metric_card(
            "Solar Irradiance (GHI)", f"{irradiance:.0f}", "W/m²",
            delta="🌞 Above STC" if irradiance > 1000 else ("☁️ Below STC" if irradiance < 600 else "≈ STC"),
            delta_ok=(irradiance >= 600),
        ), unsafe_allow_html=True)
    with w2:
        st.markdown(render_metric_card(
            "Ambient Temperature", f"{temperature:.1f}", "°C",
            delta="🔥 Hot" if temperature > 35 else ("❄️ Cool" if temperature < 15 else "🌡 Normal"),
            delta_ok=(temperature < 35),
        ), unsafe_allow_html=True)
    with w3:
        eff_cell = pvlib_result.get("cell_temp_c")
        cell_str = f"{eff_cell:.1f}" if eff_cell is not None else "—"
        st.markdown(render_metric_card(
            "Estimated Cell Temperature", cell_str, "°C",
            delta="pvlib / Faiman model",
        ), unsafe_allow_html=True)

    # ── SECTION: Power Comparison ─────────────────────────────────────────
    st.markdown('<div class="section-title">⚡ DC Power — FMU vs pvlib</div>',
                unsafe_allow_html=True)

    fmu_dc   = fmu_result.get("Ppanneau")
    pvlib_dc = pvlib_result.get("dc_power_w")

    # Percentage error
    if fmu_dc is not None and pvlib_dc is not None and pvlib_dc != 0:
        pct_err = (fmu_dc - pvlib_dc) / pvlib_dc * 100.0
        err_str = f"{pct_err:+.1f}%"
        err_ok  = abs(pct_err) < 10
    else:
        err_str = "N/A"
        err_ok  = True

    cmp_l, cmp_c, cmp_r = st.columns([1, 1, 1])

    with cmp_l:
        st.markdown('<div class="compare-box">', unsafe_allow_html=True)
        st.markdown(render_metric_card(
            "FMU DC Power (Ppanneau)",
            f"{fmu_dc:.1f}" if fmu_dc is not None else "Error",
            "W",
            delta="Simulink physics model",
        ), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with cmp_c:
        st.markdown('<div class="compare-box">', unsafe_allow_html=True)
        st.markdown(render_metric_card(
            "pvlib DC Power",
            f"{pvlib_dc:.1f}" if pvlib_dc is not None else "Error",
            "W",
            delta="PVWatts analytical",
        ), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with cmp_r:
        st.markdown('<div class="compare-box">', unsafe_allow_html=True)
        st.markdown(render_metric_card(
            "Deviation (FMU – pvlib) / pvlib",
            err_str,
            "",
            delta="< 10 % considered good" if err_ok else "⚠️ Large deviation — check FMU inputs",
            delta_ok=err_ok,
        ), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Bar chart + FMU gauges ─────────────────────────────────────────────
    bar_col, gauge_col = st.columns([1.5, 1])

    with bar_col:
        st.plotly_chart(
            comparison_bar(fmu_dc, pvlib_dc),
            use_container_width=True, config={"displayModeBar": False},
        )

    with gauge_col:
        max_dc = PANEL_PARAMS["pdc0"] * N_MODULES_SERIES * N_MODULES_PARALLEL * 1.1
        st.plotly_chart(
            gauge_chart(fmu_dc, "FMU DC Power", "W", max_val=max_dc, color="#f59e0b"),
            use_container_width=True, config={"displayModeBar": False},
        )

    # ── SECTION: Inverter Outputs ─────────────────────────────────────────
    st.markdown('<div class="section-title">🔌 Inverter Outputs (FMU)</div>',
                unsafe_allow_html=True)

    if fmu_result.get("error"):
        st.markdown(f'<div class="err-box">❌ FMU Error: {fmu_result["error"]}</div>',
                    unsafe_allow_html=True)

    i1, i2, i3, i4 = st.columns(4)

    p_ondu  = fmu_result.get("P_ondu")
    vond    = fmu_result.get("Vonduleur")
    rend    = fmu_result.get("rendemet de onduleur")
    pboost  = fmu_result.get("Pbooste")   # bonus output visible in XML

    with i1:
        st.markdown(render_metric_card(
            "AC Active Power (P_ondu)",
            f"{p_ondu:.1f}" if p_ondu is not None else "—", "W",
        ), unsafe_allow_html=True)
    with i2:
        st.markdown(render_metric_card(
            "AC Voltage (Vonduleur)",
            f"{vond:.1f}" if vond is not None else "—", "V",
        ), unsafe_allow_html=True)
    with i3:
        st.markdown(render_metric_card(
            "Boosted DC Power",
            f"{pboost:.1f}" if pboost is not None else "—", "W",
        ), unsafe_allow_html=True)
    with i4:
        # Show efficiency as percentage
        if rend is not None:
            rend_pct = rend * 100.0 if rend <= 1.0 else rend
            rend_str = f"{rend_pct:.1f}"
        else:
            rend_str = "—"
        st.markdown(render_metric_card(
            "Inverter Efficiency",
            rend_str, "%",
        ), unsafe_allow_html=True)

    # Efficiency donut + AC gauge side by side
    d1, d2, d3 = st.columns(3)
    with d1:
        st.plotly_chart(
            efficiency_donut(rend),
            use_container_width=True, config={"displayModeBar": False},
        )
    with d2:
        st.plotly_chart(
            gauge_chart(p_ondu, "AC Power", "W",
                        max_val=max_dc, color="#3b82f6"),
            use_container_width=True, config={"displayModeBar": False},
        )
    with d3:
        st.plotly_chart(
            gauge_chart(vond, "AC Voltage", "V",
                        min_val=0, max_val=500, color="#a78bfa"),
            use_container_width=True, config={"displayModeBar": False},
        )

    # ── SECTION: pvlib additional info ────────────────────────────────────
    if pvlib_result.get("error"):
        st.markdown(f'<div class="err-box">❌ pvlib Error: {pvlib_result["error"]}</div>',
                    unsafe_allow_html=True)

    # ── Footer ────────────────────────────────────────────────────────────
    st.markdown("""
    <hr style="border:none;border-top:1px solid rgba(255,255,255,0.06);margin:2rem 0 .8rem"/>
    <div style="text-align:center;font-size:.72rem;color:#475569">
      Solar PV Digital Twin · Mohammedia, Morocco ·
      FMU: PV_MPPT_Inverter1 (Simulink R2024a) ·
      pvlib PVWatts model · Open-Meteo API
    </div>
    """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
