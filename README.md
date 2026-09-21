# Josesito Home Assistant

## 📋 Visión del Proyecto

**Josesito Home Assistant** es un asistente personal inteligente de voz y texto, diseñado como un "briefing matutino" personalizado para Gabriel, estudiante de ingeniería de software. El sistema combina múltiples fuentes de información en tiempo real (clima, noticias, búsqueda web) con una personalidad única de presentador de radio satírico y directo, originario de Melipilla, que habla en español neutro.

### Objetivo Principal
Proporcionar un resumen diario personalizado y conversacional de información relevante, permitiendo interacción por voz o texto, con capacidades de búsqueda en tiempo real, memoria contextual y delegación de tareas de programación vía opencode.

---

## 🏗️ Arquitectura del Sistema

### Patrón de Diseño: **Orquestación Modular con Pipeline Central**

El sistema sigue una arquitectura de **microservicios locales** donde un orquestador central (`main.py`) coordina módulos especializados independientes, conectados mediante inyección de dependencias (DI).

```
┌─────────────────────────────────────────────────────────────┐
│                    main.py (Orquestador)                     │
│  - Menú de selección de entrada (Texto/Micrófono)            │
│  - DI: construye proveedores y los inyecta al registro       │
│  - Ciclo de vida de la aplicación                            │
└──────────┬──────────────────────────────────────────────────┘
           │
           ├──► modules/weather.py      (WeatherProvider)
           ├──► modules/news.py          (NewsFetcher)
           ├──► modules/search.py        (WebSearcher)
           ├──► modules/opencode_tool.py (OpenCodeRunner)
           ├──► modules/summarizer.py    (Brain - motor Gemini Live)
           ├──► modules/voice.py         (VoiceAssistant)
           └──► modules/ear.py           (AudioEar)
```

### Tool Registry (extensible)

`modules/tools/registry.py` modela cada capacidad como una `Herramienta` (declaración JSON Schema para el LLM + handler local). El `Brain` no conoce las herramientas: delega el dispatch al registro. Para añadir una habilidad basta construir una `Herramienta` y registrarla.

**Herramientas actuales:**

| Nombre | Parámetros | Handler |
|---|---|---|
| `get_weather_data` | — | `WeatherProvider.get_weather()` |
| `get_news_data` | — | `NewsFetcher.get_top_news()` |
| `search_internet_data` | `query` (requerido) | `WebSearcher.search_internet(query)` |
| `ejecutar_opencode` | `proyecto` (enum allowlist) + `peticion` (requeridos) | `OpenCodeRunner.ejecutar(...)` |

### Contrato de Respuestas (envelope)

Todos los módulos devuelven un envelope JSON-serializable (`modules/contract.py`):

```json
{"status": "ok",    "data": ...}
{"status": "error", "mensaje": "texto genérico"}
```

Los `status: error` llegan al LLM como `{"result": {"status": "error", ...}}`; el detalle técnico va solo a consola, nunca al modelo.

### Flujo de Datos

```
ENTRADA (Texto/Mic)
        │
        ▼
┌───────────────────────────────────────┐
│   AudioEar (si es voz)                │
│   - VAD por RMS + calibración          │
│   - Transcripción con Gemini           │
│   (gemini-3.5-transcribe)              │
└───────────────┬───────────────────────┘
                │
                ▼
┌───────────────────────────────────────┐
│   Brain (Motor de IA)                 │
│   - Gemini 3.1 Flash (Live API)       │
│   - Sesión por turno (WebSocket)      │
│   - Tool calling vía registry         │
│   - Memoria por pares user/model      │
└───────────────┬───────────────────────┘
                │
        ┌───────┴────────┐
        │                │
        ▼                ▼
   [Tools libres]   [Chitchat]
        │                │
        ▼                ▼
┌──────────────┐  ┌──────────────┐
│ WeatherProv  │  │ Respuesta    │
│ NewsFetcher  │  │ directa      │
│ WebSearcher  │  └──────┬───────┘
│ OpenCode     │         │
└──────┬───────┘         │
       │                │
       └────────┬───────┘
                ▼
       ┌────────────────┐
       │ VoiceAssistant │
       │ - Edge-TTS     │
       │ - pygame mixer │
       └────────────────┘
```

#### Sesión por turno (Live API)

Cada consulta abre una sesión WebSocket propia: se siembra el historial (pares user/model) más el mensaje actual vía `send_client_content(turns=..., turn_complete=True)` con `history_config.initial_history_in_client_content=True`. Esto resuelve el bug histórico del trim del sliding window: **la memoria client-side solo contiene pares user/model**, recortada por turnos completos, sin mensajes `tool` huérfanos.

---

## 🧩 Módulos del Sistema

### 1. **WeatherProvider** (`modules/weather.py`)
**Responsabilidad**: Obtención de datos meteorológicos en tiempo real.

- API: Open-Meteo (sin autenticación)
- Ubicación: Melipilla, Chile (`-33.6895, -71.2146`) — configuración en `config.py`
- Campos: `max`, `min`, `current`, `feels_like`, `rain_prob`, `condition` (mapeo WMO a etiqueta en español: despejado / parcialmente nublado / niebla / lluvia / nieve / tormenta / nublado)
- Timeout de red y errores envueltos en el envelope (`status: error`)

**Interfaz**:
```python
get_weather() -> {"status": "ok", "data": {...}} | {"status": "error", "mensaje": str}
```

---

### 2. **NewsFetcher** (`modules/news.py`)
**Responsabilidad**: Agregación de noticias desde múltiples fuentes RSS chilenas y latinoamericanas.

- 13 fuentes RSS en `config.py` (Biobío, La Tercera, El Mostrador, Cooperativa, ADN, BBC Mundo, Xataka, etc.)
- Filtrado **timezone-aware** (comparación en UTC, últimas 24 h); descarta sin fecha
- **Descarga en paralelo** (ThreadPoolExecutor, `NOTICIAS_WORKERS=6`) con reintento simple ante `429/5xx`
- **Mini-caché en memoria** (`NOTICIAS_CACHE_TTL=120` s): llamadas repetidas de la misma sesión no re-descargan feeds
- **Dedup por título** entre fuentes
- Capa global `MAX_NOTICIAS_TOTAL=40` **y** capa por fuente (`por_fuente=8`)
- Descripciones truncadas a `DESCRIPCION_MAX=200` caracteres solo si realmente exceden
- Timeout de 10 s y User-Agent de navegador
- Fuentes que fallan se saltan sin romper el agregado

**Interfaz**:
```python
get_top_news() -> {"status": "ok", "data": [{"title", "description", "category"}]} | error
```

---

### 3. **WebSearcher** (`modules/search.py`)
**Responsabilidad**: Búsqueda en internet en tiempo real.

- Motor: DuckDuckGo (vía `ddgs`), región Chile (`cl-es`)
- Máx. 4 resultados; **dedup por título**; snippets truncados a `SNIPPET_MAX=300`
- Bloque de texto plano estructurado para el LLM

**Interfaz**:
```python
search_internet(query: str) -> {"status": "ok", "data": str} | {"status": "error", "mensaje": str}
```

---

### 4. **Brain** (`modules/summarizer.py`) — Motor cognitivo
**Responsabilidad**: Conversación + orquestación de herramientas vía Gemini Live API.

- **Modelo**: `gemini-3.1-flash-live-preview` (Live API WebSocket, sesión por turno)
- **Modo de salida**: el modelo es *voice-first* (`response_modalities=["AUDIO"]`) y rechaza la modalidad TEXT; el texto de la respuesta se obtiene con `output_audio_transcription` (campo `output_transcription` en `server_content`), que llega en varios chunks que se concatenan
- **Tool calling**: el modelo decide qué herramienta llamar; el `Brain` resuelve el `FunctionResponse` y recibe el texto final del mismo turno de sesión
- **Memoria**: pares user/model limitados a `MAX_HISTORIAL_TURNOS=12`, recorte por turnos completos
- **Config Live**: `response_modalities=["AUDIO"]` + `output_audio_transcription` (es-CL), `thinking_level="LOW"`, temperatura 0.7, máx 1024 tokens
- **Personalidad**: Josesito, presentador satírico, irónico y directo, originario de Melipilla, hablando en **español neutro** (sin modismos chilenos) para que el TTS lo lea naturalmente
- **Sin markdown** en la salida (para que el TTS la lea naturalmente)

**Interfaz**:
```python
Brain(api_key, registro) -> generate_response(user_command: str) -> str
Brain(...) -> limpiar_historial() -> None
```

---

### 5. **VoiceAssistant** (`modules/voice.py`)
**Responsabilidad**: Síntesis de voz y reproducción.

- Motor Edge-TTS, voz `es-CL-LorenzoNeural`, velocidad 1.2x
- Limpieza de texto (URLs, asteriscos, hashtags)
- `pygame.mixer` con inicialización **perezosa y tolerante a fallos** (sin audio → responde solo por texto)
- MP3 temporal en `tempfile.gettempdir()` (`speech_<pid>.mp3`), eliminado en `finally` — no deja residuos en el cwd

**Interfaz**:
```python
speak(text: str) -> None
```

---

### 6. **AudioEar** (`modules/ear.py`)
**Responsabilidad**: Captura de audio y transcripción.

- VAD casero por RMS + calibración dinámica de ruido (x1.5, mínimo `UMBRAL_MINIMO_RMS`)
- Cortes por silencio (1.5 s), **tope de seguridad de 30 s**, y aborte por **ESC** (con `msvcrt`, solo Windows)
- WAV a 16 kHz en int16, `np.clip` para evitar saturación
- **Transcripción**: Gemini `gemini-3.5-transcribe`, con `AudioTranscriptionConfig(language_codes=["es-CL"], custom_vocabulary=...)`
- WAV temporal eliminado en `finally`

**Interfaz**:
```python
record_audio() -> str | None      # ruta WAV, o None si se abortó / no hubo voz
transcribe_audio(file_path: str) -> str
calibrate_ambient_noise(duration: float = 2.0) -> None
```

---

### 7. **OpenCodeRunner** (`modules/opencode_tool.py`)
**Responsabilidad**: Delegar tareas de programación al CLI `opencode` en los proyectos locales del usuario.

- Ejecuta `opencode run --dir <ruta> "<petición>"` via `subprocess` (sin `--auto`)
- **Confirmación humana obligatoria**: llamada a un callback (en `main.py` es un `input(¿Confirmas? s/N)`)
- **Allowlist**: `OPENCODE_PROYECTOS` en `config.py` — el modelo solo elige un *nombre*, nunca una ruta arbitraria
- Timeout de 300 s, ventana de consola oculta en Windows (`CREATE_NO_WINDOW`), salida truncada a 4000 caracteres, encoding UTF-8

**Interfaz**:
```python
OpenCodeRunner(confirmador=fn) -> ejecutar(*, proyecto: str, peticion: str) -> envelope
```

---

## 🔄 Modos de Operación

Al iniciar, `main.py` muestra un menú interactivo (`seleccionar_modo_interfaz()`). No existe una constante; la selección se hace en cada ejecución.

### Opción 1: **Modo Texto**
- Entrada por consola con prompt `Gabriel >>>`
- Comandos de salida: `exit`, `quit`, `salir`
- Multiplataforma (no requiere `msvcrt`)
- Si `BRIEFING_POR_VOZ` está en `True` (config), la respuesta además se lee por voz

### Opción 2: **Modo Micrófono**
- Entrada por voz con VAD por RMS
- Calibración inicial de ruido (2 s)
- Controles: **ESPACIO** graba, **ESC** apaga
- **Solo Windows** (`msvcrt`); en otra plataforma el wizard aborta el arranque con mensaje claro

---

## 🛠️ Stack Tecnológico

### Dependencias (`requirements.txt`, pineadas con `==`)
```
google-genai==2.24.0   # Gemini Live API (LLM) y transcripción
requests               # HTTP para APIs y RSS
feedparser             # Parsing de feeds RSS
ddgs                   # Búsqueda web DuckDuckGo
edge-tts               # Síntesis de voz neural
pygame                 # Reproducción de audio
sounddevice            # Captura de audio desde micrófono
numpy                  # Procesamiento de señales (RMS)
scipy                  # Escritura de archivos WAV
python-dotenv          # Variables de entorno
websockets             # Transporte de la Live API
pytest                 # Tests
```

### APIs Externas
1. **Gemini (Google AI Studio)** — LLM Live y transcripción
   - Modelos: `gemini-3.1-flash-live-preview` (LLM) y `gemini-3.5-transcribe` (STT)
   - API Key: variable de entorno `GOOGLE_API_KEY`
2. **Open-Meteo API** (clima, sin auth)
3. **Edge-TTS** (voz, sin key)
4. **DuckDuckGo** (búsqueda, sin key)
5. **opencode CLI** (local) para `ejecutar_opencode`

---

## 🚀 Instalación y Configuración

### Prerrequisitos
- Python 3.8+
- Windows 10/11 (modo micrófono)
- API Key de Gemini (Google AI Studio)
- `opencode` en el PATH (solo para la tool `ejecutar_opencode`)

### Pasos

```bash
# 1. Crear entorno virtual
python -m venv venv
venv\Scripts\activate  # Windows (source venv/bin/activate en Linux/Mac)

# 2. Instalar dependencias (pinneadas)
pip install -r requirements.txt

# 3. Crear el .env con tu clave de Gemini
# (Google AI Studio -> Get API key -> Create key)
echo GOOGLE_API_KEY=tu_clave_aqui > .env

# 4. Ejecutar
python main.py
```

### Tests

```bash
python -m pytest -q
```

> Nota: `main.py` importa `modules.*` como namespace package; ejecuta siempre desde la raíz del proyecto.

### Configuración de `.env`
```env
GOOGLE_API_KEY=tu_clave_de_gemini
```

---

## 🎯 Casos de Uso

```
Usuario: "Buenos días Josesito, ¿qué hay para hoy?"
Usuario: "¿Cómo está el clima en Melipilla?"
Usuario: "¿Qué pasó con la U ayer?"
Usuario: "¿Cuándo es el próximo partido de la Roja?"
Usuario: "Crea un skill de opencode para X en el proyecto briefing"
```

---

## 🧪 Testing

- **53 tests** en `tests/` (`test_weather.py`, `test_news.py`, `test_search.py`, `test_tools_registry.py`, `test_brain.py`, `test_opencode_tool.py`).
- Cubren: mapeo WMO, filtro de 24 h y caps de noticias, dedup de búsqueda, formato de declaración Live (validado offline contra el `LiveConnectConfig` del SDK), recorte de memoria por pares, dispatch de herramientas y el ciclo de `OpenCodeRunner` (confirmación, timeout, truncado) — todo mockeado, sin red.
- Verificación manual: `python -m pytest` y una corrida en modo texto preguntando clima/noticias/búsqueda.

---

## 🔒 Seguridad

- API Key solo en `.env` (gitignored)
- `ejecutar_opencode` exige confirmación humana y allowlist de proyectos
- Errores internos nunca se exponen al LLM (solo mensaje genérico)
- Audios corruptos/estrías: archivos temporales se eliminan en `finally`

---

## 📝 Notas de Desarrollo

### Decisiones de Diseño
1. **Gemini Live API por turno** sobre sesión persistente: aislamiento, sin estado web de larga vida, y memoria seed explícita
2. **Registry declarativo** sobre dispatch manual: añadir una tool = una `Herramienta`, sin tocar `Brain`
3. **Envelope `{status, data|mensaje}`** como contrato único: el LLM siempre recibe datos o un mensaje parseable
4. **Recorte por pares** resolvió el bug del trim impreciso (tool calls huérfanas)
5. **Edge-TTS + pygame lazy**: gratuito y sin dependencia de audio si se corre headless
6. **opencode con confirmación + allowlist**: la única tool con efectos sobre el sistema de archivos

### Limitaciones Conocidas
- Modo micrófono solo en Windows (`msvcrt`)
- Memoria no persiste entre sesiones
- Sin interfaz gráfica
- `ejecutar_opencode` depende de que el CLI `opencode` esté autenticado en el equipo

---

## 🔗 Referencias

- [Gemini Live API docs](https://ai.google.dev/gemini-api/docs/live)
- [Google AI Python SDK (google-genai)](https://github.com/googleapis/python-genai)
- [Edge-TTS](https://github.com/rany2/edge-tts)
- [Open-Meteo API](https://open-meteo.com/en/docs)
- [ddgs (DuckDuckGo Search)](https://github.com/fourleif/ddgs)

---

**Última actualización**: Septiembre 2026
**Versión**: 2.0.0