import requests

from config import TIMEOUT_HTTP
from modules.contract import error, ok


def mapear_condicion(w_code):
    """Traduce el código meteorológico WMO a una etiqueta en español.

    Rangos oficiales:
      0            despejado
      1-3          parcialmente nublado
      45, 48       niebla
      51-67, 80-82 lluvia
      71-77, 85-86 nieve
      95-99        tormenta
    """
    if w_code == 0:
        return "despejado"
    if w_code <= 3:
        return "parcialmente nublado"
    if w_code in (45, 48):
        return "con niebla"
    if 51 <= w_code <= 67 or 80 <= w_code <= 82:
        return "con lluvia"
    if 71 <= w_code <= 77 or w_code in (85, 86):
        return "con nieve"
    if 95 <= w_code <= 99:
        return "con tormenta"
    return "nublado"


class WeatherProvider:
    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude
        self.url_api = "https://api.open-meteo.com/v1/forecast"

    def get_weather(self):
        parameters = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "current": ["temperature_2m", "apparent_temperature", "weather_code"],
            "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_probability_max"],
            "timezone": "auto",
        }
        try:
            response = requests.get(self.url_api, params=parameters, timeout=(5, TIMEOUT_HTTP))
            response.raise_for_status()
            json_data = response.json()

            rain_prob = json_data["daily"]["precipitation_probability_max"][0]
            clima = {
                "max": json_data["daily"]["temperature_2m_max"][0],
                "min": json_data["daily"]["temperature_2m_min"][0],
                "current": json_data["current"]["temperature_2m"],
                "feels_like": json_data["current"]["apparent_temperature"],
                "rain_prob": rain_prob,
                "condition": mapear_condicion(json_data["current"]["weather_code"]),
            }
            return ok(clima)
        except Exception as exc:  # noqa: BLE001
            print(f"[WeatherProvider] Error interno: {exc}")
            return error("No fue posible obtener el clima en este momento.")