# ════════════════════════════════════════════════════════════════════
# DIGITAL TWIN PV — MERGED DASHBOARD
# ENSET Mohammedia — Comparative Architecture
# Combines: MQTT Real-Time UI  +  pvlib Analytical Model  +  Open-Meteo
# Architecture: MATLAB/Simulink (via MQTT) vs pvlib (Theoretical Baseline)
# ════════════════════════════════════════════════════════════════════

import streamlit as st
import paho.mqtt.client as mqtt
import pandas as pd
import numpy as np
import time
import plotly.graph_objects as go
import plotly.subplots as sp
import requests
import base64
import warnings
from io import StringIO
from datetime import datetime, timedelta
import pathlib
import streamlit.components.v1 as components

# ── Optional pvlib import ────────────────────────────────────────
try:
    import pvlib
    from pvlib import location, irradiance, atmosphere, temperature
    from pvlib.location import Location
    PVLIB_AVAILABLE = True
except ImportError:
    PVLIB_AVAILABLE = False

warnings.simplefilter(action='ignore', category=FutureWarning)

# ════════════════════════════════════════════════════════════════════
# CONFIGURATION CONSTANTS
# ════════════════════════════════════════════════════════════════════
TIME_SLEEP   = 0.001       # Dashboard refresh rate (seconds)
RECORD_EVERY = 1.0         # CSV history sampling interval (seconds)
MAX_HISTORY  = 10_000      # Max history points

# ── Site Parameters (Mohammedia) ─────────────────────────────────
LAT       = 33.6861
LON       = -7.3833
ALTITUDE  = 15
TIMEZONE  = 'Africa/Casablanca'
SITE_NAME = 'Mohammedia, Maroc'

# ── PV Panel: Cell Amrecan OS-P72-330W ──────────────────────────
TILT        = 31           # Optimal tilt for latitude ~33°
AZIMUTH     = 180          # True South
SURFACE     = 1.939        # m² per panel
EFF_STC     = 0.170        # STC efficiency (17%)
NB_PANELS   = 12
GAMMA_PMAX  = -0.0040      # Thermal coefficient (%/°C)
T_STC       = 25.0
EFF_SYSTEM  = 0.65         # BOS + inverter efficiency
PNOM        = NB_PANELS * SURFACE * EFF_STC * 1000  # Nominal power (W)

# ── MQTT Configuration ───────────────────────────────────────────
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

# ── Open-Meteo Forecast API URL ──────────────────────────────────
OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"

# ── Color Palette ────────────────────────────────────────────────
C = {
    "bg":     "#0d1117",
    "panel":  "#161b22",
    "border": "#2a3547",
    "green":  "#00d1b2",
    "blue":   "#3b82f6",
    "amber":  "#f59e0b",
    "red":    "#ef4444",
    "muted":  "#8fa3bf",
    "text":   "#e8edf5",
    "purple": "#a855f7",
    "pink":   "#ec4899",
}


# ════════════════════════════════════════════════════════════════════
# SECTION 1 — UTILITIES
# ════════════════════════════════════════════════════════════════════

def load_logo_base64(filepath: str) -> str:
    """Load an image file and return its base64-encoded string."""
    try:
        with open(filepath, 'rb') as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return ""


def apply_global_css():
    """Inject global dark-theme CSS into the Streamlit app."""
    st.markdown("""
    <style>
    .stMetric {
        background-color: #161b22;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #2a3547;
    }
    .main { background-color: #0d1117; }
    [data-testid="stSidebar"] {
        background-color: #1a1d2e;
        border-right: 1px solid #2a3547;
    }
    .section-header {
        font-size: 1.1rem;
        font-weight: 700;
        color: #00d1b2;
        border-left: 4px solid #00d1b2;
        padding-left: 10px;
        margin: 18px 0 10px 0;
    }
    .delta-positive { color: #00d1b2; font-weight: bold; }
    .delta-negative { color: #ef4444; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# SECTION 2 — GLOBAL STATE (cached across reruns)
# ════════════════════════════════════════════════════════════════════

@st.cache_resource
def get_global_store() -> dict:
    """
    Single shared state object. Cached so it persists across all
    Streamlit reruns within the same process.
    """
    return {
        # Live MQTT values
        "store":          {k: 0.0 for k in TOPICS_MAP.values()},
        # Time-series history for CSV export and charts
        "history":        [],
        # MQTT status flags
        "connected":      False,
        "last_error":     "",
        "last_record":    0.0,
        # Open-Meteo + pvlib results cache
        "weather_cache":  None,      # Raw Open-Meteo JSON
        "pvlib_result":   None,      # pd.DataFrame from pvlib run
        "weather_ts":     0.0,       # Timestamp of last weather fetch
        # Comparative history: (timestamp, P_mqtt, P_pvlib)
        "compare_hist":   [],
    }

global_data  = get_global_store()
data_store   = global_data["store"]
history_list = global_data["history"]


# ════════════════════════════════════════════════════════════════════
# SECTION 3 — MQTT SERVICE
# ════════════════════════════════════════════════════════════════════

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
    """
    Start MQTT client in background thread. Cached so it is only
    instantiated once, even across hot-reloads.
    """
    try:
        uid    = f"DT_PV_{int(time.time())}"
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


# ════════════════════════════════════════════════════════════════════
# SECTION 4 — OPEN-METEO WEATHER FETCHER
# ════════════════════════════════════════════════════════════════════

WEATHER_REFRESH_INTERVAL = 600  # Refresh Open-Meteo every 10 minutes


def fetch_openmeteo_forecast() -> dict | None:
    """
    Fetch hourly solar irradiance + temperature from Open-Meteo
    for today (and next 24 h). Returns raw JSON dict or None on error.
    """
    try:
        params = {
            "latitude":   LAT,
            "longitude":  LON,
            "hourly": (
                "shortwave_radiation,"
                "direct_normal_irradiance,"
                "diffuse_radiation,"
                "temperature_2m,"
                "windspeed_10m"
            ),
            "forecast_days": 2,
            "timezone":  TIMEZONE,
        }
        resp = requests.get(OPENMETEO_URL, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        global_data["last_error"] = f"Open-Meteo: {e}"
        return None


def get_current_weather_values(raw: dict) -> dict:
    """
    Extract the current-hour slice from an Open-Meteo JSON response.
    Returns a dict with GHI, DNI, DHI, Temp, Wind keys.
    """
    try:
        times = pd.to_datetime(raw["hourly"]["time"])
        now   = pd.Timestamp.now()
        # Find the closest past hour in the forecast
        idx = np.searchsorted(times, now, side='right') - 1
        idx = max(0, min(idx, len(times) - 1))
        return {
            "GHI":  float(raw["hourly"]["shortwave_radiation"][idx]),
            "DNI":  float(raw["hourly"]["direct_normal_irradiance"][idx]),
            "DHI":  float(raw["hourly"]["diffuse_radiation"][idx]),
            "Temp": float(raw["hourly"]["temperature_2m"][idx]),
            "Wind": float(raw["hourly"]["windspeed_10m"][idx]),
            "time": times[idx],
        }
    except Exception:
        return {"GHI": 0, "DNI": 0, "DHI": 0, "Temp": 25, "Wind": 1, "time": None}


def maybe_refresh_weather():
    """
    Refresh Open-Meteo only if the cache is stale (> WEATHER_REFRESH_INTERVAL).
    Thread-safe via the @st.cache_resource singleton pattern.
    """
    now = time.time()
    if now - global_data["weather_ts"] > WEATHER_REFRESH_INTERVAL:
        raw = fetch_openmeteo_forecast()
        if raw:
            global_data["weather_cache"] = raw
            global_data["weather_ts"]    = now


# ════════════════════════════════════════════════════════════════════
# SECTION 5 — PVLIB ANALYTICAL MODEL (Model B)
# ════════════════════════════════════════════════════════════════════

def pvlib_calculate_power(weather: dict) -> dict:
    """
    Model B — Analytical baseline via pvlib.

    Given current-hour weather data (GHI, DNI, DHI, Temp, Wind),
    returns:
      - P_DC_pvlib  (W)   : DC power from array
      - P_AC_pvlib  (W)   : AC power at inverter output
      - T_module    (°C)  : Estimated cell temperature
      - POA         (W/m²): Plane-of-Array irradiance
    """
    if not PVLIB_AVAILABLE:
        return {"P_DC_pvlib": 0, "P_AC_pvlib": 0, "T_module": 0, "POA": 0}

    try:
        now   = pd.Timestamp.now(tz=TIMEZONE)
        site  = Location(LAT, LON, tz=TIMEZONE, altitude=ALTITUDE, name=SITE_NAME)
        times = pd.DatetimeIndex([now])

        # Solar position
        solar_pos = site.get_solarposition(times)

        # Extra-terrestrial radiation for Perez model
        dni_extra = irradiance.get_extra_radiation(times)

        # Plane-of-Array irradiance (Perez transposition model)
        poa = irradiance.get_total_irradiance(
            surface_tilt     = TILT,
            surface_azimuth  = AZIMUTH,
            solar_zenith     = solar_pos['apparent_zenith'],
            solar_azimuth    = solar_pos['azimuth'],
            dni              = weather["DNI"],
            ghi              = weather["GHI"],
            dhi              = weather["DHI"],
            dni_extra        = dni_extra,
            model            = 'perez',
        )
        poa_val = float(poa['poa_global'].clip(lower=0).iloc[0])

        # Module temperature (Faiman thermal model)
        t_mod = temperature.faiman(
            poa_global = poa_val,
            temp_air   = weather["Temp"],
            wind_speed = weather["Wind"],
        )
        t_mod_val = float(t_mod) if not isinstance(t_mod, pd.Series) else float(t_mod.iloc[0])

        # DC power with temperature de-rating
        P_dc = (
            (poa_val / 1000.0)
            * PNOM
            * (1.0 + GAMMA_PMAX * (t_mod_val - T_STC))
        )
        P_dc = max(0.0, P_dc)

        # AC power after system losses
        P_ac = max(0.0, P_dc * EFF_SYSTEM)

        return {
            "P_DC_pvlib": P_dc,
            "P_AC_pvlib": P_ac,
            "T_module":   t_mod_val,
            "POA":        poa_val,
        }
    except Exception as e:
        global_data["last_error"] = f"pvlib: {e}"
        return {"P_DC_pvlib": 0, "P_AC_pvlib": 0, "T_module": 0, "POA": 0}


# ════════════════════════════════════════════════════════════════════
# SECTION 6 — MATLAB / SIMULINK PLACEHOLDER (Model A)
# ════════════════════════════════════════════════════════════════════
#
# INTEGRATION NOTES:
# ------------------
# The physical MATLAB/Simulink model is assumed to push its outputs
# to the same MQTT broker under the topics defined in TOPICS_MAP.
# This is the existing live data already captured in `data_store`.
#
# If you prefer direct MATLAB Engine API integration, replace the
# `get_matlab_power()` stub below with your actual engine calls:
#
#   import matlab.engine
#   eng = matlab.engine.start_matlab()
#   eng.workspace['GHI']  = weather["GHI"]
#   eng.workspace['Temp'] = weather["Temp"]
#   eng.eval("run('pv_simulink_model.m')", nargout=0)
#   P_ac = eng.workspace['P_AC_output']
#
# For now, the MQTT-received P_inv is used as Model A output.

def get_matlab_power() -> float:
    """
    Model A — Physical/Simulink output.
    Returns AC power (W) as received from MATLAB via MQTT.
    Replace this function body with direct MATLAB Engine API calls
    if not using MQTT as the communication bridge.
    """
    return data_store.get("P_inv", 0.0)


# ════════════════════════════════════════════════════════════════════
# SECTION 7 — CHART FACTORY FUNCTIONS
# ════════════════════════════════════════════════════════════════════

CHART_LAYOUT = dict(
    template    = "plotly_dark",
    paper_bgcolor = "rgba(0,0,0,0)",
    plot_bgcolor  = "rgba(22,27,34,1)",
    margin      = dict(l=10, r=10, t=40, b=10),
    font        = dict(color=C["muted"]),
    showlegend  = True,
    legend      = dict(
        bgcolor     = "rgba(22,27,34,0.8)",
        bordercolor = C["border"],
        borderwidth = 1,
        font        = dict(color=C["text"], size=10),
    ),
)


def make_area_chart(y_data, color, fill_color, title,
                    y_min=0, y_max=10000, y_label="W") -> go.Figure:
    """Single-series filled area chart for power/voltage evolution."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=y_data, mode='lines', fill='tozeroy',
        line=dict(color=color, width=2),
        fillcolor=fill_color,
        name=title,
    ))
    fig.update_layout(
        **CHART_LAYOUT,
        title=dict(text=title, font=dict(color=C["text"], size=12)),
        height=260,
        yaxis=dict(title=y_label, range=[y_min, y_max], fixedrange=True,
                   gridcolor=C["border"]),
        xaxis=dict(title="Sample", gridcolor=C["border"]),
    )
    return fig


def make_line_chart(y_data, color, title,
                    y_min=0, y_max=600, y_label="V") -> go.Figure:
    """Single-series line chart for voltage evolution."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=y_data, mode='lines',
        line=dict(color=color, width=2),
        name=title,
    ))
    fig.update_layout(
        **CHART_LAYOUT,
        title=dict(text=title, font=dict(color=C["text"], size=12)),
        height=250,
        yaxis=dict(title=y_label, range=[y_min, y_max], fixedrange=True,
                   gridcolor=C["border"]),
        xaxis=dict(title="Sample", gridcolor=C["border"]),
    )
    return fig


def make_thd_bar_chart(thd_v: float, thd_i: float) -> go.Figure:
    """THD bar chart with IEC 5% norm line."""
    fig = go.Figure(go.Bar(
        x=["THD_V (%)", "THD_I (%)"],
        y=[thd_v, thd_i],
        marker_color=[C["blue"], C["pink"]],
        text=[f"{thd_v:.2f}%", f"{thd_i:.2f}%"],
        textposition='outside',
    ))
    fig.add_hline(
        y=5, line_dash="dash", line_color=C["amber"], line_width=2,
        annotation_text="Norme 5%", annotation_position="top right",
    )
    fig.update_layout(
        **CHART_LAYOUT,
        height=230,
        yaxis=dict(title="THD (%)", gridcolor=C["border"]),
        showlegend=False,
    )
    return fig


def make_comparative_chart(compare_hist: list) -> go.Figure:
    """
    Overlaid area chart: MATLAB (MQTT) vs pvlib power output.
    Also shows the delta (error band) between the two models.
    """
    if not compare_hist:
        fig = go.Figure()
        fig.update_layout(
            **CHART_LAYOUT,
            title=dict(text="En attente de données comparatives…",
                       font=dict(color=C["muted"])),
            height=380,
        )
        return fig

    df_c = pd.DataFrame(compare_hist, columns=["ts", "P_matlab", "P_pvlib"])
    x    = list(range(len(df_c)))

    fig = sp.make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.68, 0.32],
        vertical_spacing=0.05,
        subplot_titles=("Puissance AC : MATLAB vs pvlib (W)",
                        "Δ Erreur = MATLAB − pvlib (W)"),
    )

    # ── Top panel: overlaid power curves ────────────────────────
    fig.add_trace(go.Scatter(
        x=x, y=df_c["P_matlab"],
        mode='lines', fill='tozeroy',
        name="MATLAB / Simulink",
        line=dict(color=C["green"], width=2.5),
        fillcolor="rgba(0,209,178,0.12)",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=x, y=df_c["P_pvlib"],
        mode='lines', fill='tozeroy',
        name="pvlib (Théorique)",
        line=dict(color=C["blue"], width=2, dash='dot'),
        fillcolor="rgba(59,130,246,0.08)",
    ), row=1, col=1)

    # ── Bottom panel: delta / error ──────────────────────────────
    delta = df_c["P_matlab"] - df_c["P_pvlib"]
    colors_delta = [C["green"] if v >= 0 else C["red"] for v in delta]

    fig.add_trace(go.Bar(
        x=x, y=delta,
        name="Δ (MATLAB − pvlib)",
        marker_color=colors_delta,
        marker_line_width=0,
        opacity=0.75,
    ), row=2, col=1)

    fig.add_hline(y=0, line_dash="solid", line_color=C["muted"],
                  line_width=1, row=2, col=1)

    fig.update_layout(
        **CHART_LAYOUT,
        height=420,
        bargap=0.02,
    )
    fig.update_yaxes(title_text="Puissance (W)", gridcolor=C["border"], row=1, col=1)
    fig.update_yaxes(title_text="Δ (W)",         gridcolor=C["border"], row=2, col=1)
    fig.update_xaxes(title_text="Échantillon",   gridcolor=C["border"], row=2, col=1)

    return fig


def make_power_triangle_chart(P: float, Q: float, S: float) -> go.Figure:
    """
    Polar / bar representation of the power triangle:
    Active (P), Reactive (Q), Apparent (S).
    """
    fig = go.Figure(go.Bar(
        x=["P Active (W)", "Q Réactive (VAR)", "S Apparente (VA)"],
        y=[P, Q, S],
        marker_color=[C["green"], C["amber"], C["blue"]],
        text=[f"{P:.0f}", f"{Q:.0f}", f"{S:.0f}"],
        textposition='outside',
    ))
    fig.update_layout(
        **CHART_LAYOUT,
        height=220,
        showlegend=False,
        yaxis=dict(title="Valeur", gridcolor=C["border"]),
        margin=dict(l=5, r=5, t=10, b=5),
    )
    return fig


# ════════════════════════════════════════════════════════════════════
# SECTION 7b — 3D PANEL WIDGET
# ════════════════════════════════════════════════════════════════════

def render_3d_panel(p_inv: float, thd_v: float, thd_i: float):
    """
    Embed the interactive 3D PV panel widget (pv_panel_3d.html).

    Auto-selects the defect mode from live MQTT values:
      - ok   → P_inv normal, THD < 5 %
      - warn → THD entre 5 % et 8 %  OU  légère chute de puissance
      - err  → THD > 8 %  OU  P_inv quasi nul (panne détectée)
    """
    html_path = pathlib.Path(__file__).parent / "pv_panel_3d.html"
    if not html_path.exists():
        st.error("⚠️ Fichier `pv_panel_3d.html` introuvable — placez-le dans le même dossier.")
        return

    html_src = html_path.read_text(encoding="utf-8")

    # ── Détermination automatique du mode ────────────────────────
    if thd_v > 8 or thd_i > 8 or (0 < p_inv < 50):
        auto_mode = "err"
    elif thd_v > 5 or thd_i > 5:
        auto_mode = "warn"
    else:
        auto_mode = "ok"

    # ── Injection du script d'initialisation ─────────────────────
    inject = f"""
    <script>
    // Auto-apply mode derived from live MQTT data
    window.addEventListener('load', function() {{
        setMode('{auto_mode}');
    }});
    </script>
    """
    html_src = html_src.replace("</body>", inject + "\n</body>")

    components.html(html_src, height=620, scrolling=False)


# ════════════════════════════════════════════════════════════════════
# SECTION 8 — SIDEBAR RENDERER
# ════════════════════════════════════════════════════════════════════

def render_sidebar(img_b64: str, history_list: list, weather: dict | None):
    """Render the left sidebar with logo, status, export, and settings."""
    with st.sidebar:
        # ── Logo & branding ──────────────────────────────────────
        if img_b64:
            img_tag = f'<img src="data:image/jpeg;base64,{img_b64}" alt="ENSET" style="width:9rem;height:9rem;border-radius:50%;border:3px solid #00d1b2;">'
        else:
            img_tag = '<div style="font-size:4rem;">☀️</div>'

        st.markdown(f"""
        <div style="text-align:center;padding:20px 0;">
          {img_tag}
          <h2 style="color:#00d1b2;font-size:1.35rem;margin:10px 0 2px;">ENSET Mohammedia</h2>
          <p style="color:#aaa;font-size:0.78rem;margin:0;">Digital Twin — Système PV</p>
          <p style="color:#00d1b2;font-size:0.72rem;margin-top:6px;">2025 / 2026</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # ── MQTT status ──────────────────────────────────────────
        st.subheader("📡 Connexion MQTT")
        if global_data.get("connected"):
            st.success("✅ Broker connecté")
        else:
            st.error("🔴 Broker déconnecté")
        st.caption(f"Broker : `{BROKER}`")
        st.caption(f"Prefix : `{PREFIX}`")

        st.markdown("---")

        # ── Weather status ───────────────────────────────────────
        st.subheader("🌤️ Open-Meteo")
        if weather:
            age_min = (time.time() - global_data["weather_ts"]) / 60
            st.success(f"✅ Météo fraîche ({age_min:.0f} min)")
            st.caption(f"GHI  : {weather.get('GHI', 0):.1f} W/m²")
            st.caption(f"DNI  : {weather.get('DNI', 0):.1f} W/m²")
            st.caption(f"Temp : {weather.get('Temp', 0):.1f} °C")
        else:
            st.warning("⏳ Données météo non disponibles")

        st.markdown("---")

        # ── pvlib status ─────────────────────────────────────────
        st.subheader("🔬 Modèle pvlib")
        if PVLIB_AVAILABLE:
            st.success("✅ pvlib chargé")
            st.caption(f"Pnom : {PNOM:.0f} W")
            st.caption(f"Panneaux : {NB_PANELS} × 330 W")
            st.caption(f"Inclinaison : {TILT}° / Azimuth : {AZIMUTH}°")
        else:
            st.error("❌ pvlib non installé")
            st.caption("pip install pvlib")

        st.markdown("---")

        # ── CSV export ───────────────────────────────────────────
        st.subheader("📂 Export des données")
        if history_list:
            df_export = pd.DataFrame(history_list).astype(float)
            df_export.insert(0, "Sample", range(1, len(df_export) + 1))
            csv_buf = StringIO()
            df_export.to_csv(csv_buf, index=False, sep=";", decimal=",")
            st.download_button(
                label="⬇️ Télécharger CSV (Excel)",
                data=csv_buf.getvalue().encode("utf-8-sig"),
                file_name="digital_twin_pv_data.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.caption(f"📊 {len(history_list)} échantillons")
        else:
            st.info("Aucune donnée encore reçue.")

        st.markdown("---")

        # ── Settings info ────────────────────────────────────────
        st.subheader("⚙️ Paramètres")
        st.caption(f"Refresh dashboard : {TIME_SLEEP} s")
        st.caption(f"Enreg. CSV        : {RECORD_EVERY} s")
        st.caption(f"Historique max    : {MAX_HISTORY:,} pts")
        st.caption(f"Météo refresh     : {WEATHER_REFRESH_INTERVAL//60} min")
        st.caption(f"Site              : {SITE_NAME}")

        if global_data["last_error"]:
            st.warning(f"⚠️ {global_data['last_error']}")


# ════════════════════════════════════════════════════════════════════
# SECTION 9 — MAIN DASHBOARD RENDERER
# ════════════════════════════════════════════════════════════════════

def render_dashboard(current_vals: dict, df: pd.DataFrame,
                     pvlib_result: dict, weather: dict | None):
    """
    Render all dashboard sections inside the Streamlit placeholder.
    Organised into tabs for clarity.
    """
    tab_rt, tab_cmp, tab_elec, tab_thd, tab_3d = st.tabs([
        "⚡ Temps Réel (MQTT)",
        "📊 Analyse Comparative",
        "🔌 Grandeurs Électriques",
        "〰️ Qualité Réseau (THD)",
        "🧩 Vue 3D — Panneau PV",
    ])

    # ────────────────────────────────────────────────────────────
    # TAB 1 — Real-Time MQTT values
    # ────────────────────────────────────────────────────────────
    with tab_rt:
        # ── Row 1 : Power instantaneous values ──────────────────
        st.markdown('<p class="section-header">Puissances — Valeurs instantanées</p>',
                    unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("☀️ P_PV",       f"{current_vals['P_pv']:.1f} W")
        with c2: st.metric("⚡ P_Boost DC", f"{current_vals['P_dc']:.1f} W")
        with c3: st.metric("🔌 P_Onduleur", f"{current_vals['P_inv']:.1f} W")

        st.markdown(" ")

        # ── Row 2 : Voltages & efficiency ───────────────────────
        st.markdown('<p class="section-header">Tensions & Performance</p>',
                    unsafe_allow_html=True)
        v_rms = float(np.sqrt(np.mean(df['V_inv']**2))) if len(df) > 1 else 0.0
        eff   = (current_vals['P_inv'] / current_vals['P_pv'] * 100) \
                if current_vals['P_pv'] > 0 else 0.0

        c4, c5, c6 = st.columns(3)
        with c4: st.metric("🔁 V_inv RMS", f"{v_rms:.2f} V")
        with c5: st.metric("🌞 V_PV",      f"{current_vals['V_pv']:.1f} V")
        with c6: st.metric("📈 Rendement", f"{eff:.1f} %")

        st.markdown("---")

        # ── Row 3 : Power curves ─────────────────────────────────
        st.markdown('<p class="section-header">Évolution des Puissances Actives</p>',
                    unsafe_allow_html=True)
        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            st.plotly_chart(
                make_area_chart(df['P_pv'],  C["green"], 'rgba(0,209,178,0.15)',
                                'P_PV (W)', y_max=6700),
                use_container_width=True, key="ch_p_pv")
        with pc2:
            st.plotly_chart(
                make_area_chart(df['P_dc'],  C["amber"], 'rgba(245,158,11,0.15)',
                                'P_Boost DC (W)', y_max=5500),
                use_container_width=True, key="ch_p_dc")
        with pc3:
            st.plotly_chart(
                make_area_chart(df['P_inv'], C["pink"],  'rgba(236,72,153,0.15)',
                                'P_Onduleur AC (W)', y_max=5000),
                use_container_width=True, key="ch_p_inv")

        st.markdown("---")

        # ── Row 4 : Voltage curves ───────────────────────────────
        st.markdown('<p class="section-header">Évolution des Tensions</p>',
                    unsafe_allow_html=True)
        vc1, vc2, vc3 = st.columns(3)
        with vc1:
            st.plotly_chart(
                make_line_chart(df['V_pv'], C["green"], 'V_PV (V)',
                                y_max=315),
                use_container_width=True, key="ch_v_pv")
        with vc2:
            st.plotly_chart(
                make_line_chart(df['V_dc'], C["amber"], 'V_Bus DC (V)',
                                y_max=610),
                use_container_width=True, key="ch_v_dc")
        with vc3:
            st.plotly_chart(
                make_line_chart(df['V_inv'], C["blue"], 'V_Onduleur AC (V)',
                                y_max=220),
                use_container_width=True, key="ch_v_ac")

    # ────────────────────────────────────────────────────────────
    # TAB 2 — Comparative Analysis (MATLAB vs pvlib)
    # ────────────────────────────────────────────────────────────
    with tab_cmp:
        st.markdown('<p class="section-header">Modèle A (MATLAB/Simulink via MQTT) vs Modèle B (pvlib Analytique)</p>',
                    unsafe_allow_html=True)

        # ── Weather snapshot ────────────────────────────────────
        if weather:
            wc1, wc2, wc3, wc4 = st.columns(4)
            with wc1: st.metric("🌤️ GHI",  f"{weather.get('GHI',0):.1f} W/m²")
            with wc2: st.metric("🌡️ Temp", f"{weather.get('Temp',0):.1f} °C")
            with wc3: st.metric("💨 Vent", f"{weather.get('Wind',0):.1f} m/s")
            with wc4: st.metric("📐 POA",  f"{pvlib_result.get('POA',0):.1f} W/m²")
        else:
            st.info("⏳ En attente de données météo Open-Meteo…")

        st.markdown(" ")

        # ── Side-by-side model KPIs ──────────────────────────────
        st.markdown('<p class="section-header">Comparaison Instantanée</p>',
                    unsafe_allow_html=True)

        P_matlab = get_matlab_power()
        P_pvlib  = pvlib_result.get("P_AC_pvlib", 0.0)
        delta_P  = P_matlab - P_pvlib
        delta_pct = (delta_P / P_pvlib * 100) if P_pvlib > 1 else 0.0

        km1, km2, km3, km4 = st.columns(4)
        with km1:
            st.metric("🟢 MATLAB P_AC",    f"{P_matlab:.1f} W",
                      help="Puissance AC mesurée via MQTT (Simulink)")
        with km2:
            st.metric("🔵 pvlib P_AC",     f"{P_pvlib:.1f} W",
                      help="Puissance AC calculée par pvlib (baseline théorique)")
        with km3:
            sign = "+" if delta_P >= 0 else ""
            st.metric("Δ Puissance",       f"{sign}{delta_P:.1f} W",
                      delta=f"{sign}{delta_pct:.1f} %",
                      help="Différence absolue entre les deux modèles")
        with km4:
            t_mod = pvlib_result.get("T_module", 0)
            st.metric("🌡️ T_Module pvlib", f"{t_mod:.1f} °C",
                      help="Température cellule estimée (modèle Faiman)")

        st.markdown(" ")

        # ── Error interpretation banner ──────────────────────────
        abs_err = abs(delta_pct)
        if P_pvlib < 10:
            st.info("🌙 Irradiance trop faible — comparaison non significative.")
        elif abs_err < 5:
            st.success(f"✅ Modèles bien corrélés — écart relatif : {delta_pct:+.1f} %")
        elif abs_err < 15:
            st.warning(f"⚠️ Légère divergence entre modèles — écart : {delta_pct:+.1f} %")
        else:
            st.error(f"❌ Forte divergence détectée — écart : {delta_pct:+.1f} %")

        st.markdown("---")

        # ── Comparative time-series chart ────────────────────────
        st.markdown('<p class="section-header">Évolution Comparative (MATLAB vs pvlib)</p>',
                    unsafe_allow_html=True)
        st.plotly_chart(
            make_comparative_chart(global_data["compare_hist"]),
            use_container_width=True,
            key="ch_compare",
        )

        # ── pvlib detail metrics ─────────────────────────────────
        st.markdown("---")
        st.markdown('<p class="section-header">Détails du modèle pvlib</p>',
                    unsafe_allow_html=True)
        pd1, pd2, pd3 = st.columns(3)
        with pd1: st.metric("P_DC pvlib", f"{pvlib_result.get('P_DC_pvlib',0):.1f} W")
        with pd2: st.metric("P_AC pvlib", f"{pvlib_result.get('P_AC_pvlib',0):.1f} W")
        with pd3: st.metric("POA",        f"{pvlib_result.get('POA',0):.1f} W/m²")

        if not PVLIB_AVAILABLE:
            st.error("⚠️ pvlib non installé. Exécutez : `pip install pvlib`")

    # ────────────────────────────────────────────────────────────
    # TAB 3 — Electrical quantities (S, Q, P, FP)
    # ────────────────────────────────────────────────────────────
    with tab_elec:
        st.markdown('<p class="section-header">Puissances Apparente & Réactive</p>',
                    unsafe_allow_html=True)

        S_val = current_vals['S']
        Q_val = current_vals['Q']
        P_val = current_vals['P_inv']
        fp    = (P_val / S_val) if S_val > 0.1 else 0.0

        e1, e2, e3, e4 = st.columns(4)
        with e1: st.metric("🔵 S Apparente",          f"{S_val:.1f} VA")
        with e2: st.metric("🟠 Q Réactive",           f"{Q_val:.1f} VAR")
        with e3: st.metric("🟢 P Active",             f"{P_val:.1f} W")
        with e4: st.metric("📊 Facteur de Puissance", f"{fp:.3f}")

        st.markdown("---")

        # ── Power triangle chart ─────────────────────────────────
        st.markdown('<p class="section-header">Triangle des Puissances</p>',
                    unsafe_allow_html=True)
        col_tri, col_detail = st.columns([2, 1])
        with col_tri:
            st.plotly_chart(
                make_power_triangle_chart(P_val, Q_val, S_val),
                use_container_width=True, key="ch_pwr_tri",
            )
        with col_detail:
            st.markdown("**Interprétation**")
            fp_cat = "Excellent (≥ 0.95)" if fp >= 0.95 \
                else "Acceptable (0.85–0.95)" if fp >= 0.85 \
                else "À corriger (< 0.85)"
            st.info(f"FP : **{fp:.3f}** — {fp_cat}")
            if Q_val > 0:
                phi_deg = np.degrees(np.arctan2(Q_val, P_val)) if P_val > 0 else 90
                st.caption(f"φ = {phi_deg:.1f}°  (déphasage I/U)")
            st.caption(f"S² = P² + Q²")
            st.caption(f"  = {P_val**2:.0f} + {Q_val**2:.0f}")
            if S_val > 0:
                check = (P_val**2 + Q_val**2)**0.5
                st.caption(f"  ≈ {check:.1f} VA  (calculé)")

    # ────────────────────────────────────────────────────────────
    # TAB 4 — THD / Power Quality
    # ────────────────────────────────────────────────────────────
    with tab_thd:
        st.markdown('<p class="section-header">Distorsion Harmonique Totale (THD)</p>',
                    unsafe_allow_html=True)

        thd_v = current_vals['THD_V']
        thd_i = current_vals['THD_I']

        t1, t2, t3 = st.columns(3)
        with t1:
            st.metric("THD_V (Tension onduleur)", f"{thd_v:.2f} %")
            if thd_v < 5:
                st.success("✅ < 5 % — Conforme IEC")
            elif thd_v < 8:
                st.warning("⚠️ Légèrement élevé")
            else:
                st.error("❌ Hors norme")

        with t2:
            st.metric("THD_I (Courant onduleur)", f"{thd_i:.2f} %")
            if thd_i < 5:
                st.success("✅ < 5 % — Conforme IEC")
            elif thd_i < 8:
                st.warning("⚠️ Légèrement élevé")
            else:
                st.error("❌ Hors norme")

        with t3:
            st.plotly_chart(
                make_thd_bar_chart(thd_v, thd_i),
                use_container_width=True, key="ch_thd_bar",
            )

        st.markdown("---")
        st.markdown('<p class="section-header">Évolution THD dans le temps</p>',
                    unsafe_allow_html=True)
        if len(df) > 1:
            fig_thd_hist = go.Figure()
            fig_thd_hist.add_trace(go.Scatter(
                y=df['THD_V'], mode='lines', name="THD_V (%)",
                line=dict(color=C["blue"], width=1.8),
            ))
            fig_thd_hist.add_trace(go.Scatter(
                y=df['THD_I'], mode='lines', name="THD_I (%)",
                line=dict(color=C["pink"], width=1.8),
            ))
            fig_thd_hist.add_hline(
                y=5, line_dash="dash", line_color=C["amber"],
                annotation_text="Limite 5 %",
            )
            fig_thd_hist.update_layout(
                **CHART_LAYOUT,
                height=300,
                yaxis=dict(title="THD (%)", gridcolor=C["border"]),
                xaxis=dict(title="Échantillon", gridcolor=C["border"]),
            )
            st.plotly_chart(fig_thd_hist, use_container_width=True, key="ch_thd_hist")
        else:
            st.info("⏳ Historique insuffisant.")

    # ────────────────────────────────────────────────────────────
    # TAB 5 — Interactive 3D PV Panel
    # ────────────────────────────────────────────────────────────
    with tab_3d:
        st.markdown('<p class="section-header">Vue 3D — État du Panneau Solaire</p>',
                    unsafe_allow_html=True)

        # ── Live KPIs above the panel ────────────────────────────
        k1, k2, k3, k4 = st.columns(4)
        thd_v_live = current_vals['THD_V']
        thd_i_live = current_vals['THD_I']
        p_inv_live = current_vals['P_inv']

        # Determine status label & color for display
        if thd_v_live > 8 or thd_i_live > 8 or (0 < p_inv_live < 50):
            status_label = "❌ PANNE CRITIQUE"
            status_color = C["red"]
        elif thd_v_live > 5 or thd_i_live > 5:
            status_label = "⚠️ DÉFAUT PARTIEL"
            status_color = C["amber"]
        else:
            status_label = "✅ NOMINAL"
            status_color = C["green"]

        with k1: st.metric("🔌 P_Onduleur",  f"{p_inv_live:.1f} W")
        with k2: st.metric("〰️ THD_V",       f"{thd_v_live:.2f} %")
        with k3: st.metric("〰️ THD_I",       f"{thd_i_live:.2f} %")
        with k4:
            st.markdown(
                f'<div style="background:{status_color}22;border:1px solid {status_color};"'
                f' class="stMetric"><p style="font-size:0.75rem;color:{C["muted"]};margin:0;">'
                f'Diagnostic Auto</p>'
                f'<p style="font-size:1rem;font-weight:700;color:{status_color};margin:4px 0 0;">'
                f'{status_label}</p></div>',
                unsafe_allow_html=True,
            )

        st.markdown(" ")
        st.caption(
            "🖱️ **Glisser** pour faire pivoter le panneau · "
            "**Cliquer** sur une cellule pour voir ses paramètres · "
            "Les boutons Normal / Défaut / Panne permettent de simuler des scénarios"
        )
        st.markdown("---")

        # ── 3D Panel widget ──────────────────────────────────────
        render_3d_panel(
            p_inv = p_inv_live,
            thd_v = thd_v_live,
            thd_i = thd_i_live,
        )


# ════════════════════════════════════════════════════════════════════
# SECTION 10 — APPLICATION ENTRY POINT
# ════════════════════════════════════════════════════════════════════

def main():
    # ── Page config ──────────────────────────────────────────────
    st.set_page_config(
        page_title="Digital Twin PV — ENSET",
        layout="wide",
        page_icon="☀️",
    )
    apply_global_css()

    # ── Load logo ────────────────────────────────────────────────
    img_b64 = load_logo_base64("th.jpg")

    # ── Start MQTT (background thread, cached) ───────────────────
    start_mqtt_service()

    # ── Page title ───────────────────────────────────────────────
    st.markdown("""
    <h1 style="color:#00d1b2;margin-bottom:0;">
      ☀️ Digital Twin PV — ENSET Mohammedia
    </h1>
    <p style="color:#8fa3bf;margin-top:4px;font-size:0.9rem;">
      Architecture comparative : MATLAB/Simulink (MQTT) ⟷ pvlib (Analytique) ⟷ Open-Meteo (Météo temps réel)
    </p>
    """, unsafe_allow_html=True)

    # ── Main loop placeholder ────────────────────────────────────
    placeholder = st.empty()

    while True:
        try:
            now          = time.time()
            current_vals = data_store.copy()

            # ── 1. Record history sample ──────────────────────────
            if now - global_data["last_record"] >= RECORD_EVERY:
                history_list.append(current_vals.copy())
                global_data["last_record"] = now
                if len(history_list) > MAX_HISTORY:
                    history_list.pop(0)

            # ── 2. Refresh Open-Meteo weather (throttled) ─────────
            maybe_refresh_weather()
            raw_weather = global_data.get("weather_cache")
            weather     = get_current_weather_values(raw_weather) if raw_weather else None

            # ── 3. Run pvlib model ────────────────────────────────
            pvlib_result = pvlib_calculate_power(weather) if weather else \
                           {"P_DC_pvlib": 0, "P_AC_pvlib": 0, "T_module": 0, "POA": 0}

            # ── 4. Append to comparative history ─────────────────
            cmp_entry = (now, get_matlab_power(), pvlib_result["P_AC_pvlib"])
            global_data["compare_hist"].append(cmp_entry)
            if len(global_data["compare_hist"]) > MAX_HISTORY:
                global_data["compare_hist"].pop(0)

            # ── 5. Build history DataFrame ────────────────────────
            if history_list:
                df = pd.DataFrame(history_list).astype(float)
                # Ensure all required columns exist
                for col in TOPICS_MAP.values():
                    if col not in df.columns:
                        df[col] = 0.0
            else:
                df = pd.DataFrame({k: [0.0] for k in TOPICS_MAP.values()})

            # ── 6. Sidebar ────────────────────────────────────────
            render_sidebar(img_b64, history_list, weather)

            # ── 7. Waiting state check ────────────────────────────
            data_present = not (
                current_vals["P_pv"] == 0 and
                current_vals["V_inv"] == 0 and
                current_vals["P_inv"] == 0
            )

            with placeholder.container():
                if not data_present:
                    col_wait, col_info = st.columns(2)
                    with col_wait:
                        st.warning("⏳ En attente de données MQTT…")
                        st.caption(f"Topics surveillés sous : `{PREFIX}`")
                    with col_info:
                        if weather:
                            st.info(
                                f"🌤️ Météo Open-Meteo disponible | "
                                f"GHI={weather.get('GHI',0):.0f} W/m²  "
                                f"T={weather.get('Temp',0):.1f}°C"
                            )
                            st.caption(
                                f"pvlib P_AC théorique : "
                                f"**{pvlib_result.get('P_AC_pvlib',0):.1f} W**"
                            )
                        else:
                            st.info("🌐 Connexion à Open-Meteo en cours…")
                else:
                    render_dashboard(current_vals, df, pvlib_result, weather)

        except Exception as e:
            # Silently absorb transient errors to keep the loop alive
            global_data["last_error"] = str(e)

        time.sleep(TIME_SLEEP)


# ════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    main()
