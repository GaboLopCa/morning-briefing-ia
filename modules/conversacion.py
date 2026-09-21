"""Cerebro + voz para el segundo plano (Sesión 5).

`MotorConversacion` reúne la cascada `router.decidir → Brain` y el TTS de
`voice.py` para el proceso de fondo, de modo que la wake word devuelva
respuesta real hablada. Todo lo que bloquea (Groq, edge-tts) corre SIEMPRE
fuera del hilo de la cola: los manejadores de `app.py` lanzan hilos daemon que
encolan `RESPUESTA_LISTA` / `TERMINAR_VOZ` cuando terminan.

Confirmación de opencode: sin consola ni UI de confirmación en segundo plano,
`_confirmar_segundo_plano` rechaza cualquier `ejecutar_opencode` y lo loguea.
"""
import logging

from config import GROQ_API_KEY, LATITUD, LONGITUD, RSS_URLS
from modules.news import NewsFetcher
from modules.opencode_tool import OpenCodeRunner
from modules.router import RouterIntenciones
from modules.search import WebSearcher
from modules.summarizer import Brain
from modules.tools import construir_registro
from modules.voice import VoiceAssistant
from modules.weather import WeatherProvider

logger = logging.getLogger("josesito")

RESPUESTA_SIN_CEREBRO = (
    "No tengo el cerebro configurado en segundo plano: falta la clave de Groq."
)


def _confirmar_segundo_plano(peticion, ruta):
    """ejecutar_opencode desde la voz se rechaza (no hay confirmación UI) y se loguea."""
    logger.warning(
        "ejecutar_opencode (segundo plano) rechazado sin confirmación UI: %s (%s)",
        peticion,
        ruta,
    )
    return False


class MotorConversacion:
    """Resolutor de frases + locutor del proceso de fondo (testeable con dobles)."""

    def __init__(self, router=None, brain=None, voz=None):
        self.router = router
        self.brain = brain
        self.voz = voz or VoiceAssistant()

    def resolver(self, texto):
        """Texto -> respuesta hablable: router local primero, Brain después."""
        if self.router is not None:
            decision = self.router.decidir(texto)
            if decision is not None:
                logger.info("Router → %s (%s)", decision.herramienta, decision.origen)
                return self.router.ejecutar(decision)
        if self.brain is not None:
            return self.brain.generate_response(texto)
        return RESPUESTA_SIN_CEREBRO

    def hablar(self, texto):
        """Sintetiza y reproduce el texto (bloquea hasta terminar de hablar)."""
        self.voz.speak(texto)

    def detener(self):
        """Corta el TTS en curso (barge-in); seguro de llamar desde cualquier hilo."""
        self.voz.detener()


def crear_motor(confirmador=None):
    """Ensambla el motor real del segundo plano (providers + registro + Brain + voz)."""
    weather = WeatherProvider(LATITUD, LONGITUD)
    news = NewsFetcher(RSS_URLS)
    search = WebSearcher()
    opencode = OpenCodeRunner(confirmador=confirmador or _confirmar_segundo_plano)

    registro = construir_registro(
        weather=weather,
        news=news,
        search=search,
        opencode=opencode,
    )
    router = RouterIntenciones(registro)
    brain = Brain(GROQ_API_KEY, registro) if GROQ_API_KEY else None
    if brain is None:
        logger.warning("GROQ_API_KEY ausente: en segundo plano solo responde el router local.")
    else:
        logger.info("Cerebro Groq listo en segundo plano (modelo: %s).", brain.modelo)
    return MotorConversacion(router=router, brain=brain, voz=VoiceAssistant())