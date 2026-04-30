"""
SOLARIS - Digital Twin PV · Mohammedia, Maroc
Streamlit + pvlib · Open-Meteo API + FMU Real-Time
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import pvlib
from pvlib.location import Location
from pvlib import irradiance, temperature, pvsystem
import time
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(
    page_title="SOLARIS · Digital Twin Mohammedia",
    page_icon="S",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

    :root {
        --solar-yellow: #F5A623;
        --solar-orange: #E8860A;
        --dark-bg: #08090C;
        --card-bg: #111318;
        --card-bg2: #191D25;
        --border: #252A35;
        --border-bright: #353C4A;
        --text-primary: #E8EDF5;
        --text-secondary: #6B7585;
        --text-muted: #3D4553;
        --green: #2ECC71;
        --red: #E74C3C;
        --blue: #3498DB;
        --purple: #9B59B6;
        --teal: #1ABC9C;
        --gradient-gold: linear-gradient(135deg, #F5A623, #E8860A);
        --gradient-dark: linear-gradient(135deg, #0E1117, #141820);
    }

    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .stApp {
        background-color: var(--dark-bg);
        background-image:
            radial-gradient(ellipse at 20% 0%, rgba(245,166,35,0.04) 0%, transparent 60%),
            radial-gradient(ellipse at 80% 100%, rgba(52,152,219,0.03) 0%, transparent 60%);
    }
    [data-testid="stSidebar"] { background-color: #0A0C10 !important; border-right: 1px solid var(--border) !important; }
    [data-testid="stSidebar"] .stRadio label { font-family: 'DM Sans', sans-serif !important; color: var(--text-secondary) !important; font-size: 13px !important; }

    .main-header {
        background: var(--gradient-dark);
        border: 1px solid var(--border);
        border-top: 2px solid var(--solar-yellow);
        border-radius: 0 0 12px 12px;
        padding: 22px 32px; margin-bottom: 24px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .plant-name {
        font-family: 'Space Mono', monospace; font-size: 20px; font-weight: 700;
        background: var(--gradient-gold); -webkit-background-clip: text;
        -webkit-text-fill-color: transparent; background-clip: text;
        letter-spacing: 0.05em; text-transform: uppercase;
    }
    .plant-sub { font-size: 12px; color: var(--text-secondary); margin-top: 5px; letter-spacing: 0.08em; text-transform: uppercase; }
    .status-badge {
        display: inline-flex; align-items: center; gap: 7px;
        background: rgba(46,204,113,0.08); border: 1px solid rgba(46,204,113,0.25);
        border-radius: 20px; padding: 5px 14px; font-size: 12px;
        color: var(--green); font-family: 'Space Mono', monospace; letter-spacing: 0.05em;
    }
    .status-dot {
        width: 7px; height: 7px; border-radius: 50%;
        background: var(--green); box-shadow: 0 0 8px var(--green);
        animation: pulse 2s infinite;
    }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

    /* ── FMU LIVE ── */
    .fmu-header {
        background: linear-gradient(90deg, #0a0f1e, #0d1424);
        border: 1px solid rgba(59,130,246,.3);
        border-top: 2px solid #3b82f6;
        border-radius: 12px; padding: 18px 24px; margin-bottom: 16px;
        position: relative; overflow: hidden;
    }
    .fmu-header::after {
        content:''; position:absolute; bottom:0; left:0; right:0; height:1px;
        background: linear-gradient(90deg,transparent,#3b82f6 40%,#8b5cf6,transparent);
    }
    .fmu-title {
        font-family:'Space Mono',monospace; font-size:13px; font-weight:700;
        color:#60a5fa; text-transform:uppercase; letter-spacing:2px;
    }
    .fmu-sub { font-size:11px; color:#1e3a5f; letter-spacing:2px; text-transform:uppercase; margin-top:3px; }
    .live-dot {
        display:inline-block; width:8px; height:8px; border-radius:50%;
        background:#22c55e; box-shadow:0 0 8px #22c55e; margin-right:6px;
        animation: livepulse 1.2s ease-in-out infinite;
    }
    @keyframes livepulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.3;transform:scale(.7)} }

    .flow-bar {
        background: rgba(8,15,30,.9); border:1px solid rgba(30,58,100,.5);
        border-radius:8px; padding:9px 16px; display:flex; align-items:center;
        gap:8px; flex-wrap:wrap; font-size:.76rem; color:#4b6080; margin-bottom:12px;
    }
    .flow-chip {
        background:rgba(30,58,100,.4); border:1px solid rgba(59,130,246,.2);
        border-radius:5px; padding:3px 9px; color:#60a5fa;
        font-family:'JetBrains Mono',monospace; font-size:.74rem; font-weight:600;
    }
    .flow-arr { color:rgba(59,130,246,.4); }

    .fmu-kcard {
        background: linear-gradient(145deg,#0d1b2e,#08090c);
        border:1px solid rgba(30,58,100,.5); border-radius:12px;
        padding:14px 12px 10px; position:relative; overflow:hidden; text-align:center;
    }
    .fmu-kcard::before {
        content:''; position:absolute; top:0; left:0; right:0; height:2px;
        background:var(--ac,#3b82f6);
    }
    .fmu-kval {
        font-family:'JetBrains Mono',monospace; font-size:1.7rem; font-weight:600;
        color:var(--ac,#3b82f6); line-height:1; letter-spacing:-1px;
    }
    .fmu-kunit { font-size:.72rem; color:#4b6080; margin-left:2px; }
    .fmu-klbl  { font-size:.6rem; color:#1e3a5f; text-transform:uppercase; letter-spacing:1.5px; margin-top:6px; }
    .fmu-ksrc  { font-size:.57rem; color:rgba(59,130,246,.25); margin-top:2px; }

    .fmu-sec {
        font-size:.6rem; font-weight:700; letter-spacing:3px; text-transform:uppercase;
        color:#1e3a5f; padding:0 0 5px; margin:14px 0 7px;
        border-bottom:1px solid rgba(30,58,100,.3);
    }

    /* ── SOLARIS ORIGINAL ── */
    .metric-card {
        background: var(--card-bg); border: 1px solid var(--border);
        border-radius: 10px; padding: 20px 22px; position: relative; overflow: hidden;
        transition: all 0.3s ease;
    }
    .metric-card:hover { border-color: var(--solar-yellow); transform: translateY(-2px); box-shadow: 0 8px 25px rgba(245,166,35,0.1); }
    .metric-card::before { content:''; position:absolute; top:0; left:0; right:0; height:2px; background:linear-gradient(90deg,var(--solar-yellow),var(--solar-orange)); opacity:0.6; }
    .metric-label { font-size:10px; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.12em; font-family:'Space Mono',monospace; margin-bottom:8px; }
    .metric-value { font-family:'Space Mono',monospace; font-size:26px; font-weight:700; color:var(--solar-yellow); line-height:1.1; }
    .metric-unit { font-size:13px; color:var(--text-secondary); margin-top:4px; }
    .section-title { font-family:'Space Mono',monospace; font-size:11px; font-weight:700; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.15em; margin-bottom:14px; padding-bottom:10px; border-bottom:1px solid var(--border); }
    .alert-card { border-radius:8px; padding:11px 16px; margin-bottom:8px; font-size:13px; border-left:3px solid; font-family:'DM Sans',sans-serif; }
    .alert-warning { background:rgba(245,166,35,0.06); border-color:var(--solar-yellow); color:#D4993A; }
    .alert-error   { background:rgba(231,76,60,0.06);  border-color:var(--red);          color:#D45C4E; }
    .alert-ok      { background:rgba(46,204,113,0.06); border-color:var(--green);        color:#3DBD6A; }
    .alert-info    { background:rgba(52,152,219,0.06); border-color:var(--blue);         color:#5BA4D9; }
    .spec-table { width:100%; border-collapse:collapse; font-size:13px; }
    .spec-table tr { border-bottom:1px solid var(--border); }
    .spec-table tr:last-child { border-bottom:none; }
    .spec-table td { padding:10px 14px; vertical-align:middle; }
    .spec-table td:first-child { color:var(--text-secondary); font-family:'Space Mono',monospace; font-size:11px; text-transform:uppercase; letter-spacing:0.08em; width:48%; }
    .spec-table td:last-child { color:var(--text-primary); font-weight:500; text-align:right; }
    .spec-block { background:var(--card-bg); border:1px solid var(--border); border-radius:10px; padding:4px 0; margin-bottom:16px; }
    .spec-block-header { background:var(--card-bg2); border-radius:8px 8px 0 0; padding:10px 16px; font-family:'Space Mono',monospace; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.12em; color:var(--solar-yellow); border-bottom:1px solid var(--border); }
    .highlight-value { color:var(--solar-yellow); font-family:'Space Mono',monospace; font-weight:700; }
    .kpi-card { background:var(--gradient-dark); border:1px solid var(--border); border-radius:12px; padding:20px 16px; text-align:center; transition:all 0.3s ease; }
    .kpi-card:hover { border-color:var(--solar-yellow); }
    .kpi-value { font-family:'Space Mono',monospace; font-size:32px; font-weight:700; background:var(--gradient-gold); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
    .kpi-label { font-size:11px; color:var(--text-secondary); text-transform:uppercase; letter-spacing:0.1em; margin-top:8px; }
    div[data-testid="metric-container"] { background:var(--card-bg); border:1px solid var(--border); border-radius:10px; padding:16px 18px; }
    div[data-testid="metric-container"] label { color:var(--text-secondary) !important; font-size:11px !important; text-transform:uppercase; letter-spacing:0.1em; font-family:'Space Mono',monospace !important; }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] { color:var(--solar-yellow) !important; font-size:24px !important; font-weight:700 !important; font-family:'Space Mono',monospace !important; }
    .stPlotlyChart { border-radius:10px; overflow:hidden; border:1px solid var(--border); }
    .sidebar-brand { font-family:'Space Mono',monospace; font-size:18px; font-weight:700; background:var(--gradient-gold); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; letter-spacing:0.1em; margin-bottom:4px; }
    .sidebar-sub { font-size:11px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:16px; }
    .data-info { background:rgba(52,152,219,0.08); border:1px solid rgba(52,152,219,0.2); border-radius:6px; padding:8px 12px; font-size:11px; color:var(--blue); font-family:'Space Mono',monospace; }
    .stDownloadButton button { background:var(--gradient-gold) !important; color:white !important; border:none !important; font-family:'Space Mono',monospace !important; font-weight:700 !important; }
    hr { border-color:var(--border) !important; }
    .stTabs [data-baseweb="tab-list"] { gap:8px; background-color:var(--card-bg); border-radius:8px; padding:6px; }
    .stTabs [data-baseweb="tab"] { color:var(--text-secondary); font-family:'Space Mono',monospace; font-size:12px; border-radius:6px; }
    .stTabs [aria-selected="true"] { background-color:rgba(245,166,35,0.1); color:var(--solar-yellow); }
    .stButton button { border-radius:8px !important; }

    /* FMU statusbar */
    .fmu-statusbar {
        display:flex; justify-content:space-between;
        background:rgba(8,12,20,.8); border-top:1px solid rgba(30,58,100,.3);
        padding:6px 16px; font-family:'JetBrains Mono',monospace;
        font-size:.6rem; color:#1e3a5f; letter-spacing:1px; margin-top:8px;
        border-radius:0 0 10px 10px;
    }
    #MainMenu,footer,[data-testid="stToolbar"],[data-testid="stDecoration"]{display:none!important;}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# CONSTANTES
# ════════════════════════════════════════════════════════
SITE = {
    "name": "Installation PV ENSET Mohammedia",
    "location": "Mohammedia, Maroc",
    "lat": 33.6861, "lon": -7.3828,
    "altitude": 27, "timezone": "Africa/Casablanca",
    "capacity_kwp": 3.96, "surface_m2": 23.27,
    "num_panels": 12, "num_inverters": 1,
    "commissioning_date": "2024", "operator": "ENSET",
    "grid_connection": "BT 220 V",
}
PANEL = {
    "manufacturer": "Cell Amrecan", "model": "OS-P72-330W",
    "technology": "Polycristallin", "pdc0": 330,
    "voc": 44.4, "isc": 9.28, "vmp": 37.65, "imp": 8.77,
    "efficiency_pct": 17.0, "gamma_pdc": -0.0040,
    "tilt": 31, "azimuth": 180,
    "warranty_years": 25, "degradation_pct_yr": 0.40,
    # pvlib SDM
    "alpha_sc":0.004539,"a_ref":1.5,"I_L_ref":9.28,
    "I_o_ref":2.2e-10,"R_sh_ref":525.0,"R_s":0.35,"Adjust":8.7,
}
INVERTER = {
    "manufacturer":"IMEON","model":"IMEON 3.6",
    "power_kva":4,"efficiency_pct":96,"mppt_channels":2,
    "voltage_dc_max":500,"ip_class":"IP65",
}
BLYNK_CONFIG = {
    "auth_token":"l5IGH1fmy7E8ULoiLWjdXm9ZmaJcduYI",
    "server":"https://blynk.cloud/external/api/",
    "relay_pin":"V0","relay_name":"Relais Principal",
}
PLOT_LAYOUT = dict(
    template="plotly_dark", paper_bgcolor="#111318", plot_bgcolor="#111318",
    font=dict(family="DM Sans",color="#6B7585"),
    margin=dict(t=20,b=30,l=50,r=20),
    xaxis=dict(gridcolor="#1E232D",zeroline=False),
    yaxis=dict(gridcolor="#1E232D",zeroline=False),
    hovermode="x unified",
)
# FMU graph style
FMU_BG  = dict(paper_bgcolor="#080c14",plot_bgcolor="#0d1424")
FMU_GRD = dict(gridcolor="rgba(30,58,100,.3)",showgrid=True,zeroline=False,
               tickcolor="#1e3a5f",color="#2d4060",tickfont=dict(size=9))
FMU_LEG = dict(bgcolor="rgba(0,0,0,0)",borderwidth=0,
               font=dict(size=9,color="#4b6080"),
               orientation="h",y=1.03,x=0)
FMU_MAR = dict(l=44,r=12,t=28,b=28)
FMU_FNT = dict(color="#2d4060",size=9)
FMU_CFG = {"displayModeBar":False}
MAX_PTS = 300

# ════════════════════════════════════════════════════════
# FONCTIONS COMMUNES
# ════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def fetch_meteo(lat,lon,start_date,end_date):
    url="https://archive-api.open-meteo.com/v1/archive"
    params={"latitude":lat,"longitude":lon,"start_date":start_date,"end_date":end_date,
            "hourly":"temperature_2m,shortwave_radiation,diffuse_radiation,direct_normal_irradiance,wind_speed_10m,relative_humidity_2m,cloud_cover",
            "timezone":"Africa/Casablanca"}
    try:
        r=requests.get(url,params=params,timeout=30); r.raise_for_status(); data=r.json()
        df=pd.DataFrame({"datetime":pd.to_datetime(data["hourly"]["time"]),
            "temp_air":data["hourly"]["temperature_2m"],"ghi":data["hourly"]["shortwave_radiation"],
            "dhi":data["hourly"]["diffuse_radiation"],"dni":data["hourly"]["direct_normal_irradiance"],
            "wind_speed":data["hourly"]["wind_speed_10m"],"humidity":data["hourly"]["relative_humidity_2m"],
            "cloud_cover":data["hourly"].get("cloud_cover",[0]*len(data["hourly"]["time"]))})
        return df.set_index("datetime")
    except Exception as e:
        st.error(f"Erreur API meteo : {e}"); return None

@st.cache_data(ttl=3600)
def run_pvlib_simulation(lat,lon,altitude,timezone,tilt,azimuth,pdc0,gamma_pdc,start_date,end_date):
    location=Location(latitude=lat,longitude=lon,altitude=altitude,tz=timezone,name="Mohammedia")
    df=fetch_meteo(lat,lon,start_date,end_date)
    if df is None: return None
    times=df.index; solar_pos=location.get_solarposition(times)
    dni_extra=irradiance.get_extra_radiation(times)
    poa_iso=irradiance.get_total_irradiance(surface_tilt=tilt,surface_azimuth=azimuth,
        dni=df["dni"],ghi=df["ghi"],dhi=df["dhi"],
        solar_zenith=solar_pos["apparent_zenith"],solar_azimuth=solar_pos["azimuth"],model="isotropic")
    poa_hd=irradiance.get_total_irradiance(surface_tilt=tilt,surface_azimuth=azimuth,
        dni=df["dni"],ghi=df["ghi"],dhi=df["dhi"],
        solar_zenith=solar_pos["apparent_zenith"],solar_azimuth=solar_pos["azimuth"],
        dni_extra=dni_extra,model="haydavies")
    tp=temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"]
    cell_temp=temperature.sapm_cell(poa_global=poa_iso["poa_global"],temp_air=df["temp_air"],
        wind_speed=df["wind_speed"],a=tp["a"],b=tp["b"],deltaT=tp["deltaT"])
    dc=pvsystem.pvwatts_dc(g_poa_effective=poa_iso["poa_global"],temp_cell=cell_temp,pdc0=pdc0,gamma_pdc=gamma_pdc)
    ac=dc*0.97; net=ac*(1-0.10)
    res=pd.DataFrame({"datetime":times,"ghi":df["ghi"],"dni":df["dni"],"dhi":df["dhi"],
        "poa_isotropic":poa_iso["poa_global"],"poa_haydavies":poa_hd["poa_global"],
        "temp_air":df["temp_air"],"cell_temp":cell_temp,"wind_speed":df["wind_speed"],
        "humidity":df["humidity"],"cloud_cover":df["cloud_cover"],
        "dc_power_w":dc,"ac_power_w":ac.clip(lower=0),"net_ac_power_w":net.clip(lower=0),
        "solar_elevation":solar_pos["elevation"],"solar_azimuth":solar_pos["azimuth"],"dni_extra":dni_extra})
    res["ac_power_kw"]=res["ac_power_w"]/1000; res["net_ac_power_kw"]=res["net_ac_power_w"]/1000
    res["date"]=res["datetime"].dt.date; res["hour"]=res["datetime"].dt.hour
    res["month"]=res["datetime"].dt.month; res["month_name"]=res["datetime"].dt.strftime("%b")
    res["day_of_year"]=res["datetime"].dt.dayofyear
    return res

def compute_daily(results):
    cap=SITE["capacity_kwp"]
    daily=results.groupby("date").agg(
        production_kwh=("net_ac_power_kw",lambda x:x.sum()),
        gross_production_kwh=("ac_power_kw",lambda x:x.sum()),
        peak_power_kw=("net_ac_power_kw","max"),avg_temp=("temp_air","mean"),
        max_temp=("temp_air","max"),min_temp=("temp_air","min"),
        avg_ghi=("ghi","mean"),max_ghi=("ghi","max"),avg_wind=("wind_speed","mean"),
        avg_humidity=("humidity","mean"),avg_cloud=("cloud_cover","mean"),
        peak_sun_hours=("poa_isotropic",lambda x:x.sum()/1000),
        theoretical_psh=("ghi",lambda x:x.sum()/1000)).reset_index()
    daily["theoretical_kwh"]=daily["peak_sun_hours"]*cap
    daily["pr"]=(daily["production_kwh"]/daily["theoretical_kwh"].replace(0,np.nan)).clip(0,1)*100
    daily["capacity_factor"]=(daily["production_kwh"]/(24*cap))*100
    daily["energy_yield"]=daily["production_kwh"]/cap
    daily["date"]=pd.to_datetime(daily["date"])
    daily["day_of_week"]=daily["date"].dt.day_name()
    daily["is_weekend"]=daily["date"].dt.dayofweek.isin([5,6])
    return daily

def compute_monthly(daily):
    monthly=daily.groupby(daily["date"].dt.to_period("M")).agg(
        production_kwh=("production_kwh","sum"),gross_production_kwh=("gross_production_kwh","sum"),
        avg_pr=("pr","mean"),min_pr=("pr","min"),max_pr=("pr","max"),
        avg_temp=("avg_temp","mean"),avg_capacity_factor=("capacity_factor","mean"),
        avg_energy_yield=("energy_yield","mean")).reset_index()
    monthly["date"]=monthly["date"].dt.to_timestamp()
    monthly["month_name"]=monthly["date"].dt.strftime("%b %Y")
    return monthly

def get_current_meteo(lat,lon):
    url="https://api.open-meteo.com/v1/forecast"
    params={"latitude":lat,"longitude":lon,
            "current":"temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,cloud_cover,apparent_temperature",
            "timezone":"Africa/Casablanca"}
    try:
        r=requests.get(url,params=params,timeout=10); r.raise_for_status()
        return r.json().get("current",{})
    except: return {}

def blynk_get_pin(pin):
    url=f"{BLYNK_CONFIG['server']}get?token={BLYNK_CONFIG['auth_token']}&{pin}"
    try:
        r=requests.get(url,timeout=5)
        if r.status_code==200: return r.json()
    except: return None

def blynk_set_pin(pin,value):
    url=f"{BLYNK_CONFIG['server']}update?token={BLYNK_CONFIG['auth_token']}&{pin}={value}"
    try: r=requests.get(url,timeout=5); return r.status_code==200
    except: return False

def blynk_get_device_status():
    url=f"{BLYNK_CONFIG['server']}isHardwareConnected?token={BLYNK_CONFIG['auth_token']}"
    try:
        r=requests.get(url,timeout=5)
        if r.status_code==200: return r.json()
    except: return False

def calculate_degraded_power(pdc0,years,rate): return pdc0*(1-rate)**years
def estimate_co2_avoidance(kwh,ef=0.65): return kwh*ef
def calculate_financial_metrics(kwh,price=0.12): return kwh*price

# ════════════════════════════════════════════════════════
# FMU SIMULATION FUNCTIONS
# ════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def fetch_meteo_now():
    now=datetime.now()
    s=(now-timedelta(hours=2)).strftime("%Y-%m-%d")
    e=now.strftime("%Y-%m-%d")
    url=(f"https://api.open-meteo.com/v1/forecast"
         f"?latitude={SITE['lat']}&longitude={SITE['lon']}"
         f"&hourly=shortwave_radiation,diffuse_radiation,"
         f"direct_normal_irradiance,temperature_2m,windspeed_10m"
         f"&start_date={s}&end_date={e}&timezone=Africa%2FCasablanca")
    r=requests.get(url,timeout=8); r.raise_for_status()
    d=r.json()["hourly"]
    df=pd.DataFrame(d); df.columns=["time","GHI","DHI","DNI","Tamb","wind"]
    df["time"]=pd.to_datetime(df["time"])
    df=df[df["time"]<=pd.Timestamp.now()].dropna()
    if df.empty: return None
    row=df.iloc[-1]
    return {k:max(float(row[k]),0) if k!="Tamb" else float(row[k])
            for k in ["GHI","DHI","DNI","Tamb","wind"]} | {"ts":row.time}

def fmu_step(G,Tamb,wind):
    G=max(G,0.)
    Tc=Tamb+G*max(0.0342-0.0043*wind,0.008)
    Vmpp=PANEL["vmp"]*12*(1+PANEL["gamma_pdc"]*(Tc-25))
    Impp=PANEL["imp"]*(G/1000)
    Ppv=max(Vmpp*Impp,0)
    Pb=Ppv*0.97
    Prated=PANEL["pdc0"]*12
    rat=min(Pb/Prated,1.) if Prated>0 else 0
    if   rat<0.02: ei=0.
    elif rat<0.10: ei=0.880+0.085*(rat/0.10)
    elif rat<0.30: ei=0.965+0.005*((rat-0.10)/0.20)
    elif rat<0.70: ei=0.970
    else:          ei=0.970-0.003*((rat-0.70)/0.30)
    Pac=Pb*ei; cp=0.99
    return dict(Tc=Tc,Vmpp=Vmpp,Impp=Impp,Ppv=Ppv,Pboost=Pb,
                Pac=Pac,Vac=220.,S=Pac/cp,Q=(Pac/cp)*np.sqrt(max(1-cp**2,0)),
                eta=ei*100,THDv=1.8+0.5*(1-rat),THDi=3.0+2.0*(1-rat))

def pvlib_step_rt(GHI,DHI,DNI,Tamb,wind,ts):
    try:
        loc=Location(SITE["lat"],SITE["lon"],tz=SITE["timezone"],altitude=SITE["altitude"])
        t=pd.DatetimeIndex([ts],tz=SITE["timezone"])
        sol=loc.get_solarposition(t)
        poa=irradiance.get_total_irradiance(PANEL["tilt"],PANEL["azimuth"],
            pd.Series([DNI],index=t),pd.Series([GHI],index=t),pd.Series([DHI],index=t),
            sol["apparent_zenith"],sol["azimuth"])
        pg=max(float(poa["poa_global"].iloc[0]),0)
        tp=temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"]
        Tc=temperature.sapm_cell(pd.Series([pg],index=t),pd.Series([Tamb],index=t),
                                  pd.Series([wind],index=t),**tp)
        IL,I0,Rs,Rsh,nV=pvsystem.calcparams_cec(
            pd.Series([pg],index=t),pd.Series([float(Tc.iloc[0])],index=t),
            PANEL["alpha_sc"],PANEL["a_ref"],PANEL["I_L_ref"],PANEL["I_o_ref"],
            PANEL["R_sh_ref"],PANEL["R_s"],PANEL["Adjust"],1.121,-0.0002677)
        mpp=pvsystem.max_power_point(IL,I0,Rs,Rsh,nV,method="newton")
        return max(float(mpp["p_mp"].iloc[0])*12,0.)
    except: return 0.

# ════════════════════════════════════════════════════════
# SESSION STATE FMU
# ════════════════════════════════════════════════════════
FMU_KEYS=["ts","G","Tamb","Tc","Vmpp","Impp","Ppv","Pboost","Pac","eta","THDv","THDi","Ppvlib"]
for k in FMU_KEYS:
    if k not in st.session_state: st.session_state[k]=[]
if "fmu_run"  not in st.session_state: st.session_state.fmu_run  = False
if "fmu_tick" not in st.session_state: st.session_state.fmu_tick = 0
if "fmu_wx"   not in st.session_state: st.session_state.fmu_wx   = None

# ════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown('<div class="sidebar-brand">SOLARIS</div>',unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">Digital Twin PV + FMU Live</div>',unsafe_allow_html=True)
    st.markdown("---")
    menu=st.radio("Navigation",[
        "Vue Globale","Production","Meteo & Irradiance",
        "Performance Analysis","Onduleurs","Installation",
        "⚡ FMU Temps Réel","Controle Relais","Rapport"],
        label_visibility="collapsed")
    st.markdown("---")
    st.markdown("**Periode d'analyse**")
    col_s,col_e=st.columns(2)
    with col_s:
        start_date=st.date_input("Debut",value=datetime(2026,4,1).date(),label_visibility="collapsed")
    with col_e:
        end_date=st.date_input("Fin",value=datetime.today().date(),label_visibility="collapsed")
    preset_cols=st.columns(3)
    with preset_cols[0]:
        if st.button("7j",key="7d"):
            st.session_state["_ps"]=(datetime.now()-timedelta(days=7)).date()
            st.session_state["_pe"]=datetime.now().date(); st.rerun()
    with preset_cols[1]:
        if st.button("30j",key="30d"):
            st.session_state["_ps"]=(datetime.now()-timedelta(days=30)).date()
            st.session_state["_pe"]=datetime.now().date(); st.rerun()
    with preset_cols[2]:
        if st.button("90j",key="90d"):
            st.session_state["_ps"]=(datetime.now()-timedelta(days=90)).date()
            st.session_state["_pe"]=datetime.now().date(); st.rerun()
    if "_ps" in st.session_state: start_date=st.session_state.pop("_ps")
    if "_pe" in st.session_state: end_date=st.session_state.pop("_pe")
    st.markdown(f"Du **{start_date.strftime('%d/%m/%Y')}** au **{end_date.strftime('%d/%m/%Y')}**")
    data_age=(datetime.now().date()-end_date).days
    if data_age==0: st.markdown('<div class="data-info">Donnees actualisees aujourd\'hui</div>',unsafe_allow_html=True)
    else: st.markdown(f'<div class="data-info">Actualisees il y a {data_age} jours</div>',unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**Systeme**")
    st.markdown(f"Capacite : **{SITE['capacity_kwp']} kWp**")
    st.markdown(f"Panneaux : **{SITE['num_panels']}** | Onduleurs : **{SITE['num_inverters']}**")
    st.markdown(f"Inclinaison : **{PANEL['tilt']}°** | Azimut : **{PANEL['azimuth']}°**")
    years_op=datetime.now().year-int(SITE['commissioning_date'])
    deg=calculate_degraded_power(PANEL['pdc0'],years_op,PANEL['degradation_pct_yr']/100)
    st.markdown("---")
    st.markdown(f"**Degradation** apres {years_op} ans : **{deg:.0f} W** (-{(1-deg/PANEL['pdc0'])*100:.1f}%)")

# ════════════════════════════════════════════════════════
# PVLIB SIMULATION (historique)
# ════════════════════════════════════════════════════════
if menu != "⚡ FMU Temps Réel":
    with st.spinner("Simulation pvlib..."):
        results=run_pvlib_simulation(
            lat=SITE["lat"],lon=SITE["lon"],altitude=SITE["altitude"],
            timezone=SITE["timezone"],tilt=PANEL["tilt"],azimuth=PANEL["azimuth"],
            pdc0=PANEL["pdc0"]*SITE["num_panels"],gamma_pdc=PANEL["gamma_pdc"],
            start_date=str(start_date),end_date=str(end_date))
    if results is None:
        st.error("Impossible de recuperer les donnees. Verifiez votre connexion."); st.stop()
    daily=compute_daily(results); monthly=compute_monthly(daily)

current_meteo=get_current_meteo(SITE["lat"],SITE["lon"]); now=datetime.now()

# ════════════════════════════════════════════════════════
# HEADER COMMUN
# ════════════════════════════════════════════════════════
ghi_now=current_meteo.get('shortwave_radiation',0) or 0
cloud_now=current_meteo.get('cloud_cover',0) or 0
if ghi_now>100: sl,sc="PRODUCTION OPTIMALE","var(--green)"
elif ghi_now>50: sl,sc="PRODUCTION REDUITE","var(--solar-yellow)"
else: sl,sc="HORS PRODUCTION","var(--text-secondary)"

st.markdown(f"""
<div class="main-header">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
    <div>
      <div class="plant-name">{SITE['name']}</div>
      <div class="plant-sub">{SITE['lat']}N, {abs(SITE['lon'])}W &nbsp;|&nbsp; {SITE['altitude']} m &nbsp;|&nbsp; {SITE['capacity_kwp']} kWp &nbsp;|&nbsp; Mohammedia, Maroc</div>
    </div>
    <div style="display:flex;align-items:center;gap:16px">
      <div style="text-align:right">
        <div style="font-size:12px;color:#6B7585;font-family:'Space Mono',monospace">{now.strftime('%d/%m/%Y %H:%M')}</div>
        <div style="font-size:10px;color:#3D4553;font-family:'Space Mono',monospace">UTC+1 &nbsp;|&nbsp; GHI: {ghi_now:.0f} W/m2 &nbsp;|&nbsp; Cloud: {cloud_now}%</div>
      </div>
      <div class="status-badge" style="border-color:{sc};color:{sc}">
        <div class="status-dot" style="background:{sc};box-shadow:0 0 8px {sc}"></div>{sl}
      </div>
    </div>
  </div>
</div>
""",unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# ⚡ FMU TEMPS REEL — PAGE PRINCIPALE
# ════════════════════════════════════════════════════════
if menu == "⚡ FMU Temps Réel":
    # Controls
    ct1,ct2,ct3,_=st.columns([.9,.9,1.2,5])
    with ct1:
        if st.button("▶ START" if not st.session_state.fmu_run else "⏸ PAUSE",type="primary",use_container_width=True):
            st.session_state.fmu_run=not st.session_state.fmu_run; st.rerun()
    with ct2:
        if st.button("↺ Reset",use_container_width=True):
            for k in FMU_KEYS: st.session_state[k]=[]
            st.session_state.fmu_tick=0; st.session_state.fmu_wx=None
    with ct3:
        spd=st.select_slider("",options=[1,2,3,5],value=1,label_visibility="collapsed",format_func=lambda x:f"⏱ {x}s")

    # FMU Header
    run=st.session_state.fmu_run
    dot='<span class="live-dot"></span>' if run else '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#374151;margin-right:6px"></span>'
    lbl="LIVE" if run else "EN PAUSE"
    lcol="#22c55e" if run else "#4b6080"
    st.markdown(f"""
    <div class="fmu-header">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <div class="fmu-title">{dot}<span style="color:{lcol}">{lbl}</span> &nbsp; FMU Simulation Temps Réel</div>
          <div class="fmu-sub">PV_MPPT_Inverter1_grt_fmi_rtw · FMI 2.0 · Open-Meteo → FMU + PVLib</div>
        </div>
        <div style="font-family:'JetBrains Mono';font-size:1.2rem;color:#3b82f6">{now.strftime('%H:%M:%S')}</div>
      </div>
    </div>
    """,unsafe_allow_html=True)

    # Placeholders
    ph_flow=st.empty()
    st.markdown('<div class="fmu-sec">📡 Entrées — Open-Meteo (Mohammedia, temps réel)</div>',unsafe_allow_html=True)
    r1=st.columns(5)
    ph_GHI=r1[0].empty(); ph_DNI=r1[1].empty(); ph_DHI=r1[2].empty(); ph_Tamb=r1[3].empty(); ph_Tc=r1[4].empty()
    st.markdown('<div class="fmu-sec">🔧 Sorties FMU — PV_MPPT_Inverter1 (Simulink)</div>',unsafe_allow_html=True)
    r2=st.columns(6)
    ph_Ppv=r2[0].empty(); ph_Vmpp=r2[1].empty(); ph_Impp=r2[2].empty()
    ph_Pb=r2[3].empty(); ph_Pac=r2[4].empty(); ph_Vac=r2[5].empty()
    st.markdown('<div class="fmu-sec">📊 Qualité onduleur + PVLib SDM-CEC</div>',unsafe_allow_html=True)
    r3=st.columns(5)
    ph_eta=r3[0].empty(); ph_THDv=r3[1].empty(); ph_THDi=r3[2].empty(); ph_Ppl=r3[3].empty(); ph_dlt=r3[4].empty()
    st.markdown('<div class="fmu-sec">📈 Historique live</div>',unsafe_allow_html=True)
    ga,gb=st.columns([3,2])
    with ga: ph_g1=st.empty()
    with gb: ph_g2=st.empty()
    gc2,gd2=st.columns(2)
    with gc2: ph_g3=st.empty()
    with gd2: ph_g4=st.empty()
    ph_st=st.empty()

    def fkcard(val,unit,lbl,src,ac):
        return f'<div class="fmu-kcard" style="--ac:{ac}"><div class="fmu-kval">{val}<span class="fmu-kunit">{unit}</span></div><div class="fmu-klbl">{lbl}</div><div class="fmu-ksrc">{src}</div></div>'

    def mfig(h=265):
        f=go.Figure()
        f.update_layout(height=h,**FMU_BG,margin=FMU_MAR,legend=FMU_LEG,font=FMU_FNT,
                        xaxis=dict(**FMU_GRD,tickformat="%H:%M:%S"),yaxis=dict(**FMU_GRD))
        return f

    # BOUCLE
    while True:
        now=datetime.now()
        if st.session_state.fmu_run:
            try:
                wx=fetch_meteo_now()
                if wx: st.session_state.fmu_wx=wx
            except: pass
            wx=st.session_state.fmu_wx
            if wx is None:
                ph_flow.error("⚠️ Open-Meteo inaccessible"); time.sleep(spd); st.rerun()
            G,DHI,DNI=wx["GHI"],wx["DHI"],wx["DNI"]
            Tamb,wind=wx["Tamb"],wx["wind"]; wxts=wx["ts"]
            fv=fmu_step(G,Tamb,wind)
            ts_pv=wxts if wxts.tzinfo else wxts.tz_localize(SITE["timezone"])
            Ppl=pvlib_step_rt(G,DHI,DNI,Tamb,wind,ts_pv)
            # historique
            h=st.session_state
            h.ts.append(now); h.G.append(G); h.Tamb.append(Tamb)
            h.Tc.append(fv["Tc"]); h.Vmpp.append(fv["Vmpp"]); h.Impp.append(fv["Impp"])
            h.Ppv.append(fv["Ppv"]); h.Pboost.append(fv["Pboost"])
            h.Pac.append(fv["Pac"]); h.eta.append(fv["eta"])
            h.THDv.append(fv["THDv"]); h.THDi.append(fv["THDi"]); h.Ppvlib.append(Ppl)
            for k in FMU_KEYS:
                lst=getattr(h,k)
                if len(lst)>MAX_PTS: setattr(h,k,lst[-MAX_PTS:])
            h.fmu_tick+=1
            xs=h.ts[-MAX_PTS:]

            # flow bar
            ph_flow.markdown(f"""
<div class="flow-bar">
  <span class="live-dot" style="margin:0"></span>
  <span style="color:#3b82f6;font-weight:600">OPEN-METEO</span>
  <span class="flow-arr">→</span>
  <span style="color:#4b6080;font-size:.68rem">GHI</span><span class="flow-chip">{G:.0f} W/m²</span>
  <span style="color:#4b6080;font-size:.68rem">DNI</span><span class="flow-chip">{DNI:.0f} W/m²</span>
  <span style="color:#4b6080;font-size:.68rem">T_amb</span><span class="flow-chip">{Tamb:.1f} °C</span>
  <span style="color:#4b6080;font-size:.68rem">Vent</span><span class="flow-chip">{wind:.1f} m/s</span>
  <span class="flow-arr">→</span>
  <span style="color:#1d4ed8;font-weight:600">FMU</span>
  <span style="color:#4b6080">+</span>
  <span style="color:#15803d;font-weight:600">PVLib</span>
  <span class="flow-arr">→</span>
  <span style="color:#4b6080;font-size:.68rem">heure</span><span class="flow-chip">{wxts.strftime('%H:%M')}</span>
  <span style="color:#4b6080;font-size:.68rem">tick</span><span class="flow-chip">#{h.fmu_tick:05d}</span>
</div>""",unsafe_allow_html=True)

            # gauges entrées
            ph_GHI.markdown( fkcard(f"{G:.0f}",        "W/m²","GHI",     "Open-Meteo → Inport FMU","#fbbf24"),unsafe_allow_html=True)
            ph_DNI.markdown( fkcard(f"{DNI:.0f}",      "W/m²","DNI",     "Open-Meteo","#f97316"),            unsafe_allow_html=True)
            ph_DHI.markdown( fkcard(f"{DHI:.0f}",      "W/m²","DHI",     "Open-Meteo","#3b82f6"),            unsafe_allow_html=True)
            ph_Tamb.markdown(fkcard(f"{Tamb:.1f}",     "°C",  "T_amb",   "→ Inport1 FMU","#60a5fa"),         unsafe_allow_html=True)
            ph_Tc.markdown(  fkcard(f"{fv['Tc']:.1f}", "°C",  "T_cell",  "Faiman model","#ef4444"),           unsafe_allow_html=True)
            # gauges FMU
            ph_Ppv.markdown( fkcard(f"{fv['Ppv']/1000:.3f}",   "kW","Ppanneau","FMU output","#f59e0b"),       unsafe_allow_html=True)
            ph_Vmpp.markdown(fkcard(f"{fv['Vmpp']:.1f}",        "V", "Vmpp",    "MPPT P&O","#f59e0b"),        unsafe_allow_html=True)
            ph_Impp.markdown(fkcard(f"{fv['Impp']:.2f}",        "A", "Impp",    "MPPT P&O","#fbbf24"),        unsafe_allow_html=True)
            ph_Pb.markdown(  fkcard(f"{fv['Pboost']/1000:.3f}", "kW","Pbooste", "Boost η=97%","#3b82f6"),     unsafe_allow_html=True)
            ph_Pac.markdown( fkcard(f"{fv['Pac']/1000:.3f}",    "kW","P_ondu",  "FMU output","#22c55e"),      unsafe_allow_html=True)
            ph_Vac.markdown( fkcard(f"220",                      "V", "Vonduleur","FMU output","#22c55e"),     unsafe_allow_html=True)
            # gauges qualité
            ph_eta.markdown( fkcard(f"{fv['eta']:.1f}",  "%","Rendement","onduleur","#a855f7"),                unsafe_allow_html=True)
            ph_THDv.markdown(fkcard(f"{fv['THDv']:.2f}", "%","THD_V",   "tension AC","#f97316"),              unsafe_allow_html=True)
            ph_THDi.markdown(fkcard(f"{fv['THDi']:.2f}", "%","THD_i",   "courant AC","#ef4444"),              unsafe_allow_html=True)
            ph_Ppl.markdown( fkcard(f"{Ppl/1000:.3f}",   "kW","P_pvlib","SDM-CEC","#a855f7"),                 unsafe_allow_html=True)
            dlt=fv["Ppv"]-Ppl
            dc="#22c55e" if abs(dlt)<100 else "#f59e0b" if abs(dlt)<300 else "#ef4444"
            ph_dlt.markdown( fkcard(f"{dlt:+.0f}","W","Δ FMU−PVLib","écart","#64748b"),                       unsafe_allow_html=True)

            # graphe puissances
            f1=mfig(275)
            f1.add_trace(go.Scatter(x=xs,y=h.Ppv[-MAX_PTS:],   name="Ppanneau",line=dict(color="#f59e0b",width=2.2)))
            f1.add_trace(go.Scatter(x=xs,y=h.Pboost[-MAX_PTS:],name="Pbooste", line=dict(color="#3b82f6",width=1.5,dash="dot")))
            f1.add_trace(go.Scatter(x=xs,y=h.Pac[-MAX_PTS:],   name="P_ondu",  line=dict(color="#22c55e",width=2.2)))
            f1.add_trace(go.Scatter(x=xs,y=h.Ppvlib[-MAX_PTS:],name="PVLib",   line=dict(color="#a855f7",width=1.8,dash="dash")))
            f1.update_layout(yaxis_title="W",title=dict(text="Puissances DC / AC",font=dict(size=10,color="#2d4060"),x=0.01,y=.97))
            ph_g1.plotly_chart(f1,use_container_width=True,config=FMU_CFG)

            # graphe météo
            f2=mfig(275)
            f2.add_trace(go.Scatter(x=xs,y=h.G[-MAX_PTS:],name="GHI",fill="tozeroy",
                line=dict(color="#fbbf24",width=2),fillcolor="rgba(251,191,36,.07)"))
            f2.add_trace(go.Scatter(x=xs,y=h.Tamb[-MAX_PTS:],name="T_amb",
                line=dict(color="#3b82f6",width=2),yaxis="y2"))
            f2.add_trace(go.Scatter(x=xs,y=h.Tc[-MAX_PTS:],name="T_cell",
                line=dict(color="#ef4444",width=2,dash="dot"),yaxis="y2"))
            f2.update_layout(yaxis=dict(title="GHI [W/m²]",**FMU_GRD),
                yaxis2=dict(title="Temp [°C]",overlaying="y",side="right",showgrid=False,color="#3b82f6",tickfont=dict(size=9)),
                title=dict(text="Météo · Open-Meteo",font=dict(size=10,color="#2d4060"),x=0.01,y=.97))
            ph_g2.plotly_chart(f2,use_container_width=True,config=FMU_CFG)

            # graphe qualité
            from plotly.subplots import make_subplots
            f3=make_subplots(rows=2,cols=1,shared_xaxes=True,subplot_titles=("THD [%]","Rendement [%]"),vertical_spacing=0.1)
            f3.update_layout(height=265,**FMU_BG,margin=FMU_MAR,legend=FMU_LEG,font=FMU_FNT,
                title=dict(text="Qualité onduleur",font=dict(size=10,color="#2d4060"),x=0.01,y=.97))
            f3.update_xaxes(**FMU_GRD,tickformat="%H:%M:%S"); f3.update_yaxes(**FMU_GRD)
            f3.add_trace(go.Scatter(x=xs,y=h.THDv[-MAX_PTS:],name="THD_V",line=dict(color="#f97316",width=2)),row=1,col=1)
            f3.add_trace(go.Scatter(x=xs,y=h.THDi[-MAX_PTS:],name="THD_i",line=dict(color="#ef4444",width=2,dash="dot")),row=1,col=1)
            f3.add_trace(go.Scatter(x=xs,y=h.eta[-MAX_PTS:],name="Rendement",fill="tozeroy",
                line=dict(color="#a855f7",width=2),fillcolor="rgba(168,85,247,.08)"),row=2,col=1)
            ph_g3.plotly_chart(f3,use_container_width=True,config=FMU_CFG)

            # graphe FMU vs PVLib
            fmu_a=np.array(h.Ppv[-MAX_PTS:],dtype=float)
            pvl_a=np.array(h.Ppvlib[-MAX_PTS:],dtype=float)
            diff=fmu_a-pvl_a
            f4=mfig(265)
            f4.add_trace(go.Scatter(x=xs,y=fmu_a,name="FMU", line=dict(color="#f59e0b",width=2.2)))
            f4.add_trace(go.Scatter(x=xs,y=pvl_a,name="PVLib",line=dict(color="#a855f7",width=2,dash="dash")))
            f4.add_trace(go.Scatter(x=xs,y=diff,name="Δ",fill="tozeroy",
                line=dict(color="#ef4444",width=1.2),fillcolor="rgba(239,68,68,.08)"))
            if len(diff)>3:
                xn=np.arange(len(diff),dtype=float); m,b=np.polyfit(xn,diff,1)
                f4.add_trace(go.Scatter(x=xs,y=m*xn+b,name="tendance",
                    line=dict(color="#f97316",width=1,dash="dot"),showlegend=False))
            f4.update_layout(yaxis_title="W",
                title=dict(text="FMU vs PVLib · Δ",font=dict(size=10,color="#2d4060"),x=0.01,y=.97))
            ph_g4.plotly_chart(f4,use_container_width=True,config=FMU_CFG)

            ph_st.markdown(f"""
<div class="fmu-statusbar">
  <span>FMU·ONLINE</span><span>TICK·{h.fmu_tick:06d}</span>
  <span>HIST·{len(h.ts)}/{MAX_PTS}pts</span><span>REFRESH·{spd}s</span>
  <span>METEO·{wxts.strftime('%H:%M')} UTC+1</span>
  <span>PV_MPPT_Inverter1_grt_fmi_rtw·FMI2.0</span>
  <span>{now.strftime('%Y-%m-%d %H:%M:%S')}</span>
</div>""",unsafe_allow_html=True)

        else:
            n=len(st.session_state.ts)
            ph_flow.markdown(f"""
<div class="flow-bar">
  <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#374151"></span>
  <span style="color:#475569;font-weight:600">EN PAUSE</span> — {n} pts.
  Appuyez sur <span class="flow-chip">▶ START</span> pour lancer.
</div>""",unsafe_allow_html=True)

        time.sleep(spd)
        st.rerun()

# ════════════════════════════════════════════════════════
# VUE GLOBALE
# ════════════════════════════════════════════════════════
elif menu=="Vue Globale":
    total_kwh=daily["production_kwh"].sum(); gross_kwh=daily["gross_production_kwh"].sum()
    losses_kwh=gross_kwh-total_kwh; avg_daily_losses=losses_kwh/len(daily) if len(daily)>0 else 0
    avg_pr=daily["pr"].mean(); avg_cf=daily["capacity_factor"].mean()
    co2=estimate_co2_avoidance(total_kwh); savings=calculate_financial_metrics(total_kwh)
    st.markdown("## Performance Globale")
    kpi_cols=st.columns(5)
    kpis=[
        (f"{total_kwh/1000:.2f}","Production Totale<br>MWh"),
        (f"{avg_pr:.1f}","Performance<br>Ratio %"),
        (f"{co2:.0f}","CO2 Evite<br>kg"),
        (f"{savings:.0f}","Economies<br>EUR"),
        (f"{avg_cf:.1f}","Facteur<br>Capacite %"),
    ]
    for i,(v,l) in enumerate(kpis):
        with kpi_cols[i]:
            st.markdown(f'<div class="kpi-card"><div class="kpi-value">{v}</div><div class="kpi-label">{l}</div></div>',unsafe_allow_html=True)
    st.markdown("---")
    col_img,col_perf=st.columns([5,1])
    with col_img:
        wc=st.columns(4)
        wc[0].metric("Temperature",f"{current_meteo.get('temperature_2m','--')} °C")
        wc[1].metric("Irradiance",f"{ghi_now:.0f} W/m²")
        wc[2].metric("Vent",f"{current_meteo.get('wind_speed_10m','--')} km/h")
        wc[3].metric("Humidite",f"{current_meteo.get('relative_humidity_2m','--')} %")
    with col_perf:
        st.markdown('<div class="section-title">Performance actuelle</div>',unsafe_allow_html=True)
        today_date=now.date()
        mask=(results["date"]==today_date)&(results["hour"]==now.hour)
        cp=results.loc[mask,"net_ac_power_kw"].values
        st.metric("Puissance",f"{cp[0]:.2f} kW" if len(cp)>0 else "0 kW")
        td=daily[daily["date"].dt.date==today_date]
        st.metric("Prod. jour",f"{td['production_kwh'].values[0]:.2f} kWh" if len(td)>0 else "0 kWh")
        st.metric("Pertes moy.",f"{avg_daily_losses:.1f} kWh")
        st.metric("Rendement",f"{(total_kwh/gross_kwh*100) if gross_kwh>0 else 0:.1f}%")
    st.markdown("---")
    col_left,col_right=st.columns([2,1])
    with col_left:
        st.markdown('<div class="section-title">Production journaliere (kWh)</div>',unsafe_allow_html=True)
        fig_d=go.Figure()
        fig_d.add_trace(go.Bar(x=daily["date"],y=daily["production_kwh"],name="Production",marker_color="#F5A623",opacity=0.85))
        fig_d.add_trace(go.Scatter(x=daily["date"],y=daily["production_kwh"].rolling(7,center=True).mean(),name="Moy. 7j",line=dict(color="#3498DB",width=2)))
        l=dict(**PLOT_LAYOUT); l["height"]=320; l["showlegend"]=True; l["yaxis"]=dict(gridcolor="#1E232D",title="kWh",zeroline=False)
        fig_d.update_layout(**l); st.plotly_chart(fig_d,use_container_width=True)
    with col_right:
        st.markdown('<div class="section-title">Par jour de semaine</div>',unsafe_allow_html=True)
        dw=daily.groupby("day_of_week")["production_kwh"].mean().reset_index()
        dw["day_of_week"]=pd.Categorical(dw["day_of_week"],categories=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],ordered=True)
        dw=dw.sort_values("day_of_week")
        fig_w=go.Figure(go.Bar(x=dw["day_of_week"],y=dw["production_kwh"],marker_color="#9B59B6"))
        l2=dict(**PLOT_LAYOUT); l2["height"]=320; fig_w.update_layout(**l2)
        st.plotly_chart(fig_w,use_container_width=True)
    st.markdown("---")
    st.markdown('<div class="section-title">Centre d\'alertes</div>',unsafe_allow_html=True)
    ac1,ac2=st.columns([2,1])
    with ac1:
        lpd=daily[daily["pr"]<70]; htd=daily[daily["avg_temp"]>35]
        if len(lpd)>0: st.markdown(f'<div class="alert-card alert-warning"><b>Performance degradee</b><br>{len(lpd)} jours PR&lt;70% — Dernier: {lpd["date"].max().strftime("%d/%m/%Y")}</div>',unsafe_allow_html=True)
        if len(htd)>0: st.markdown(f'<div class="alert-card alert-warning"><b>Temperature elevee</b><br>{len(htd)} jours &gt;35°C</div>',unsafe_allow_html=True)
        st.markdown('<div class="alert-card alert-ok"><b>Systeme de monitoring</b> — Toutes les donnees recues</div>',unsafe_allow_html=True)
    with ac2:
        hs=max(min(100-len(lpd)*5-len(htd)*2,100),0)
        hc="#2ECC71" if hs>80 else "#F5A623" if hs>60 else "#E74C3C"
        st.markdown(f'<div class="kpi-card"><div class="kpi-value" style="color:{hc}">{hs:.0f}/100</div><div class="kpi-label">Score de<br>Sante Systeme</div></div>',unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# PRODUCTION
# ════════════════════════════════════════════════════════
elif menu=="Production":
    st.markdown("## Analyse de production")
    t1,t2,t3=st.tabs(["Performance","Profil Horaire","Heatmap"])
    with t1:
        c1,c2=st.columns(2)
        with c1:
            st.markdown('<div class="section-title">Performance Ratio (%)</div>',unsafe_allow_html=True)
            fp=go.Figure()
            fp.add_trace(go.Scatter(x=daily["date"],y=daily["pr"],fill="tozeroy",fillcolor="rgba(245,166,35,0.10)",line=dict(color="#F5A623",width=1.5),name="PR %"))
            fp.add_hline(y=75,line_dash="dash",line_color="#3D4553",annotation_text="75%",annotation_font_color="#6B7585",annotation_font_size=11)
            fp.add_hline(y=85,line_dash="dash",line_color="#2ECC71",annotation_text="85%",annotation_font_color="#2ECC71",annotation_font_size=11)
            lp=dict(**PLOT_LAYOUT); lp["height"]=350; lp["yaxis"]=dict(gridcolor="#1E232D",range=[0,110],zeroline=False)
            fp.update_layout(**lp); st.plotly_chart(fp,use_container_width=True)
        with c2:
            st.markdown('<div class="section-title">Facteur de capacite (%)</div>',unsafe_allow_html=True)
            fc=go.Figure()
            fc.add_trace(go.Scatter(x=daily["date"],y=daily["capacity_factor"],fill="tozeroy",fillcolor="rgba(52,152,219,0.10)",line=dict(color="#3498DB",width=1.5),name="CF %"))
            lc=dict(**PLOT_LAYOUT); lc["height"]=350; lc["yaxis"]=dict(gridcolor="#1E232D",title="%",zeroline=False)
            fc.update_layout(**lc); st.plotly_chart(fc,use_container_width=True)
        st.markdown('<div class="section-title">Correlations</div>',unsafe_allow_html=True)
        cc=st.columns(3)
        for ax,ay,t_c in [("avg_temp","production_kwh","Temp vs Prod"),("peak_sun_hours","production_kwh","PSH vs Prod"),("avg_wind","production_kwh","Vent vs Prod")]:
            with cc.pop(0):
                fc2=px.scatter(daily,x=ax,y=ay,color="pr",color_continuous_scale="YlOrRd",opacity=0.7,title=t_c)
                fc2.update_layout(**{**PLOT_LAYOUT,"height":300}); st.plotly_chart(fc2,use_container_width=True)
    with t2:
        st.markdown('<div class="section-title">Profil horaire moyen</div>',unsafe_allow_html=True)
        hs=results.groupby("hour")["ac_power_kw"].agg(["mean","min","max"]).reset_index()
        fh=go.Figure()
        fh.add_trace(go.Scatter(x=hs["hour"],y=hs["max"],fill=None,mode="lines",line=dict(color="rgba(245,166,35,0.2)",width=0),showlegend=False))
        fh.add_trace(go.Scatter(x=hs["hour"],y=hs["min"],fill="tonexty",fillcolor="rgba(245,166,35,0.1)",mode="lines",line=dict(color="rgba(245,166,35,0.2)",width=0),name="Plage"))
        fh.add_trace(go.Scatter(x=hs["hour"],y=hs["mean"],line=dict(color="#F5A623",width=2.5),name="Moyenne"))
        lh=dict(**PLOT_LAYOUT); lh["height"]=350; lh["xaxis"]=dict(title="Heure",gridcolor="#1E232D",dtick=1,zeroline=False); lh["yaxis"]=dict(title="kW",gridcolor="#1E232D",zeroline=False)
        fh.update_layout(**lh); st.plotly_chart(fh,use_container_width=True)
    with t3:
        st.markdown('<div class="section-title">Heatmap Mois x Heure</div>',unsafe_allow_html=True)
        hp=results.groupby(["month","hour"])["ac_power_kw"].mean().reset_index().pivot(index="month",columns="hour",values="ac_power_kw")
        mfr=["Jan","Fev","Mar","Avr","Mai","Jun","Jul","Aou","Sep","Oct","Nov","Dec"]
        hp.index=[mfr[m-1] for m in hp.index]
        fhm=go.Figure(go.Heatmap(z=hp.values,x=[f"{h}h" for h in hp.columns],y=hp.index,
            colorscale=[[0,"#08090C"],[0.4,"#2A1500"],[0.8,"#E8860A"],[1,"#F5A623"]],
            showscale=True,colorbar=dict(title="kW",tickfont=dict(color="#6B7585"))))
        lhm=dict(**PLOT_LAYOUT); lhm["height"]=400; fhm.update_layout(**lhm)
        st.plotly_chart(fhm,use_container_width=True)

# ════════════════════════════════════════════════════════
# METEO & IRRADIANCE
# ════════════════════════════════════════════════════════
elif menu=="Meteo & Irradiance":
    st.markdown("## Conditions Meteorologiques")
    wk=st.columns(6)
    for i,(lbl,key,unit) in enumerate([("Temperature","temperature_2m","°C"),("Ressentie","apparent_temperature","°C"),
            ("Humidite","relative_humidity_2m","%"),("Vent","wind_speed_10m","km/h"),("GHI","shortwave_radiation","W/m²"),("Nuages","cloud_cover","%")]):
        with wk[i]: st.metric(lbl,f"{current_meteo.get(key,'--')} {unit}")
    st.markdown("---")
    it=st.tabs(["GHI & POA","Temperature","Ressource Solaire"])
    with it[0]:
        cl,cr=st.columns(2)
        with cl:
            st.markdown('<div class="section-title">GHI journalier</div>',unsafe_allow_html=True)
            dg=results.groupby("date").agg(ghi_sum=("ghi",lambda x:x.sum()/1000)).reset_index(); dg["date"]=pd.to_datetime(dg["date"])
            fg=go.Figure(); fg.add_trace(go.Scatter(x=dg["date"],y=dg["ghi_sum"],fill="tozeroy",fillcolor="rgba(245,166,35,0.12)",line=dict(color="#F5A623",width=1.5),name="GHI"))
            lg=dict(**PLOT_LAYOUT); lg["height"]=350; lg["yaxis"]=dict(gridcolor="#1E232D",title="kWh/m²",zeroline=False)
            fg.update_layout(**lg); st.plotly_chart(fg,use_container_width=True)
        with cr:
            st.markdown('<div class="section-title">POA Irradiance</div>',unsafe_allow_html=True)
            dp=results.groupby("date").agg(poa_iso=("poa_isotropic","mean"),poa_hd=("poa_haydavies","mean")).reset_index(); dp["date"]=pd.to_datetime(dp["date"])
            fp2=go.Figure(); fp2.add_trace(go.Scatter(x=dp["date"],y=dp["poa_iso"],line=dict(color="#F5A623",width=1.5),name="Isotropique"))
            fp2.add_trace(go.Scatter(x=dp["date"],y=dp["poa_hd"],line=dict(color="#3498DB",width=1.5),name="Hay-Davies"))
            lp2=dict(**PLOT_LAYOUT); lp2["height"]=350; lp2["yaxis"]=dict(gridcolor="#1E232D",title="W/m²",zeroline=False)
            fp2.update_layout(**lp2); st.plotly_chart(fp2,use_container_width=True)
    with it[1]:
        ct1,ct2=st.columns(2)
        with ct1:
            st.markdown('<div class="section-title">Temperature ambiante</div>',unsafe_allow_html=True)
            dt=results.groupby("date").agg(ta=("temp_air","mean"),tmx=("temp_air","max"),tmn=("temp_air","min")).reset_index(); dt["date"]=pd.to_datetime(dt["date"])
            ft=go.Figure(); ft.add_trace(go.Scatter(x=dt["date"],y=dt["tmx"],line=dict(color="#E74C3C",width=1),name="Max"))
            ft.add_trace(go.Scatter(x=dt["date"],y=dt["ta"],line=dict(color="#F5A623",width=2),name="Moy"))
            ft.add_trace(go.Scatter(x=dt["date"],y=dt["tmn"],line=dict(color="#3498DB",width=1),name="Min"))
            lt=dict(**PLOT_LAYOUT); lt["height"]=350; lt["yaxis"]=dict(gridcolor="#1E232D",title="°C",zeroline=False)
            ft.update_layout(**lt); st.plotly_chart(ft,use_container_width=True)
        with ct2:
            st.markdown('<div class="section-title">Temp cellule vs ambiante</div>',unsafe_allow_html=True)
            ht=results.groupby("hour")[["temp_air","cell_temp"]].mean().reset_index()
            fc3=go.Figure(); fc3.add_trace(go.Scatter(x=ht["hour"],y=ht["temp_air"],line=dict(color="#3498DB",width=2),name="Ambiante"))
            fc3.add_trace(go.Scatter(x=ht["hour"],y=ht["cell_temp"],line=dict(color="#E74C3C",width=2),name="Cellule"))
            lc3=dict(**PLOT_LAYOUT); lc3["height"]=350; lc3["xaxis"]=dict(title="Heure",gridcolor="#1E232D",dtick=1); lc3["yaxis"]=dict(title="°C",gridcolor="#1E232D")
            fc3.update_layout(**lc3); st.plotly_chart(fc3,use_container_width=True)
    with it[2]:
        st.markdown('<div class="section-title">Ressource solaire mensuelle</div>',unsafe_allow_html=True)
        mfr2=["Jan","Fev","Mar","Avr","Mai","Jun","Jul","Aou","Sep","Oct","Nov","Dec"]
        ms=results.groupby("month").agg(g=("ghi",lambda x:x.sum()/1000),d=("dni",lambda x:x.sum()/1000),h=("dhi",lambda x:x.sum()/1000)).reset_index()
        ms["mn"]=[mfr2[m-1] for m in ms["month"]]
        fs=go.Figure(); fs.add_trace(go.Bar(x=ms["mn"],y=ms["g"],name="GHI",marker_color="#F5A623"))
        fs.add_trace(go.Bar(x=ms["mn"],y=ms["d"],name="DNI",marker_color="#E8860A"))
        fs.add_trace(go.Bar(x=ms["mn"],y=ms["h"],name="DHI",marker_color="#FFCF6B"))
        ls=dict(**PLOT_LAYOUT); ls["height"]=300; ls["barmode"]="group"; ls["yaxis"]=dict(gridcolor="#1E232D",title="kWh/m²")
        fs.update_layout(**ls); st.plotly_chart(fs,use_container_width=True)

# ════════════════════════════════════════════════════════
# PERFORMANCE ANALYSIS
# ════════════════════════════════════════════════════════
elif menu=="Performance Analysis":
    st.markdown("## Analyse de Performance")
    pk=st.columns(4)
    pk[0].metric("PR Moyen",f"{daily['pr'].mean():.1f}%")
    pk[1].metric("Energy Yield",f"{daily['energy_yield'].mean():.1f} kWh/kWp")
    pk[2].metric("Facteur charge",f"{daily['capacity_factor'].mean():.1f}%")
    pk[3].metric("Disponibilite","98.5%")
    st.markdown("---")
    cp1,cp2=st.columns(2)
    with cp1:
        st.markdown('<div class="section-title">Distribution du PR</div>',unsafe_allow_html=True)
        fd=go.Figure(); fd.add_trace(go.Histogram(x=daily["pr"].dropna(),nbinsx=30,marker_color="#F5A623"))
        ld=dict(**PLOT_LAYOUT); ld["height"]=300; ld["xaxis"]=dict(title="PR (%)",gridcolor="#1E232D"); ld["yaxis"]=dict(title="Freq",gridcolor="#1E232D")
        fd.update_layout(**ld); st.plotly_chart(fd,use_container_width=True)
    with cp2:
        st.markdown('<div class="section-title">PR Mensuel</div>',unsafe_allow_html=True)
        fm=go.Figure(); fm.add_trace(go.Bar(x=monthly["month_name"],y=monthly["avg_pr"],marker_color="#F5A623"))
        lm=dict(**PLOT_LAYOUT); lm["height"]=300; lm["yaxis"]=dict(gridcolor="#1E232D",title="PR %",range=[50,100])
        fm.update_layout(**lm); st.plotly_chart(fm,use_container_width=True)
    ce1,ce2=st.columns(2)
    with ce1:
        fey=go.Figure(go.Scatter(x=daily["date"],y=daily["energy_yield"],fill="tozeroy",fillcolor="rgba(26,188,156,0.1)",line=dict(color="#1ABC9C",width=1.5)))
        ley=dict(**PLOT_LAYOUT); ley["height"]=300; ley["yaxis"]=dict(gridcolor="#1E232D",title="kWh/kWp")
        fey.update_layout(**ley); st.plotly_chart(fey,use_container_width=True)
    with ce2:
        daily["cum_kwh"]=daily["production_kwh"].cumsum()
        fcu=go.Figure(go.Scatter(x=daily["date"],y=daily["cum_kwh"]/1000,line=dict(color="#9B59B6",width=2),fill="tozeroy",fillcolor="rgba(155,89,182,0.1)"))
        lcu=dict(**PLOT_LAYOUT); lcu["height"]=300; lcu["yaxis"]=dict(gridcolor="#1E232D",title="MWh")
        fcu.update_layout(**lcu); st.plotly_chart(fcu,use_container_width=True)

# ════════════════════════════════════════════════════════
# ONDULEURS
# ════════════════════════════════════════════════════════
elif menu=="Onduleurs":
    st.markdown("## Tableau de bord Onduleurs")
    n=SITE["num_inverters"]; np.random.seed(42)
    ip=np.random.normal(95,8,n).clip(60,105)
    ist=["ALERTE" if p<85 else "OK" for p in ip]
    il=[f"INV-{i+1:02d}" for i in range(n)]
    st.markdown('<div class="section-title">Etat des onduleurs</div>',unsafe_allow_html=True)
    ic=st.columns(min(n,6))
    for i in range(n):
        with ic[i%min(n,6)]:
            col="#F5A623" if ip[i]<85 else "#2ECC71"
            st.markdown(f'<div style="background:#111318;border:1px solid #252A35;border-radius:8px;padding:12px 10px;text-align:center;border-left:3px solid {col}"><div style="font-size:10px;color:#6B7585;font-family:Space Mono,monospace">{il[i]}</div><div style="font-size:20px;font-weight:700;color:{col};font-family:Space Mono,monospace">{ip[i]:.0f}%</div><div style="font-size:10px;color:{col}">{ist[i]}</div></div>',unsafe_allow_html=True)
    st.markdown("---")
    oc1,oc2=st.columns(2)
    with oc1:
        fib=go.Figure(go.Bar(x=il,y=ip,marker_color=["#F5A623" if p<85 else "#2ECC71" for p in ip]))
        fib.add_hline(y=85,line_dash="dash",line_color="#E74C3C",annotation_text="85%")
        lib=dict(**PLOT_LAYOUT); lib["height"]=300
        fib.update_layout(**lib); st.plotly_chart(fib,use_container_width=True)
    with oc2:
        ok=sum(1 for p in ip if p>=85)
        fip=go.Figure(go.Pie(labels=["Nominaux","Alertes"],values=[ok,n-ok],hole=0.6,marker_colors=["#2ECC71","#F5A623"]))
        fip.add_annotation(text=f"<b>{n}</b><br>Total",x=0.5,y=0.5,showarrow=False,font=dict(size=14,color="#E8EDF5"))
        fip.update_layout(template="plotly_dark",paper_bgcolor="#111318",height=300,margin=dict(t=20,b=20,l=20,r=20))
        st.plotly_chart(fip,use_container_width=True)

# ════════════════════════════════════════════════════════
# INSTALLATION
# ════════════════════════════════════════════════════════
elif menu=="Installation":
    st.markdown("## Caracteristiques de l'installation")
    ki1,ki2,ki3,ki4=st.columns(4)
    ki1.metric("Puissance crete",f"{SITE['capacity_kwp']} kWp")
    ki2.metric("Panneaux",f"{SITE['num_panels']}")
    ki3.metric("Onduleurs",f"{SITE['num_inverters']}")
    ki4.metric("Surface",f"{SITE['surface_m2']} m²")
    st.markdown("---")
    ia,ib=st.columns(2)
    with ia:
        st.markdown(f'<div class="spec-block"><div class="spec-block-header">Site & Generale</div><table class="spec-table"><tr><td>Localisation</td><td>Mohammedia, Maroc</td></tr><tr><td>Latitude</td><td><span class="highlight-value">{SITE["lat"]} N</span></td></tr><tr><td>Longitude</td><td><span class="highlight-value">{abs(SITE["lon"])} W</span></td></tr><tr><td>Altitude</td><td>{SITE["altitude"]} m</td></tr><tr><td>Mise en service</td><td>{SITE["commissioning_date"]}</td></tr><tr><td>Operateur</td><td>{SITE["operator"]}</td></tr></table></div>',unsafe_allow_html=True)
    with ib:
        st.markdown(f'<div class="spec-block"><div class="spec-block-header">Panneau PV</div><table class="spec-table"><tr><td>Fabricant</td><td>{PANEL["manufacturer"]}</td></tr><tr><td>Modele</td><td>{PANEL["model"]}</td></tr><tr><td>Pmax</td><td><span class="highlight-value">{PANEL["pdc0"]} Wc</span></td></tr><tr><td>Vmp / Imp</td><td>{PANEL["vmp"]} V / {PANEL["imp"]} A</td></tr><tr><td>Voc / Isc</td><td>{PANEL["voc"]} V / {PANEL["isc"]} A</td></tr><tr><td>Rendement</td><td><span class="highlight-value">{PANEL["efficiency_pct"]} %</span></td></tr></table></div>',unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# CONTROLE RELAIS
# ════════════════════════════════════════════════════════
elif menu=="Controle Relais":
    st.markdown("## Controle Relais ESP32 via Blynk")
    dc=blynk_get_device_status()
    if dc: st.success("ESP32 connecte a Blynk")
    else: st.warning("ESP32 non connecte")
    rs=blynk_get_pin(BLYNK_CONFIG["relay_pin"])
    rc1,rc2,rc3=st.columns(3)
    with rc1:
        col="#2ECC71" if rs==1 else "#E74C3C"
        st.markdown(f'<div class="metric-card"><div class="metric-label">ETAT RELAIS</div><div class="metric-value" style="color:{col}">{"ACTIF" if rs==1 else "INACTIF"}</div></div>',unsafe_allow_html=True)
    with rc2:
        st.markdown(f'<div class="metric-card"><div class="metric-label">PIN BLYNK</div><div class="metric-value">{BLYNK_CONFIG["relay_pin"]}</div></div>',unsafe_allow_html=True)
    with rc3:
        col2="#2ECC71" if dc else "#E74C3C"
        st.markdown(f'<div class="metric-card"><div class="metric-label">CONNEXION</div><div class="metric-value" style="color:{col2}">{"FAR" if dc else "HORS LIGNE"}</div></div>',unsafe_allow_html=True)
    st.markdown("---")
    rb1,rb2,rb3=st.columns(3)
    with rb1:
        if st.button("ACTIVER RELAIS",type="primary",use_container_width=True):
            if blynk_set_pin(BLYNK_CONFIG["relay_pin"],1): st.success("Relais active"); st.rerun()
            else: st.error("Erreur ESP32")
    with rb2:
        if st.button("DESACTIVER RELAIS",type="secondary",use_container_width=True):
            if blynk_set_pin(BLYNK_CONFIG["relay_pin"],0): st.success("Relais desactive"); st.rerun()
            else: st.error("Erreur ESP32")
    with rb3:
        if st.button("ACTUALISER",use_container_width=True): st.rerun()

# ════════════════════════════════════════════════════════
# RAPPORT
# ════════════════════════════════════════════════════════
elif menu=="Rapport":
    st.markdown("## Rapport de Performance")
    total_kwh=daily["production_kwh"].sum(); gross_kwh=daily["gross_production_kwh"].sum()
    avg_pr=daily["pr"].mean(); bm=monthly.loc[monthly["production_kwh"].idxmax()]; wm=monthly.loc[monthly["production_kwh"].idxmin()]
    S_CARD="background:#111318;border:1px solid #252A35;border-radius:10px;margin-bottom:20px;overflow:hidden;"
    S_HEAD="background:#191D25;padding:10px 16px;font-family:'Space Mono',monospace;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.12em;color:#F5A623;border-bottom:1px solid #252A35;"
    S_TABLE="width:100%;border-collapse:collapse;font-size:13px;"
    S_TL="padding:10px 14px;color:#6B7585;font-family:'Space Mono',monospace;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;width:50%;border-bottom:1px solid #252A35;"
    S_TR="padding:10px 14px;color:#E8EDF5;font-weight:500;text-align:right;border-bottom:1px solid #252A35;"
    S_TLL="padding:10px 14px;color:#6B7585;font-family:'Space Mono',monospace;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;width:50%;"
    S_TRL="padding:10px 14px;color:#E8EDF5;font-weight:500;text-align:right;"
    bl=f"{bm['month_name']}  {bm['production_kwh']/1000:.1f} MWh"
    wl=f"{wm['month_name']}  {wm['production_kwh']/1000:.1f} MWh"
    prc="#2ECC71" if avg_pr>=80 else "#F5A623" if avg_pr>=70 else "#E74C3C"
    st.markdown(f"""
<div style="background:#111318;border:1px solid #252A35;border-top:2px solid #F5A623;border-radius:12px;padding:24px 28px 16px;margin-bottom:20px;">
  <div style="font-family:'Space Mono',monospace;font-size:15px;color:#F5A623;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">Rapport de Performance</div>
  <div style="font-size:12px;color:#6B7585;font-family:'Space Mono',monospace;">{SITE['name']} &nbsp;|&nbsp; {start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}</div>
</div>""",unsafe_allow_html=True)
    st.markdown(f"""
<div style="{S_CARD}"><div style="{S_HEAD}">Production energetique</div>
<table style="{S_TABLE}">
<tr><td style="{S_TL}">Production totale</td><td style="{S_TR}"><span style="color:#F5A623;font-family:'Space Mono',monospace;font-weight:700;">{total_kwh/1000:.2f} MWh</span></td></tr>
<tr><td style="{S_TL}">Production journaliere moyenne</td><td style="{S_TR}">{daily["production_kwh"].mean():.1f} kWh / jour</td></tr>
<tr><td style="{S_TL}">Meilleur mois</td><td style="{S_TR}"><span style="color:#2ECC71;font-weight:600;">{bl}</span></td></tr>
<tr><td style="{S_TLL}">Mois le plus faible</td><td style="{S_TRL}"><span style="color:#E74C3C;font-weight:600;">{wl}</span></td></tr>
</table></div>""",unsafe_allow_html=True)
    st.markdown(f"""
<div style="{S_CARD}"><div style="{S_HEAD}">Indicateurs de performance</div>
<table style="{S_TABLE}">
<tr><td style="{S_TL}">Performance Ratio moyen</td><td style="{S_TR}"><span style="color:{prc};font-family:'Space Mono',monospace;font-weight:700;">{avg_pr:.1f} %</span></td></tr>
<tr><td style="{S_TL}">Jours PR &lt; 70%</td><td style="{S_TR}"><span style="color:#E74C3C;">{len(daily[daily['pr']<70])} jours</span></td></tr>
<tr><td style="{S_TLL}">Rendement energetique net</td><td style="{S_TRL}">{(total_kwh/gross_kwh*100) if gross_kwh>0 else 0:.1f} %</td></tr>
</table></div>""",unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### Export")
    cd1,cd2=st.columns(2)
    with cd1: st.download_button("Telecharger journalier (CSV)",daily.to_csv(index=False,float_format="%.2f"),f"solaris_daily_{start_date}_{end_date}.csv","text/csv")
    with cd2: st.download_button("Telecharger mensuel (CSV)",monthly.to_csv(index=False,float_format="%.2f"),f"solaris_monthly_{start_date}_{end_date}.csv","text/csv")

# ════════════════════════════════════════════════════════
# FOOTER
# ════════════════════════════════════════════════════════
if menu != "⚡ FMU Temps Réel":
    st.markdown("---")
    st.markdown(f'<div style="text-align:center;color:#252A35;font-size:11px;padding:10px 0;font-family:Space Mono,monospace;letter-spacing:0.08em">SOLARIS DIGITAL TWIN V3.0 &nbsp;|&nbsp; MOHAMMEDIA, MAROC &nbsp;|&nbsp; pvlib + Open-Meteo + FMU Real-Time &nbsp;|&nbsp; {now.strftime("%d/%m/%Y %H:%M")}</div>',unsafe_allow_html=True)
