"""Tests del motor de conversación del segundo plano (Sesión 5)."""
from types import SimpleNamespace

from modules.conversacion import (
    RESPUESTA_SIN_CEREBRO,
    MotorConversacion,
    _confirmar_segundo_plano,
)


class RouterFalso:
    def __init__(self, decision):
        self._decision = decision

    def decidir(self, texto):
        return self._decision

    def ejecutar(self, decision):
        return "respuesta del router"


class BrainFalso:
    def __init__(self):
        self.ultimo = None

    def generate_response(self, texto):
        self.ultimo = texto
        return "respuesta del brain"


class VozFalsa:
    def __init__(self):
        self.dichos = []
        self.detenciones = 0

    def speak(self, texto):
        self.dichos.append(texto)

    def detener(self):
        self.detenciones += 1


def test_resolver_enruta_por_el_router():
    voz = VozFalsa()
    decision = SimpleNamespace(herramienta="get_weather_data", origen="reglas")
    motor = MotorConversacion(router=RouterFalso(decision=decision), brain=BrainFalso(), voz=voz)
    assert motor.resolver("mi frase") == "respuesta del router"
    assert voz.dichos == []  # resolver NO habla


def test_resolver_cae_al_brain_cuando_el_router_no_decide():
    brain = BrainFalso()
    motor = MotorConversacion(router=RouterFalso(decision=None), brain=brain, voz=VozFalsa())
    assert motor.resolver("pregunta") == "respuesta del brain"
    assert brain.ultimo == "pregunta"


def test_resolver_sin_cerebro_ni_router_devuelve_mensaje():
    motor = MotorConversacion(router=None, brain=None, voz=VozFalsa())
    assert motor.resolver("hola") == RESPUESTA_SIN_CEREBRO


def test_hablar_delega_en_la_voz():
    voz = VozFalsa()
    motor = MotorConversacion(voz=voz)
    motor.hablar("hola Gabriel")
    assert voz.dichos == ["hola Gabriel"]


def test_confirmador_segundo_plano_siempre_rechaza():
    assert _confirmar_segundo_plano("revisar el código", "C:\\proyectos\\x") is False


def test_detener_frena_la_voz_barge_in():
    voz = VozFalsa()
    motor = MotorConversacion(voz=voz)
    motor.detener()
    assert voz.detenciones == 1