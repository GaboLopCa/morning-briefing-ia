import sys
import time as time_mod

from dotenv import load_dotenv


def _configurar_encoding_consola():
    """Fuerza UTF-8 en la consola (evita crashes de emojis/tildes al redirigir)."""
    if not sys.platform.startswith("win"):
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_configurar_encoding_consola()

from config import (  # noqa: E402
    BRIEFING_POR_VOZ,
    GOOGLE_API_KEY,
    LATITUD,
    LONGITUD,
    RSS_URLS,
)
from modules.ear import AudioEar
from modules.news import NewsFetcher
from modules.opencode_tool import OpenCodeRunner
from modules.search import WebSearcher
from modules.summarizer import Brain
from modules.tools import construir_registro
from modules.voice import VoiceAssistant
from modules.weather import WeatherProvider


def seleccionar_modo_interfaz():
    """Despliega un menú interactivo en la terminal para elegir la entrada."""
    while True:
        print("\n🎛️  SELECCIÓN DE ENTRADA (Josesito Assistant)")
        print("1. [Modo Texto]   -> Ideal para clases o trabajo en silencio.")
        print("2. [Modo Mic]     -> Activa el micrófono dinámico con VAD (RMS).")

        opcion = input("Selecciona una opción (1 o 2): ").strip()
        if opcion == "1":
            return "texto"
        if opcion == "2":
            return "mic"
        print("⚠️ Opción no válida. Por favor, digita 1 o 2.")


def pedir_confirmacion_opencode(peticion, ruta):
    """Confirmación humana antes de lanzar opencode."""
    print("\n[OpenCode] Petición:")
    print(f"   Proyecto : {ruta}")
    print(f"   Tarea    : {peticion}")
    return input("¿Confirmas ejecutar opencode? (s/N): ").strip().lower() in (
        "s",
        "si",
        "y",
        "yes",
    )


def main():
    load_dotenv()
    if not GOOGLE_API_KEY:
        print("❌ Error Crítico: No se encontró la variable GOOGLE_API_KEY en el archivo .env.")
        return

    print("==========================================================")
    print("🤖 JOSESITO HOME ASSISTANT - INICIALIZANDO...")
    print("==========================================================")

    modo = seleccionar_modo_interfaz()

    if modo == "mic":
        if not sys.platform.startswith("win"):
            print("❌ El modo micrófono solo está disponible en Windows (msvcrt).")
            return
        try:
            import msvcrt
        except ImportError:
            print("❌ No se pudo cargar el módulo msvcrt; modo micrófono no disponible aquí.")
            return

    # --- DI: ecosistema de módulos + registro de tools extensible ---
    weather_service = WeatherProvider(LATITUD, LONGITUD)      # Melipilla
    news_service = NewsFetcher(RSS_URLS)
    search_service = WebSearcher()
    opencode_runner = OpenCodeRunner(confirmador=pedir_confirmacion_opencode)

    registro = construir_registro(
        weather=weather_service,
        news=news_service,
        search=search_service,
        opencode=opencode_runner,
    )
    ai_service = Brain(GOOGLE_API_KEY, registro)
    voice_service = VoiceAssistant()
    ear_service = AudioEar(GOOGLE_API_KEY)

    print("\n----------------------------------------------------------")
    print("🤖 CONFIGURACIÓN COMPLETADA CON ÉXITO")
    print("----------------------------------------------------------")

    if modo == "texto":
        print("⌨️  MODO TEXTO: Escribe tus dudas en la consola.")
        print("    (exit / quit / salir para terminar)")
    else:
        print("🎙️ MODO MIC: Escuchando el entorno físico de tu pieza.")
        ear_service.calibrate_ambient_noise(duration=2.0)
        print("-> Presiona la [BARRA ESPACIADORA] para hablar con Josesito.")
        print("-> Presiona la tecla [ESC] para apagar el sistema.")

    print("----------------------------------------------------------\n")

    try:
        while True:
            user_command = ""

            # GESTIÓN DE ENTRADA: MODO TEXTO
            if modo == "texto":
                try:
                    user_command = input(" Gabriel >>> ")
                except (KeyboardInterrupt, EOFError):
                    print("\n💤 Apagando a Josesito de manera segura.")
                    break
                limpio = user_command.strip()
                if limpio.lower() in ("exit", "quit", "salir"):
                    print("💤 Apagando a Josesito de manera segura.")
                    break
                if not limpio:
                    continue

            # GESTIÓN DE ENTRADA: MODO MICRÓFONO
            else:
                if msvcrt.kbhit():
                    tecla = msvcrt.getch()
                    if ord(tecla) == 27:  # ESC
                        print("\n💤 Apagando a Josesito. Nos vemos, Gabriel.")
                        break
                    if ord(tecla) == 32:  # ESPACIO
                        print("\n🔔 [Josesito Escuchando]")
                        audio_file = ear_service.record_audio()
                        if audio_file is None:
                            continue  # abortado por ESC o sin voz

                        print("🧠 Transcribiendo audio con Gemini...")
                        user_command = ear_service.transcribe_audio(audio_file)
                        if not user_command.strip():
                            print("⚠️ Transcripción vacía; intenta de nuevo.")
                            continue
                        print(f"🗣️ Transcripción: \"{user_command}\"")
                else:
                    time_mod.sleep(0.05)  # evita busy-wait al 100% de CPU

            # --- PIPELINE DE PROCESAMIENTO COMÚN (Orquestador Central) ---
            if user_command:
                print("🤖 Enviando comando a la red cognitiva...")
                briefing = ai_service.generate_response(user_command)

                print("\n" + "=" * 40)
                print(briefing)
                print("=" * 40 + "\n")

                if modo == "texto":
                    if BRIEFING_POR_VOZ:
                        voice_service.speak(briefing)
                else:
                    voice_service.speak(briefing)
    except KeyboardInterrupt:
        print("\n💤 Apagando a Josesito. Nos vemos, Gabriel.")


if __name__ == "__main__":
    main()