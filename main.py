import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Importación de módulos locales
from modules.weather import WeatherProvider
from modules.news import NewsFetcher
from modules.summarizer import NewsSummarizer
from modules.voice import VoiceAssistant
from modules.ear import AudioEar
from modules.search import WebSearcher

def seleccionar_modo_interfaz():
    """Despliega un menú interactivo en la terminal para elegir la entrada."""
    while True:
        print("\n🎛️  SELECCIÓN DE ENTRADA (Josesito Assistant)")
        print("1. [Modo Texto]   -> Ideal para clases o trabajo en silencio.")
        print("2. [Modo Mic]     -> Activa el micrófono dinámico con VAD (RMS).")
        
        opcion = input("Selecciona una opción (1 o 2): ").strip()
        if opcion == "1":
            return True   # MODO_CLASES = True
        elif opcion == "2":
            return False  # MODO_CLASES = False
        else:
            print("⚠️ Opción no válida. Por favor, digita 1 o 2.")

def main():
    load_dotenv()
    API_KEY = os.getenv("GROQ_API_KEY")
    
    if not API_KEY:
        print("❌ Error Crítico: No se encontró la variable GROQ_API_KEY en el archivo .env.")
        return

    print("==========================================================")
    print("🤖 JOSESITO HOME ASSISTANT - INICIALIZANDO...")
    print("==========================================================")

    MODO_CLASES = seleccionar_modo_interfaz()

    # Carga condicional y segura de msvcrt para control de teclado nativo en Windows
    if not MODO_CLASES:
        global msvcrt
        import msvcrt

    # Pool de canales RSS
    rss_urls = [
        "https://www.biobiochile.cl/lista/tag/chile/feed",
        "https://www.latercera.com/arc/outboundfeeds/rss/?outputType=xml",
        "https://www.elmostrador.cl/destacado/feed/",
        "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_5_6_1.xml",
        "https://www.alairelibre.cl/noticias/site/tax/port/all/rss_2_0.xml",
        "https://redgol.cl/rss/tag/universidad-de-chile",
        "https://www.adnradio.cl/category/deportes/feed/",
        "https://as.com/rss/pro/internacional.xml",
        "https://www.xataka.com/feed",
        "https://hipertextual.com/feed",
        "https://www.fayerwayer.com/feed/",
        "https://feeds.bbci.co.uk/mundo/rss.xml",
        "https://elpais.com/rss/el-pais/portada.xml",
        "https://nmas1.org/rss"
    ]
    
    # Instanciación del ecosistema completo de hardware y software
    weather_service = WeatherProvider(-33.6895, -71.2146) # Melipilla
    news_service = NewsFetcher(rss_urls)
    search_service = WebSearcher()                       # <- Instanciado
    ai_service = NewsSummarizer(API_KEY)
    voice_service = VoiceAssistant(speed=1.2)
    ear_service = AudioEar(API_KEY)

    print("\n----------------------------------------------------------")
    print("🤖 CONFIGURACIÓN COMPLETADA CON ÉXITO")
    print("----------------------------------------------------------")
    
    if MODO_CLASES:
        print("⌨️  MODO TEXTO: Escribe tus dudas en la consola.")
    else:
        print("🎙️ MODO MIC: Escuchando el entorno físico de tu pieza.")
        ear_service.calibrate_ambient_noise(duration=2.0)
        print("-> Presiona la [BARRA ESPACIADORA] para hablar con Josesito.")
        print("-> Presiona la tecla [ESC] para apagar el sistema.")
        
    print("----------------------------------------------------------\n")

    while True:
        user_command = ""

        # GESTIÓN DE ENTRADA: MODO TEXTO
        if MODO_CLASES:
            try:
                user_command = input(" Gabriel >>> ")
                if user_command.strip().lower() in ["exit", "quit", "salir"]:
                    print("💤 Apagando a Josesito de manera segura.")
                    break
                if not user_command.strip():
                    continue
            except (KeyboardInterrupt, EOFError):
                break

        # GESTIÓN DE ENTRADA: MODO MICRÓFONO
        else:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if ord(key) == 27: # ESC
                    print("\n💤 Apagando a Josesito. Nos vemos, Gabriel.")
                    break
                elif ord(key) == 32: # ESPACIO
                    print("\n🔔 [Josesito Escuchando]")
                    audio_file = ear_service.record_audio()
                    
                    print("🧠 Transcribiendo ráfaga de audio con Whisper...")
                    user_command = ear_service.transcribe_audio(audio_file)
                    
                    if not user_command.strip():
                        print("⚠️ Umbral RMS no superado o audio vacío.")
                        continue
                        
                    print(f"🗣️ Transcripción: \"{user_command}\"")

        # --- PIPELINE DE PROCESAMIENTO COMÚN (Orquestador Central) ---
        if user_command:
            print("🤖 Enviando comando a la red cognitiva...")
            briefing = ai_service.generate_response(
                weather_provider=weather_service,
                news_fetcher=news_service,
                search_provider=search_service, # <- Pasado como argumento directo
                user_command=user_command
            )

            print("\n" + "="*40)
            print(briefing)
            print("="*40 + "\n")

            voice_service.speak(briefing)
            
            if not MODO_CLASES:
                print("🎙️ En espera... Presiona [ESPACIO] para hablar de nuevo.")

if __name__ == "__main__":
    main()