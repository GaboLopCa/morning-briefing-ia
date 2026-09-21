"""Tool registry extensible.

Cada capacidad interna se modela como una `Herramienta` (declaración JSON Schema
para el LLM + handler local). Para añadir una nueva habilidad basta construir una
instancia y registrarla: el orquestador (`Brain`) no se toca.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

Handler = Callable[..., Dict[str, Any]]


@dataclass
class Herramienta:
    """Definición declarativa de una tool disponible para el LLM.

    `frases` son ejemplos de cómo pide el usuario esta capacidad; el router local
    las usa como prototipos de similitud. No viajan al LLM (`a_declaracion` las ignora).
    """

    nombre: str
    descripcion: str
    parametros_schema: Dict[str, Any] = field(default_factory=dict)
    handler: Handler = lambda: {}
    requerido: List[str] = field(default_factory=list)
    frases: List[str] = field(default_factory=list)

    def a_declaracion(self) -> Dict[str, Any]:
        """Convierte la tool al `FunctionDeclaration` plano ({name, description, parameters})."""
        declaracion: Dict[str, Any] = {
            "name": self.nombre,
            "description": self.descripcion,
            "parameters": {
                "type": "object",
                "properties": self.parametros_schema,
            },
        }
        if self.requerido:
            declaracion["parameters"]["required"] = self.requerido
        return declaracion


def construir_registro(*, weather, news, search, opencode) -> Dict[str, Herramienta]:
    """Ensambla el registro de tools con los proveedores ya inyectados."""
    opciones_proyectos = sorted(opencode.proyectos.keys()) if hasattr(opencode, "proyectos") else []

    return {
        "get_weather_data": Herramienta(
            nombre="get_weather_data",
            descripcion=(
                "Obtiene las condiciones del clima actuales en Melipilla, Chile: "
                "temperatura, sensación térmica, máxima, mínima, probabilidad de lluvia y condición del cielo."
            ),
            parametros_schema={},
            handler=lambda: weather.get_weather(),
            frases=[
                "¿cómo está el clima?",
                "¿va a llover hoy?",
                "¿qué temperatura hay?",
                "¿cómo está el tiempo?",
                "dame el pronóstico",
                "¿necesito paraguas?",
            ],
        ),
        "get_news_data": Herramienta(
            nombre="get_news_data",
            descripcion=(
                "Recupera los titulares y resúmenes de las últimas 24 horas de los portales "
                "de noticias de Chile (máximo un número acotado para optimizar tokens)."
            ),
            parametros_schema={},
            handler=lambda: news.get_top_news(),
            frases=[
                "¿cuáles son las noticias de hoy?",
                "dame los titulares",
                "¿qué pasó en Chile?",
                "última hora",
                "resumen de noticias",
                "qué se dice en las portadas",
            ],
        ),
        "search_internet_data": Herramienta(
            nombre="search_internet_data",
            descripcion=(
                "Busca en internet en tiempo real sobre noticias de última hora, resultados "
                "deportivos o datos actualizados y devuelve títulos y fragmentos de resultados."
            ),
            parametros_schema={
                "query": {
                    "type": "string",
                    "description": "La frase clave o términos de búsqueda exactos.",
                }
            },
            requerido=["query"],
            handler=lambda query: search.search_internet(query),
            frases=[
                "busca en internet sobre un tema",
                "¿quién ganó el partido de anoche?",
                "investiga las novedades de tecnología",
                "resultados de la fecha de fútbol",
                "googlea esa duda",
            ],
        ),
        "ejecutar_opencode": Herramienta(
            nombre="ejecutar_opencode",
            descripcion=(
                "Ejecuta el agente opencode (CLI) dentro de uno de los proyectos locales del "
                "usuario para tareas de programación: crear skills de opencode, revisar o "
                "modificar código, añadir funcionalidades o explicar una base de código. "
                "ÚSALA SOLO cuando el usuario lo pida explícitamente; el sistema pedirá "
                "confirmación antes de ejecutar."
            ),
            parametros_schema={
                "proyecto": {
                    "type": "string",
                    "enum": opciones_proyectos,
                    "description": "Nombre clave del proyecto local donde ejecutar opencode.",
                },
                "peticion": {
                    "type": "string",
                    "description": "Instrucción detallada en español para el agente opencode.",
                },
            },
            requerido=["proyecto", "peticion"],
            handler=lambda proyecto, peticion: opencode.ejecutar(proyecto=proyecto, peticion=peticion),
            frases=[
                "ejecuta opencode en el proyecto briefing",
                "pídele a opencode que revise el código",
            ],
        ),
    }