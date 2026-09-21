"""Tests del detector de wake word (lógica pura con modelo falso)."""
import builtins

import numpy as np

from modules.wakeword import WakeWordDetector, crear_detector


class ModeloFalso:
    """Devuelve los puntajes que se le encolen; por defecto silencio."""

    def __init__(self):
        self.cola = []
        self.reinicios = 0

    def predict(self, audio):
        return self.cola.pop(0) if self.cola else {"hey jarvis": 0.0}

    def reset(self):
        self.reinicios += 1


def _detector(**kwargs):
    disparos = []
    modelo = ModeloFalso()
    detector = WakeWordDetector(modelo, al_detectar=lambda: disparos.append("jarvis"), **kwargs)
    return detector, modelo, disparos


def test_no_dispara_bajo_el_umbral():
    detector, modelo, disparos = _detector()
    modelo.cola = [{"hey jarvis": 0.2}]
    assert detector.alimentar(np.zeros(1280, dtype=np.int16)) is False
    assert disparos == []


def test_dispara_en_el_flanco_y_no_se_repite():
    detector, modelo, disparos = _detector()
    modelo.cola = [{"hey jarvis": 0.9}, {"hey jarvis": 0.8}]  # mantiene energía
    assert detector.alimentar(np.zeros(1280, dtype=np.int16)) is True
    assert detector.alimentar(np.zeros(1280, dtype=np.int16)) is False  # ya disparado
    assert disparos == ["jarvis"]


def test_rearme_tras_caer_bajo_la_histeresis():
    detector, modelo, disparos = _detector()
    modelo.cola = [
        {"hey jarvis": 0.9},  # dispara
        {"hey jarvis": 0.1},  # rearma
        {"hey jarvis": 0.9},  # dispara de nuevo
    ]
    assert detector.alimentar(np.zeros(1280, dtype=np.int16)) is True
    assert detector.alimentar(np.zeros(1280, dtype=np.int16)) is False
    assert detector.alimentar(np.zeros(1280, dtype=np.int16)) is True
    assert disparos == ["jarvis", "jarvis"]


def test_gating_mientras_habla():
    hablando = {"valor": True}

    def _hablando():
        return hablando["valor"]

    detector, modelo, disparos = _detector(esta_hablando=_hablando)
    modelo.cola = [{"hey jarvis": 0.9}, {"hey jarvis": 0.1}]
    assert detector.alimentar(np.zeros(1280, dtype=np.int16)) is False  # hablando
    assert disparos == []
    assert detector.alimentar(np.zeros(1280, dtype=np.int16)) is False  # rearma
    hablando["valor"] = False
    modelo.cola = [{"hey jarvis": 0.9}]
    assert detector.alimentar(np.zeros(1280, dtype=np.int16)) is True  # ya libre
    assert disparos == ["jarvis"]


def test_clave_jarvis_gana_y_reset_rearma():
    detector, modelo, disparos = _detector()
    # alexa suena más fuerte pero la clave jarvis queda por debajo del umbral.
    modelo.cola = [{"alexa": 0.9, "hey jarvis": 0.2}]
    assert detector.alimentar(np.zeros(80, dtype=np.int16)) is False
    detector.reset()
    modelo.cola = [{"alexa": 0.0, "hey jarvis": 0.9}]
    assert detector.alimentar(np.zeros(80, dtype=np.int16)) is True


def test_crear_detector_degrada_sin_la_dependencia(monkeypatch):
    import importlib
    import sys

    real_import = builtins.__import__

    def bloquear(nombre, *args, **kwargs):
        if nombre in ("openwakeword", "openwakeword.model", "onnxruntime"):
            raise ImportError("síntesis: dependencia faltante")
        return real_import(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", bloquear)
    for mod in ("openwakeword", "openwakeword.model"):
        sys.modules.pop(mod, None)

    # `crear_detector` importa dentro; forzar recarga limpia.
    import modules.wakeword as wakeword_mod
    importlib.reload(wakeword_mod)
    assert wakeword_mod.crear_detector() is None