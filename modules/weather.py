import requests

class WeatherProvider:
    
    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude
        self.url_api = "https://api.open-meteo.com/v1/forecast"

    def get_weather(self):
        parameters = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "current": ["temperature_2m", "apparent_temperature", "weather_code"], # Info actual
            "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_probability_max"],
            "timezone": "auto"
        }
        try: 
            response = requests.get(self.url_api, params=parameters)
            response.raise_for_status()
            json_data = response.json()

            # Datos actuales
            current_temp = json_data["current"]["temperature_2m"]
            feels_like = json_data["current"]["apparent_temperature"]
            w_code = json_data["current"]["weather_code"]

            # Datos diarios
            temp_max = json_data["daily"]["temperature_2m_max"][0]
            temp_min = json_data["daily"]["temperature_2m_min"][0]
            rain_prob = json_data["daily"]["precipitation_probability_max"][0]

            # Diccionario de códigos básicos para que la IA entienda el cielo
            # 0: Despejado, 1-3: Parcial/Nublado, 45-48: Niebla, 51+: Lluvia/Nieve
            sky_condition = "despejado" if w_code == 0 else "parcialmente nublado" if w_code <= 3 else "nublado o con neblina"
            if w_code > 50: sky_condition = "con lluvia"

            return {
                "max": temp_max,
                "min": temp_min,
                "current": current_temp,
                "feels_like": feels_like,
                "rain_prob": rain_prob,
                "condition": sky_condition
            }

        except Exception as e:
            return f"Error al obtener el clima: {e}"