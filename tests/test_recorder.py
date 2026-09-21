"""Tests del grabador por VAD (módulo reutilizable del segundo plano)."""
import os

import numpy as np

from modules.recorder import Grabadora, nivel_rms

TASA = 16000
BLOQUE = 1280  # 80 ms @ 16 kHz
DURACION_BLOQUE = BLOQUE / TASA


class Reloj:
    """Reloj simulado: cada bloque de audio avanza el tiempo como en lo real."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def avanzar(self, segundos=DURACION_BLOQUE):
        self.t += segundos


def _voz(segundos=0.1, amplitud=0.3):
    n = int(TASA * segundos)
    tono = np.sin(2 * np.pi * 440 * np.arange(n) / TASA)
    return (tono * amplitud * 32767).astype(np.int16)


def _silencio():
    return np.zeros(BLOQUE, dtype=np.int16)


def _alimentar_voz(grabadora, reloj, segundos=0.1):
    muestras = _voz(segundos)
    for i in range(0, len(muestras), BLOQUE):
        if grabadora.esta_lista():
            break
        grabadora.alimentar(muestras[i : i + BLOQUE].copy())
        reloj.avanzar()


def _alimentar_silencio(grabadora, reloj, bloques=10):
    for _ in range(bloques):
        if grabadora.esta_lista():
            return
        grabadora.alimentar(_silencio())
        reloj.avanzar()


def test_nivel_rms_normaliza_int16_a_escala_menos1_1():
    onda = np.sin(2 * np.pi * 440 * np.arange(16000) / 16000)
    int16 = (onda * 32767).astype(np.int16)
    flotante = onda.astype(np.float32)
    assert abs(nivel_rms(int16) - nivel_rms(flotante)) < 1e-3
    assert 0.6 < nivel_rms(int16) < 0.8  # RMS de una sinusoide ≈ 0.707


def test_silencio_sin_voz_aborta():
    eventos = []
    reloj = Reloj()
    grabadora = Grabadora(
        umbral=0.02, pausa=0.05, tope=0.25, time_fn=reloj,
        on_fin=lambda ruta: eventos.append(("fin", ruta)),
        on_abortado=lambda: eventos.append(("abortado", None)),
    )
    grabadora.comenzar()
    _alimentar_silencio(grabadora, reloj, bloques=30)

    assert grabadora.esta_lista()
    assert grabadora.ruta_wav is None
    assert eventos == [("abortado", None)]


def test_voz_seguida_de_silencio_guarda_wav():
    eventos = []
    ruta_salvada = {}
    reloj = Reloj()
    grabadora = Grabadora(
        umbral=0.02, pausa=0.05, tope=5.0, time_fn=reloj,
        on_fin=lambda ruta: (eventos.append("fin"), ruta_salvada.__setitem__("ruta", ruta)),
        on_abortado=lambda: eventos.append("abortado"),
    )
    grabadora.comenzar()
    _alimentar_voz(grabadora, reloj, segundos=0.2)
    _alimentar_silencio(grabadora, reloj, bloques=5)

    assert grabadora.esta_lista()
    assert eventos == ["fin"]
    ruta = ruta_salvada["ruta"]
    assert ruta and os.path.exists(ruta)
    assert os.path.getsize(ruta) > 0
    assert grabadora.ruta_wav == ruta
    os.remove(ruta)


def test_alimentar_sin_comenzar_ignora_bloques():
    grabadora = Grabadora()
    assert grabadora.alimentar(_silencio()) is False
    assert grabadora.esta_grabando() is False


def test_comenzar_reinicia_el_buffer():
    reloj = Reloj()
    grabadora = Grabadora(umbral=0.02, pausa=0.01, tope=0.5, time_fn=reloj,
                          on_fin=lambda ruta: None)
    grabadora.comenzar()
    _alimentar_voz(grabadora, reloj, segundos=0.15)
    _alimentar_silencio(grabadora, reloj, bloques=3)
    assert grabadora.esta_lista()  # cortó por pausa al llegar el silencio

    grabadora.comenzar()
    assert grabadora.esta_grabando()
    assert grabadora.ruta_wav is None


def test_tope_de_duracion_finaliza_aunque_haya_voz_continua():
    eventos = []
    reloj = Reloj()
    grabadora = Grabadora(umbral=0.02, pausa=99.0, tope=0.2, time_fn=reloj,
                          on_fin=lambda ruta: eventos.append(ruta),
                          on_abortado=lambda: eventos.append(None))
    grabadora.comenzar()
    _alimentar_voz(grabadora, reloj, segundos=0.5)  # dura más que el tope

    assert grabadora.esta_lista()
    assert len(eventos) == 1
    assert eventos[0]
    os.remove(grabadora.ruta_wav)


def test_finalizar_manual_devuelve_ruta_sin_disparar_on_fin():
    on_fin = []
    reloj = Reloj()
    grabadora = Grabadora(umbral=0.02, pausa=99.0, tope=99.0, time_fn=reloj,
                          on_fin=lambda ruta: on_fin.append(ruta))
    grabadora.comenzar()
    _alimentar_voz(grabadora, reloj, segundos=0.1)

    ruta = grabadora.finalizar_manual()

    assert ruta and os.path.exists(ruta)
    assert on_fin == []  # el flujo PTT usa la ruta directa, sin re-eventear
    assert grabadora.esta_lista()
    assert grabadora.ruta_wav == ruta
    os.remove(ruta)


def test_finalizar_manual_sin_voz_devuelve_none_y_aborta():
    abortado = []
    grabadora = Grabadora(on_abortado=lambda: abortado.append(True))
    grabadora.comenzar()
    assert grabadora.finalizar_manual() is None
    assert abortado == [True]