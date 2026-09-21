"""Cola de eventos del segundo plano.

Todas las fuentes (hotkeys, bandeja, wake word, audio) encolan `Evento`
aquí; un único hilo las procesa contra la `MaquinaEstados`, que por diseño
no es thread-safe. Así `MaquinaEstados` nunca se toca desde dos hilos.
"""
import logging
import queue
import threading

logger = logging.getLogger("josesito")


class ColaEventos:
    def __init__(self):
        self._cola = queue.Queue()
        self._hilo = None

    def encolar(self, evento, datos=None):
        self._cola.put((evento, datos))

    def iniciar(self, como_procesar):
        self._hilo = threading.Thread(
            target=self._bucle, args=(como_procesar,), name="josesito-eventos", daemon=True
        )
        self._hilo.start()
        return self

    def _bucle(self, como_procesar):
        while True:
            evento, datos = self._cola.get()
            if evento is None:  # centinela de detención
                break
            try:
                como_procesar(evento, datos)
            except Exception:
                logger.exception("Error procesando evento %s", evento)

    def detener(self):
        self._cola.put((None, None))
        if self._hilo is not None:
            self._hilo.join(timeout=2)
            self._hilo = None