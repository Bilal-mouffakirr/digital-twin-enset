# utils/openmeteo.py
# Récupère température + radiation depuis Open-Meteo (Mohammedia)

import requests

LAT = 33.6866
LON = -7.3833

def fetch_openmeteo() -> dict:
    """
    Retourne les données météo actuelles + prévisions horaires.

    Returns
    -------
    {
      "current": {"temperature_2m": float, "shortwave_radiation": float},
      "hourly":  {"time": [...], "temperature_2m": [...], "shortwave_radiation": [...]}
    }
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&current=temperature_2m,shortwave_radiation"
        f"&hourly=temperature_2m,shortwave_radiation"
        f"&timezone=Africa%2FCasablanca"
        f"&forecast_days=1"
    )

    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    return {
        "current": {
            "temperature_2m":     data["current"]["temperature_2m"],
            "shortwave_radiation": data["current"].get("shortwave_radiation", 0),
        },
        "hourly": {
            "time":               data["hourly"]["time"],
            "temperature_2m":     data["hourly"]["temperature_2m"],
            "shortwave_radiation": data["hourly"]["shortwave_radiation"],
        },
    }
