"""E2E de la conversación completa en el segundo plano (Sesión 5).

Máquina real + `Grabadora` real + transcripción falsa + `MotorConversacion`
simulado: WAKE → voz → FIN_AUDIO → TEXTO_LISTO → PENSANDO (resuelve) →
RESPUESTA_LISTA → HABLANDO (habla) → TERMINAR_VOZ → IDLE.
"""
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


class MotorStub:
    """Simula resolver (Brain) y hablar (TTS) con latencia mínima."""

    def __init__(self):
        self.hablado = []
        self.respuesta = "respuesta de prueba"
        self.detenciones = 0

    def resolver(self, texto):
        time.sleep(0.05)  # ~latencia de Groq
        return self.respuesta

    def hablar(self, texto):
        time.sleep(0.05)  # ~duración del TTS
        self.hablado.append(texto)

    def detener(self):
        self.detenciones += 1


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


def _montar(motor, tope=5.0):
    compartido = CompartidoStub()
    cola = ColaEventos()
    reloj = Reloj()
    grabadora = Grabadora(
        umbral=0.02, pausa=0.05, tope=tope, time_fn=reloj,
        on_fin=lambda ruta: cola.encolar(Evento.FIN_AUDIO, ruta),
        on_abortado=lambda: cola.encolar(Evento.AUDIO_ABORTADO),
    )
    maquina = MaquinaEstados(
        construir_manejadores(
            compartido,
            grabadora=grabadora,
            encolar=cola.encolar,
            transcribir=lambda ruta: cola.encolar(Evento.TEXTO_LISTO, "hola josesito"),
            motor=motor,
        )
    )
    cola.iniciar(lambda evento, datos: maquina.evento(evento, datos))
    return maquina, grabadora, reloj, compartido


def _hablar_a_josesito(maquina, grabadora, reloj):
    maquina.evento(Evento.WAKE)
    for bloque in _voz().reshape(-1, BLOQUE):
        grabadora.alimentar(bloque)
        reloj.avanzar()
    for _ in range(3):
        grabadora.alimentar(_silencio())
        reloj.avanzar()


def test_conversacion_completa_idle_a_idle():
    motor = MotorStub()
    maquina, grabadora, reloj, compartido = _montar(motor)

    _hablar_a_josesito(maquina, grabadora, reloj)
    assert _esperar(lambda: maquina.estado is Estado.PENSANDO)
    assert _esperar(lambda: maquina.estado is Estado.HABLANDO)

    hablando_durante = compartido.hablando  # gating de eco activo mientras habla
    assert _esperar(lambda: maquina.estado is Estado.IDLE)

    assert motor.hablado == ["respuesta de prueba"]
    assert hablando_durante is True
    assert compartido.hablando is False  # vuelve a escuchar tras terminar


def test_silencio_sin_voz_no_hace_hablar_al_motor():
    motor = MotorStub()
    maquina, grabadora, reloj, _ = _montar(motor, tope=0.25)

    maquina.evento(Evento.WAKE)
    for _ in range(5):  # solo silencio hasta superar el tope
        grabadora.alimentar(_silencio())
        reloj.avanzar()

    assert _esperar(lambda: maquina.estado is Estado.IDLE)
    assert motor.hablado == []


def test_texto_directo_por_la_cola_tambien_conversa():
    """Equivalent al `t <texto>` del debug: TEXTO_LISTO llega por cola."""
    motor = MotorStub()
    maquina, _, _, _ = _montar(motor)

    maquina.evento(Evento.WAKE)
    maquina.evento(Evento.PTT_SOLTAR)  # -> TRANSCRIBIENDO (sin ruta: finaliza manual vacío)
    maquina.evento(Evento.TEXTO_LISTO, "qué hora es")

    assert _esperar(lambda: maquina.estado is Estado.HABLANDO)
    assert _esperar(lambda: maquina.estado is Estado.IDLE)
    assert motor.hablado == ["respuesta de prueba"]


def test_barge_in_interrumpe_mientras_habla():
    """Wake word mientras Josesito habla: corta el TTS y vuelve a escuchar."""
    motor = MotorStub()
    maquina, grabadora, reloj, compartido = _montar(motor)

    maquina.evento(Evento.WAKE)
    maquina.evento(Evento.PTT_SOLTAR)
    maquina.evento(Evento.TEXTO_LISTO, "qué hora es")
    assert _esperar(lambda: maquina.estado is Estado.HABLANDO)

    maquina.evento(Evento.WAKE)  # barge-in
    assert maquina.estado is Estado.GRABANDO
    assert motor.detenciones >= 1  # cortó el TTS
    assert compartido.hablando is False  # gating limpio, ya escucha

    for bloque in _voz().reshape(-1, BLOQUE):  # habla de nuevo tras el corte
        grabadora.alimentar(bloque)
        reloj.avanzar()
    for _ in range(3):
        grabadora.alimentar(_silencio())
        reloj.avanzar()

    assert _esperar(lambda: maquina.estado is Estado.HABLANDO)
    assert _esperar(lambda: maquina.estado is Estado.IDLE)
    assert motor.hablado == ["respuesta de prueba", "respuesta de prueba"]