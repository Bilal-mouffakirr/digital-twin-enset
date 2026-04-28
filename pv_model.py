# utils/pv_model.py
# Modèle PV — identique formule MATLAB/Simulink
# Source: Rapport PI ENSET Mohammedia SSDIA 2023-2024

# ── Paramètres installation (Tableau 2 & 3 du rapport) ───────────────────────
INSTALLATION = {
    "site": {
        "name":      "ENSET Mohammedia — Labo SSDIA",
        "latitude":  33.6866,
        "longitude": -7.3833,
        "tilt":      31,    # degrés
        "azimuth":   0,     # Sud
    },
    "panel": {
        "model":     "Panneau 330W",
        "Pmax_stc":  330,       # W
        "Vmp":       37.65,     # V
        "Imp":       8.77,      # A
        "Voc":       44.4,      # V
        "Isc":       9.28,      # A
        "eta_ref":   0.17,      # 17%
        "beta":     -0.0035,    # /°C
        "Tref":      25.0,      # °C (STC)
        "Gref":      1000.0,    # W/m² (STC)
        "NOCT":      45.0,      # °C
    },
    "field": {
        "Ns":           12,     # panneaux en série
        "Np":           1,      # strings parallèle
        "total_panels": 12,
        "Pmax_field":   3960,   # Wc (12 × 330W)
    },
    "inverter": {
        "model":        "IMEON 3.6",
        "Pac_max":      3600,   # W
        "Vmppt_min":    120,    # V
        "Vmppt_max":    450,    # V
        "eta":          0.96,
    },
    "battery": {
        "Vbat":     12,         # V
        "capacity": 456,        # Ah
        "DOD":      0.80,
    },
}


def computePV(G: float, T_amb: float) -> dict:
    """
    Modèle de puissance maximale du champ PV.

    Formule (identique MATLAB):
        Pmodèle = Pmax_STC × (1 + β × (Tc − Tref)) × (G / G_STC)

    Paramètres
    ----------
    G     : Irradiation solaire (W/m²)
    T_amb : Température ambiante (°C)

    Retourne
    --------
    dict avec P_field, Vmp, Imp, Voc, Isc, eta, Tc
    """
    p = INSTALLATION["panel"]
    f = INSTALLATION["field"]

    if G is None or G < 5:
        return dict(P_field=0, P_single=0, eta=0, Isc=0, Voc=0, Vmp=0, Imp=0, Tc=T_amb or 25)

    # Température cellule (modèle NOCT)
    Tc = T_amb + ((p["NOCT"] - 20) / 800) * G

    # Facteur température
    k_T = 1 + p["beta"] * (Tc - p["Tref"])

    # Puissance 1 panneau
    P_single = p["Pmax_stc"] * k_T * (G / p["Gref"])
    P_single = max(0.0, P_single)

    # Champ complet
    P_field = P_single * f["total_panels"]

    # Tension et courant champ
    Vmp = p["Vmp"] * f["Ns"] * k_T
    Imp = p["Imp"] * f["Np"] * (G / p["Gref"])
    Voc = p["Voc"] * f["Ns"] * (1 + p["beta"] * (Tc - p["Tref"]) * 0.3)
    Isc = p["Isc"] * f["Np"] * (G / p["Gref"])

    # Efficacité réelle
    eta = p["eta_ref"] * k_T * 100

    return {
        "P_field":  round(P_field,  2),
        "P_single": round(P_single, 2),
        "eta":      round(eta,      3),
        "Isc":      round(Isc,      3),
        "Voc":      round(Voc,      2),
        "Vmp":      round(Vmp,      2),
        "Imp":      round(Imp,      3),
        "Tc":       round(Tc,       2),
    }
