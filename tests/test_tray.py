"""Tests de la bandeja (solo la generación del icono; la icon real es GUI)."""
from modules.tray import crear_icono


def test_crear_icono_es_una_imagen_rgb():
    imagen = crear_icono()
    assert imagen.size == (64, 64)
    assert imagen.mode == "RGB"


def test_crear_icono_tamano_custom():
    imagen = crear_icono(tam=32)
    assert imagen.size == (32, 32)