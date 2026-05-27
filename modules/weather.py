import requests

class WeatherProvider:
    
    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude
        self.url_api = "https://api.open-meteo.com/v1/forecast"

    def get_weather(self):

        parameters = {
            "latitude" : self.latitude,
            "longitude" : self.longitude,
            "daily" : ["temperature_2m_max", "temperature_2m_min", "precipitation_probability_max"],
            "current_weather" : True,
            "timezone" : "auto"
        }
        try: 
            response = requests.get(self.url_api, params=parameters)

            json_data = response.json()

            temp_max = json_data["daily"]["temperature_2m_max"][0]
            temp_min = json_data["daily"]["temperature_2m_min"][0]
            rain_prob = json_data["daily"]["precipitation_probability_max"][0]

            return f"Hoy habrá una máxima de {temp_max}°C, una mínima de {temp_min}°C y un {rain_prob}% de probabilidad de lluvia."

        except Exception as e:
            return f"Error al obtener el clima: {e}"