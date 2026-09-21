"""Helper para el contrato de respuestas de herramientas (errores = datos).

Todos los módulos externos devuelven un 'envelope' JSON-serializable:

    {"status": "ok",    "data": ...}        # éxito
    {"status": "error", "mensaje": "..."}   # error con texto genérico

Las excepciones se registran en consola; al LLM solo llega el mensaje genérico.
"""
from typing import Any


def ok(data: Any) -> dict:
    """Envelope de éxito."""
    return {"status": "ok", "data": data}


def error(mensaje: str) -> dict:
    """Envelope de error con mensaje genérico (sin rastros internos)."""
    return {"status": "error", "mensaje": mensaje}