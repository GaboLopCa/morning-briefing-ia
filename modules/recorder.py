"""Grabación por VAD (RMS) reutilizable para el segundo plano.

`nivel_rms()` normaliza a escala [-1, 1] (los int16 se dividen por 32767) para
que un umbral valga igual con bloques float32 o int16. `Grabadora` acumula
bloques, corta por silencio prolongado o tope de duración, guarda el WAV en el
temp del SO y notifica:

  - `on_fin(ruta)`: hubo voz y se guardó el audio (Evento.FIN_AUDIO).
  - `on_abortado()`: nunca hubo voz útil (Evento.AUDIO_ABORTADO).

También permite `finalizar_manual()` (para el push-to-talk: cortar "ahora",
sin esperar el silencio) que devuelve la ruta directamente.
"""
import logging
import os
import tempfile
import threading
import time as time_mod

import numpy as np
from scipy.io import wavfile

from config import (
    DURACION_MAX_GRABACION,
    PAUSA_SILENCIO,
    STREAM_TASA,
    UMBRAL_MINIMO_RMS,
)

logger = logging.getLogger("josesito")


def nivel_rms(bloque):
    """RMS en escala [-1, 1]: divide los int16 por 32767 (los float no cambian)."""
    x = bloque.astype(np.float32)
    if bloque.dtype.kind in "iu":
        x = x / 32767.0
    return float(np.sqrt(np.mean(x * x)))


def _guardar_wav(tasa, audio_int16):
    fd, ruta = tempfile.mkstemp(prefix="josesito_", suffix=".wav")
    os.close(fd)
    wavfile.write(ruta, tasa, audio_int16)
    return ruta


class Grabadora:
    """Stateful: `comenzar()` reinicia el buffer y `alimentar()` decide el corte.

    Llamada desde el hilo del micrófono (audio thread), así que protege su
    estado con un lock; los callbacks (`on_fin`/`on_abortado`) deben ser
    rápidos y solo **encolar** (nunca procesar en línea).
    """

    def __init__(
        self,
        tasa=STREAM_TASA,
        umbral=UMBRAL_MINIMO_RMS,
        pausa=PAUSA_SILENCIO,
        tope=DURACION_MAX_GRABACION,
        on_fin=None,
        on_abortado=None,
        time_fn=None,
    ):
        self._tasa = tasa
        self._umbral = umbral
        self._pausa = pausa
        self._tope = tope
        self.on_fin = on_fin
        self.on_abortado = on_abortado
        self._cronometro = time_fn or time_mod.monotonic
        self.ruta_wav = None
        self._lock = threading.Lock()
        self._grabando = False
        self._frames = []
        self._t_inicio = 0.0
        self._t_ultima_voz = 0.0
        self._tiene_voz = False

    # ------------------------------------------------------------------ API

    def comenzar(self):
        with self._lock:
            self._frames = []
            self._t_inicio = self._cronometro()
            self._t_ultima_voz = self._t_inicio
            self._tiene_voz = False
            self.ruta_wav = None
            self._grabando = True

    def esta_grabando(self):
        return self._grabando

    def esta_lista(self):
        return not self._grabando

    def alimentar(self, bloque):
        """Bloque int16 mono (~80 ms). Devuelve True si la grabación terminó."""
        with self._lock:
            if not self._grabando:
                return False
            self._frames.append(bloque)
            ahora = self._cronometro()
            if nivel_rms(bloque) >= self._umbral:
                self._tiene_voz = True
                self._t_ultima_voz = ahora
            if self._tiene_voz and (ahora - self._t_ultima_voz) >= self._pausa:
                self._finalizar()
                return True
            if (ahora - self._t_inicio) >= self._tope:
                self._finalizar()
                return True
            return False

    def finalizar_manual(self):
        """Corta la grabación ahora (push-to-talk) y devuelve la ruta o None.

        A diferencia del corte por silencio, NO llama a `on_fin`: la ruta se
        devuelve directamente para que el flujo la use sin re-eventear.
        """
        with self._lock:
            if not self._grabando:
                return self.ruta_wav
            self._grabando = False
            if not self._tiene_voz:
                if self.on_abortado is not None:
                    self.on_abortado()
                return None
            self.ruta_wav = _guardar_wav(self._tasa, np.concatenate(self._frames, axis=0))
            return self.ruta_wav

    # ---------------------------------------------------------------- interno

    def _finalizar(self):
        self._grabando = False
        if not self._tiene_voz:
            logger.debug("Sin voz útil: grabación abortada.")
            if self.on_abortado is not None:
                self.on_abortado()
            return
        audio = np.concatenate(self._frames, axis=0)
        self.ruta_wav = _guardar_wav(self._tasa, audio)
        logger.info("WAV guardado: %s (%0.1f s)", self.ruta_wav, len(audio) / self._tasa)
        if self.on_fin is not None:
            self.on_fin(self.ruta_wav)