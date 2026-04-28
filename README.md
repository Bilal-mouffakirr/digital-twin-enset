# ☀️ Solar Digital Twin — PV + MPPT + Inverter

> **Real-time co-simulation** of a photovoltaic system using a MATLAB/Simulink-generated FMU,
> live weather data from Open-Meteo, and a Streamlit web interface.

---

## 🌍 Overview

This project implements a **Digital Twin** for a grid-connected solar energy system located in
**Mohammedia, Morocco** (lat 33.68 °N, lon 7.38 °W).

Every time you open the app it:

1. **Fetches live weather** (temperature & solar irradiance) from [Open-Meteo](https://open-meteo.com/)
2. **Feeds the values** into a physics-accurate FMU model (exported from Simulink R2024a)
3. **Runs a 1-second Co-Simulation** step using the FMI 2.0 standard
4. **Displays** power quality metrics and time-series charts in an interactive dashboard

### System Architecture

```
Open-Meteo API
   │  Temperature (°C)
   │  Irradiance GHI (W/m²)
   ▼
┌─────────────────────────────────────────────┐
│          PV_MPPT_Inverter1.fmu              │
│  ┌──────┐   ┌──────┐   ┌────────────────┐  │
│  │  PV  │──▶│ MPPT │──▶│  3-φ Inverter  │  │
│  │ Panel│   │Boost │   │  (THD, PQ)     │  │
│  └──────┘   └──────┘   └────────────────┘  │
└─────────────────────────────────────────────┘
   │
   ▼
Streamlit Dashboard
```

---

## 📊 FMU Variables

| Direction | Variable | Description | Unit |
|-----------|----------|-------------|------|
| Input  | `Inport`  | Solar Irradiance (GHI) | W/m² |
| Input  | `Inport1` | Cell Temperature       | °C   |
| Output | `Ppanneau`| PV Panel Power         | W    |
| Output | `Pbooste` | Boost Converter Power  | W    |
| Output | `Vonduleur`| Inverter Output Voltage | V   |
| Output | `P_ondu`  | Active Power (AC)      | W    |
| Output | `Q_ondu`  | Reactive Power         | VAR  |
| Output | `S_ondu`  | Apparent Power         | VA   |
| Output | `THD_V`   | THD — Voltage          | %    |
| Output | `THD_i`   | THD — Current          | %    |
| Output | `rendemet de onduleur` | Inverter Efficiency | % |

---

## 🚀 Quick Start (Local)

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/solar-digital-twin.git
cd solar-digital-twin

# 2. Copy your FMU file
cp /path/to/PV_MPPT_Inverter1.fmu model.fmu

# 3. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run the app
streamlit run app.py
```

---

## ☁️ Deploy on Streamlit Community Cloud

1. Push this repository to **GitHub** (include `model.fmu`)
2. Go to [share.streamlit.io](https://share.streamlit.io/) → **New app**
3. Select your repo, branch `main`, main file `app.py`
4. Click **Deploy** — Streamlit Cloud reads `requirements.txt` and `packages.txt` automatically

> **Note:** `packages.txt` installs the system libraries (`libgfortran5`, etc.) needed
> for Simulink-generated FMU binaries to load on Ubuntu.

---

## 📁 Repository Structure

```
solar-digital-twin/
├── app.py             ← Streamlit application (main entry point)
├── model.fmu          ← FMU file (PV_MPPT_Inverter1, FMI 2.0 Co-Simulation)
├── requirements.txt   ← Python dependencies
├── packages.txt       ← APT system packages (for Linux/Cloud)
└── README.md          ← This file
```

---

## 🛠 Technology Stack

| Component | Technology |
|-----------|------------|
| Model format | FMI 2.0 Co-Simulation (`.fmu`) |
| Model source | MATLAB / Simulink R2024a + FMI Kit 3.1 |
| Simulation engine | [fmpy](https://github.com/CATIA-Systems/FMPy) |
| Weather data | [Open-Meteo API](https://open-meteo.com/) (free, no key needed) |
| Web framework | [Streamlit](https://streamlit.io/) |
| Hosting | [Streamlit Community Cloud](https://share.streamlit.io/) |

---

## 👤 Author

**Bilal Mouffakir** — Solar Energy Digital Twin Project  
FMU generated: 2026-04-28 | Simulink R2024a | FMI Kit 3.1
