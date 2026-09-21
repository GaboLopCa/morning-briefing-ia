"""Máquina de estados del asistente en segundo plano.

Lógica pura (sin I/O): aquí viven los estados y las transiciones. El audio
(sounddevice), Whisper, el router y la bandeja se conectan como *manejadores*
inyectados por estado → el núcleo se puede probar offline y cada pieza se puede
reemplazar sin tocar este módulo.

Estados: IDLE → GRABANDO → TRANSCRIBIENDO → PENSANDO → HABLANDO → IDLE, con
PAUSADO como compuerta manual y ERROR como red de seguridad hacia IDLE.
"""
import logging
from enum import Enum, auto

logger = logging.getLogger("josesito")


class Estado(Enum):
    IDLE = auto()            # escuchando trigger (wake word u hotkey)
    GRABANDO = auto()        # capturando voz con VAD
    TRANSCRIBIENDO = auto()  # Whisper (Groq)
    PENSANDO = auto()        # router de intenciones o Brain
    HABLANDO = auto()        # TTS en curso (edge-tts + pygame)
    PAUSADO = auto()         # pausa manual desde la bandeja


class Evento(Enum):
    PTT = auto()             # push-to-talk: empieza a grabar
    PTT_SOLTAR = auto()      # push-to-talk: suelta y transcribe
    WAKE = auto()            # wake word detectada
    FIN_AUDIO = auto()       # silencio o tope de duración alcanzado
    AUDIO_ABORTADO = auto()  # la grabación se canceló (sin voz útil)
    TEXTO_LISTO = auto()     # transcripción lista (datos: texto)
    RESPUESTA_LISTA = auto() # respuesta lista (datos: texto)
    ERROR = auto()           # fallo en cualquier fase
    TERMINAR_VOZ = auto()    # el TTS terminó de hablar
    PAUSAR = auto()
    REANUDAR = auto()


# Mapas de transición: (estado_origen, evento) -> estado_destino.
# Todo par que no esté aquí es una transición inválida → se ignora en silencio.
TRANSICIONES = {
    (Estado.IDLE, Evento.PTT): Estado.GRABANDO,
    (Estado.IDLE, Evento.WAKE): Estado.GRABANDO,
    (Estado.IDLE, Evento.PAUSAR): Estado.PAUSADO,
    (Estado.PAUSADO, Evento.REANUDAR): Estado.IDLE,
    (Estado.GRABANDO, Evento.PTT_SOLTAR): Estado.TRANSCRIBIENDO,
    (Estado.GRABANDO, Evento.FIN_AUDIO): Estado.TRANSCRIBIENDO,
    (Estado.GRABANDO, Evento.AUDIO_ABORTADO): Estado.IDLE,
    (Estado.GRABANDO, Evento.ERROR): Estado.IDLE,
    (Estado.TRANSCRIBIENDO, Evento.TEXTO_LISTO): Estado.PENSANDO,
    (Estado.TRANSCRIBIENDO, Evento.AUDIO_ABORTADO): Estado.IDLE,
    (Estado.TRANSCRIBIENDO, Evento.ERROR): Estado.IDLE,
    (Estado.PENSANDO, Evento.RESPUESTA_LISTA): Estado.HABLANDO,
    (Estado.PENSANDO, Evento.ERROR): Estado.IDLE,
    (Estado.HABLANDO, Evento.TERMINAR_VOZ): Estado.IDLE,
    (Estado.HABLANDO, Evento.ERROR): Estado.IDLE,
}


class MaquinaEstados:
    """Máquina determinista; `manejadores` es `{Estado: callable(datos)}`."""

    def __init__(self, manejadores=None):
        self.manejadores = manejadores or {}
        self.estado = Estado.IDLE

    def evento(self, evento, datos=None):
        """Dispara `evento`; devuelve el estado resultante (ignora inválidas)."""
        if (self.estado, evento) not in TRANSICIONES:
            logger.debug("Transición ignorada: %s + %s", self.estado, evento)
            return self.estado
        destino = TRANSICIONES[(self.estado, evento)]
        logger.info("Transición: %s --%s--> %s", self.estado, evento, destino)
        self.estado = destino
        manejador = self.manejadores.get(self.estado)
        if manejador:
            try:
                manejador(datos)
            except Exception:
                logger.exception("Manejador de %s falló; volviendo a IDLE", self.estado)
                self.estado = Estado.IDLE
        return self.estado

    def pausar(self):
        return self.evento(Evento.PAUSAR)

    def reanudar(self):
        return self.evento(Evento.REANUDAR)