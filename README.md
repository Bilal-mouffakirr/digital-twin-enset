# ☀️ PV MPPT Inverter – Streamlit Dashboard

Dashboard Streamlit pour simuler et visualiser un système photovoltaïque avec MPPT et onduleur, basé sur le FMU MATLAB/Simulink `PV_MPPT_Inverter1_grt_fmi_rtw`.

## 📸 Description

Ce projet est développé dans le cadre du **Projet d'Innovation – ENSET Mohammedia 2023-2024** :  
*Mise en service et supervision de l'installation solaire PV (Laboratoire SSDIA).*

### Architecture du système simulé

```
Open-Meteo API
(Mohammedia, Maroc)
       │
       ▼
  ┌────────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────┐
  │ Panneau PV │────▶│  Boost MPPT  │────▶│  Onduleur 3φ  │────▶│   Réseau AC  │
  │  330W×12S  │     │  (P&O algo)  │     │  (SPWM, VSI)  │     │  220V/50Hz   │
  └────────────┘     └──────────────┘     └───────────────┘     └──────────────┘
```

## 🗂️ Structure du projet

```
pv_dashboard/
├── app.py                          # Application Streamlit principale
├── requirements.txt                # Dépendances Python
├── README.md                       # Ce fichier
└── PV_MPPT_Inverter1.fmu          # FMU Simulink (à placer ici)
```

> **Note:** Le fichier `PV_MPPT_Inverter1.fmu` (win64) est généré depuis MATLAB/Simulink.  
> Le modèle Python dans `app.py` est une réplique fidèle de ce FMU, fonctionnant sur toutes les plateformes.

## ⚙️ Entrées / Sorties du FMU

**Entrées (Inport):**
| Variable | Description | Unité |
|---|---|---|
| `Inport` | Irradiance solaire GHI | W/m² |
| `Inport1` | Température ambiante | °C |

**Sorties (Output):**
| Variable | Description | Unité |
|---|---|---|
| `Vonduleur` | Tension de sortie onduleur | V |
| `Pbooste` | Puissance après convertisseur boost | W |
| `Ppanneau` | Puissance panneau PV (MPPT) | W |
| `S_ondu` | Puissance apparente onduleur | VA |
| `P_ondu` | Puissance active onduleur | W |
| `Q_ondu` | Puissance réactive onduleur | VAR |
| `THD_V` | Distorsion harmonique totale tension | % |
| `THD_i` | Distorsion harmonique totale courant | % |
| `rendemet de onduleur` | Rendement onduleur | % |

## ☀️ Caractéristiques du panneau (RAPPORT_PI.pdf – Tableau 2)

| Paramètre | Valeur |
|---|---|
| Puissance maximale (Pmax) | 330 W |
| Tolérance | +3% |
| Tension à puissance maximale (Vmp) | 37.65 V |
| Intensité à puissance maximale (Imp) | 8.77 A |
| Tension circuit ouvert (Voc) | 44.4 V |
| Intensité court-circuit (Isc) | 9.28 A |
| Efficacité Module | 17.0% |
| Configuration | 12 en série (string unique) |
| Total installés | 32 panneaux |
| Puissance crête totale | 3.96 kWc |
| Inclinaison | 31° (angle optimal) |
| Orientation | Sud (0° Azimut) |

## 🚀 Installation & Lancement

### 1. Cloner le dépôt
```bash
git clone https://github.com/<your-username>/pv-mppt-dashboard.git
cd pv-mppt-dashboard
```

### 2. Créer un environnement virtuel
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 3. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 4. Lancer l'application
```bash
streamlit run app.py
```

L'application s'ouvre automatiquement sur `http://localhost:8501`

## 📊 Fonctionnalités du Dashboard

### 📊 Onglet 1 – Résultats FMU
- KPIs temps réel : P_panneau, P_onduleur, Rendement, THD
- Graphes des puissances DC/AC sur la période sélectionnée
- Courbe de rendement et THD en fonction du temps
- Tableau des données exportable

### 🌤️ Onglet 2 – Données Météo
- Irradiance GHI, DHI, DNI depuis **Open-Meteo** (Mohammedia)
- Température ambiante et vitesse du vent
- Distribution horaire du rayonnement

### 📈 Onglet 3 – Comparaison PVLib
- Comparaison FMU Simulink vs **PVLib** (modèle SDM-CEC)
- Graphe de corrélation (scatter plot)
- Métriques : R², RMSE, Ratio moyen

### 🔬 Onglet 4 – Courbes Panneau
- Courbes I-V pour différentes irradiances (200–1000 W/m²)
- Courbes P-V pour différentes températures (15–55°C)
- Points MPP affichés sur chaque courbe
- Fiche technique complète du panneau

### ℹ️ Onglet 5 – À propos
- Architecture du projet
- Références FMU et rapport

## 🌍 Données météo (Open-Meteo)

L'application utilise l'API **Open-Meteo** (gratuite, sans clé API) :
- **Site:** Mohammedia, Maroc
- **Coordonnées:** 33.6861°N, 7.3828°W
- **Altitude:** 27 m
- **Variables:** `shortwave_radiation`, `diffuse_radiation`, `direct_normal_irradiance`, `temperature_2m`, `windspeed_10m`

## 📦 Dépendances principales

| Package | Usage |
|---|---|
| `streamlit` | Interface web |
| `pvlib` | Simulation PV (modèle CEC) |
| `plotly` | Graphiques interactifs |
| `fmpy` | Lecture/simulation FMU |
| `requests` | API Open-Meteo |
| `numpy/pandas` | Calcul numérique |

## 📄 Références

- **Rapport:** *Mise en service et supervision de l'installation solaire PV* – ENSET Mohammedia 2023-2024
- **FMU:** `PV_MPPT_Inverter1_grt_fmi_rtw` – MATLAB/Simulink R2022a (FMI 2.0)
- **Données météo:** [Open-Meteo](https://open-meteo.com)
- **PVLib:** [pvlib-python.readthedocs.io](https://pvlib-python.readthedocs.io)

## 👥 Équipe

HAMI Hassan · LAASRI Ayoub · BAGHAR Brahim · BERGDI Oussama · AZMAMI Halima · MGADA Mohammed Elhassan  
Encadrants: M. EL BAHATI & M. EL MAGRI
