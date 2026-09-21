"""Captura continua del micrófono (16 kHz, mono, int16, bloques de 80 ms).

Un único `sounddevice.InputStream` que alimenta a los suscriptores: la wake
word ahora; en la sesión 4, la grabación para transcripción reusa el mismo
stream. El callback de sounddevice corre en su propio hilo: los suscriptores
deben ser rápidos y solo **encolar** trabajo, nunca bloquear.
"""
import logging

import numpy as np
import sounddevice as sd

from config import STREAM_BLOQUE, STREAM_TASA

logger = logging.getLogger("josesito")


class Capturador:
    def __init__(self, tasa=STREAM_TASA, bloque=STREAM_BLOQUE, fabrica_stream=None):
        self._tasa = tasa
        self._bloque = bloque
        self._fabrica = fabrica_stream or sd.InputStream
        self._suscriptores = set()
        self._stream = None

    def suscribir(self, fn):
        self._suscriptores.add(fn)

    def desuscribir(self, fn):
        self._suscriptores.discard(fn)

    def _callback(self, datos, tramas, hora, estado):
        if estado:
            logger.warning("Estado del micrófono: %s", estado)
        bloque = np.array(datos[:, 0], copy=True)  # mono -> int16 1-D (80 ms)
        for fn in list(self._suscriptores):
            try:
                fn(bloque)
            except Exception:
                logger.exception("Suscriptor de audio falló (se ignora el bloque)")

    def iniciar(self):
        self._stream = self._fabrica(
            samplerate=self._tasa,
            channels=1,
            dtype="int16",
            blocksize=self._bloque,
            callback=self._callback,
        )
        self._stream.start()
        logger.info("Micrófono continuo activo (%s Hz, bloques de %s).", self._tasa, self._bloque)

    def detener(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.warning("Al detener el micrófono: %s", exc)
            self._stream = None