"""
PV MPPT Inverter - Supervision TEMPS REEL
ENSET Mohammedia
Flux: Open-Meteo -> FMU + PVLib -> Dashboard live (chaque seconde)
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

# ══════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════
st.set_page_config(
    page_title="PV Supervision - ENSET Mohammedia",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Inter:wght@400;700&display=swap');
* { box-sizing: border-box; }
body, [class*="css"] { background: #050a14 !important; color: #e2e8f0; font-family: 'Inter', sans-serif; }

/* ---- header ---- */
.scada-header {
    background: linear-gradient(90deg, #0a1628 0%, #0d1f3c 50%, #0a1628 100%);
    border-bottom: 2px solid #1e40af;
    padding: 10px 20px;
    display: flex; align-items: center; justify-content: space-between;
    margin: -1rem -1rem 1rem -1rem;
}
.scada-title { font-size: 1.3rem; font-weight: 700; color: #60a5fa; letter-spacing: 2px; text-transform: uppercase; }
.scada-sub   { font-size: .7rem;  color: #475569; letter-spacing: 3px; text-transform: uppercase; }

/* ---- gauge card ---- */
.gauge-card {
    background: linear-gradient(145deg, #0d1b2e, #050a14);
    border: 1px solid #1e3a5f;
    border-radius: 10px;
    padding: 14px 10px 10px;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.gauge-card::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: var(--accent, #3b82f6);
}
.gauge-val  { font-family: 'Share Tech Mono', monospace; font-size: 2rem; font-weight: 700; color: var(--accent, #3b82f6); line-height: 1; }
.gauge-unit { font-size: .75rem; color: #64748b; margin-left: 3px; }
.gauge-lbl  { font-size: .65rem; color: #475569; text-transform: uppercase; letter-spacing: 1.5px; margin-top: 5px; }
.gauge-src  { font-size: .6rem; color: #1e3a5f; margin-top: 2px; }

/* ---- status dot ---- */
.dot-live { display:inline-block; width:8px; height:8px; border-radius:50%; background:#22c55e;
    box-shadow: 0 0 8px #22c55e; animation: blink 1s ease-in-out infinite; margin-right:5px; }
.dot-warn { display:inline-block; width:8px; height:8px; border-radius:50%; background:#f59e0b;
    box-shadow: 0 0 8px #f59e0b; margin-right:5px; }
.dot-off  { display:inline-block; width:8px; height:8px; border-radius:50%; background:#374151; margin-right:5px; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }

/* ---- flow bar ---- */
.flow-bar {
    background: #0a1628; border: 1px solid #1e3a5f; border-radius: 8px;
    padding: 8px 16px; font-size: .78rem; color: #94a3b8;
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px;
}
.flow-val { color: #60a5fa; font-family: 'Share Tech Mono', monospace; font-weight: 700; }
.flow-sep { color: #1e3a5f; }

/* ---- section label ---- */
.sec-lbl {
    font-size: .65rem; letter-spacing: 3px; text-transform: uppercase;
    color: #334155; border-bottom: 1px solid #1e293b;
    padding-bottom: 3px; margin: 12px 0 6px;
}

/* ---- bottom bar ---- */
.bottom-bar {
    background: #0a1628; border-top: 1px solid #1e3a5f;
    padding: 5px 16px; font-size: .65rem; color: #334155;
    font-family: 'Share Tech Mono', monospace; letter-spacing: 1px;
    margin: 8px -1rem -1rem; display: flex; justify-content: space-between;
}

/* plotly override */
.js-plotly-plot .plotly .modebar { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════
# CONSTANTES PANNEAU (Rapport PI - Tableau 2)
# ══════════════════════════════════════════
LOCATION = dict(lat=33.6861, lon=-7.3828, alt=27, tz="Africa/Casablanca")
P = dict(
    Pmax=330, Vmp=37.65, Imp=8.77, Voc=44.4, Isc=9.28,
    Tc=-0.0035, Ns=12, Np=1, tilt=31, azimuth=180,
    alpha_sc=0.004539, a_ref=1.5, I_L_ref=9.28,
    I_o_ref=2.2e-10, R_sh_ref=525.0, R_s=0.35, Adjust=8.7,
)
MAX_PTS = 300  # ~5 min d'historique a 1s

# ══════════════════════════════════════════
# OPEN-METEO — donnee de l'heure courante
# cache 5 min (API horaire)
# ══════════════════════════════════════════
@st.cache_data(ttl=300)
def get_meteo():
    now   = datetime.now()
    start = (now - timedelta(hours=2)).strftime("%Y-%m-%d")
    end   = now.strftime("%Y-%m-%d")
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LOCATION['lat']}&longitude={LOCATION['lon']}"
        "&hourly=shortwave_radiation,diffuse_radiation,"
        "direct_normal_irradiance,temperature_2m,windspeed_10m"
        f"&start_date={start}&end_date={end}"
        "&timezone=Africa%2FCasablanca"
    )
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    d  = r.json()["hourly"]
    df = pd.DataFrame(d)
    df.columns = ["time","GHI","DHI","DNI","Tamb","wind"]
    df["time"] = pd.to_datetime(df["time"])
    df = df[df["time"] <= pd.Timestamp.now()].dropna()
    if df.empty: return None
    row = df.iloc[-1]
    return {k: max(float(row[k]), 0) if k != "Tamb" else float(row[k])
            for k in ["GHI","DHI","DNI","Tamb","wind"]} | {"ts": row.time}

# ══════════════════════════════════════════
# FMU — PV_MPPT_Inverter1 replica
#   Inport  -> G [W/m2]
#   Inport1 -> Tamb [C]
# ══════════════════════════════════════════
def fmu(G, Tamb, wind):
    G = max(G, 0.0)
    Tc   = Tamb + G * max(0.0342 - 0.0043 * wind, 0.008)
    Vmpp = P["Vmp"] * P["Ns"] * (1 + P["Tc"] * (Tc - 25))
    Impp = P["Imp"] * P["Np"] * (G / 1000)
    Ppv  = max(Vmpp * Impp, 0)
    Pboost = Ppv * 0.97
    Prated = P["Pmax"] * P["Ns"] * P["Np"]
    r = min(Pboost / Prated, 1.0) if Prated > 0 else 0
    if   r < 0.02: ei = 0.0
    elif r < 0.10: ei = 0.88  + 0.085*(r/0.10)
    elif r < 0.30: ei = 0.965 + 0.005*((r-0.10)/0.20)
    elif r < 0.70: ei = 0.970
    else:          ei = 0.970 - 0.003*((r-0.70)/0.30)
    Pac   = Pboost * ei
    Vac   = 220.0
    cosphi= 0.99
    S     = Pac / cosphi
    Q     = S * (1 - cosphi**2)**0.5
    return dict(
        G=G, Tamb=Tamb, Tc=Tc, Vmpp=Vmpp, Impp=Impp,
        Ppv=Ppv, Pboost=Pboost, Pac=Pac, Vac=Vac,
        S=S, Q=Q, eta=ei*100,
        THDv=1.8+0.5*(1-r), THDi=3.0+2.0*(1-r),
    )

# ══════════════════════════════════════════
# PVLIB — SDM-CEC
# ══════════════════════════════════════════
def pvlib_calc(GHI, DHI, DNI, Tamb, wind, ts):
    try:
        loc   = pvlib.location.Location(LOCATION["lat"], LOCATION["lon"],
                                         tz=LOCATION["tz"], altitude=LOCATION["alt"])
        tpv   = pd.DatetimeIndex([ts], tz=LOCATION["tz"])
        sol   = loc.get_solarposition(tpv)
        poa   = pvlib.irradiance.get_total_irradiance(
            P["tilt"], P["azimuth"],
            pd.Series([DNI],index=tpv), pd.Series([GHI],index=tpv),
            pd.Series([DHI],index=tpv),
            sol["apparent_zenith"], sol["azimuth"])
        pg    = max(float(poa["poa_global"].iloc[0]), 0)
        tp    = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"]
        Tc    = pvlib.temperature.sapm_cell(
            pd.Series([pg],index=tpv), pd.Series([Tamb],index=tpv),
            pd.Series([wind],index=tpv), **tp)
        IL,I0,Rs,Rsh,nV = pvlib.pvsystem.calcparams_cec(
            pd.Series([pg],index=tpv), pd.Series([float(Tc.iloc[0])],index=tpv),
            P["alpha_sc"],P["a_ref"],P["I_L_ref"],P["I_o_ref"],
            P["R_sh_ref"],P["R_s"],P["Adjust"],1.121,-0.0002677)
        mpp = pvlib.pvsystem.max_power_point(IL,I0,Rs,Rsh,nV,method="newton")
        return max(float(mpp["p_mp"].iloc[0])*P["Ns"]*P["Np"], 0)
    except:
        return 0.0

# ══════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════
KEYS = ["ts","G","Tamb","Tc","Vmpp","Impp","Ppv",
        "Pboost","Pac","Vac","eta","THDv","THDi","Ppvlib"]
for k in KEYS:
    if k not in st.session_state: st.session_state[k] = []
if "run"   not in st.session_state: st.session_state.run   = False
if "tick"  not in st.session_state: st.session_state.tick  = 0
if "wx"    not in st.session_state: st.session_state.wx    = None
if "wxts"  not in st.session_state: st.session_state.wxts  = None

# ══════════════════════════════════════════
# HEADER SCADA
# ══════════════════════════════════════════
now = datetime.now()

dot = '<span class="dot-live"></span>' if st.session_state.run else '<span class="dot-off"></span>'
st.markdown(f"""
<div class="scada-header">
  <div>
    <div class="scada-title">⚡ PV MPPT — Supervision Temps Réel</div>
    <div class="scada-sub">ENSET Mohammedia · FMU Simulink · PVLib · Open-Meteo</div>
  </div>
  <div style="text-align:right">
    <div style="font-family:'Share Tech Mono';color:#60a5fa;font-size:1.2rem">{now.strftime('%H:%M:%S')}</div>
    <div style="font-size:.65rem;color:#334155">{now.strftime('%Y-%m-%d')} — Mohammedia, Maroc</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════
# CONTROLS (inline)
# ══════════════════════════════════════════
ctl1, ctl2, ctl3, ctl4 = st.columns([1,1,1,5])
with ctl1:
    if st.button("▶ START" if not st.session_state.run else "⏸ PAUSE",
                 type="primary", use_container_width=True):
        st.session_state.run = not st.session_state.run
with ctl2:
    if st.button("🔄 Reset", use_container_width=True):
        for k in KEYS: st.session_state[k] = []
        st.session_state.tick = 0
        st.session_state.wx   = None
with ctl3:
    spd = st.selectbox("Refresh", [1,2,3,5], index=0, label_visibility="collapsed")

# ══════════════════════════════════════════
# FLOW BAR (meteo actuelle)
# ══════════════════════════════════════════
ph_flow = st.empty()

# ══════════════════════════════════════════
# GAUGES INSTANTANEES — ligne 1 (entrees)
# ══════════════════════════════════════════
st.markdown('<div class="sec-lbl">📡 Entrées — Open-Meteo (temps réel)</div>', unsafe_allow_html=True)
gc = st.columns(5)
ph_G    = gc[0].empty()
ph_DNI  = gc[1].empty()
ph_DHI  = gc[2].empty()
ph_Tamb = gc[3].empty()
ph_Tc   = gc[4].empty()

# GAUGES — ligne 2 (sorties FMU)
st.markdown('<div class="sec-lbl">🔧 Sorties FMU — PV_MPPT_Inverter1 (Simulink)</div>', unsafe_allow_html=True)
gf = st.columns(6)
ph_Ppv    = gf[0].empty()
ph_Vmpp   = gf[1].empty()
ph_Impp   = gf[2].empty()
ph_Pboost = gf[3].empty()
ph_Pac    = gf[4].empty()
ph_Vac    = gf[5].empty()

# GAUGES — ligne 3 (qualite)
st.markdown('<div class="sec-lbl">📊 Qualité onduleur + PVLib</div>', unsafe_allow_html=True)
gq = st.columns(5)
ph_eta    = gq[0].empty()
ph_THDv   = gq[1].empty()
ph_THDi   = gq[2].empty()
ph_Ppvlib = gq[3].empty()
ph_delta  = gq[4].empty()

# ══════════════════════════════════════════
# GRAPHES
# ══════════════════════════════════════════
st.markdown('<div class="sec-lbl">📈 Historique live</div>', unsafe_allow_html=True)
ca, cb = st.columns([3, 2])
with ca: ph_chart_pwr = st.empty()
with cb: ph_chart_met = st.empty()

cc, cd = st.columns(2)
with cc: ph_chart_qual = st.empty()
with cd: ph_chart_cmp  = st.empty()

ph_status = st.empty()

# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════
BG   = dict(paper_bgcolor="#050a14", plot_bgcolor="#0a1628")
GRD  = dict(gridcolor="#0d1f3c", showgrid=True, zeroline=False, color="#334155")
LEG  = dict(bgcolor="#050a14", bordercolor="#1e3a5f", font=dict(size=9,color="#94a3b8"),
            orientation="h", y=1.02, x=0)
MAR  = dict(l=48,r=12,t=28,b=32)
FNT  = dict(color="#64748b", size=10)

def mk_fig(h=260):
    f = go.Figure()
    f.update_layout(height=h, **BG, margin=MAR, legend=LEG, font=FNT,
                    xaxis=dict(**GRD, tickformat="%H:%M:%S"),
                    yaxis=dict(**GRD))
    return f

def gauge_html(val, unit, lbl, src, color):
    return f"""
<div class="gauge-card" style="--accent:{color}">
  <div class="gauge-val">{val}<span class="gauge-unit">{unit}</span></div>
  <div class="gauge-lbl">{lbl}</div>
  <div class="gauge-src">{src}</div>
</div>"""

# ══════════════════════════════════════════
# BOUCLE PRINCIPALE
# ══════════════════════════════════════════
while True:
    now = datetime.now()

    if st.session_state.run:

        # ─── 1. METEO (cache 5 min, API horaire) ───
        try:
            wx = get_meteo()
            if wx: st.session_state.wx = wx
        except Exception as e:
            wx = st.session_state.wx

        wx = st.session_state.wx
        if wx is None:
            ph_flow.warning("⚠️ Open-Meteo inaccessible — vérifiez la connexion.")
            time.sleep(spd); st.rerun()

        G    = wx["GHI"]
        DHI  = wx["DHI"]
        DNI  = wx["DNI"]
        Tamb = wx["Tamb"]
        wind = wx["wind"]
        wxts = wx["ts"]

        # ─── 2. FMU (Inport=G, Inport1=Tamb) ───
        r = fmu(G, Tamb, wind)

        # ─── 3. PVLib ───
        ts_pv = wxts if wxts.tzinfo else wxts.tz_localize(LOCATION["tz"])
        Ppvlib = pvlib_calc(G, DHI, DNI, Tamb, wind, ts_pv)

        # ─── 4. Historique ───
        h = st.session_state
        h.ts.append(now); h.G.append(G); h.Tamb.append(Tamb)
        h.Tc.append(r["Tc"]); h.Vmpp.append(r["Vmpp"]); h.Impp.append(r["Impp"])
        h.Ppv.append(r["Ppv"]); h.Pboost.append(r["Pboost"])
        h.Pac.append(r["Pac"]); h.Vac.append(r["Vac"])
        h.eta.append(r["eta"]); h.THDv.append(r["THDv"]); h.THDi.append(r["THDi"])
        h.Ppvlib.append(Ppvlib)
        for k in KEYS:
            lst = getattr(h, k)
            if len(lst) > MAX_PTS: setattr(h, k, lst[-MAX_PTS:])
        h.tick += 1

        xs = h.ts[-MAX_PTS:]

        # ─── 5. FLOW BAR ───
        ph_flow.markdown(f"""
<div class="flow-bar">
  <span class="dot-live"></span>
  <b style="color:#60a5fa">OPEN-METEO</b>
  <span class="flow-sep">→</span>
  GHI <span class="flow-val">{G:.0f} W/m²</span>
  <span class="flow-sep">|</span>
  DNI <span class="flow-val">{DNI:.0f} W/m²</span>
  <span class="flow-sep">|</span>
  DHI <span class="flow-val">{DHI:.0f} W/m²</span>
  <span class="flow-sep">|</span>
  T_amb <span class="flow-val">{Tamb:.1f} °C</span>
  <span class="flow-sep">|</span>
  Vent <span class="flow-val">{wind:.1f} m/s</span>
  <span class="flow-sep">→</span>
  <b style="color:#1d4ed8">FMU</b>
  <span class="flow-sep">+</span>
  <b style="color:#15803d">PVLib</b>
  <span class="flow-sep">→</span>
  heure météo <span class="flow-val">{wxts.strftime('%H:%M')}</span>
  <span class="flow-sep">|</span>
  tick <span class="flow-val">#{h.tick}</span>
</div>""", unsafe_allow_html=True)

        # ─── 6. GAUGES ENTREES ───
        ph_G.markdown(gauge_html(f"{G:.0f}","W/m²","GHI","Open-Meteo","#fbbf24"), unsafe_allow_html=True)
        ph_DNI.markdown(gauge_html(f"{DNI:.0f}","W/m²","DNI","Open-Meteo","#f97316"), unsafe_allow_html=True)
        ph_DHI.markdown(gauge_html(f"{DHI:.0f}","W/m²","DHI","Open-Meteo","#3b82f6"), unsafe_allow_html=True)
        ph_Tamb.markdown(gauge_html(f"{Tamb:.1f}","°C","T_amb","→ Inport1 FMU","#0ea5e9"), unsafe_allow_html=True)
        ph_Tc.markdown(gauge_html(f"{r['Tc']:.1f}","°C","T_cell","Faiman model","#ef4444"), unsafe_allow_html=True)

        # ─── 7. GAUGES FMU SORTIES ───
        ph_Ppv.markdown(gauge_html(f"{r['Ppv']/1000:.3f}","kW","Ppanneau","FMU output","#f59e0b"), unsafe_allow_html=True)
        ph_Vmpp.markdown(gauge_html(f"{r['Vmpp']:.1f}","V","Vmpp","MPPT P&O","#f59e0b"), unsafe_allow_html=True)
        ph_Impp.markdown(gauge_html(f"{r['Impp']:.2f}","A","Impp","MPPT P&O","#fbbf24"), unsafe_allow_html=True)
        ph_Pboost.markdown(gauge_html(f"{r['Pboost']/1000:.3f}","kW","Pbooste","Boost η=97%","#3b82f6"), unsafe_allow_html=True)
        ph_Pac.markdown(gauge_html(f"{r['Pac']/1000:.3f}","kW","P_ondu (AC)","FMU output","#22c55e"), unsafe_allow_html=True)
        ph_Vac.markdown(gauge_html(f"{r['Vac']:.0f}","V","Vonduleur","FMU output","#22c55e"), unsafe_allow_html=True)

        # ─── 8. GAUGES QUALITE ───
        ph_eta.markdown(gauge_html(f"{r['eta']:.1f}","%","Rendement","onduleur","#a855f7"), unsafe_allow_html=True)
        ph_THDv.markdown(gauge_html(f"{r['THDv']:.2f}","%","THD_V","tension AC","#f97316"), unsafe_allow_html=True)
        ph_THDi.markdown(gauge_html(f"{r['THDi']:.2f}","%","THD_i","courant AC","#ef4444"), unsafe_allow_html=True)
        ph_Ppvlib.markdown(gauge_html(f"{Ppvlib/1000:.3f}","kW","P_pvlib","SDM-CEC","#a855f7"), unsafe_allow_html=True)
        delta = r["Ppv"] - Ppvlib
        dcol  = "#22c55e" if abs(delta) < 100 else "#f59e0b" if abs(delta) < 300 else "#ef4444"
        ph_delta.markdown(gauge_html(f"{delta:+.0f}","W","Δ FMU−PVLib","écart","#64748b"), unsafe_allow_html=True)

        # ─── 9. GRAPHE PUISSANCES ───
        f1 = mk_fig(270)
        f1.add_trace(go.Scatter(x=xs,y=h.Ppv[-MAX_PTS:],    name="Ppanneau [W]", line=dict(color="#f59e0b",width=2)))
        f1.add_trace(go.Scatter(x=xs,y=h.Pboost[-MAX_PTS:], name="Pbooste [W]",  line=dict(color="#3b82f6",width=1.5,dash="dot")))
        f1.add_trace(go.Scatter(x=xs,y=h.Pac[-MAX_PTS:],    name="P_ondu [W]",   line=dict(color="#22c55e",width=2)))
        f1.add_trace(go.Scatter(x=xs,y=h.Ppvlib[-MAX_PTS:], name="PVLib [W]",    line=dict(color="#a855f7",width=1.8,dash="dash")))
        f1.update_layout(title=dict(text="Puissances FMU + PVLib",font=dict(size=11,color="#475569"),x=0),
                         yaxis_title="W")
        ph_chart_pwr.plotly_chart(f1, use_container_width=True, config={"displayModeBar":False})

        # ─── 10. GRAPHE METEO ───
        f2 = mk_fig(270)
        f2.add_trace(go.Scatter(x=xs,y=h.G[-MAX_PTS:],
            name="GHI [W/m²]", fill="tozeroy",
            line=dict(color="#fbbf24",width=2), fillcolor="rgba(251,191,36,.08)"))
        f2.add_trace(go.Scatter(x=xs,y=h.Tamb[-MAX_PTS:],
            name="T_amb [°C]", line=dict(color="#3b82f6",width=2), yaxis="y2"))
        f2.add_trace(go.Scatter(x=xs,y=h.Tc[-MAX_PTS:],
            name="T_cell [°C]", line=dict(color="#ef4444",width=2,dash="dot"), yaxis="y2"))
        f2.update_layout(
            title=dict(text="Météo — Open-Meteo",font=dict(size=11,color="#475569"),x=0),
            yaxis =dict(title="GHI [W/m²]",**GRD),
            yaxis2=dict(title="Temp [°C]", overlaying="y", side="right",
                        showgrid=False, color="#3b82f6"))
        ph_chart_met.plotly_chart(f2, use_container_width=True, config={"displayModeBar":False})

        # ─── 11. GRAPHE QUALITE ───
        f3 = make_subplots(rows=2,cols=1,shared_xaxes=True,
                           subplot_titles=("THD [%]","Rendement [%]"),
                           vertical_spacing=0.12)
        f3.update_layout(height=260,**BG,margin=MAR,legend=LEG,font=FNT)
        f3.update_xaxes(**GRD,tickformat="%H:%M:%S")
        f3.update_yaxes(**GRD)
        f3.add_trace(go.Scatter(x=xs,y=h.THDv[-MAX_PTS:],name="THD_V",line=dict(color="#f97316",width=2)),row=1,col=1)
        f3.add_trace(go.Scatter(x=xs,y=h.THDi[-MAX_PTS:],name="THD_i",line=dict(color="#ef4444",width=2,dash="dot")),row=1,col=1)
        f3.add_trace(go.Scatter(x=xs,y=h.eta[-MAX_PTS:],name="eta",fill="tozeroy",
            line=dict(color="#a855f7",width=2),fillcolor="rgba(168,85,247,.1)"),row=2,col=1)
        ph_chart_qual.plotly_chart(f3, use_container_width=True, config={"displayModeBar":False})

        # ─── 12. GRAPHE FMU vs PVLIB ───
        fmu_a  = np.array(h.Ppv[-MAX_PTS:],    dtype=float)
        pvl_a  = np.array(h.Ppvlib[-MAX_PTS:], dtype=float)
        diff_a = fmu_a - pvl_a
        f4 = mk_fig(260)
        f4.add_trace(go.Scatter(x=xs,y=fmu_a, name="FMU [W]",  line=dict(color="#f59e0b",width=2)))
        f4.add_trace(go.Scatter(x=xs,y=pvl_a, name="PVLib [W]",line=dict(color="#a855f7",width=2,dash="dash")))
        f4.add_trace(go.Scatter(x=xs,y=diff_a,name="Delta",fill="tozeroy",
            line=dict(color="#ef4444",width=1.2),fillcolor="rgba(239,68,68,.1)"))
        f4.update_layout(title=dict(text="FMU vs PVLib",font=dict(size=11,color="#475569"),x=0),
                         yaxis_title="W")
        ph_chart_cmp.plotly_chart(f4, use_container_width=True, config={"displayModeBar":False})

        # ─── 13. STATUS ───
        ph_status.markdown(f"""
<div class="bottom-bar">
  <span>SYS: ONLINE</span>
  <span>TICK: {h.tick:06d}</span>
  <span>PTS: {len(h.ts)}/{MAX_PTS}</span>
  <span>REFRESH: {spd}s</span>
  <span>METEO: {wxts.strftime('%H:%M')} UTC+1</span>
  <span>{now.strftime('%Y-%m-%d %H:%M:%S')}</span>
</div>""", unsafe_allow_html=True)

    else:
        # PAUSE
        ph_flow.markdown(f"""
<div class="flow-bar">
  <span class="dot-off"></span>
  <b style="color:#475569">EN PAUSE</b>
  <span class="flow-sep">—</span>
  {len(st.session_state.ts)} points enregistrés.
  Appuyez sur <b>▶ START</b> pour lancer la simulation temps réel.
</div>""", unsafe_allow_html=True)

        # Afficher dernier etat si disponible
        if len(st.session_state.ts) > 0:
            h  = st.session_state
            xs = h.ts[-MAX_PTS:]
            fmu_a  = np.array(h.Ppv[-MAX_PTS:],    dtype=float)
            pvl_a  = np.array(h.Ppvlib[-MAX_PTS:], dtype=float)
            diff_a = fmu_a - pvl_a

            f1 = mk_fig(270)
            f1.add_trace(go.Scatter(x=xs,y=h.Ppv[-MAX_PTS:],   name="Ppanneau",line=dict(color="#f59e0b",width=2)))
            f1.add_trace(go.Scatter(x=xs,y=h.Pboost[-MAX_PTS:],name="Pbooste", line=dict(color="#3b82f6",width=1.5,dash="dot")))
            f1.add_trace(go.Scatter(x=xs,y=h.Pac[-MAX_PTS:],   name="P_ondu",  line=dict(color="#22c55e",width=2)))
            f1.add_trace(go.Scatter(x=xs,y=h.Ppvlib[-MAX_PTS:],name="PVLib",   line=dict(color="#a855f7",width=1.8,dash="dash")))
            ph_chart_pwr.plotly_chart(f1, use_container_width=True, config={"displayModeBar":False})

            f4 = mk_fig(260)
            f4.add_trace(go.Scatter(x=xs,y=fmu_a, name="FMU",  line=dict(color="#f59e0b",width=2)))
            f4.add_trace(go.Scatter(x=xs,y=pvl_a, name="PVLib",line=dict(color="#a855f7",width=2,dash="dash")))
            f4.add_trace(go.Scatter(x=xs,y=diff_a,name="Delta",fill="tozeroy",
                line=dict(color="#ef4444",width=1.2),fillcolor="rgba(239,68,68,.1)"))
            ph_chart_cmp.plotly_chart(f4, use_container_width=True, config={"displayModeBar":False})

    time.sleep(spd)
    st.rerun()
