"""Tests del capturador continuo de micro (con micrófono falso inyectado)."""
import numpy as np

from modules.audio_stream import Capturador


class FalsoStream:
    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.detenido = False
        self.cerrado = False

    def start(self):
        pass

    def stop(self):
        self.detenido = True

    def close(self):
        self.cerrado = True

    def emitir(self, stereo_2d):
        self.callback(stereo_2d, stereo_2d.shape[0], None, None)


def _capturador():
    falso = None

    def fabrica(**kwargs):
        nonlocal falso
        falso = FalsoStream(**kwargs)
        return falso

    capturador = Capturador(fabrica_stream=fabrica)
    return capturador, lambda: falso


def test_suscriptores_reciben_bloques_mono_int16():
    capturador, obtener = _capturador()
    recibido = []
    capturador.suscribir(lambda bloque: recibido.append(bloque))
    capturador.iniciar()

    falso = obtener()
    audio = np.zeros((1280, 1), dtype=np.int16)
    audio[10, 0] = 42
    falso.emitir(audio)

    assert len(recibido) == 1
    assert recibido[0].shape == (1280,)
    assert recibido[0].dtype == np.int16
    assert recibido[0][10] == 42
    capturador.detener()


def test_excepcion_de_un_suscriptor_no_corta_a_los_demas():
    capturador, obtener = _capturador()
    vistos = []

    def roto(bloque):
        raise RuntimeError("boom")

    capturador.suscribir(roto)
    capturador.suscribir(lambda bloque: vistos.append(bloque))
    capturador.iniciar()

    obtener().emitir(np.zeros((1280, 1), dtype=np.int16))
    assert len(vistos) == 1
    capturador.detener()


def test_detener_cierra_el_stream():
    capturador, obtener = _capturador()
    capturador.iniciar()
    falso = obtener()
    capturador.detener()
    assert falso.detenido is True
    assert falso.cerrado is True