"""
pages/2_🔬_Analyse_Modele.py
Comparaison modèle MATLAB vs données réelles + balayage G/T
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from utils.pv_model import computePV, INSTALLATION

st.set_page_config(page_title="Analyse Modèle — PV Digital Twin", page_icon="🔬", layout="wide")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #020817; }
[data-testid="stSidebar"]          { background: #0f172a; }
h1,h2,h3 { color: #f1f5f9 !important; }
p, label  { color: #94a3b8 !important; }
</style>
""", unsafe_allow_html=True)

st.title("🔬 Analyse du Modèle PV")
st.caption("Formule MATLAB: P = Pmax_STC × (1 + β(Tc − Tref)) × G/G_STC")

st.divider()

# ── Paramètres interactifs ────────────────────────────────────────────────────
st.subheader("⚙️ Simulation interactive")
col1, col2, col3 = st.columns(3)

with col1:
    G_sim = st.slider("Irradiation G (W/m²)", 0, 1200, 800, 50)
with col2:
    T_sim = st.slider("Température T_amb (°C)", 0, 50, 28, 1)
with col3:
    st.markdown("**Résultat instantané:**")
    res = computePV(G_sim, T_sim)
    st.metric("Puissance PV", f"{res['P_field']:.1f} W",
              delta=f"{res['P_field']/3960*100:.1f}% de Pnom")
    st.metric("Efficacité η", f"{res['eta']:.2f}%")
    st.metric("Tc cellule",   f"{res['Tc']:.1f}°C")

st.divider()

# ── Courbe P = f(G) pour plusieurs températures ───────────────────────────────
st.subheader("📈 Puissance en fonction de G — par température")

G_range = np.arange(0, 1201, 50)
T_list  = [15, 25, 35, 45]
colors  = ["#38bdf8", "#22c55e", "#f59e0b", "#ef4444"]

fig_pg = go.Figure()
for T, color in zip(T_list, colors):
    P_vals = [computePV(g, T)["P_field"] for g in G_range]
    fig_pg.add_trace(go.Scatter(
        x=G_range, y=P_vals,
        name=f"T = {T}°C",
        line=dict(color=color, width=2),
        mode="lines",
    ))

fig_pg.update_layout(
    paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
    font_color="#94a3b8", height=350,
    xaxis=dict(title="Irradiation (W/m²)", gridcolor="#1e293b"),
    yaxis=dict(title="Puissance PV (W)",   gridcolor="#1e293b"),
    legend=dict(bgcolor="#0f172a", bordercolor="#1e293b"),
    margin=dict(t=20, b=40),
)
st.plotly_chart(fig_pg, use_container_width=True)

# ── Heatmap P = f(G, T) ───────────────────────────────────────────────────────
st.subheader("🗺️ Carte de puissance P(G, T) — Heatmap")

G_ax = list(range(100, 1050, 100))
T_ax = list(range(15, 46, 5))
Z    = [[computePV(g, t)["P_field"] for g in G_ax] for t in T_ax]

fig_hm = go.Figure(go.Heatmap(
    z=Z, x=G_ax, y=T_ax,
    colorscale="YlOrRd",
    colorbar=dict(title="W", tickfont=dict(color="#94a3b8"), titlefont=dict(color="#94a3b8")),
    text=[[f"{v:.0f}W" for v in row] for row in Z],
    texttemplate="%{text}", textfont=dict(size=10),
    hovertemplate="G=%{x} W/m²<br>T=%{y}°C<br>P=%{z:.0f} W<extra></extra>",
))
fig_hm.update_layout(
    paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
    font_color="#94a3b8", height=350,
    xaxis=dict(title="Irradiation G (W/m²)"),
    yaxis=dict(title="Température T (°C)"),
    margin=dict(t=20, b=40),
)
st.plotly_chart(fig_hm, use_container_width=True)

# ── Balayage tableau ──────────────────────────────────────────────────────────
st.subheader("📋 Tableau de balayage G × T")

rows = []
for g in [200, 400, 600, 800, 1000]:
    for t in [20, 25, 30, 35, 40]:
        r = computePV(g, t)
        rows.append({
            "G (W/m²)":   g,
            "T_amb (°C)": t,
            "Tc (°C)":    r["Tc"],
            "P_field (W)": r["P_field"],
            "Vmp (V)":    r["Vmp"],
            "Imp (A)":    r["Imp"],
            "η (%)":      r["eta"],
        })

df = pd.DataFrame(rows)
st.dataframe(
    df.style.format({
        "Tc (°C)":     "{:.1f}",
        "P_field (W)": "{:.1f}",
        "Vmp (V)":     "{:.1f}",
        "Imp (A)":     "{:.2f}",
        "η (%)":       "{:.2f}",
    }).background_gradient(subset=["P_field (W)"], cmap="YlOrRd"),
    use_container_width=True, hide_index=True
)

csv = df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Télécharger tableau CSV", csv, "sweep_results.csv", "text/csv")

# ── Fiche installation ────────────────────────────────────────────────────────
st.divider()
st.subheader("📄 Fiche technique installation")
inst = INSTALLATION

col_a, col_b, col_c = st.columns(3)
with col_a:
    st.markdown("**🔆 Panneau PV**")
    st.markdown(f"""
    - Pmax STC: **{inst['panel']['Pmax_stc']} W**
    - Vmp: **{inst['panel']['Vmp']} V**
    - Imp: **{inst['panel']['Imp']} A**
    - Voc: **{inst['panel']['Voc']} V**
    - Isc: **{inst['panel']['Isc']} A**
    - η ref: **{inst['panel']['eta_ref']*100:.0f}%**
    - β: **{inst['panel']['beta']} /°C**
    """)
with col_b:
    st.markdown("**⚡ Champ PV**")
    st.markdown(f"""
    - 12 panneaux en série
    - 1 string parallèle
    - **Pmax = 3 960 Wc**
    - Vmp champ: **{inst['panel']['Vmp']*12:.1f} V**
    - Voc champ: **{inst['panel']['Voc']*12:.1f} V**
    - Orientation: **Sud 31°**
    """)
with col_c:
    st.markdown("**🔌 Onduleur IMEON 3.6**")
    st.markdown(f"""
    - Pac max: **3 600 W**
    - Pdc max: **3 960 Wc**
    - MPPT: **120 – 450 V**
    - Rendement: **~96%**
    - Batterie: **12V / 456 Ah**
    - DOD: **80%**
    """)
