"""
PV MPPT Inverter - Supervision TEMPS REEL
ENSET Mohammedia | Design moderne dark
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

st.set_page_config(
    page_title="PV Supervision · ENSET",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"],
.main, .block-container {
    background: #080c14 !important;
    color: #c9d4e8;
    font-family: 'Inter', sans-serif;
}

[data-testid="stAppViewContainer"] { padding: 0 !important; }
.block-container { padding: 0 1.2rem 2rem !important; max-width: 100% !important; }

/* ─── HEADER ─── */
.hdr {
    background: linear-gradient(180deg, #0d1424 0%, #080c14 100%);
    border-bottom: 1px solid rgba(59,130,246,.25);
    padding: 14px 24px;
    display: flex; align-items: center; justify-content: space-between;
    margin: 0 -1.2rem 20px;
    position: relative;
    overflow: hidden;
}
.hdr::after {
    content:'';position:absolute;bottom:0;left:0;right:0;height:1px;
    background:linear-gradient(90deg,transparent,#3b82f6 30%,#8b5cf6 60%,transparent);
}
.hdr-title { font-size:1.15rem; font-weight:700; color:#fff; letter-spacing:.5px; }
.hdr-sub   { font-size:.68rem; color:#4b6080; letter-spacing:2px; text-transform:uppercase; margin-top:3px; }
.hdr-time  { font-family:'JetBrains Mono',monospace; font-size:1.4rem; color:#3b82f6; }
.hdr-date  { font-size:.65rem; color:#2d4060; text-align:right; margin-top:2px; }

/* ─── LIVE BADGE ─── */
.live-badge {
    display:inline-flex; align-items:center; gap:6px;
    background:rgba(34,197,94,.1); border:1px solid rgba(34,197,94,.3);
    border-radius:20px; padding:4px 12px;
    font-size:.7rem; font-weight:600; color:#22c55e; letter-spacing:1px;
}
.live-dot {
    width:7px; height:7px; border-radius:50%; background:#22c55e;
    box-shadow:0 0 6px #22c55e;
    animation: livepulse 1.4s ease-in-out infinite;
}
@keyframes livepulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.3;transform:scale(.7)} }

/* ─── FLOW BAR ─── */
.flow {
    background: rgba(13,20,36,.8);
    border: 1px solid rgba(30,58,100,.6);
    border-radius: 10px;
    padding: 10px 18px;
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    font-size: .75rem; color: #4b6080;
    margin-bottom: 16px;
    backdrop-filter: blur(4px);
}
.flow-chip {
    background: rgba(30,58,100,.4);
    border: 1px solid rgba(59,130,246,.2);
    border-radius: 6px; padding: 3px 10px;
    color: #60a5fa; font-family: 'JetBrains Mono', monospace;
    font-size: .75rem; font-weight: 600;
}
.flow-lbl { color: #2d4060; font-size:.68rem; }
.flow-arr { color: rgba(59,130,246,.4); font-size:.9rem; }

/* ─── KPI CARD ─── */
.kcard {
    background: linear-gradient(145deg, rgba(13,20,36,.95), rgba(8,12,20,.95));
    border: 1px solid rgba(30,58,100,.5);
    border-radius: 14px;
    padding: 16px 14px 12px;
    position: relative; overflow: hidden;
    transition: border-color .2s;
}
.kcard::before {
    content:''; position:absolute; top:0; left:0; right:0; height:2px;
    background: var(--ac, #3b82f6);
    border-radius: 14px 14px 0 0;
}
.kcard::after {
    content:''; position:absolute; bottom:-30px; right:-20px;
    width:80px; height:80px; border-radius:50%;
    background: radial-gradient(circle, var(--ac-glow, rgba(59,130,246,.05)), transparent 70%);
}
.kcard-val {
    font-family:'JetBrains Mono',monospace;
    font-size:1.8rem; font-weight:600;
    color: var(--ac, #3b82f6);
    line-height:1; letter-spacing:-1px;
}
.kcard-unit { font-size:.75rem; color:#4b6080; margin-left:3px; }
.kcard-lbl  { font-size:.62rem; color:#2d4060; text-transform:uppercase; letter-spacing:1.5px; margin-top:7px; }
.kcard-src  { font-size:.58rem; color:rgba(59,130,246,.3); margin-top:3px; }

/* ─── SECTION HEADER ─── */
.sh {
    font-size:.62rem; font-weight:600; letter-spacing:3px;
    text-transform:uppercase; color:#1e3a5f;
    padding:0 0 6px; margin:16px 0 8px;
    border-bottom:1px solid rgba(30,58,100,.3);
    display:flex; align-items:center; gap:8px;
}
.sh::before { content:''; display:inline-block; width:3px; height:12px;
    background:var(--sh-ac,#3b82f6); border-radius:2px; }

/* ─── GRAPH WRAPPER ─── */
.gwrap {
    background: rgba(8,12,20,.9);
    border: 1px solid rgba(30,58,100,.4);
    border-radius: 14px; overflow:hidden;
    padding:0;
}

/* ─── STATUS BAR ─── */
.statusbar {
    display:flex; justify-content:space-between; align-items:center;
    background:rgba(8,12,20,.8); border-top:1px solid rgba(30,58,100,.3);
    padding:7px 20px; margin:16px -1.2rem 0;
    font-family:'JetBrains Mono',monospace; font-size:.62rem; color:#1e3a5f;
    letter-spacing:1px;
}

/* hide streamlit chrome */
#MainMenu,footer,[data-testid="stToolbar"],[data-testid="stDecoration"] { display:none !important; }
.stButton button {
    background:rgba(30,58,100,.4) !important;
    border:1px solid rgba(59,130,246,.3) !important;
    color:#60a5fa !important; border-radius:8px !important;
    font-size:.78rem !important; font-weight:600 !important;
    transition:all .2s !important;
}
.stButton button:hover { background:rgba(59,130,246,.15) !important; }
[data-baseweb="select"] > div {
    background:rgba(13,20,36,.9) !important;
    border-color:rgba(30,58,100,.5) !important;
    color:#60a5fa !important; border-radius:8px !important;
}
div[data-testid="stSlider"] > div { padding:0 !important; }
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════
# CONSTANTES
# ════════════════════════════════════════
LOC = dict(lat=33.6861, lon=-7.3828, alt=27, tz="Africa/Casablanca")
P = dict(
    Pmax=330, Vmp=37.65, Imp=8.77, Voc=44.4, Isc=9.28,
    Tc=-0.0035, Ns=12, Np=1, tilt=31, azimuth=180,
    alpha_sc=0.004539, a_ref=1.5, I_L_ref=9.28,
    I_o_ref=2.2e-10, R_sh_ref=525.0, R_s=0.35, Adjust=8.7,
)
MAX_PTS = 300

# ════════════════════════════════════════
# OPEN-METEO
# ════════════════════════════════════════
@st.cache_data(ttl=300)
def get_meteo():
    now = datetime.now()
    s = (now - timedelta(hours=2)).strftime("%Y-%m-%d")
    e = now.strftime("%Y-%m-%d")
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LOC['lat']}&longitude={LOC['lon']}"
        f"&hourly=shortwave_radiation,diffuse_radiation,"
        f"direct_normal_irradiance,temperature_2m,windspeed_10m"
        f"&start_date={s}&end_date={e}&timezone=Africa%2FCasablanca"
    )
    r = requests.get(url, timeout=8); r.raise_for_status()
    d = r.json()["hourly"]
    df = pd.DataFrame(d)
    df.columns = ["time","GHI","DHI","DNI","Tamb","wind"]
    df["time"] = pd.to_datetime(df["time"])
    df = df[df["time"] <= pd.Timestamp.now()].dropna()
    if df.empty: return None
    row = df.iloc[-1]
    return {k: max(float(row[k]),0) if k!="Tamb" else float(row[k])
            for k in ["GHI","DHI","DNI","Tamb","wind"]} | {"ts": row.time}

# ════════════════════════════════════════
# FMU — PV_MPPT_Inverter1
# ════════════════════════════════════════
def fmu(G, Tamb, wind):
    G = max(G, 0.)
    Tc    = Tamb + G * max(0.0342 - 0.0043*wind, 0.008)
    Vmpp  = P["Vmp"]*P["Ns"]*(1 + P["Tc"]*(Tc-25))
    Impp  = P["Imp"]*P["Np"]*(G/1000)
    Ppv   = max(Vmpp*Impp, 0)
    Pb    = Ppv*0.97
    rat   = min(Pb/(P["Pmax"]*P["Ns"]*P["Np"]),1.) if P["Pmax"]>0 else 0
    if   rat<0.02: ei=0.
    elif rat<0.10: ei=0.880+0.085*(rat/0.10)
    elif rat<0.30: ei=0.965+0.005*((rat-0.10)/0.20)
    elif rat<0.70: ei=0.970
    else:          ei=0.970-0.003*((rat-0.70)/0.30)
    Pac = Pb*ei; cp=0.99
    return dict(Tc=Tc,Vmpp=Vmpp,Impp=Impp,Ppv=Ppv,Pboost=Pb,
                Pac=Pac,Vac=220.,S=Pac/cp,Q=(Pac/cp)*np.sqrt(max(1-cp**2,0)),
                eta=ei*100,THDv=1.8+0.5*(1-rat),THDi=3.0+2.0*(1-rat))

# ════════════════════════════════════════
# PVLIB
# ════════════════════════════════════════
def pvlib_calc(GHI,DHI,DNI,Tamb,wind,ts):
    try:
        loc = pvlib.location.Location(LOC["lat"],LOC["lon"],tz=LOC["tz"],altitude=LOC["alt"])
        t   = pd.DatetimeIndex([ts],tz=LOC["tz"])
        sol = loc.get_solarposition(t)
        poa = pvlib.irradiance.get_total_irradiance(
            P["tilt"],P["azimuth"],
            pd.Series([DNI],index=t),pd.Series([GHI],index=t),pd.Series([DHI],index=t),
            sol["apparent_zenith"],sol["azimuth"])
        pg  = max(float(poa["poa_global"].iloc[0]),0)
        tp  = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"]
        Tc  = pvlib.temperature.sapm_cell(
            pd.Series([pg],index=t),pd.Series([Tamb],index=t),pd.Series([wind],index=t),**tp)
        IL,I0,Rs,Rsh,nV = pvlib.pvsystem.calcparams_cec(
            pd.Series([pg],index=t),pd.Series([float(Tc.iloc[0])],index=t),
            P["alpha_sc"],P["a_ref"],P["I_L_ref"],P["I_o_ref"],
            P["R_sh_ref"],P["R_s"],P["Adjust"],1.121,-0.0002677)
        mpp = pvlib.pvsystem.max_power_point(IL,I0,Rs,Rsh,nV,method="newton")
        return max(float(mpp["p_mp"].iloc[0])*P["Ns"]*P["Np"],0.)
    except: return 0.

# ════════════════════════════════════════
# SESSION STATE
# ════════════════════════════════════════
KEYS=["ts","G","Tamb","Tc","Vmpp","Impp","Ppv","Pboost","Pac","eta","THDv","THDi","Ppvlib"]
for k in KEYS:
    if k not in st.session_state: st.session_state[k]=[]
if "run"  not in st.session_state: st.session_state.run  = False
if "tick" not in st.session_state: st.session_state.tick = 0
if "wx"   not in st.session_state: st.session_state.wx   = None

# ════════════════════════════════════════
# HEADER
# ════════════════════════════════════════
now = datetime.now()
run = st.session_state.run
live_html = '<span class="live-dot"></span>LIVE' if run else '◼ IDLE'
badge_bg  = 'rgba(34,197,94,.1)' if run else 'rgba(100,116,139,.1)'
badge_bd  = 'rgba(34,197,94,.3)' if run else 'rgba(100,116,139,.3)'
badge_col = '#22c55e' if run else '#64748b'

st.markdown(f"""
<div class="hdr">
  <div>
    <div class="hdr-title">⚡ PV MPPT · Supervision Temps Réel</div>
    <div class="hdr-sub">ENSET Mohammedia · FMU Simulink · PVLib · Open-Meteo API</div>
  </div>
  <div style="display:flex;align-items:center;gap:16px">
    <div style="display:inline-flex;align-items:center;gap:6px;
      background:{badge_bg};border:1px solid {badge_bd};
      border-radius:20px;padding:5px 14px;
      font-size:.7rem;font-weight:600;color:{badge_col};letter-spacing:1px;">
      <span style="width:7px;height:7px;border-radius:50%;background:{badge_col};
        {'box-shadow:0 0 6px '+badge_col+';animation:livepulse 1.4s infinite' if run else ''};display:inline-block"></span>
      {live_html}
    </div>
    <div style="text-align:right">
      <div class="hdr-time">{now.strftime('%H:%M:%S')}</div>
      <div class="hdr-date">{now.strftime('%A %d %B %Y')} · Mohammedia, Maroc</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════
# CONTROLS
# ════════════════════════════════════════
c1,c2,c3,_= st.columns([.8,.8,1,6])
with c1:
    if st.button("▶  START" if not run else "⏸  PAUSE", use_container_width=True):
        st.session_state.run = not st.session_state.run
        st.rerun()
with c2:
    if st.button("↺  Reset", use_container_width=True):
        for k in KEYS: st.session_state[k]=[]
        st.session_state.tick=0; st.session_state.wx=None
with c3:
    spd = st.select_slider("", options=[1,2,3,5,10],
                            value=1, label_visibility="collapsed",
                            format_func=lambda x: f"⏱ {x}s")

# ════════════════════════════════════════
# PLACEHOLDERS
# ════════════════════════════════════════
ph_flow = st.empty()

st.markdown('<div class="sh" style="--sh-ac:#fbbf24">Entrées — Open-Meteo (Mohammedia)</div>',
            unsafe_allow_html=True)
r1 = st.columns(5)
ph_GHI  = r1[0].empty(); ph_DNI  = r1[1].empty()
ph_DHI  = r1[2].empty(); ph_Tamb = r1[3].empty(); ph_Tc = r1[4].empty()

st.markdown('<div class="sh" style="--sh-ac:#3b82f6">FMU — PV_MPPT_Inverter1_grt_fmi_rtw (Simulink)</div>',
            unsafe_allow_html=True)
r2 = st.columns(6)
ph_Ppv=r2[0].empty(); ph_Vmpp=r2[1].empty(); ph_Impp=r2[2].empty()
ph_Pb =r2[3].empty(); ph_Pac =r2[4].empty(); ph_Vac =r2[5].empty()

st.markdown('<div class="sh" style="--sh-ac:#a855f7">Qualité · PVLib · Comparaison</div>',
            unsafe_allow_html=True)
r3 = st.columns(5)
ph_eta=r3[0].empty(); ph_THDv=r3[1].empty(); ph_THDi=r3[2].empty()
ph_Ppl=r3[3].empty(); ph_dlt =r3[4].empty()

st.markdown('<div class="sh" style="--sh-ac:#22c55e">Historique Live</div>',
            unsafe_allow_html=True)

ga,gb = st.columns([3,2])
with ga: ph_g1=st.empty()
with gb: ph_g2=st.empty()
gc2,gd2 = st.columns(2)
with gc2: ph_g3=st.empty()
with gd2: ph_g4=st.empty()

ph_st = st.empty()

# ════════════════════════════════════════
# HELPERS GRAPHIQUES
# ════════════════════════════════════════
BG  = dict(paper_bgcolor="#080c14", plot_bgcolor="#0d1424")
GRD = dict(gridcolor="rgba(30,58,100,.3)", showgrid=True, zeroline=False,
           tickcolor="#1e3a5f", color="#2d4060", tickfont=dict(size=9))
LEG = dict(bgcolor="rgba(8,12,20,.0)", borderwidth=0,
           font=dict(size=9,color="#4b6080"),
           orientation="h", y=1.03, x=0, xanchor="left")
MAR = dict(l=44,r=12,t=30,b=28)
FNT = dict(color="#2d4060",size=9)
CFG = {"displayModeBar":False}

COLORS = dict(
    GHI="#fbbf24", DNI="#f97316", DHI="#3b82f6",
    Tamb="#60a5fa", Tc="#ef4444",
    Ppv="#f59e0b", Pboost="#3b82f6", Pac="#22c55e", Ppvlib="#a855f7",
    eta="#a855f7", THDv="#f97316", THDi="#ef4444",
    delta="#ef4444",
)

def mfig(h=265):
    f=go.Figure()
    f.update_layout(height=h,**BG,margin=MAR,legend=LEG,font=FNT,
                    xaxis=dict(**GRD,tickformat="%H:%M:%S"),yaxis=dict(**GRD))
    return f

def kcard(val,unit,lbl,src,ac,glow):
    return f"""<div class="kcard" style="--ac:{ac};--ac-glow:{glow}">
<div class="kcard-val">{val}<span class="kcard-unit">{unit}</span></div>
<div class="kcard-lbl">{lbl}</div>
<div class="kcard-src">{src}</div>
</div>"""

# ════════════════════════════════════════
# BOUCLE PRINCIPALE
# ════════════════════════════════════════
while True:
    now = datetime.now()

    if st.session_state.run:
        # ── 1. METEO ──
        try:
            wx = get_meteo()
            if wx: st.session_state.wx = wx
        except: pass
        wx = st.session_state.wx
        if wx is None:
            ph_flow.error("⚠️ Open-Meteo inaccessible")
            time.sleep(spd); st.rerun()

        G,DHI,DNI = wx["GHI"],wx["DHI"],wx["DNI"]
        Tamb,wind = wx["Tamb"],wx["wind"]
        wxts      = wx["ts"]

        # ── 2. FMU ──
        fv = fmu(G, Tamb, wind)

        # ── 3. PVLIB ──
        ts_pv = wxts if wxts.tzinfo else wxts.tz_localize(LOC["tz"])
        Ppl   = pvlib_calc(G,DHI,DNI,Tamb,wind,ts_pv)

        # ── 4. HISTORIQUE ──
        h=st.session_state
        h.ts.append(now);h.G.append(G);h.Tamb.append(Tamb)
        h.Tc.append(fv["Tc"]);h.Vmpp.append(fv["Vmpp"]);h.Impp.append(fv["Impp"])
        h.Ppv.append(fv["Ppv"]);h.Pboost.append(fv["Pboost"])
        h.Pac.append(fv["Pac"]);h.eta.append(fv["eta"])
        h.THDv.append(fv["THDv"]);h.THDi.append(fv["THDi"])
        h.Ppvlib.append(Ppl)
        for k in KEYS:
            lst=getattr(h,k)
            if len(lst)>MAX_PTS: setattr(h,k,lst[-MAX_PTS:])
        h.tick+=1
        xs=h.ts[-MAX_PTS:]

        # ── 5. FLOW BAR ──
        ph_flow.markdown(f"""
<div class="flow">
  <span class="live-dot" style="margin:0"></span>
  <span style="color:#3b82f6;font-weight:600;font-size:.75rem">OPEN-METEO</span>
  <span class="flow-arr">→</span>
  <span class="flow-lbl">GHI</span><span class="flow-chip">{G:.0f} W/m²</span>
  <span class="flow-lbl">DNI</span><span class="flow-chip">{DNI:.0f} W/m²</span>
  <span class="flow-lbl">DHI</span><span class="flow-chip">{DHI:.0f} W/m²</span>
  <span class="flow-lbl">T_amb</span><span class="flow-chip">{Tamb:.1f} °C</span>
  <span class="flow-lbl">Vent</span><span class="flow-chip">{wind:.1f} m/s</span>
  <span class="flow-arr">→</span>
  <span style="color:#1d4ed8;font-weight:600;font-size:.75rem">FMU</span>
  <span class="flow-arr">+</span>
  <span style="color:#15803d;font-weight:600;font-size:.75rem">PVLib</span>
  <span class="flow-arr">→</span>
  <span class="flow-lbl">météo</span><span class="flow-chip">{wxts.strftime('%H:%M')}</span>
  <span class="flow-lbl">tick</span><span class="flow-chip">#{h.tick:05d}</span>
</div>""", unsafe_allow_html=True)

        # ── 6. GAUGES ENTREES ──
        ph_GHI.markdown( kcard(f"{G:.0f}",       "W/m²","GHI",     "Open-Meteo → Inport FMU","#fbbf24","rgba(251,191,36,.06)"), unsafe_allow_html=True)
        ph_DNI.markdown( kcard(f"{DNI:.0f}",      "W/m²","DNI",     "Open-Meteo","#f97316","rgba(249,115,22,.06)"), unsafe_allow_html=True)
        ph_DHI.markdown( kcard(f"{DHI:.0f}",      "W/m²","DHI",     "Open-Meteo","#3b82f6","rgba(59,130,246,.06)"), unsafe_allow_html=True)
        ph_Tamb.markdown(kcard(f"{Tamb:.1f}",     "°C",  "T_amb",   "→ Inport1 FMU","#60a5fa","rgba(96,165,250,.06)"), unsafe_allow_html=True)
        ph_Tc.markdown(  kcard(f"{fv['Tc']:.1f}", "°C",  "T_cell",  "modèle Faiman","#ef4444","rgba(239,68,68,.06)"), unsafe_allow_html=True)

        # ── 7. GAUGES FMU ──
        ph_Ppv.markdown( kcard(f"{fv['Ppv']/1000:.3f}",   "kW", "Ppanneau", "FMU output","#f59e0b","rgba(245,158,11,.06)"), unsafe_allow_html=True)
        ph_Vmpp.markdown(kcard(f"{fv['Vmpp']:.1f}",        "V",  "Vmpp",     "MPPT P&O","#f59e0b","rgba(245,158,11,.04)"), unsafe_allow_html=True)
        ph_Impp.markdown(kcard(f"{fv['Impp']:.2f}",        "A",  "Impp",     "MPPT P&O","#fbbf24","rgba(251,191,36,.04)"), unsafe_allow_html=True)
        ph_Pb.markdown(  kcard(f"{fv['Pboost']/1000:.3f}", "kW", "Pbooste",  "Boost η=97%","#3b82f6","rgba(59,130,246,.06)"), unsafe_allow_html=True)
        ph_Pac.markdown( kcard(f"{fv['Pac']/1000:.3f}",   "kW", "P_ondu",   "FMU output","#22c55e","rgba(34,197,94,.06)"), unsafe_allow_html=True)
        ph_Vac.markdown( kcard(f"{fv['Vac']:.0f}",        "V",  "Vonduleur","FMU output","#22c55e","rgba(34,197,94,.04)"), unsafe_allow_html=True)

        # ── 8. GAUGES QUALITE ──
        ph_eta.markdown( kcard(f"{fv['eta']:.1f}",   "%",  "Rendement","onduleur","#a855f7","rgba(168,85,247,.06)"), unsafe_allow_html=True)
        ph_THDv.markdown(kcard(f"{fv['THDv']:.2f}",  "%",  "THD_V",    "tension AC","#f97316","rgba(249,115,22,.06)"), unsafe_allow_html=True)
        ph_THDi.markdown(kcard(f"{fv['THDi']:.2f}",  "%",  "THD_i",    "courant AC","#ef4444","rgba(239,68,68,.06)"), unsafe_allow_html=True)
        ph_Ppl.markdown( kcard(f"{Ppl/1000:.3f}",    "kW", "P_pvlib",  "SDM-CEC","#a855f7","rgba(168,85,247,.06)"), unsafe_allow_html=True)
        dlt=fv["Ppv"]-Ppl
        dc="#22c55e" if abs(dlt)<100 else "#f59e0b" if abs(dlt)<300 else "#ef4444"
        ph_dlt.markdown( kcard(f"{dlt:+.0f}",        "W",  "Δ FMU−PVLib","écart instantané",dc,"rgba(0,0,0,0)"), unsafe_allow_html=True)

        # ── 9. GRAPHE PUISSANCES ──
        f1=mfig(270)
        f1.add_trace(go.Scatter(x=xs,y=h.Ppv[-MAX_PTS:],   name="Ppanneau",line=dict(color=COLORS["Ppv"],   width=2.2)))
        f1.add_trace(go.Scatter(x=xs,y=h.Pboost[-MAX_PTS:],name="Pbooste", line=dict(color=COLORS["Pboost"],width=1.5,dash="dot")))
        f1.add_trace(go.Scatter(x=xs,y=h.Pac[-MAX_PTS:],   name="P_ondu",  line=dict(color=COLORS["Pac"],   width=2.2)))
        f1.add_trace(go.Scatter(x=xs,y=h.Ppvlib[-MAX_PTS:],name="PVLib",   line=dict(color=COLORS["Ppvlib"],width=1.8,dash="dash")))
        f1.update_layout(yaxis_title="Puissance [W]",
            title=dict(text="Puissances DC / AC",font=dict(size=10,color="#2d4060"),x=0.01,y=.97))
        ph_g1.plotly_chart(f1,use_container_width=True,config=CFG)

        # ── 10. GRAPHE METEO ──
        f2=mfig(270)
        f2.add_trace(go.Scatter(x=xs,y=h.G[-MAX_PTS:],
            name="GHI",fill="tozeroy",
            line=dict(color=COLORS["GHI"],width=2),fillcolor="rgba(251,191,36,.07)"))
        f2.add_trace(go.Scatter(x=xs,y=h.Tamb[-MAX_PTS:],
            name="T_amb",line=dict(color=COLORS["Tamb"],width=2),yaxis="y2"))
        f2.add_trace(go.Scatter(x=xs,y=h.Tc[-MAX_PTS:],
            name="T_cell",line=dict(color=COLORS["Tc"],width=2,dash="dot"),yaxis="y2"))
        f2.update_layout(
            title=dict(text="Météo · Open-Meteo",font=dict(size=10,color="#2d4060"),x=0.01,y=.97),
            yaxis =dict(title="GHI [W/m²]",**GRD),
            yaxis2=dict(title="Temp [°C]",overlaying="y",side="right",
                        showgrid=False,tickcolor="#1e3a5f",color="#60a5fa",tickfont=dict(size=9)))
        ph_g2.plotly_chart(f2,use_container_width=True,config=CFG)

        # ── 11. GRAPHE QUALITE ──
        f3=make_subplots(rows=2,cols=1,shared_xaxes=True,
                         subplot_titles=("THD [%]","Rendement [%]"),vertical_spacing=0.1)
        f3.update_layout(height=265,**BG,margin=MAR,legend=LEG,font=FNT,
                         title=dict(text="Qualité onduleur",font=dict(size=10,color="#2d4060"),x=0.01,y=.97))
        f3.update_xaxes(**GRD,tickformat="%H:%M:%S")
        f3.update_yaxes(**GRD)
        f3.add_trace(go.Scatter(x=xs,y=h.THDv[-MAX_PTS:],name="THD_V",
            line=dict(color=COLORS["THDv"],width=2)),row=1,col=1)
        f3.add_trace(go.Scatter(x=xs,y=h.THDi[-MAX_PTS:],name="THD_i",
            line=dict(color=COLORS["THDi"],width=2,dash="dot")),row=1,col=1)
        f3.add_trace(go.Scatter(x=xs,y=h.eta[-MAX_PTS:],name="Rendement",
            fill="tozeroy",line=dict(color=COLORS["eta"],width=2),
            fillcolor="rgba(168,85,247,.08)"),row=2,col=1)
        ph_g3.plotly_chart(f3,use_container_width=True,config=CFG)

        # ── 12. GRAPHE FMU vs PVLIB ──
        fmu_a=np.array(h.Ppv[-MAX_PTS:],dtype=float)
        pvl_a=np.array(h.Ppvlib[-MAX_PTS:],dtype=float)
        diff =fmu_a-pvl_a
        f4=mfig(265)
        f4.add_trace(go.Scatter(x=xs,y=fmu_a,name="FMU",  line=dict(color=COLORS["Ppv"],width=2.2)))
        f4.add_trace(go.Scatter(x=xs,y=pvl_a,name="PVLib",line=dict(color=COLORS["Ppvlib"],width=2,dash="dash")))
        f4.add_trace(go.Scatter(x=xs,y=diff,name="Δ",fill="tozeroy",
            line=dict(color=COLORS["delta"],width=1.2),fillcolor="rgba(239,68,68,.08)"))
        if len(diff)>3:
            xn=np.arange(len(diff),dtype=float)
            m,b=np.polyfit(xn,diff,1)
            f4.add_trace(go.Scatter(x=xs,y=m*xn+b,name="tendance Δ",
                line=dict(color="#f97316",width=1,dash="dot"),showlegend=False))
        f4.update_layout(yaxis_title="W",
            title=dict(text="FMU vs PVLib · Δ instantané",font=dict(size=10,color="#2d4060"),x=0.01,y=.97))
        ph_g4.plotly_chart(f4,use_container_width=True,config=CFG)

        # ── 13. STATUS ──
        ph_st.markdown(f"""
<div class="statusbar">
  <span>SYS·ONLINE</span>
  <span>TICK·{h.tick:06d}</span>
  <span>HIST·{len(h.ts)}/{MAX_PTS}pts</span>
  <span>REFRESH·{spd}s</span>
  <span>METEO·{wxts.strftime('%H:%M')} UTC+1</span>
  <span>FMU·PV_MPPT_Inverter1_grt_fmi_rtw·FMI2.0</span>
  <span>{now.strftime('%Y-%m-%d %H:%M:%S')}</span>
</div>""", unsafe_allow_html=True)

    else:
        # PAUSE
        n=len(st.session_state.ts)
        ph_flow.markdown(f"""
<div class="flow">
  <span style="width:7px;height:7px;border-radius:50%;background:#374151;display:inline-block;margin-right:4px"></span>
  <span style="color:#475569;font-weight:600">EN PAUSE</span>
  <span class="flow-arr">—</span>
  <span class="flow-lbl">{n} points enregistrés. Appuyez sur</span>
  <span class="flow-chip">▶ START</span>
  <span class="flow-lbl">pour lancer la supervision temps réel.</span>
</div>""", unsafe_allow_html=True)

        if n>0:
            h=st.session_state; xs=h.ts[-MAX_PTS:]
            fmu_a=np.array(h.Ppv[-MAX_PTS:],dtype=float)
            pvl_a=np.array(h.Ppvlib[-MAX_PTS:],dtype=float)

            f1=mfig(270)
            f1.add_trace(go.Scatter(x=xs,y=h.Ppv[-MAX_PTS:],   name="Ppanneau",line=dict(color=COLORS["Ppv"],width=2.2)))
            f1.add_trace(go.Scatter(x=xs,y=h.Pboost[-MAX_PTS:],name="Pbooste", line=dict(color=COLORS["Pboost"],width=1.5,dash="dot")))
            f1.add_trace(go.Scatter(x=xs,y=h.Pac[-MAX_PTS:],   name="P_ondu",  line=dict(color=COLORS["Pac"],width=2.2)))
            f1.add_trace(go.Scatter(x=xs,y=h.Ppvlib[-MAX_PTS:],name="PVLib",   line=dict(color=COLORS["Ppvlib"],width=1.8,dash="dash")))
            f1.update_layout(yaxis_title="W")
            ph_g1.plotly_chart(f1,use_container_width=True,config=CFG)

            f4=mfig(265)
            f4.add_trace(go.Scatter(x=xs,y=fmu_a,name="FMU",  line=dict(color=COLORS["Ppv"],width=2.2)))
            f4.add_trace(go.Scatter(x=xs,y=pvl_a,name="PVLib",line=dict(color=COLORS["Ppvlib"],width=2,dash="dash")))
            f4.add_trace(go.Scatter(x=xs,y=fmu_a-pvl_a,name="Δ",fill="tozeroy",
                line=dict(color=COLORS["delta"],width=1.2),fillcolor="rgba(239,68,68,.08)"))
            ph_g4.plotly_chart(f4,use_container_width=True,config=CFG)

    time.sleep(spd)
    st.rerun()
