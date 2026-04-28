"""
╔══════════════════════════════════════════════════════════════════╗
║         Solar Digital Twin — PV + MPPT + Inverter               ║
║         Mohammedia, Morocco | FMU Co-Simulation (FMI 2.0)        ║
║         Author: Bilal Mouffakir                                   ║
╚══════════════════════════════════════════════════════════════════╝

FMU Variables (from modelDescription.xml):
  Inputs:
    - Inport   → Solar Irradiance GHI (W/m²)
    - Inport1  → Temperature (°C)

  Outputs:
    - Vonduleur          → Inverter Output Voltage (V)
    - Pbooste            → Boost Converter Power (W)
    - Ppanneau           → PV Panel Power (W)
    - S_ondu             → Apparent Power (VA)
    - P_ondu             → Active Power (W)
    - Q_ondu             → Reactive Power (VAR)
    - THD_V              → Total Harmonic Distortion - Voltage (%)
    - THD_i              → Total Harmonic Distortion - Current (%)
    - rendemet de onduleur → Inverter Efficiency (%)
"""

import os
import time
import numpy as np
import pandas as pd
import requests
import streamlit as st
from datetime import datetime

# ── FMPy import (graceful fallback if not installed yet) ──────────────────────
try:
    from fmpy import read_model_description, extract
    from fmpy.fmi2 import FMU2Slave
    FMPY_AVAILABLE = True
except ImportError:
    FMPY_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# FMU file — must live in the same directory as app.py (relative path for cloud)
FMU_PATH = os.path.join(os.path.dirname(__file__), "model.fmu")

# Open-Meteo API — Mohammedia, Morocco
LAT, LON = 33.68, -7.38
WEATHER_API_URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LAT}&longitude={LON}"
    "&current=temperature_2m,direct_normal_irradiance,global_tilted_irradiance"
    "&timezone=Africa%2FCasablanca"
    "&forecast_days=1"
)

# Simulation time window (seconds) — keep short for cloud performance
SIM_START   = 0.0
SIM_STOP    = 1.0          # 1 second of electrical simulation
SIM_STEP    = 1e-3         # 1 ms communication step

# ═══════════════════════════════════════════════════════════════════════════════
#  1. WEATHER DATA  (Open-Meteo)
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=600)          # refresh every 10 minutes
def fetch_weather() -> dict:
    """
    Fetches current weather from Open-Meteo for Mohammedia, Morocco.
    Returns a dict with keys: temperature (°C), ghi (W/m²), dni (W/m²),
    timestamp, and optionally 'error'.
    """
    try:
        resp = requests.get(WEATHER_API_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current", {})
        temperature = current.get("temperature_2m", 25.0)
        ghi         = current.get("global_tilted_irradiance", 800.0)
        dni         = current.get("direct_normal_irradiance", 700.0)
        timestamp   = current.get("time", datetime.now().strftime("%Y-%m-%dT%H:%M"))

        return {
            "temperature": float(temperature),
            "ghi":         float(ghi),
            "dni":         float(dni),
            "timestamp":   timestamp,
            "error":       None,
        }
    except requests.exceptions.ConnectionError:
        return _fallback_weather("Connection error — using default values.")
    except requests.exceptions.Timeout:
        return _fallback_weather("API timeout — using default values.")
    except Exception as exc:
        return _fallback_weather(f"Unexpected error: {exc}")


def _fallback_weather(reason: str) -> dict:
    """Returns safe default values when the API is unavailable."""
    return {
        "temperature": 25.0,
        "ghi":         800.0,
        "dni":         700.0,
        "timestamp":   datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "error":       reason,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  2. FMU SIMULATION  (fmpy + Co-Simulation)
# ═══════════════════════════════════════════════════════════════════════════════

def run_fmu_simulation(temperature: float, irradiance: float) -> dict | None:
    """
    Runs the PV_MPPT_Inverter FMU (Co-Simulation, FMI 2.0) for a short
    time window and returns time-averaged output values.

    FMU Input mapping:
        Inport   ← irradiance  (W/m²)
        Inport1  ← temperature (°C)

    FMU Output mapping:
        Vonduleur           → inverter_voltage   (V)
        Pbooste             → boost_power        (W)
        Ppanneau            → panel_power        (W)
        S_ondu              → apparent_power     (VA)
        P_ondu              → active_power       (W)
        Q_ondu              → reactive_power     (VAR)
        THD_V               → thd_voltage        (%)
        THD_i               → thd_current        (%)
        rendemet de onduleur→ efficiency         (%)
    """
    if not FMPY_AVAILABLE:
        st.warning("fmpy is not installed. Showing analytical estimate instead.")
        return None

    if not os.path.isfile(FMU_PATH):
        st.error(
            f"❌ FMU file not found at `{FMU_PATH}`.\n\n"
            "Make sure `model.fmu` is in the same folder as `app.py`."
        )
        return None

    try:
        # ── Read model description ──────────────────────────────────────────
        model_desc = read_model_description(FMU_PATH)

        # Build a name→valueReference lookup
        vr = {v.name: v.valueReference for v in model_desc.modelVariables}

        # ── Extract FMU to a temp directory ────────────────────────────────
        unzip_dir = extract(FMU_PATH)

        # ── Instantiate FMU slave ───────────────────────────────────────────
        fmu = FMU2Slave(
            guid            = model_desc.guid,
            unzipDirectory  = unzip_dir,
            modelIdentifier = model_desc.coSimulation.modelIdentifier,
            instanceName    = "solar_twin",
        )

        fmu.instantiate()
        fmu.setupExperiment(startTime=SIM_START, stopTime=SIM_STOP)
        fmu.enterInitializationMode()

        # ── Set inputs before initialization completes ──────────────────────
        fmu.setReal([vr["Inport"]],  [irradiance])   # GHI → PV irradiance
        fmu.setReal([vr["Inport1"]], [temperature])  # T   → cell temperature

        fmu.exitInitializationMode()

        # ── Step through simulation ──────────────────────────────────────────
        output_names = [
            "Vonduleur", "Pbooste", "Ppanneau",
            "S_ondu", "P_ondu", "Q_ondu",
            "THD_V", "THD_i", "rendemet de onduleur",
        ]
        output_vrs  = [vr[n] for n in output_names]

        records = []
        t = SIM_START
        while t < SIM_STOP:
            fmu.doStep(currentCommunicationPoint=t, communicationStepSize=SIM_STEP)
            values = fmu.getReal(output_vrs)
            records.append([t] + list(values))
            t += SIM_STEP

        fmu.terminate()
        fmu.freeInstance()

        # ── Build results DataFrame ─────────────────────────────────────────
        cols = ["time"] + output_names
        df   = pd.DataFrame(records, columns=cols)

        # Return final-cycle averages (last 20 % of simulation = steady state)
        ss = df.iloc[int(len(df) * 0.8):]
        return {
            "df":              df,
            "inverter_voltage": ss["Vonduleur"].mean(),
            "boost_power":      ss["Pbooste"].mean(),
            "panel_power":      ss["Ppanneau"].mean(),
            "apparent_power":   ss["S_ondu"].mean(),
            "active_power":     ss["P_ondu"].mean(),
            "reactive_power":   ss["Q_ondu"].mean(),
            "thd_voltage":      ss["THD_V"].mean(),
            "thd_current":      ss["THD_i"].mean(),
            "efficiency":       ss["rendemet de onduleur"].mean(),
        }

    except Exception as exc:
        st.error(f"FMU simulation error: {exc}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  3. ANALYTICAL FALLBACK  (when FMU is unavailable)
# ═══════════════════════════════════════════════════════════════════════════════

def analytical_estimate(temperature: float, irradiance: float) -> dict:
    """
    Simple physics-based estimate used when the FMU cannot be run
    (e.g. missing binary on the cloud).  NOT a substitute for the real model.
    """
    G_ref, T_ref    = 1000.0, 25.0
    P_rated         = 5000.0    # W  — adjust to match your PV array
    eta_mppt        = 0.98
    eta_inverter    = 0.96
    temp_coeff      = -0.004    # %/°C power temperature coefficient

    G_ratio  = max(irradiance / G_ref, 0.0)
    T_derate = 1 + temp_coeff * (temperature - T_ref)

    panel_power   = P_rated * G_ratio * T_derate
    boost_power   = panel_power * eta_mppt
    active_power  = boost_power * eta_inverter
    voltage       = 230.0 * (G_ratio ** 0.05)   # slight sag at low irradiance
    efficiency    = eta_inverter * 100.0

    # Build a synthetic 1-second waveform for the chart
    t_vals = np.linspace(0, 1, 1000)
    noise  = np.random.normal(0, active_power * 0.005, len(t_vals))
    df = pd.DataFrame({
        "time":       t_vals,
        "Ppanneau":   panel_power  + noise,
        "P_ondu":     active_power + noise * 0.96,
        "Vonduleur":  voltage      + np.random.normal(0, 0.5, len(t_vals)),
    })

    return {
        "df":              df,
        "inverter_voltage": voltage,
        "boost_power":      boost_power,
        "panel_power":      panel_power,
        "apparent_power":   active_power / 0.98,
        "active_power":     active_power,
        "reactive_power":   active_power * 0.1,
        "thd_voltage":      2.1,
        "thd_current":      3.4,
        "efficiency":       efficiency,
        "is_estimate":      True,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  4. STREAMLIT  UI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    # ── Page config ─────────────────────────────────────────────────────────
    st.set_page_config(
        page_title="Solar Digital Twin — Mohammedia",
        page_icon="☀️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Custom CSS ───────────────────────────────────────────────────────────
    st.markdown("""
    <style>
        :root {
            --sun:    #f5a623;
            --green:  #27ae60;
            --blue:   #2980b9;
            --dark:   #1a1a2e;
        }
        .block-container { padding-top: 1.5rem; }
        h1 { color: var(--sun); font-size: 2rem !important; }
        .stMetric label  { font-size: 0.8rem !important; color: #888; }
        .stMetric [data-testid="stMetricValue"] { font-size: 1.6rem !important; }
        .badge {
            display: inline-block;
            background: #f5a62322;
            color: #f5a623;
            border: 1px solid #f5a62366;
            border-radius: 6px;
            padding: 2px 10px;
            font-size: 0.78rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }
        .section-card {
            background: #ffffff08;
            border: 1px solid #ffffff15;
            border-radius: 12px;
            padding: 1rem 1.2rem;
            margin-bottom: 1rem;
        }
    </style>
    """, unsafe_allow_html=True)

    # ── Header ───────────────────────────────────────────────────────────────
    st.markdown('<p class="badge">☀️ DIGITAL TWIN · FMI 2.0 Co-Simulation</p>', unsafe_allow_html=True)
    st.title("Solar PV · MPPT · Inverter — Digital Twin")
    st.caption("📍 Mohammedia, Morocco  |  Real-time weather → FMU simulation")

    # ── Sidebar controls ────────────────────────────────────────────────────
    with st.sidebar:
        st.header("⚙️ Controls")
        override = st.toggle("Manual input override", value=False)

        if override:
            man_irr  = st.slider("Irradiance GHI (W/m²)", 0, 1200, 800)
            man_temp = st.slider("Temperature (°C)", -10, 70, 25)
        else:
            man_irr  = None
            man_temp = None

        run_btn = st.button("▶ Run Simulation", type="primary", use_container_width=True)

        st.divider()
        st.markdown("**FMU file:**")
        fmu_exists = os.path.isfile(FMU_PATH)
        if fmu_exists:
            st.success(f"✅ `model.fmu` found")
        else:
            st.warning("⚠️ `model.fmu` not found\n\nAnalytical estimate will be used.")
        st.markdown("**fmpy:**")
        if FMPY_AVAILABLE:
            st.success("✅ Installed")
        else:
            st.warning("⚠️ Not installed — using estimate")

    # ── Fetch weather ────────────────────────────────────────────────────────
    with st.spinner("🌤 Fetching weather data from Open-Meteo…"):
        wx = fetch_weather()

    if wx["error"]:
        st.warning(f"⚠️ Weather API: {wx['error']}")

    temperature = man_temp if override else wx["temperature"]
    irradiance  = man_irr  if override else wx["ghi"]

    # ── Weather metrics row ──────────────────────────────────────────────────
    st.subheader("🌡 Current Weather · Mohammedia")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Temperature",      f"{wx['temperature']:.1f} °C",  delta=None)
    c2.metric("GHI (Global Horiz. Irr.)", f"{wx['ghi']:.0f} W/m²")
    c3.metric("DNI (Direct Normal Irr.)", f"{wx['dni']:.0f} W/m²")
    c4.metric("Last update", wx["timestamp"][-5:])   # HH:MM

    if override:
        st.info(f"🛠 Manual override active — Irradiance: **{irradiance} W/m²**, Temperature: **{temperature} °C**")

    st.divider()

    # ── Run / display simulation ─────────────────────────────────────────────
    if run_btn or "sim_results" not in st.session_state:
        with st.spinner("⚙️ Running FMU Co-Simulation…"):
            results = run_fmu_simulation(temperature, irradiance)
            if results is None:
                results = analytical_estimate(temperature, irradiance)
                results["is_estimate"] = True
            else:
                results["is_estimate"] = False
        st.session_state["sim_results"] = results
        st.session_state["sim_inputs"]  = (temperature, irradiance)

    results = st.session_state.get("sim_results")
    sim_T, sim_G = st.session_state.get("sim_inputs", (temperature, irradiance))

    if results is None:
        st.info("Press **▶ Run Simulation** to start.")
        return

    if results.get("is_estimate"):
        st.warning(
            "ℹ️ FMU not available — showing **analytical estimate** based on PV physics. "
            "Upload `model.fmu` to the app directory for full co-simulation."
        )

    # ── Simulation inputs ────────────────────────────────────────────────────
    st.subheader("📥 Simulation Inputs")
    si1, si2 = st.columns(2)
    si1.metric("🌡 Temperature used", f"{sim_T:.1f} °C")
    si2.metric("☀️ Irradiance used",  f"{sim_G:.0f} W/m²")

    st.divider()

    # ── PV / MPPT results ────────────────────────────────────────────────────
    st.subheader("🔆 PV Panel & MPPT Results")
    r1, r2, r3 = st.columns(3)
    r1.metric("Panel Power Ppanneau",    f"{results['panel_power']:.1f} W")
    r2.metric("Boost Power Pbooste",     f"{results['boost_power']:.1f} W")
    r3.metric("Inverter Voltage Vonduleur", f"{results['inverter_voltage']:.2f} V")

    # ── Inverter / Grid results ──────────────────────────────────────────────
    st.subheader("⚡ Inverter & Grid Power Quality")
    g1, g2, g3, g4, g5 = st.columns(5)
    g1.metric("Active Power P",    f"{results['active_power']:.1f} W")
    g2.metric("Reactive Power Q",  f"{results['reactive_power']:.1f} VAR")
    g3.metric("Apparent Power S",  f"{results['apparent_power']:.1f} VA")
    g4.metric("THD Voltage",       f"{results['thd_voltage']:.2f} %")
    g5.metric("THD Current",       f"{results['thd_current']:.2f} %")

    st.metric("Inverter Efficiency η", f"{results['efficiency']:.2f} %")

    st.divider()

    # ── Power time-series chart ──────────────────────────────────────────────
    st.subheader("📈 Power Time-Series (Simulation Window)")
    df: pd.DataFrame = results["df"]

    # Select columns that exist and are numeric
    plot_cols = [c for c in ["Ppanneau", "P_ondu", "Pbooste"] if c in df.columns]
    if plot_cols:
        chart_df = df.set_index("time")[plot_cols].rename(columns={
            "Ppanneau": "Panel Power (W)",
            "P_ondu":   "Active Power (W)",
            "Pbooste":  "Boost Power (W)",
        })
        st.line_chart(chart_df, height=320)

    # ── Voltage chart ────────────────────────────────────────────────────────
    if "Vonduleur" in df.columns:
        st.subheader("🔌 Inverter Output Voltage (V)")
        st.line_chart(df.set_index("time")[["Vonduleur"]].rename(
            columns={"Vonduleur": "Voltage (V)"}), height=220)

    # ── Raw data expander ────────────────────────────────────────────────────
    with st.expander("🗂 Raw simulation data (DataFrame)"):
        st.dataframe(df.round(4), use_container_width=True)

    # ── Footer ───────────────────────────────────────────────────────────────
    st.divider()
    st.caption(
        "Digital Twin · PV_MPPT_Inverter1 · FMI 2.0 Co-Simulation  |  "
        "Weather: [Open-Meteo](https://open-meteo.com/)  |  "
        "Built with [Streamlit](https://streamlit.io/) + [fmpy](https://github.com/CATIA-Systems/FMPy)"
    )


if __name__ == "__main__":
    main()
