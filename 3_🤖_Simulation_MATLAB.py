"""
pages/3_🤖_Simulation_MATLAB.py
Exécute le modèle FMU exporté depuis Simulink (ou simulation analytique)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path
import json
import subprocess
import sys

from utils.pv_model import computePV, INSTALLATION

st.set_page_config(page_title="Simulation MATLAB — PV Digital Twin", page_icon="🤖", layout="wide")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #020817; }
[data-testid="stSidebar"]          { background: #0f172a; }
h1,h2,h3 { color: #f1f5f9 !important; }
p, label  { color: #94a3b8 !important; }
</style>
""", unsafe_allow_html=True)

st.title("🤖 Simulation MATLAB / FMU")
st.caption("Modèle Simulink exporté en FMU 2.0 — exécution via fmpy")

st.divider()

# ── FMU status ────────────────────────────────────────────────────────────────
fmu_path = Path("matlab_export/PV_MPPT_Inverter1.fmu")
fmpy_ok  = False

try:
    import fmpy
    fmpy_ok = True
except ImportError:
    pass

col_fmu, col_py = st.columns(2)
with col_fmu:
    if fmu_path.exists():
        st.success(f"✅ FMU trouvé: `{fmu_path.name}`")
    else:
        st.warning("⚠️ FMU non trouvé — placer `PV_MPPT_Inverter1.fmu` dans `matlab_export/`")
        st.info("**Export depuis Simulink:**\nSimulation → Export Model to → FMU 2.0 Co-Simulation")

with col_py:
    if fmpy_ok:
        st.success("✅ fmpy installé")
    else:
        st.warning("⚠️ fmpy non installé")
        if st.button("📦 Installer fmpy"):
            with st.spinner("pip install fmpy..."):
                subprocess.run([sys.executable, "-m", "pip", "install", "fmpy"], capture_output=True)
            st.rerun()

st.divider()

# ── Mode simulation ───────────────────────────────────────────────────────────
mode = st.radio(
    "Mode de simulation",
    ["🔬 Analytique (sans FMU)", "🤖 FMU Simulink"],
    horizontal=True,
)

st.divider()

if "🔬 Analytique" in mode:
    st.subheader("🔬 Simulation analytique — profil journalier")

    col1, col2 = st.columns(2)
    with col1:
        T_profile = st.slider("Température max journalière (°C)", 20, 45, 32)
        G_peak    = st.slider("Irradiation pic (W/m²)", 400, 1200, 900, 50)
    with col2:
        duration_h = st.slider("Durée simulation (heures)", 6, 24, 12)
        step_min   = st.select_slider("Pas de temps", [1, 5, 10, 15, 30], value=5)

    if st.button("▶️ Lancer simulation", type="primary"):
        with st.spinner("Simulation en cours..."):
            # Génère profil solaire gaussien
            hours  = np.arange(0, duration_h, step_min / 60)
            t_peak = duration_h / 2

            G_profile = G_peak * np.exp(-0.5 * ((hours - t_peak) / (t_peak * 0.4)) ** 2)
            G_profile = np.clip(G_profile, 0, G_peak)

            T_profile_arr = T_profile - 5 + 8 * (hours / duration_h) * np.exp(1 - hours / t_peak)

            results = []
            for i, h in enumerate(hours):
                g = float(G_profile[i])
                t = float(T_profile_arr[i])
                r = computePV(g, t)
                results.append({
                    "Temps (h)": round(h, 2),
                    "G (W/m²)":  round(g, 1),
                    "T_amb (°C)": round(t, 1),
                    "Tc (°C)":   r["Tc"],
                    "P_PV (W)":  r["P_field"],
                    "Vmp (V)":   r["Vmp"],
                    "Imp (A)":   r["Imp"],
                    "η (%)":     r["eta"],
                })

            df_sim = pd.DataFrame(results)
            df_sim["E_cum (kWh)"] = (df_sim["P_PV (W)"] * step_min / 60 / 1000).cumsum()

            st.success(f"✅ Simulation terminée — {len(df_sim)} points")

            # Graphique multi-traces
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_sim["Temps (h)"], y=df_sim["P_PV (W)"],
                name="Puissance (W)", line=dict(color="#22c55e", width=2), yaxis="y1"))
            fig.add_trace(go.Scatter(x=df_sim["Temps (h)"], y=df_sim["G (W/m²)"],
                name="Irradiation (W/m²)", line=dict(color="#fbbf24", width=2, dash="dot"), yaxis="y2"))
            fig.add_trace(go.Scatter(x=df_sim["Temps (h)"], y=df_sim["T_amb (°C)"],
                name="Température (°C)", line=dict(color="#fb923c", width=2, dash="dash"), yaxis="y2"))

            fig.update_layout(
                paper_bgcolor="#0f172a", plot_bgcolor="#0f172a",
                font_color="#94a3b8", height=380,
                xaxis=dict(title="Temps (h)", gridcolor="#1e293b"),
                yaxis=dict(title="Puissance (W)", gridcolor="#1e293b", side="left"),
                yaxis2=dict(title="G / T", overlaying="y", side="right", gridcolor="#1e293b"),
                legend=dict(bgcolor="#0f172a"),
                margin=dict(t=20, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Métriques summary
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Énergie totale",  f"{df_sim['E_cum (kWh)'].iloc[-1]:.3f} kWh")
            m2.metric("Puissance pic",   f"{df_sim['P_PV (W)'].max():.0f} W")
            m3.metric("Efficacité moy.", f"{df_sim['η (%)'].mean():.2f}%")
            m4.metric("Tc max",          f"{df_sim['Tc (°C)'].max():.1f}°C")

            st.dataframe(df_sim.style.format({
                "G (W/m²)":    "{:.0f}",
                "T_amb (°C)":  "{:.1f}",
                "Tc (°C)":     "{:.1f}",
                "P_PV (W)":    "{:.1f}",
                "Vmp (V)":     "{:.1f}",
                "Imp (A)":     "{:.3f}",
                "η (%)":       "{:.2f}",
                "E_cum (kWh)": "{:.4f}",
            }), use_container_width=True, hide_index=True)

            csv = df_sim.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Télécharger résultats CSV", csv, "simulation_results.csv", "text/csv")

else:
    st.subheader("🤖 Simulation FMU Simulink")

    if not fmu_path.exists():
        st.error("❌ FMU non trouvé — voir instructions ci-dessus")
    elif not fmpy_ok:
        st.error("❌ fmpy non installé — cliquer 'Installer fmpy' ci-dessus")
    else:
        col1, col2 = st.columns(2)
        with col1:
            G_fmu = st.number_input("Irradiation G (W/m²)", 0, 1200, 800)
            T_fmu = st.number_input("Température T (°C)", 0, 50, 30)
        with col2:
            dur_fmu  = st.number_input("Durée (s)", 10, 10000, 3600)
            step_fmu = st.number_input("Pas de temps (s)", 0.1, 60.0, 1.0)

        if st.button("▶️ Lancer FMU", type="primary"):
            with st.spinner("Exécution du modèle Simulink FMU..."):
                try:
                    from fmpy import read_model_description, extract
                    from fmpy.fmi2 import FMU2Slave

                    model_desc = read_model_description(str(fmu_path))
                    unzipdir   = extract(str(fmu_path))

                    fmu = FMU2Slave(
                        guid=model_desc.guid,
                        unzipDirectory=unzipdir,
                        modelIdentifier=model_desc.coSimulation.modelIdentifier,
                        instanceName="PV_MPPT",
                    )
                    fmu.instantiate()
                    fmu.setupExperiment(startTime=0.0, stopTime=float(dur_fmu))
                    fmu.enterInitializationMode()

                    # Injecter entrées
                    for var in model_desc.modelVariables:
                        if var.name.lower() in ("g", "g_irradiance", "irradiance"):
                            fmu.setReal([var.valueReference], [float(G_fmu)])
                        if var.name.lower() in ("t", "t_amb", "temperature", "t_ambient"):
                            fmu.setReal([var.valueReference], [float(T_fmu)])

                    fmu.exitInitializationMode()

                    results, t = [], 0.0
                    step = float(step_fmu)
                    while t <= float(dur_fmu):
                        fmu.doStep(currentCommunicationPoint=t, communicationStepSize=step)
                        row = {"time_s": round(t, 2)}
                        for var in model_desc.modelVariables:
                            if var.causality == "output":
                                row[var.name] = fmu.getReal([var.valueReference])[0]
                        results.append(row)
                        t += step

                    fmu.terminate()
                    fmu.freeInstance()

                    df_fmu = pd.DataFrame(results)
                    st.success(f"✅ FMU terminé — {len(df_fmu)} points")
                    st.dataframe(df_fmu, use_container_width=True, hide_index=True)

                    csv = df_fmu.to_csv(index=False).encode("utf-8")
                    st.download_button("⬇️ Résultats FMU CSV", csv, "fmu_results.csv", "text/csv")

                except Exception as e:
                    st.error(f"Erreur FMU: {e}")
                    st.info("Vérifier que le FMU est exporté en **FMU 2.0 Co-Simulation** depuis Simulink.")
