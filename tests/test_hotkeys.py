"""Tests del detector de hotkeys (lógica pura, sin teclado real)."""
from modules.hotkeys import DetectorHotkeys


def _detector():
    eventos = []
    det = DetectorHotkeys(
        ptt=["ctrl", "f7"],
        wake=["ctrl", "f8"],
        al_ptt_presionar=lambda: eventos.append("pulsar"),
        al_ptt_soltar=lambda: eventos.append("soltar"),
        al_toggle_wake=lambda: eventos.append("wake"),
    )
    return det, eventos


def test_ptt_presiona_y_suelta():
    det, eventos = _detector()
    det.pulsar("ctrl")
    det.pulsar("f7")
    assert eventos == ["pulsar"]
    det.soltar("f7")
    assert eventos == ["pulsar", "soltar"]
    det.soltar("ctrl")
    assert eventos == ["pulsar", "soltar"]


def test_ptt_requiere_todas_las_teclas():
    det, eventos = _detector()
    det.pulsar("f7")  # falta el ctrl
    assert eventos == []
    det.pulsar("ctrl")
    assert eventos == ["pulsar"]


def test_ptt_no_repite_mientras_se_mantiene():
    det, eventos = _detector()
    det.pulsar("ctrl")
    det.pulsar("f7")
    det.pulsar("f7")  # evento repetido del SO
    assert eventos == ["pulsar"]


def test_soltar_ctrl_termina_el_ptt():
    det, eventos = _detector()
    det.pulsar("ctrl")
    det.pulsar("f7")
    assert eventos == ["pulsar"]
    det.soltar("ctrl")
    assert eventos == ["pulsar", "soltar"]


def test_wake_toggle_una_vez_por_mantencion():
    det, eventos = _detector()
    det.pulsar("ctrl")
    det.pulsar("f8")
    assert eventos == ["wake"]
    det.pulsar("f8")
    assert eventos == ["wake"]
    det.soltar("f8")
    det.pulsar("f8")  # nueva pulsación
    assert eventos == ["wake", "wake"]


def test_teclas_ajenas_no_disparan_nada():
    det, eventos = _detector()
    det.pulsar("a")
    det.pulsar("f8")
    det.pulsar("f7")
    assert eventos == []