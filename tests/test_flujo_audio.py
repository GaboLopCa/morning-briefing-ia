"""Tests E2E del flujo de audio en el segundo plano (Sesión 4).

Máquina de estados real + `Grabadora` real + transcripción falsa inyectada:
cubre lo que hará el usuario con la wake word / push-to-talk.
"""
import os
import time

import numpy as np

from app import construir_manejadores
from modules.cola import ColaEventos
from modules.estados import Estado, Evento, MaquinaEstados
from modules.recorder import Grabadora

TASA = 16000
BLOQUE = 1280
DURACION_BLOQUE = BLOQUE / TASA


class CompartidoStub:
    def __init__(self):
        self.wake_activa = True
        self.hablando = False


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def avanzar(self):
        self.t += DURACION_BLOQUE


def _voz():
    tono = np.sin(2 * np.pi * 440 * np.arange(BLOQUE * 2) / TASA)
    return (tono * 0.3 * 32767).astype(np.int16).reshape(-1)


def _silencio():
    return np.zeros(BLOQUE, dtype=np.int16)


def _esperar(condicion, tope=3.0):
    fin = time.monotonic() + tope
    while time.monotonic() < fin:
        if condicion():
            return True
        time.sleep(0.01)
    return False


def _montar(textos_vistos, transcribe_fake, tope=5.0):
    compartido = CompartidoStub()
    cola = ColaEventos()
    reloj = Reloj()
    grabadora = Grabadora(
        umbral=0.02, pausa=0.05, tope=tope, time_fn=reloj,
        on_fin=lambda ruta: cola.encolar(Evento.FIN_AUDIO, ruta),
        on_abortado=lambda: cola.encolar(Evento.AUDIO_ABORTADO),
    )
    manejadores = construir_manejadores(
        compartido,
        grabadora=grabadora,
        encolar=cola.encolar,
        transcribir=transcribe_fake,
    )
    pensar_original = manejadores[Estado.PENSANDO]
    manejadores[Estado.PENSANDO] = lambda datos: (textos_vistos.append(datos), pensar_original(datos))
    maquina = MaquinaEstados(manejadores)
    cola.iniciar(lambda evento, datos: maquina.evento(evento, datos))
    return maquina, cola, grabadora, reloj


def test_flujo_wake_voz_silencio_llega_a_pensando_con_texto():
    textos = []
    maquina, cola, grabadora, reloj = _montar(
        textos, lambda ruta: cola.encolar(Evento.TEXTO_LISTO, "hola josesito"))

    maquina.evento(Evento.WAKE)  # -> GRABANDO, la grabadora empieza
    assert maquina.estado is Estado.GRABANDO

    for bloque in _voz().reshape(-1, BLOQUE):
        grabadora.alimentar(bloque)
        reloj.avanzar()
    for _ in range(3):  # silencio que supera la pausa (0.05 s)
        grabadora.alimentar(_silencio())
        reloj.avanzar()

    assert _esperar(lambda: maquina.estado is Estado.PENSANDO)
    assert textos == ["hola josesito"]


def test_flujo_wake_sin_voz_vuelve_a_idle():
    textos = []
    maquina, cola, grabadora, reloj = _montar(
        textos, lambda ruta: cola.encolar(Evento.TEXTO_LISTO, "nunca"), tope=0.25)

    maquina.evento(Evento.WAKE)
    for _ in range(5):  # silencio hasta superar el tope (0.25 s)
        grabadora.alimentar(_silencio())
        reloj.avanzar()

    # Tope de pausa superado sin voz: nada que transcribir -> AUDIO_ABORTADO -> IDLE
    assert _esperar(lambda: maquina.estado is Estado.IDLE)
    assert textos == []


def test_flujo_ptt_soltar_sin_silencio_transcribe_igual():
    textos = []
    maquina, cola, grabadora, reloj = _montar(
        textos, lambda ruta: cola.encolar(Evento.TEXTO_LISTO, "pedido"))

    maquina.evento(Evento.PTT)
    for bloque in _voz().reshape(-1, BLOQUE):
        grabadora.alimentar(bloque)
        reloj.avanzar()

    maquina.evento(Evento.PTT_SOLTAR)  # sin llegar al silencio: finalizar_manual
    assert _esperar(lambda: maquina.estado is Estado.PENSANDO)
    assert textos == ["pedido"]


def test_el_wav_se_guarda_en_temp_del_so():
    textos = []
    maquina, cola, grabadora, reloj = _montar(
        textos, lambda ruta: cola.encolar(Evento.TEXTO_LISTO, "hola"))

    maquina.evento(Evento.WAKE)
    for bloque in _voz().reshape(-1, BLOQUE):
        grabadora.alimentar(bloque)
        reloj.avanzar()
    for _ in range(3):
        grabadora.alimentar(_silencio())
        reloj.avanzar()

    assert _esperar(lambda: maquina.estado is Estado.PENSANDO)
    ruta = grabadora.ruta_wav
    assert ruta and os.path.isabs(ruta)
    assert "user_command" not in ruta.lower()
    assert os.path.dirname(ruta) != os.getcwd()