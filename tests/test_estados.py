"""Tests de la máquina de estados del segundo plano (sin I/O)."""
from modules.estados import Estado, Evento, MaquinaEstados


def test_recorrido_completo_happy_path():
    maquina = MaquinaEstados()
    assert maquina.evento(Evento.WAKE) is Estado.GRABANDO
    assert maquina.evento(Evento.FIN_AUDIO) is Estado.TRANSCRIBIENDO
    assert maquina.evento(Evento.TEXTO_LISTO, "hola") is Estado.PENSANDO
    assert maquina.evento(Evento.RESPUESTA_LISTA, "respuesta") is Estado.HABLANDO
    assert maquina.evento(Evento.TERMINAR_VOZ) is Estado.IDLE


def test_push_to_talk():
    maquina = MaquinaEstados()
    assert maquina.evento(Evento.PTT) is Estado.GRABANDO
    assert maquina.evento(Evento.PTT_SOLTAR) is Estado.TRANSCRIBIENDO


def test_transicion_invalida_ignorada():
    maquina = MaquinaEstados()
    maquina.evento(Evento.WAKE)  # GRABANDO
    # Wake word de nuevo mientras grabamos no hace nada.
    assert maquina.evento(Evento.WAKE) is Estado.GRABANDO
    assert maquina.evento(Evento.TERMINAR_VOZ) is Estado.GRABANDO


def test_pausar_y_reanudar():
    maquina = MaquinaEstados()
    assert maquina.evento(Evento.PAUSAR) is Estado.PAUSADO
    # En pausa no se graba.
    assert maquina.evento(Evento.WAKE) is Estado.PAUSADO
    assert maquina.evento(Evento.REANUDAR) is Estado.IDLE


def test_recuperacion_tras_error():
    maquina = MaquinaEstados()
    maquina.evento(Evento.PTT)
    assert maquina.evento(Evento.PTT_SOLTAR) is Estado.TRANSCRIBIENDO
    assert maquina.evento(Evento.ERROR) is Estado.IDLE


def test_audio_abortado_no_transcribe():
    maquina = MaquinaEstados()
    maquina.evento(Evento.WAKE)
    assert maquina.evento(Evento.AUDIO_ABORTADO) is Estado.IDLE


def test_manejadores_llamados_por_estado():
    llamados = []

    def _grabar(datos):
        llamados.append(("grabando", datos))

    def _pensar(datos):
        llamados.append(("pensando", datos))

    maquina = MaquinaEstados({Estado.GRABANDO: _grabar, Estado.PENSANDO: _pensar})
    maquina.evento(Evento.WAKE)
    maquina.evento(Evento.FIN_AUDIO)
    maquina.evento(Evento.TEXTO_LISTO, "texto")
    assert llamados == [("grabando", None), ("pensando", "texto")]


def test_manejador_que_falla_devuelve_a_idle():
    def _falla(datos):
        raise RuntimeError("boom")

    maquina = MaquinaEstados({Estado.GRABANDO: _falla})
    assert maquina.evento(Evento.WAKE) is Estado.IDLE


def test_error_desde_pensando():
    maquina = MaquinaEstados()
    maquina.evento(Evento.WAKE)
    maquina.evento(Evento.FIN_AUDIO)
    maquina.evento(Evento.TEXTO_LISTO, "x")
    assert maquina.evento(Evento.ERROR) is Estado.IDLE


def test_barge_in_wake_interrumpe_el_turno_de_habla():
    maquina = MaquinaEstados()
    maquina.evento(Evento.WAKE)
    maquina.evento(Evento.FIN_AUDIO)
    maquina.evento(Evento.TEXTO_LISTO, "hola")
    maquina.evento(Evento.RESPUESTA_LISTA, "respuesta")
    assert maquina.estado is Estado.HABLANDO
    assert maquina.evento(Evento.WAKE) is Estado.GRABANDO
    assert maquina.evento(Evento.PTT_SOLTAR) is Estado.TRANSCRIBIENDO


def test_barge_in_ptt_interrumpe_el_turno_de_habla():
    maquina = MaquinaEstados()
    maquina.evento(Evento.PTT)
    maquina.evento(Evento.FIN_AUDIO)
    maquina.evento(Evento.TEXTO_LISTO, "pregunto")
    maquina.evento(Evento.RESPUESTA_LISTA, "respuesta")
    assert maquina.estado is Estado.HABLANDO
    assert maquina.evento(Evento.PTT) is Estado.GRABANDO
    assert maquina.evento(Evento.FIN_AUDIO) is Estado.TRANSCRIBIENDO