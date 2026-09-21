"""Router de intenciones local (cascada reglas -> embeddings -> None).

Objetivo: resolver comandos triviales sin despertar al LLM de Groq ("¿va a
llover?", "busca ...", "ejecuta opencode en ..."). Si ninguna capa decide con
suficiente confianza, `decidir()` devuelve None y `main.py` cae al Brain con el
comportamiento de siempre (cero regresión).

Capas:
- Reglas (coste ~0): patrones en español sobre el texto normalizado. Exige
  ausencia de negación para no invertir la intención ("no prendas la luz" -> LLM).
- Embeddings (opcional, ~ms): similitud coseno contra `descripcion` + `frases`
  del registry con un modelo estático multilingüe (model2vec, sin PyTorch). Se
  carga de forma perezosa: si no está instalado, el router sigue por reglas.

Tras decidir, `ejecutar()` llama al handler y devuelve un texto fijo (sin
narración del LLM), respetando el envelope de `modules/contract.py`.
"""
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict

from config import (
    ROUTER_ACTIVO,
    ROUTER_EMBEDDINGS_ACTIVO,
    ROUTER_MODELO_EMBEDDINGS,
    ROUTER_UMBRAL_CONFIANZA,
)

# Herramientas que el router puede resolver directamente.
ENRUTABLES = ("get_weather_data", "get_news_data", "search_internet_data", "ejecutar_opencode")
# Solo estas se ofrecen a la capa de embeddings (opencode exige proyecto explícito).
ENRUTABLES_EMBEDDINGS = ("get_weather_data", "get_news_data", "search_internet_data")

RESPUESTA_ERROR = "No pude completar esa acción. Intenta de nuevo."
MAX_TEXTO_BUSQUEDA = 600

# Marcadores de negación: si aparecen, ninguna regla decide (evita ejecutar lo contrario).
_NEGACIONES = re.compile(r"\b(no|nunca|jamas|ni|tampoco)\b")

# Capa 1: (herramienta, patrón sobre texto normalizado sin tildes).
_REGLAS = (
    (
        "get_weather_data",
        re.compile(
            r"\b(clima|temperatura|grados|pronostico|lluvia|paraguas|"
            r"va a llover|llovera|que tiempo (hace|esta))\b"
        ),
    ),
    (
        "get_news_data",
        re.compile(r"\b(noticias|titulares|ultima hora|portadas|resumen de noticias|novedades)\b"),
    ),
    (
        "search_internet_data",
        re.compile(
            r"^(por favor\s+)?(busca|buscame|buscar|consulta|consultame|averigua|googlea|investiga|encuentra)\b"
        ),
    ),
    ("ejecutar_opencode", re.compile(r"\bopencode\b")),
)

# Trigger al inicio; el resto del texto es la consulta (se recorta de `limpio`).
_TRIGGER_BUSQUEDA = re.compile(
    r"^(?:por favor\s+)?(?:busca(?:me)?|buscar|consulta(?:me)?|averigua|googlea|investiga|encuentra)\b"
    r"(?:\s+en\s+(?:internet|google|la web|youtube|el navegador))?"
    r"(?:\s+(?:por|sobre|de|acerca de))?\s*(?P<query>.+)$"
)


@dataclass
class Decision:
    """Resultado del router: qué herramienta usar, con qué params y por qué capa."""

    herramienta: str
    params: Dict[str, Any] = field(default_factory=dict)
    confianza: float = 1.0
    origen: str = "reglas"


def _normalizar(texto):
    """minúsculas + sin diacríticos, para que 'cómo' y 'como' casen igual.

    NFKD + eliminación de marcas conserva la longitud del texto original (ú -> u),
    por lo que los spans calculados sobre el normalizado valen para el original.
    """
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    sin_tildes = "".join(caracter for caracter in descompuesto if not unicodedata.combining(caracter))
    return sin_tildes.lower().strip()


def _vector(encoder, texto):
    """Primera fila del encode (lista de floats), tolerante a numpy o listas."""
    salida = encoder.encode([texto])
    return [float(valor) for valor in salida[0]]


def _coseno(a, b):
    producto = sum(x * y for x, y in zip(a, b))
    norma_a = math.sqrt(sum(x * x for x in a))
    norma_b = math.sqrt(sum(y * y for y in b))
    if norma_a == 0.0 or norma_b == 0.0:
        return 0.0
    return producto / (norma_a * norma_b)


class RouterIntenciones:
    def __init__(
        self,
        registro,
        encoder=None,
        umbral=ROUTER_UMBRAL_CONFIANZA,
        activo=ROUTER_ACTIVO,
        embeddings_activo=ROUTER_EMBEDDINGS_ACTIVO,
        modelo_embeddings=ROUTER_MODELO_EMBEDDINGS,
    ):
        self.registro = registro
        self.encoder = encoder          # inyectable (tests); None = carga perezosa
        self.umbral = umbral
        self.activo = activo
        self.embeddings_activo = embeddings_activo
        self.modelo_embeddings = modelo_embeddings
        self._encoder_resuelto = None
        self._encoder_cargado = False
        self._prototipos = None         # list[(herramienta, texto)]

    # ------------------------------------------------------------- decisión

    def decidir(self, texto):
        """Devuelve una `Decision` o None si hay que delegar al Brain."""
        if not self.activo:
            return None
        limpio = (texto or "").strip()
        if not limpio:
            return None
        normalizado = _normalizar(limpio)
        if _NEGACIONES.search(normalizado):
            return None  # negación -> decide el LLM (evita invertir la intención)
        return self._por_reglas(limpio, normalizado) or self._por_embeddings(limpio)

    def _por_reglas(self, limpio, normalizado):
        for nombre, patron in _REGLAS:
            if nombre not in self.registro or not patron.search(normalizado):
                continue
            params = self._extraer_params(nombre, limpio, normalizado)
            if params is None:
                continue  # faltan slots -> mejor que decida el LLM
            return Decision(herramienta=nombre, params=params, confianza=1.0, origen="reglas")
        return None

    def _extraer_params(self, nombre, limpio, normalizado):
        if nombre == "search_internet_data":
            coincidencia = _TRIGGER_BUSQUEDA.match(normalizado)
            if not coincidencia:
                return None
            inicio, fin = coincidencia.span("query")
            query = limpio[inicio:fin].strip(" .!?¡¿")
            if len(query) < 3:
                return None
            return {"query": query}
        if nombre == "ejecutar_opencode":
            proyecto = self._proyecto_mencionado(normalizado)
            if not proyecto:
                return None  # sin proyecto explícito no se enruta
            return {"proyecto": proyecto, "peticion": self._peticion_opencode(limpio, proyecto)}
        return {}

    def _proyecto_mencionado(self, normalizado):
        herramienta = self.registro.get("ejecutar_opencode")
        if herramienta is None:
            return None
        enum = herramienta.parametros_schema.get("proyecto", {}).get("enum", [])
        for opcion in enum:
            if re.search(rf"\b{re.escape(_normalizar(opcion))}\b", normalizado):
                return opcion
        return None

    @staticmethod
    def _peticion_opencode(limpio, proyecto):
        peticion = re.sub(r"\bopencode\b", " ", limpio, flags=re.IGNORECASE)
        peticion = re.sub(re.escape(proyecto), " ", peticion, flags=re.IGNORECASE)
        peticion = " ".join(peticion.split()).strip(" ,.")
        return peticion or limpio

    # ----------------------------------------------------------- embeddings

    def _obtener_encoder(self):
        if self._encoder_cargado:
            return self._encoder_resuelto
        self._encoder_cargado = True
        if self.encoder is not None:
            self._encoder_resuelto = self.encoder
            return self._encoder_resuelto
        if not self.embeddings_activo:
            self._encoder_resuelto = None
            return None
        try:
            from model2vec import StaticModel

            self._encoder_resuelto = StaticModel.from_pretrained(self.modelo_embeddings)
        except Exception as exc:  # noqa: BLE001
            print(f"[Router] Embeddings no disponibles ({type(exc).__name__}); sigo con reglas.")
            self._encoder_resuelto = None
        return self._encoder_resuelto

    def _obtener_prototipos(self):
        """Frases del registry como prototipos; la descripción es el fallback."""
        if self._prototipos is not None:
            return self._prototipos
        prototipos = []
        for nombre in ENRUTABLES_EMBEDDINGS:
            herramienta = self.registro.get(nombre)
            if herramienta is None:
                continue
            textos = list(herramienta.frases) or [herramienta.descripcion]
            prototipos.extend((nombre, texto) for texto in textos)
        self._prototipos = prototipos
        return prototipos

    def _por_embeddings(self, limpio):
        if not self.embeddings_activo:
            return None
        encoder = self._obtener_encoder()
        prototipos = self._obtener_prototipos()
        if encoder is None or not prototipos:
            return None
        try:
            vector = _vector(encoder, limpio)
            vectores = [_vector(encoder, texto) for _, texto in prototipos]
        except Exception as exc:  # noqa: BLE001
            print(f"[Router] Error de embeddings: {exc}")
            return None
        mejor_nombre, mejor_similitud = None, -1.0
        for (nombre, _), referencia in zip(prototipos, vectores):
            similitud = _coseno(vector, referencia)
            if similitud > mejor_similitud:
                mejor_nombre, mejor_similitud = nombre, similitud
        if mejor_nombre is None or mejor_similitud < self.umbral:
            return None
        params = {"query": limpio} if mejor_nombre == "search_internet_data" else {}
        return Decision(
            herramienta=mejor_nombre,
            params=params,
            confianza=float(mejor_similitud),
            origen="embeddings",
        )

    # ------------------------------------------------------------ ejecución

    def ejecutar(self, decision):
        """Corre el handler y devuelve un texto fijo listo para hablar/imprimir."""
        herramienta = self.registro.get(decision.herramienta)
        if herramienta is None:
            return RESPUESTA_ERROR
        try:
            salida = herramienta.handler(**(decision.params or {}))
        except Exception as exc:  # noqa: BLE001
            print(f"[Router] Error en '{decision.herramienta}': {exc}")
            return RESPUESTA_ERROR
        if not isinstance(salida, dict) or salida.get("status") != "ok":
            mensaje = salida.get("mensaje") if isinstance(salida, dict) else None
            return mensaje or RESPUESTA_ERROR
        return _formatear(decision.herramienta, salida.get("data"))


def _formatear(nombre, data):
    if nombre == "get_weather_data":
        return _formatear_clima(data)
    if nombre == "get_news_data":
        return _formatear_noticias(data)
    if nombre == "search_internet_data":
        texto = " ".join(str(data or "").split())
        return texto[:MAX_TEXTO_BUSQUEDA] or RESPUESTA_ERROR
    if nombre == "ejecutar_opencode":
        return str(data or "").strip() or "Listo, Gabriel."
    return str(data or "").strip() or RESPUESTA_ERROR


def _formatear_clima(data):
    if not isinstance(data, dict):
        return RESPUESTA_ERROR
    return (
        "En Melipilla está {condition}, ahora {current} grados "
        "(sensación {feels}). Máxima {max}, mínima {min}, lluvia {rain} por ciento.".format(
            condition=data.get("condition", "?"),
            current=data.get("current", "?"),
            feels=data.get("feels_like", "?"),
            max=data.get("max", "?"),
            min=data.get("min", "?"),
            rain=data.get("rain_prob", "?"),
        )
    )


def _formatear_noticias(data):
    if not isinstance(data, list) or not data:
        return "No encontré titulares recientes."
    primera = data[0].get("title", "Sin título") if isinstance(data[0], dict) else str(data[0])
    return f"Tienes {len(data)} titulares listos. El primero: {primera}"
