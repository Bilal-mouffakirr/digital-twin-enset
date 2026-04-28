# ☀️ PV Digital Twin — Streamlit Dashboard
### ENSET Mohammedia · Labo SSDIA · GE-GEER 2023-2024

Dashboard de supervision en temps réel d'une installation solaire PV hybride (3 960 Wc) avec jumeau numérique MATLAB/Simulink.

---

## 🚀 Lancement rapide

```bash
# 1. Cloner
git clone https://github.com/VOTRE_USERNAME/pv-digital-twin.git
cd pv-digital-twin

# 2. Installer dépendances
pip install -r requirements.txt

# 3. Lancer
streamlit run app.py
```

Dashboard disponible sur **http://localhost:8501**

---

## 📄 Pages

| Page | Description |
|------|-------------|
| **🏠 Dashboard** | KPIs temps réel, jauges, graphes horaires (Open-Meteo) |
| **🔬 Analyse Modèle** | Courbes P(G,T), heatmap, tableau de balayage |
| **🤖 Simulation MATLAB** | Exécution modèle FMU Simulink via fmpy |

---

## 🤖 Intégration FMU (MATLAB/Simulink)

1. Ouvrir `PV_MPPT_Inverter1_grt_fmi_rtw` dans Simulink
2. **Simulation → Export Model to → FMU 2.0 Co-Simulation**
3. Copier le `.fmu` dans `matlab_export/`
4. Page "Simulation MATLAB" → mode FMU → Lancer

---

## ☁️ Deploy sur Streamlit Cloud (gratuit)

1. Push le repo sur GitHub
2. Aller sur [share.streamlit.io](https://share.streamlit.io)
3. **New app** → choisir le repo → `app.py` → Deploy

---

## 📐 Modèle PV (identique MATLAB)

```
P = Pmax_STC × (1 + β × (Tc − Tref)) × G / G_STC
```

| Paramètre | Valeur |
|-----------|--------|
| Pmax STC  | 3 960 W (12 × 330W) |
| β         | -0.0035 /°C |
| Tref      | 25°C |
| G_STC     | 1000 W/m² |

---

## 👥 Équipe SSDIA

HAMI Hassan · LAGHASRI Ayoub · BAGHRAR Brahim · BERGDI Oussama · AZMAMI Halima · MGADA Mohammed Elhassan

**Encadrants:** M. EL BAHATI & M. EL MAGRI
