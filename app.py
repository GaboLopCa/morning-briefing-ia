"""Entrypoint del asistente en segundo plano.

Uso:
  python app.py          # proceso de fondo con bandeja + hotkeys (pythonw.exe)
  python app.py --debug  # consola de simulación de la máquina de estados

Sesión 2: todas las fuentes (hotkeys, items de la bandeja) encolan `Evento` en
una `ColaEventos`; un único hilo los procesa contra la `MaquinaEstados`, que no
es thread-safe. La bandeja corre en el hilo principal (requisito de Windows).
"""
import argparse
import logging
import sys
import time

from config import HOTKEY_PTT, HOTKEY_WAKE_TOGGLE, NOMBRE_INSTANCIA
from modules.audio_stream import Capturador
from modules.cola import ColaEventos
from modules.estados import Estado, Evento, MaquinaEstados
from modules.hotkeys import DetectorHotkeys, Hotkeys
from modules.logging_setup import configurar_logging
from modules.single_instance import InstanciaUnica
from modules.tray import Bandeja
from modules.wakeword import crear_detector

logger = None  # se asigna en main()


class Compartido:
    """Estado compartido entre bandeja, hotkeys y wake word."""

    def __init__(self):
        self.wake_activa = True
        self.hablando = False  # gating de eco: True mientras el TTS habla


def construir_manejadores(compartido=None):
    """Handlers de entrada a cada estado (Sesiones 1-3: solo logging + gating)."""
    if compartido is None:
        compartido = Compartido()

    def _manejador(txt, clave=None, hablando=None):
        def _fn(datos):
            if hablando is not None:
                compartido.hablando = hablando
            if clave and datos:
                logger.info(f"{txt} [{clave}={datos}]")
            else:
                logger.info(txt)

        return _fn

    return {
        Estado.IDLE: _manejador("En reposo (escuchando trigger)", hablando=False),
        Estado.GRABANDO: _manejador("Grabando voz"),
        Estado.TRANSCRIBIENDO: _manejador("Transcribiendo", "texto"),
        Estado.PENSANDO: _manejador("Pensando"),
        Estado.HABLANDO: _manejador("Hablando", "respuesta", hablando=True),
        Estado.PAUSADO: _manejador("Pausado"),
    }


# Comandos de la consola de simulación: letra -> (Evento, necesita texto)
COMANDOS_DEBUG = {
    "p": (Evento.PTT, False),
    "s": (Evento.PTT_SOLTAR, False),
    "w": (Evento.WAKE, False),
    "g": (Evento.FIN_AUDIO, False),
    "a": (Evento.AUDIO_ABORTADO, False),
    "x": (Evento.ERROR, False),
    "r": (Evento.RESPUESTA_LISTA, False),
    "v": (Evento.TERMINAR_VOZ, False),
    "pausa": (Evento.PAUSAR, False),
    "reanudar": (Evento.REANUDAR, False),
}


def _bucle_debug(maquina):
    print("Josesito segundo plano (simulación). h=ayuda, q=salir.")
    print(f"Estado inicial: {maquina.estado.name}")
    while True:
        try:
            linea = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not linea:
            continue
        comando, _, resto = linea.partition(" ")
        if comando == "q":
            break
        if comando == "h":
            print("p=PTT s=soltar w=wake g=fin_audio a=abort x=error "
                  "t <texto>=transcrito r=respuesta v=terminar_voz "
                  "pausa/reanudar q=salir")
            continue
        if comando == "t":
            evento, datos = Evento.TEXTO_LISTO, resto
        elif comando in COMANDOS_DEBUG:
            evento, _ = COMANDOS_DEBUG[comando]
            datos = None
        else:
            print("Comando desconocido (h para ayuda)")
            continue
        maquina.evento(evento, datos)
        print(f"    estado: {maquina.estado.name}")


def main(argv=None):
    global logger
    parser = argparse.ArgumentParser(prog="josesito-bg")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="consola de simulación (sin hotkeys ni bandeja)",
    )
    args = parser.parse_args(argv)

    logger = configurar_logging()
    puerta = InstanciaUnica(NOMBRE_INSTANCIA)
    if not puerta.adquirir():
        logger.error("Abortando: ya hay una instancia de Josesito corriendo.")
        return 1

    maquina = MaquinaEstados(construir_manejadores())
    try:
        if args.debug:
            _bucle_debug(maquina)
            return 0

        cola = ColaEventos()
        cola.iniciar(lambda evento, datos: maquina.evento(evento, datos))
        compartido = Compartido()

        detector = crear_detector(compartido, al_detectar=lambda: cola.encolar(Evento.WAKE))
        capturador = None
        if detector is not None:
            capturador = Capturador()

            def _alimento(datos):
                if compartido.wake_activa:
                    detector.alimentar(datos)

            capturador.suscribir(_alimento)
            try:
                capturador.iniciar()
            except Exception as exc:  # sin micrófono disponible: sigue sin wake word
                logger.warning("Micrófono no disponible (%s); sin wake word.", exc)
                capturador.detener()
                capturador = None

        def _toggle_wake():
            compartido.wake_activa = not compartido.wake_activa
            if detector is not None:
                detector.reset()
            logger.info("Wake word JARVIS: %s",
                        "ACTIVA" if compartido.wake_activa else "DESACTIVADA")

        detector_hotkeys = DetectorHotkeys(
            ptt=HOTKEY_PTT,
            wake=HOTKEY_WAKE_TOGGLE,
            al_ptt_presionar=lambda: cola.encolar(Evento.PTT),
            al_ptt_soltar=lambda: cola.encolar(Evento.PTT_SOLTAR),
            al_toggle_wake=_toggle_wake,
        )

        listener = None
        try:
            listener = Hotkeys(detector_hotkeys).iniciar()
        except Exception as exc:  # sin teclado/periféricos: sigue solo con bandeja
            logger.warning("Hotkeys no disponibles (%s); solo bandeja.", exc)

        bandeja = Bandeja(cola, maquina, compartido, al_toggle_wake=_toggle_wake)
        logger.info(
            "Segundo plano activo (hotkeys: PTT=%s, wake=%s).",
            HOTKEY_PTT, HOTKEY_WAKE_TOGGLE,
        )
        try:
            bandeja.correr()  # bloquea hasta "Salir"
        finally:
            if capturador is not None:
                capturador.detener()
            if listener is not None:
                listener.detener()
            cola.detener()
    finally:
        puerta.liberar()
        logger.info("Josesito en segundo plano finalizado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())