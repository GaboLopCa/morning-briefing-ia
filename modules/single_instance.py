"""Instancia única del asistente en segundo plano.

Lock clásico por archivo en el temp del SO: en Windows se bloquea el primer
byte con `msvcrt` (LK_NBLCK) y en POSIX con `flock`. Si otra instancia ya tiene
el lock, `InstanciaUnica.adquirir()` devuelve `False` y `app.py` aborta.
"""
import logging
import os
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger("josesito")


def _bloquear(fd):
    if sys.platform.startswith("win"):
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _desbloquear(fd):
    if sys.platform.startswith("win"):
        import msvcrt

        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


class InstanciaUnica:
    """Bloquea el nombre del proceso: solo una copia puede correr a la vez."""

    def __init__(self, nombre):
        self._ruta = Path(tempfile.gettempdir()) / f"{nombre}.lock"
        self._fd = None

    def adquirir(self):
        if self._fd is not None:
            return True
        try:
            fd = os.open(self._ruta, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            logger.warning("No se pudo abrir el lock %s: %s", self._ruta, exc)
            return False
        # Escribir el pid primero: si otra instancia ya bloqueó el byte 0,
        # Windows rechaza la escritura (PermissionError) = lock ocupado.
        try:
            os.write(fd, f"{os.getpid()}".encode())
            os.lseek(fd, 0, os.SEEK_SET)
        except PermissionError:
            os.close(fd)
            logger.info("Lock tomado por otra instancia: %s", self._ruta)
            return False
        if not _bloquear(fd):
            os.close(fd)
            logger.info("Ya hay una instancia de Josesito corriendo (lock: %s)", self._ruta)
            return False
        self._fd = fd
        logger.debug("Instancia única adquirida: %s", self._ruta)
        return True

    def liberar(self):
        if self._fd is None:
            return
        try:
            _desbloquear(self._fd)
        finally:
            os.close(self._fd)
            self._fd = None