"""Bandeja de sistema del segundo plano (pystray).

La icon debe correr en el hilo principal de Windows: `Bandeja.correr()`
bloquea hasta que se elige "Salir". Los items del menú solo **encolan** eventos
(o dan estado a `Compartido`), nunca tocan la máquina directamente.
"""
import logging

import pystray
from PIL import Image, ImageDraw

from config import TRAY_NOMBRE
from modules.estados import Estado, Evento

logger = logging.getLogger("josesito")


def crear_icono(tam=64):
    """Icono de la bandeja generado en caliente (sin asset): burbuja azul + 'J'."""
    imagen = Image.new("RGB", (tam, tam), "#0f172a")
    dibujo = ImageDraw.Draw(imagen)
    dibujo.ellipse((6, 6, tam - 6, tam - 6), fill="#3b82f6")
    dibujo.ellipse((tam // 2 - 10, 8, tam // 2 + 10, 28), fill="#93c5fd")
    dibujo.polygon(
        [(tam // 2 - 6, 26), (tam // 2 + 6, 26), (tam // 2, tam - 18)],
        fill="#93c5fd",
    )
    return imagen


class Bandeja:
    def __init__(self, cola, maquina, compartido, al_toggle_wake=None):
        self._cola = cola
        self._maquina = maquina
        self._compartido = compartido
        self._al_toggle_wake = al_toggle_wake
        self._icono = None

    def _menu(self):
        def _escuchar(icono, item):
            self._cola.encolar(Evento.PTT)

        def _pausa(icono, item):
            if self._maquina.estado is Estado.PAUSADO:
                self._cola.encolar(Evento.REANUDAR)
            else:
                self._cola.encolar(Evento.PAUSAR)

        def _toggle_wake(icono, item):
            if self._al_toggle_wake is not None:
                self._al_toggle_wake()
            else:
                self._compartido.wake_activa = not self._compartido.wake_activa
                logger.info("Wake word JARVIS: %s",
                            "ACTIVA" if self._compartido.wake_activa else "DESACTIVADA")

        def _salir(icono, item):
            self.detener()

        return pystray.Menu(
            pystray.MenuItem("Escuchar", _escuchar),
            pystray.MenuItem(
                "Wake word",
                _toggle_wake,
                checked=lambda item: self._compartido.wake_activa,
            ),
            pystray.MenuItem(
                "En pausa",
                _pausa,
                checked=lambda item: self._maquina.estado is Estado.PAUSADO,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", _salir),
        )

    def correr(self):
        """Bloquea hasta elegir Salir. Debe llamarse desde el main thread."""
        self._icono = pystray.Icon(TRAY_NOMBRE, crear_icono(), menu=self._menu())
        logger.info("Bandeja activa. Menú: Escuchar, Wake word, En pausa, Salir.")
        self._icono.run()
        self._icono = None

    def detener(self):
        if self._icono is not None:
            self._icono.stop()
            self._icono = None