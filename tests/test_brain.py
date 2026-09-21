from modules.summarizer import Brain
from modules.tools import Herramienta, construir_registro


class StubProveedor:
    proyectos = {"asistente": "ruta"}

    def __init__(self, nombre):
        self.nombre = nombre

    def get_weather(self):
        return {"status": "ok", "data": {"condition": "despejado"}}

    def get_top_news(self):
        return {"status": "ok", "data": []}

    def search_internet(self, query):
        return {"status": "ok", "data": "bloque"}

    def ejecutar(self, **kwargs):
        return {"status": "ok", "data": "hecho"}


def _crear_registro():
    return construir_registro(
        weather=StubProveedor("weather"),
        news=StubProveedor("news"),
        search=StubProveedor("search"),
        opencode=StubProveedor("opencode"),
    )


class TestBrainMemoria:
    def setup_method(self):
        self.brain = Brain(api_key="clave-de-prueba", registro=_crear_registro())

    def test_semilla_incluye_el_mensaje_actual(self):
        semilla = self.brain._construir_semilla("hola")
        assert len(semilla) == 1
        assert semilla[0]["role"] == "user"
        assert semilla[0]["content"] == "hola"

    def test_historial_crece_con_pares_completos(self):
        self.brain._guardar_en_historial("user1", "model1")
        self.brain._guardar_en_historial("user2", "model2")
        assert len(self.brain.historial) == 4
        roles = [p["role"] for p in self.brain.historial]
        assert roles == ["user", "assistant", "user", "assistant"]

    def test_recorte_mantiene_n_pares_max(self):
        self.brain.max_historial_turnos = 2
        for i in range(6):
            self.brain._guardar_en_historial(f"u{i}", f"m{i}")
        assert len(self.brain.historial) == 4  # 2 turnos * 2 roles
        assert self.brain.historial[0]["content"] == "u4"

    def test_semilla_con_historial_previa(self):
        self.brain._guardar_en_historial("u1", "m1")
        semilla = self.brain._construir_semilla("u2")
        assert [p["role"] for p in semilla] == ["user", "assistant", "user"]
        assert semilla[-1]["content"] == "u2"

    def test_limpiar_historial(self):
        self.brain._guardar_en_historial("u1", "m1")
        self.brain.limpiar_historial()
        assert self.brain.historial == []


class TestBrainHerramientas:
    def setup_method(self):
        self.brain = Brain(
            api_key="clave-de-prueba",
            registro={**_crear_registro(), "saluda": Herramienta(nombre="saluda", descripcion="d", handler=lambda: "hola!")},
        )

    def test_tool_desconocida_devuelve_envelope(self):
        out = self.brain._ejecutar_herramienta("no_existe", {})
        assert out["status"] == "error"
        assert "desconocida" in out["mensaje"]

    def test_tool_ok_envelope(self):
        out = self.brain._ejecutar_herramienta("saluda", {})
        assert out == "hola!"

    def test_tool_que_falla_devuelve_envelope(self):
        def boom(**kwargs):
            raise RuntimeError("falló interno")

        self.brain.registro["explota"] = Herramienta(nombre="explota", descripcion="d", handler=boom)
        out = self.brain._ejecutar_herramienta("explota", {})
        assert out["status"] == "error"
        assert "no pudo completar" in out["mensaje"]


class TestBrainConfigGroq:
    def test_tools_en_formato_openai(self):
        brain = Brain(api_key="clave-de-prueba", registro=_crear_registro())
        declaraciones = [h.a_declaracion() for h in brain.registro.values()]

        tools = brain._tools_openai(declaraciones)
        assert tools
        assert tools[0]["type"] == "function"
        funcion = tools[0]["function"]
        assert funcion["name"] in {
            "get_weather_data",
            "get_news_data",
            "search_internet_data",
            "ejecutar_opencode",
        }
        assert funcion["parameters"]["type"] == "object"

    def test_tools_incluyen_todo_el_registro(self):
        brain = Brain(api_key="clave-de-prueba", registro=_crear_registro())
        tools = brain._tools_openai([h.a_declaracion() for h in brain.registro.values()])
        nombres = {t["function"]["name"] for t in tools}
        assert nombres == set(brain.registro)

    def test_formatear_contexto_clima_y_noticias(self):
        brain = Brain(api_key="clave-de-prueba", registro=_crear_registro())
        bloque = brain._formatear_contexto(
            {"status": "ok", "data": {"condition": "despejado", "current": 15, "max": 20, "min": 8, "rain_prob": 10}},
            {"status": "ok", "data": [{"title": "Chile avanza", "description": "detalle"}]},
        )
        assert "CONTEXTO DEL DÍA" in bloque
        assert "despejado, ahora 15°C" in bloque
        assert "Chile avanza" in bloque

    def test_formatear_contexto_sin_datos(self):
        brain = Brain(api_key="clave-de-prueba", registro=_crear_registro())
        bloque = brain._formatear_contexto(None, {"status": "error", "mensaje": "cayó"})
        assert "no disponible" in bloque