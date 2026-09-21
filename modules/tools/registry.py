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
    """Definición declarativa de una tool disponible para el LLM."""

    nombre: str
    descripcion: str
    parametros_schema: Dict[str, Any] = field(default_factory=dict)
    handler: Handler = lambda: {}
    requerido: List[str] = field(default_factory=list)

    def a_declaracion(self) -> Dict[str, Any]:
        """Convierte la tool al formato `FunctionDeclaration` de la Gemini Live API."""
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
        ),
        "get_news_data": Herramienta(
            nombre="get_news_data",
            descripcion=(
                "Recupera los titulares y resúmenes de las últimas 24 horas de los portales "
                "de noticias de Chile (máximo un número acotado para optimizar tokens)."
            ),
            parametros_schema={},
            handler=lambda: news.get_top_news(),
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
        ),
    }