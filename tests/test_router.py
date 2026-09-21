from modules.router import Decision, RouterIntenciones, _normalizar
from modules.tools import construir_registro


class StubProveedor:
    """Proveedor mínimo: handlers deterministas y allowlist de proyectos."""

    proyectos = {"asistente": "ruta", "briefing": "ruta2"}

    def get_weather(self):
        return {
            "status": "ok",
            "data": {
                "condition": "despejado",
                "current": 18,
                "feels_like": 17,
                "max": 22,
                "min": 9,
                "rain_prob": 10,
            },
        }

    def get_top_news(self):
        return {"status": "ok", "data": [{"title": "n1"}, {"title": "n2"}]}

    def search_internet(self, query):
        return {"status": "ok", "data": f"resultados de {query}"}

    def ejecutar(self, **kwargs):
        return {"status": "ok", "data": f"opencode hizo: {kwargs.get('peticion')}"}


class StubProveedorRoto(StubProveedor):
    def get_weather(self):
        return {"status": "error", "mensaje": "clima caído"}


class EncoderFalso:
    """Encoder determinista por palabras clave (3 dims), sin descargar modelos."""

    def encode(self, textos):
        return [self._vector(texto) for texto in textos]

    @staticmethod
    def _vector(texto):
        minuscula = texto.lower()
        vector = [0.0, 0.0, 0.0]
        if any(p in minuscula for p in ("clima", "lluvia", "lluev", "temperatura", "pronostico")):
            vector[0] = 1.0
        if any(p in minuscula for p in ("noticias", "titulares")):
            vector[1] = 1.0
        if any(p in minuscula for p in ("busca", "internet", "google")):
            vector[2] = 1.0
        return vector


def _registro(proveedor=None):
    proveedor = proveedor or StubProveedor()
    return construir_registro(
        weather=proveedor,
        news=proveedor,
        search=proveedor,
        opencode=proveedor,
    )


def _router(**kwargs):
    kwargs.setdefault("embeddings_activo", False)  # reglas puras salvo que se pida otra cosa
    return RouterIntenciones(_registro(), **kwargs)


class TestReglas:
    def test_clima(self):
        decision = _router().decidir("¿cómo está el clima?")
        assert decision == Decision("get_weather_data", {}, 1.0, "reglas")

    def test_clima_va_a_llover(self):
        decision = _router().decidir("¿va a llover mañana?")
        assert decision.herramienta == "get_weather_data"

    def test_noticias(self):
        decision = _router().decidir("dame los titulares")
        assert decision.herramienta == "get_news_data"

    def test_busqueda_extrae_query_con_tildes(self):
        decision = _router().decidir("busca en internet la canción de moda")
        assert decision.herramienta == "search_internet_data"
        assert decision.params["query"] == "la canción de moda"

    def test_busqueda_sin_query_no_decide(self):
        assert _router().decidir("busca") is None

    def test_opencode_con_proyecto(self):
        decision = _router().decidir("ejecuta opencode en el proyecto briefing")
        assert decision.herramienta == "ejecutar_opencode"
        assert decision.params["proyecto"] == "briefing"
        assert decision.params["peticion"]

    def test_opencode_sin_proyecto_no_decide(self):
        assert _router().decidir("ejecuta opencode por favor") is None

    def test_negacion_delega_al_llm(self):
        assert _router().decidir("no me digas el clima") is None

    def test_texto_conversacional_no_decide(self):
        assert _router().decidir("cuéntame un chiste") is None

    def test_vacio_no_decide(self):
        assert _router().decidir("   ") is None


class TestEmbeddings:
    def test_sinonimo_cae_en_embeddings(self):
        router = _router(embeddings_activo=True, encoder=EncoderFalso())
        decision = router.decidir("me gustaría saber si llueve")
        assert decision.herramienta == "get_weather_data"
        assert decision.origen == "embeddings"

    def test_bajo_umbral_delega_al_llm(self):
        router = _router(embeddings_activo=True, encoder=EncoderFalso())
        assert router.decidir("cuéntame una anécdota") is None

    def test_umbral_alto_delega_al_llm(self):
        router = _router(embeddings_activo=True, encoder=EncoderFalso(), umbral=0.9)
        # mezcla clima + internet: ninguna ruta supera el 0.9 -> decide el LLM
        assert router.decidir("tengo dudas sobre internet y si llueve hoy") is None


class TestEjecucionYFormato:
    def test_formatea_clima(self):
        texto = _router().ejecutar(Decision("get_weather_data"))
        assert "despejado" in texto and "grados" in texto

    def test_formatea_noticias(self):
        texto = _router().ejecutar(Decision("get_news_data"))
        assert "2 titulares" in texto and "n1" in texto

    def test_formatea_busqueda(self):
        router = _router()
        texto = router.ejecutar(Decision("search_internet_data", {"query": "ufo"}))
        assert "ufo" in texto

    def test_envelope_de_error(self):
        router = RouterIntenciones(_registro(StubProveedorRoto()), embeddings_activo=False)
        assert router.ejecutar(Decision("get_weather_data")) == "clima caído"

    def test_handler_inexistente(self):
        assert _router().ejecutar(Decision("no_existe")) == "No pude completar esa acción. Intenta de nuevo."


class TestInterruptor:
    def test_router_inactivo_delega_todo(self):
        router = RouterIntenciones(_registro(), activo=False, embeddings_activo=False)
        assert router.decidir("¿cómo está el clima?") is None


class TestIntegracionRegistry:
    def test_frases_no_viajan_al_llm(self):
        herramienta = _registro()["get_weather_data"]
        assert herramienta.frases
        assert "frases" not in herramienta.a_declaracion()

    def test_normalizar_quita_tildes_y_conserva_largo(self):
        original = "¿Cómo está el pronóstico?"
        assert _normalizar(original) == "¿como esta el pronostico?"
        assert len(_normalizar(original)) == len(original.lower())
