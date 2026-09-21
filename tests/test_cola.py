"""Tests de la cola de eventos (procesamiento en un solo hilo)."""
import time

from modules.cola import ColaEventos


def test_procesa_en_orden_y_con_datos():
    cola = ColaEventos()
    vistos = []
    cola.iniciar(lambda evento, datos: vistos.append((evento, datos)))
    cola.encolar(1, "a")
    cola.encolar(2)
    cola.encolar(3, "c")
    time.sleep(0.05)
    assert vistos == [(1, "a"), (2, None), (3, "c")]
    cola.detener()


def test_excepcion_no_mata_el_bucle():
    cola = ColaEventos()
    vistos = []

    def proc(evento, datos):
        if evento == 0:
            raise RuntimeError("boom")
        vistos.append(evento)

    cola.iniciar(proc)
    cola.encolar(0)
    cola.encolar(1)
    time.sleep(0.05)
    assert vistos == [1]
    cola.detener()