"""Entrypoint del asistente en segundo plano.

Uso:
  python app.py          # proceso de fondo con bandeja + hotkeys (pythonw.exe)
  python app.py --debug  # consola de simulación de la máquina de estados

Sesión 2: todas las fuentes (hotkeys, items de la bandeja) encolan `Evento` en
una `ColaEventos`; un único hilo los procesa contra la `MaquinaEstados`, que no
es thread-safe. La bandeja corre en el hilo principal (requisito de Windows).

Sesión 4: el mismo `Capturador` alimenta la wake word y, cuando la máquina está
en GRABANDO, una `Grabadora` (VAD por RMS) acumula bloques; el corte por
silencio dispara FIN_AUDIO (ruta WAV en temp) y la transcripción con Whisper
(Groq) corre en un hilo que encola TEXTO_LISTO cuando termina.

Sesión 5: `MotorConversacion` (router → Brain → TTS) resuelve desde PENSANDO y
habla desde HABLANDO, siempre en hilos daemon que encolan `RESPUESTA_LISTA` /
`TERMINAR_VOZ`, sin bloquear jamás el hilo único de la cola.
"""
import argparse
import logging
import sys
import threading
import time

from config import (
    GROQ_API_KEY,
    HOTKEY_PTT,
    HOTKEY_WAKE_TOGGLE,
    NOMBRE_INSTANCIA,
)
from modules.audio_stream import Capturador
from modules.cola import ColaEventos
from modules.conversacion import crear_motor
from modules.ear import transcribir
from modules.estados import Estado, Evento, MaquinaEstados
from modules.hotkeys import DetectorHotkeys, Hotkeys
from modules.logging_setup import configurar_logging
from modules.recorder import Grabadora
from modules.single_instance import InstanciaUnica
from modules.tray import Bandeja
from modules.wakeword import crear_detector

logger = logging.getLogger("josesito")  # main() lo re-configura con archivo


class Compartido:
    """Estado compartido entre bandeja, hotkeys y wake word."""

    def __init__(self):
        self.wake_activa = True
        self.hablando = False  # gating de eco: True mientras el TTS habla


def _transcribir_y_encolar(ruta, encolar, api_key=GROQ_API_KEY):
    """Transcribe fuera del hilo de la cola y encola TEXTO_LISTO (o ERROR)."""

    def _trabajo():
        try:
            texto = transcribir(api_key, ruta)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Fallo al transcribir: %s", exc)
            encolar(Evento.ERROR)
            return
        if texto:
            encolar(Evento.TEXTO_LISTO, texto)
        else:
            encolar(Evento.AUDIO_ABORTADO)

    threading.Thread(target=_trabajo, daemon=True, name="josesito-transcribe").start()


def _resolver_y_encolar(motor, texto, encolar):
    """Resuelve (router → Brain) fuera de la cola y encola RESPUESTA_LISTA (o ERROR)."""

    def _trabajo():
        try:
            respuesta = motor.resolver(texto)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Fallo al resolver: %s", exc)
            encolar(Evento.ERROR)
            return
        encolar(Evento.RESPUESTA_LISTA, respuesta)

    threading.Thread(target=_trabajo, daemon=True, name="josesito-pensar").start()


def _hablar_y_encolar(motor, respuesta, encolar):
    """Sintetiza/reproduce la respuesta y encola TERMINAR_VOZ al terminar."""

    def _trabajo():
        try:
            motor.hablar(respuesta)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Fallo al hablar: %s", exc)
        finally:
            encolar(Evento.TERMINAR_VOZ)

    threading.Thread(target=_trabajo, daemon=True, name="josesito-hablar").start()


def construir_manejadores(compartido=None, grabadora=None, encolar=None,
                          transcribir=None, motor=None):
    """Handlers de entrada a cada estado.

    En modo real se inyectan `grabadora`/`encolar`/`transcribir`/`motor`: así
    GRABANDO acumula audio, TRANSCRIBIENDO transcribe en un hilo, PENSANDO
    resuelve la frase (router → Brain) y HABLANDO la habla — todo sin bloquear
    el hilo de la cola. En `--debug` no se pasan y los handlers solo loguean.
    """
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

    def _al_grabando(datos):
        # Barge-in: si venimos de HABLANDO (wake word o PTT mientras hablaba),
        # cortamos el TTS y limpiamos el gating de forma explícita.
        if motor is not None:
            motor.detener()
            compartido.hablando = False
        if grabadora is not None:
            grabadora.comenzar()
        logger.info("Grabando voz")

    def _al_transcribiendo(datos):
        if grabadora is None or encolar is None or transcribir is None:
            logger.info("Transcribiendo")
            return
        ruta = datos
        if ruta is None:
            ruta = grabadora.finalizar_manual()  # PTT soltado antes del silencio
        if not ruta:
            logger.info("Sin audio que transcribir; vuelvo a IDLE.")
            encolar(Evento.AUDIO_ABORTADO)
            return
        logger.info("Transcribiendo en hilo: %s", ruta)
        transcribir(ruta)

    def _al_pensando(datos):
        if motor is None or encolar is None:
            logger.info("Pensando [texto=%s]" if datos else "Pensando")
            return
        if not datos:
            logger.info("Sin texto que procesar; vuelvo a IDLE.")
            encolar(Evento.ERROR)
            return
        logger.info("Pensando (en hilo): %s", datos)
        _resolver_y_encolar(motor, datos, encolar)

    def _al_hablando(datos):
        compartido.hablando = True
        if motor is None or encolar is None:
            logger.info("Hablando [respuesta=%s]" if datos else "Hablando")
            return
        if not datos:
            logger.info("Sin respuesta que decir; vuelvo a IDLE.")
            encolar(Evento.TERMINAR_VOZ)
            return
        logger.info("Hablando (TTS en hilo)")
        _hablar_y_encolar(motor, datos, encolar)

    return {
        Estado.IDLE: _manejador("En reposo (escuchando trigger)", hablando=False),
        Estado.GRABANDO: _al_grabando,
        Estado.TRANSCRIBIENDO: _al_transcribiendo,
        Estado.PENSANDO: _al_pensando,
        Estado.HABLANDO: _al_hablando,
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
        compartido = Compartido()

        detector = crear_detector(compartido, al_detectar=lambda: cola.encolar(Evento.WAKE))

        grabadora = Grabadora(
            on_fin=lambda ruta: cola.encolar(Evento.FIN_AUDIO, ruta),
            on_abortado=lambda: cola.encolar(Evento.AUDIO_ABORTADO),
        )

        motor = crear_motor()

        maquina = MaquinaEstados(
            construir_manejadores(
                compartido,
                grabadora=grabadora,
                encolar=cola.encolar,
                transcribir=lambda ruta: _transcribir_y_encolar(ruta, cola.encolar),
                motor=motor,
            )
        )
        cola.iniciar(lambda evento, datos: maquina.evento(evento, datos))

        capturador = None
        if detector is not None:
            capturador = Capturador()

            def _alimento(datos):
                if compartido.wake_activa:
                    detector.alimentar(datos)
                if grabadora.esta_grabando():
                    grabadora.alimentar(datos)

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