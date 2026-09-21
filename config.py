"""Configuración central del asistente Josesito.

Constantes del sistema y allowlist de proyectos para la tool `ejecutar_opencode`.
La variable de entorno GROQ_API_KEY se carga desde `.env`.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Ruta absoluta al .env del repo: independiente del cwd desde el que se lance.
load_dotenv(Path(__file__).resolve().parent / ".env")

# --- Credenciales ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# --- Modelos (Groq, OpenAI-compatible) ---
MODELO_LLM = "qwen/qwen3.8-27b"  # cerebro conversacional (+ tools), rápido y sin modo reasoning
MODELO_TRANSCRIPCION = "whisper-large-v3-turbo"  # STT para el micrófono

# --- Clima (Melipilla) ---
LATITUD = -33.6895
LONGITUD = -71.2146

# --- Fuentes RSS ---
RSS_URLS = [
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
]

# --- Cervecería de noticias / búsqueda ---
MAX_NOTICIAS_TOTAL = 40
DESCRIPCION_MAX = 200
TIMEOUT_HTTP = 10
NOTICIAS_WORKERS = 6        # hilos para descargar fuentes RSS en paralelo
NOTICIAS_CACHE_TTL = 120    # segundos: no re-descargar feeds dentro de una misma sesión
NOTICIAS_CONTEXTO = 15      # titulares que se inyectan al LLM en el contexto del turno
SNIPPET_MAX = 300

# --- Memoria conversacional ---
MAX_HISTORIAL_TURNOS = 12  # pares user/model que se siembran en cada sesión

# --- LLM ---
TEMPERATURA_LLM = 0.7
MAX_TOKENS_SALIDA = 1024
EVITAR_MARKDOWN = True  # por ahora solo informativo para el prompt

# --- Router de intenciones (cascada local: reglas -> embeddings -> Brain) ---
ROUTER_ACTIVO = True              # False = todo va al LLM (comportamiento previo)
# Capa 2 (embeddings): MEDIDA Y DESCARTADA como decisora automática (2026-09).
# Con potion-multilingual-128M el coseno zero-shot no separa: "¿qué hora es?" (ruido)
# puntúa 0.61 mientras "me gustaría saber si llueve" solo 0.29. Actívala solo para
# experimentar; sin un clasificador entrenado (requiere torch) no es fiable.
ROUTER_EMBEDDINGS_ACTIVO = False
ROUTER_UMBRAL_CONFIANZA = 0.55    # similitud coseno mínima si se habilita la capa 2
ROUTER_MODELO_EMBEDDINGS = "minishlab/potion-multilingual-128M"  # estático, 101 idiomas, MIT

# --- Micrófono / voz ---
PAUSA_SILENCIO = 1.5      # segundos de silencio para cortar recording
DURACION_MAX_GRABACION = 30.0   # tope de seguridad de grabación
UMBRAL_MINIMO_RMS = 0.005
VOZ_RAPIDEZ = 1.2
VARIANTE_VOZ = "es-CL-LorenzoNeural"
BRIEFING_POR_VOZ = True  # en modo texto, ¿leer en voz alta la respuesta?

# --- Tool ejecutar_opencode ---
# Allowlist: el modelo solo elige un NOMBRE; nunca una ruta arbitraria.
OPENCODE_PROYECTOS = {
    "asistente": r"C:\Users\gabol\OneDrive\Documentos\Proyectos de programación\ASISTENTE_IA\ASISTENTE_IA",
    "briefing": r"C:\Users\gabol\OneDrive\Documentos\Proyectos de programación\Proyecto_Briefing",
    "fantasy": r"C:\Users\gabol\OneDrive\Documentos\Proyectos de programación\Chilean_Fantasy",
    "f1": r"C:\Users\gabol\OneDrive\Documentos\Proyectos de programación\F1 championship analyzer",
    "footballgm": r"C:\Users\gabol\OneDrive\Documentos\Proyectos de programación\FootballGM\FootballGM",
    "gestor": r"C:\Users\gabol\OneDrive\Documentos\Proyectos de programación\GestorFinanciero",
    "rrhh": r"C:\Users\gabol\OneDrive\Documentos\Proyectos de programación\Buscar codigos RRHH",
    "futbol": r"C:\Users\gabol\OneDrive\Documentos\Proyectos de programación\Proyecto estadísticas futbol",
    "aniversario": r"C:\Users\gabol\OneDrive\Documentos\Proyectos de programación\Aniversario",
}
OPENCODE_TIMEOUT = 300      # segundos; opencode puede ser lento
OPENCODE_SALIDA_MAX = 4000  # chars máx de salida que se devuelve al LLM

# --- Segundo plano (app.py) ---
# Proceso sin consola: `python app.py` (o `pythonw app.py`). El lock de instancia
# única y el log rotatorio viven aquí; hotkeys/wake word/bandeja se conectan en
# sesiones siguientes (ver TAREAS_PENDIENTES.md).
NOMBRE_INSTANCIA = "josesito"
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_ARCHIVO = LOG_DIR / "josesito.log"
LOG_NIVEL = "INFO"

# --- Segundo plano: hotkeys globales y bandeja ---
# Nombres de tecla válidos: ver `_normalizar` en modules/hotkeys.py.
HOTKEY_PTT = ["ctrl", "f7"]        # push-to-talk: mantener presionada para grabar
HOTKEY_WAKE_TOGGLE = ["ctrl", "f8"]  # activa/desactiva la wake word JARVIS
TRAY_NOMBRE = "Josesito"

# --- Segundo plano: wake word JARVIS y audio continuo ---
# openWakeWord (Apache-2.0, ONNX local). Sesión 3: modelo preentrenado.
# Para custom: WAKE_WORD_ARCHIVO = ruta a un .onnx entrenado.
WAKE_WORD_MODELO = "hey jarvis"  # preentrenado que trae openwakeword
WAKE_WORD_ARCHIVO = None         # None = usar el preentrenado por clave/lista
WAKE_WORD_UMBRAL = 0.5           # score para disparar
WAKE_WORD_HISTERESIS = 0.25      # por debajo de esto se rearma el detector
STREAM_TASA = 16000              # el modelo de openwakeword usa 16 kHz
STREAM_BLOQUE = 1280             # frames por bloque = 80 ms @ 16 kHz