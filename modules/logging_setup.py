"""Logging del asistente en segundo plano.

RotatingFileHandler hacia `logs/josesito.log` (config.LOG_ARCHIVO) + salida a
consola (solo útil en modo --debug). En segundo plano no hay prints: todo va al
archivo rotatorio, que no crece indefinidamente y sobrevive a la falta de
consola (pythonw.exe).
"""
import logging
import logging.handlers
from pathlib import Path

from config import LOG_ARCHIVO, LOG_NIVEL


def configurar_logging():
    """Configura la raíz y devuelve el logger de Josesito (idempotente)."""
    ruta = Path(LOG_ARCHIVO)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    formateador = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    rotatorio = logging.handlers.RotatingFileHandler(
        ruta, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    rotatorio.setFormatter(formateador)
    consola = logging.StreamHandler()
    consola.setFormatter(formateador)
    raiz = logging.getLogger()
    raiz.setLevel(getattr(logging, LOG_NIVEL.upper(), logging.INFO))
    if not raiz.handlers:  # idempotente ante re-llamadas
        raiz.addHandler(rotatorio)
        raiz.addHandler(consola)
    return logging.getLogger("josesito")