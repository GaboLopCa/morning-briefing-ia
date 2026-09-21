"""Hotkeys globales del segundo plano (pynput).

`DetectorHotkeys` es lógica pura: recibe nombres de tecla normalizados y
dispara callbacks; se testea sin tocar teclado real. `Hotkeys` solo conecta el
detector al `pynput.keyboard.Listener`. Las combinaciones se definen por nombre
en `config.HOTKEY_*` (p. ej. `["ctrl", "f7"]`).
"""
import logging

from pynput import keyboard

from config import HOTKEY_PTT, HOTKEY_WAKE_TOGGLE

logger = logging.getLogger("josesito")


def _normalizar(tecla):
    """Traduce un objeto de pynput a un nombre estable ('ctrl', 'f7', 'a', ...)."""
    if isinstance(tecla, keyboard.Key):
        return tecla.name
    if isinstance(tecla, keyboard.KeyCode):
        return tecla.char.lower() if tecla.char else f"vk{tecla.vk}"
    return str(tecla)


class DetectorHotkeys:
    """Detecta combinaciones por nombre y notifica en los flancos.

    - PTT: `al_ptt_presionar` cuando la combinación se completa; `al_ptt_soltar`
      cuando se libera cualquiera de sus teclas.
    - Wake: `al_toggle_wake` una sola vez por mantención de la combinación.
    """

    def __init__(
        self,
        ptt=None,
        wake=None,
        al_ptt_presionar=None,
        al_ptt_soltar=None,
        al_toggle_wake=None,
    ):
        self._ptt = frozenset(ptt or HOTKEY_PTT)
        self._wake = frozenset(wake or HOTKEY_WAKE_TOGGLE)
        self.al_ptt_presionar = al_ptt_presionar
        self.al_ptt_soltar = al_ptt_soltar
        self.al_toggle_wake = al_toggle_wake
        self._pulsadas = set()
        self._ptt_activo = False
        self._wake_ya = False

    def pulsar(self, nombre):
        self._pulsadas.add(nombre)
        if self._ptt <= self._pulsadas and not self._ptt_activo:
            self._ptt_activo = True
            logger.debug("PTT presionado")
            if self.al_ptt_presionar:
                self.al_ptt_presionar()
        if self._wake <= self._pulsadas and not self._wake_ya:
            self._wake_ya = True
            logger.debug("Toggle wake word")
            if self.al_toggle_wake:
                self.al_toggle_wake()

    def soltar(self, nombre):
        ptt_activo = self._ptt_activo
        self._pulsadas.discard(nombre)
        if ptt_activo and not (self._ptt <= self._pulsadas):
            self._ptt_activo = False
            logger.debug("PTT soltado")
            if self.al_ptt_soltar:
                self.al_ptt_soltar()
        if self._wake_ya and not (self._wake <= self._pulsadas):
            self._wake_ya = False


class Hotkeys:
    """Conecta `DetectorHotkeys` al listener global de pynput."""

    def __init__(self, detector=None):
        self._detector = detector or DetectorHotkeys()
        self._listener = None

    def iniciar(self):
        self._listener = keyboard.Listener(
            on_press=lambda tecla: self._detector.pulsar(_normalizar(tecla)),
            on_release=lambda tecla: self._detector.soltar(_normalizar(tecla)),
        )
        self._listener.start()
        logger.info("Hotkeys activas: PTT=%s toggle wake=%s",
                    self._detector._ptt, self._detector._wake)
        return self

    def detener(self):
        if self._listener is not None:
            self._listener.stop()
            self._listener = None