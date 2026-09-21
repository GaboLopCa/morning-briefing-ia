import pytest

from modules.weather import WeatherProvider, mapear_condicion


class TestMapearCondicion:
    @pytest.mark.parametrize(
        "codigo, esperado",
        [
            (0, "despejado"),
            (1, "parcialmente nublado"),
            (2, "parcialmente nublado"),
            (3, "parcialmente nublado"),
            (45, "con niebla"),
            (48, "con niebla"),
            (51, "con lluvia"),
            (61, "con lluvia"),
            (67, "con lluvia"),
            (80, "con lluvia"),
            (82, "con lluvia"),
            (71, "con nieve"),
            (77, "con nieve"),
            (85, "con nieve"),
            (86, "con nieve"),
            (95, "con tormenta"),
            (99, "con tormenta"),
            (500, "nublado"),
        ],
    )
    def test_mapeo(self, codigo, esperado):
        assert mapear_condicion(codigo) == esperado


class TestWeatherProvider:
    def test_error_se_devuelve_en_envelope(self, monkeypatch):
        class RespuestaFake:
            def raise_for_status(self):
                raise RuntimeError("timeout simulado")

        def get_fake(*args, **kwargs):
            raise RuntimeError("red caída")

        provider = WeatherProvider(-33.0, -71.0)
        monkeypatch.setattr("modules.weather.requests.get", get_fake)

        resultado = provider.get_weather()
        assert resultado["status"] == "error"
        assert "clima" in resultado["mensaje"]

    def test_respuesta_exitosa_en_envelope(self, monkeypatch):
        class RespuestaFake:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "current": {
                        "temperature_2m": 22.0,
                        "apparent_temperature": 21.5,
                        "weather_code": 1,
                    },
                    "daily": {
                        "temperature_2m_max": [25.0],
                        "temperature_2m_min": [12.0],
                        "precipitation_probability_max": [30],
                    },
                }

        def get_fake(*args, **kwargs):
            return RespuestaFake()

        provider = WeatherProvider(-33.0, -71.0)
        monkeypatch.setattr("modules.weather.requests.get", get_fake)

        resultado = provider.get_weather()
        assert resultado["status"] == "ok"
        datos = resultado["data"]
        assert datos["condition"] == "parcialmente nublado"
        assert datos["current"] == 22.0
        assert datos["rain_prob"] == 30