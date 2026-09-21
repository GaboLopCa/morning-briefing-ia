from modules.tools import Herramienta, construir_registro


class StubOpcional:
    """Proxies mínimos tipo Mockito (solo recuerdan qué petición les llegó)."""

    def __init__(self, nombre):
        self.nombre = nombre

    def proyectos(self):
        return {"asistente": "ruta", "briefing": "ruta2"}


class StubProveedor:
    proyectos = {"asistente": "ruta", "briefing": "ruta2"}

    def __init__(self, nombre):
        self.nombre = nombre

    def get_weather(self):
        return {"status": "ok", "data": {"condition": "despejado"}}

    def get_top_news(self):
        return {"status": "ok", "data": [{"title": "n1"}]}

    def search_internet(self, query):
        return {"status": "ok", "data": f"resultados de {query}"}

    def ejecutar(self, **kwargs):
        return {"status": "ok", "data": "hecho"}


class TestRegistry:
    def setup_method(self):
        self.registro = construir_registro(
            weather=StubProveedor("weather"),
            news=StubProveedor("news"),
            search=StubProveedor("search"),
            opencode=StubProveedor("opencode"),
        )

    def test_exponen_las_4_herramientas(self):
        assert set(self.registro) == {
            "get_weather_data",
            "get_news_data",
            "search_internet_data",
            "ejecutar_opencode",
        }

    def test_handlers_devuelven_envelope(self):
        assert self.registro["get_weather_data"].handler()["status"] == "ok"
        assert self.registro["get_news_data"].handler()["status"] == "ok"
        assert self.registro["search_internet_data"].handler(query="x")["status"] == "ok"
        assert (
            self.registro["ejecutar_opencode"].handler(proyecto="asistente", peticion="p")["status"]
            == "ok"
        )

    def test_ejecutar_opencode_valida_proyecto(self):
        herramienta = self.registro["ejecutar_opencode"]
        assert herramienta.requerido == ["proyecto", "peticion"]
        schema = herramienta.parametros_schema["proyecto"]
        assert "enum" in schema
        assert "asistente" in schema["enum"]

    def test_a_declaracion_formato_live(self):
        declaracion = self.registro["search_internet_data"].a_declaracion()
        assert declaracion["name"] == "search_internet_data"
        assert declaracion["parameters"]["type"] == "object"
        assert "query" in declaracion["parameters"]["properties"]
        assert "required" in declaracion["parameters"]


class TestHerramienta:
    def test_instancia_simple_sin_parametros(self):
        herramienta = Herramienta(nombre="foo", descripcion="d", handler=lambda: {})
        declaracion = herramienta.a_declaracion()
        assert declaracion["parameters"]["properties"] == {}
        assert "required" not in declaracion["parameters"]