"""Tests del lock de instancia única (Windows: msvcrt sobre byte-range)."""
from modules.single_instance import InstanciaUnica


def test_segunda_instancia_rechazada_y_liberacion():
    puerta = InstanciaUnica("josesito-test")
    try:
        assert puerta.adquirir() is True
        segunda = InstanciaUnica("josesito-test")
        assert segunda.adquirir() is False, "el lock ya estaba tomado"
        segunda.liberar()  # idempotente, no debe explotar
    finally:
        puerta.liberar()
    # Tras liberar, una nueva instancia puede tomar el lock.
    tercera = InstanciaUnica("josesito-test")
    assert tercera.adquirir() is True
    tercera.liberar()


def test_adquirir_doble_es_inocuo():
    puerta = InstanciaUnica("josesito-test")
    try:
        assert puerta.adquirir() is True
        assert puerta.adquirir() is True  # misma instancia ya tiene el lock
    finally:
        puerta.liberar()