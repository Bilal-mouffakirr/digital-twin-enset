# ☀️ PV MPPT Inverter – Streamlit Dashboard

Dashboard interactif pour la simulation du modèle **PV_MPPT_Inverter1** généré par Simulink R2024a (FMI 2.0).

**Auteur :** Bilal Mouffakir

---

## 📁 Structure du projet

```
pv_dashboard/
├── app.py                  ← Application Streamlit principale
├── requirements.txt        ← Dépendances Python
├── fmu/
│   └── PV_MPPT_Inverter1.fmu   ← Modèle FMU (Simulink R2024a, win64)
└── README.md
```

---

## 🚀 Déploiement sur Streamlit Cloud

1. **Fork / Push** ce repo sur GitHub
2. Aller sur [streamlit.io/cloud](https://streamlit.io/cloud)
3. **New app** → choisir votre repo → `app.py`
4. Cliquer **Deploy**

> ⚠️ **Note FMU :** Le fichier `.fmu` contient une DLL Windows 64-bit.  
> Streamlit Cloud tourne sur Linux → FMPy ne pourra pas exécuter la DLL directement.  
> L'app utilise automatiquement le **modèle physique analytique intégré** (équations PV standard, calibrées sur le modèle Simulink) qui donne des résultats fidèles.  
> Pour exécuter le vrai FMU : déployez sur une machine Windows avec FMPy installé.

---

## 📥 Entrées du modèle

| Port | Nom | Unité | Description |
|------|-----|-------|-------------|
| Inport | G | W/m² | Irradiance solaire |
| Inport1 | T | °C | Température des panneaux |

## 📤 Sorties du modèle (9 variables)

| Nom | Unité | Description |
|-----|-------|-------------|
| Vonduleur | V | Tension de sortie onduleur (RMS) |
| Pbooste | W | Puissance après convertisseur Boost |
| Ppanneau | W | Puissance générée par les panneaux PV |
| S_ondu | VA | Puissance apparente onduleur |
| P_ondu | W | Puissance active onduleur |
| Q_ondu | VAR | Puissance réactive onduleur |
| THD_V | % | Taux de distorsion harmonique en tension |
| THD_i | % | Taux de distorsion harmonique en courant |
| rendemet de onduleur | % | Rendement de l'onduleur |

---

## 🌤 Profils disponibles

**Irradiance G :**
- Échelon (step)
- Rampe
- Constante
- Jour (sinusoïde)
- Nuage (aléatoire)
- Double échelon

**Température T :**
- Constante
- Rampe
- Sinusoïde
- Échelon

---

## 🔧 Lancer en local

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## 📊 Graphiques disponibles

- Profils d'entrée G et T
- Puissances : Ppanneau · Pbooste · P_ondu
- P / Q / S onduleur
- Tension Vonduleur
- THD_V & THD_i
- Rendement onduleur
- Corrélations G → sorties (scatter)
- Tableau de données complet + export CSV
