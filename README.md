# Josesito Home Assistant

> 📌 **Roadmap y tareas pendientes**: [`TAREAS_PENDIENTES.md`](TAREAS_PENDIENTES.md) (segundo plano con wake word JARVIS + hotkey, chateo remoto desde el celular, acciones en el PC).

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
           ├──► modules/router.py        (RouterIntenciones - cascada local)
           ├──► modules/summarizer.py    (Brain - motor Groq streaming)
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
│   - Transcripción con Whisper (Groq)  │
│   (whisper-large-v3-turbo)            │
└───────────────┬───────────────────────┘
                │
                ▼
┌───────────────────────────────────────┐
│   RouterIntenciones (cascada local)   │
│   - Reglas ES (rechaza negación)      │
│   - Si no decide → delega al Brain    │
└───────────────┬───────────────────────┘
                │
                ▼
┌───────────────────────────────────────┐
│   Brain (Motor de IA)                 │
│   - Qwen 3.8 27B (Groq, streaming)    │
│   - Prefetch clima/noticias por turno │
│   - Tool calling vía registry (AFC)   │
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

#### Respuesta por turno (texto streaming)

Cada turno envía el historial (pares user/model) más el mensaje actual como `contents` en una llamada `generate_content_stream` (sin sesión persistente remota). Clima y noticias se **pre-buscan en paralelo** y se inyectan como bloque `CONTEXTO DEL DÍA` antes del mensaje del usuario: el modelo no gasta un round-trip en obtenerlos. Si decide llamar otra tool (búsqueda, opencode), el `Brain` resuelve el function call y re-alimenta el stream. La memoria client-side solo contiene pares user/model, recortada por turnos completos, sin mensajes `tool` huérfanos. El texto fluye al usuario apenas llega (`on_fragment`).

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
**Responsabilidad**: Conversación + orquestación de herramientas vía Groq (chat completions streaming).

- **Modelo**: `qwen/qwen3.8-27b` vía SDK `groq` (endpoint OpenAI-compatible); texto plano fluido, sin síntesis de audio previa
- **Prefetch**: clima y noticias se obtienen en paralelo al inicio del turno y entran como mensaje `CONTEXTO DEL DÍA` (el modelo NO llama `get_weather_data`/`get_news_data`)
- **Tool calling**: AFC manual con mensajes `role:"tool"` de re-alimentación (hasta `MAX_RONDAS_TOOLS=3`); tools se resuelven en `ThreadPoolExecutor`
- **Retries**: reintentos con backoff solo ante `429/5xx` (`_es_reintentable`), respetando `retry-after`
- **Fallback**: si el modelo no llega a redactar la respuesta final tras usar una tool, se devuelve un resumen legible de lo que la tool devolvió
- **Memoria**: pares user/model limitados a `MAX_HISTORIAL_TURNOS=12`, recorte por turnos completos
- **Streaming**: `generate_response(..., on_fragment=fn)` emite cada fragmento de texto apenas llega (latencia percibida ≈ primer token; Groq entrega el primer token en fracciones de segundo)
- **Config**: temperatura 0.7, máx 1024 tokens, sin markdown en la salida
- **Personalidad**: Josesito, presentador satírico, irónico y directo, originario de Melipilla, hablando en **español neutro** (sin modismos chilenos) para que el TTS lo lea naturalmente

**Interfaz**:
```python
Brain(api_key, registro) -> generate_response(user_command: str, on_fragment=None) -> str
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
- **Transcripción**: Groq Whisper `whisper-large-v3-turbo` (`client.audio.transcriptions.create(file=..., language="es", response_format="text")`)
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

### 8. **RouterIntenciones** (`modules/router.py`)
**Responsabilidad**: Resolver comandos triviales (clima, noticias, búsqueda, opencode) sin despertar al LLM, y delegar el resto al `Brain`.

- **Cascada**: reglas → embeddings (opcional) → `None` (delega al `Brain`)
- **Capa 1 (reglas)**: patrones en español sobre texto normalizado (NFKD sin tildes). Exige ausencia de negación (`no`, `nunca`, `ni`, …) para no invertir la intención; extrae `query` de "busca …" preservando tildes y `proyecto`/`peticion` de "opencode …" contra el enum del registry
- **Slots**: si falta el slot (p. ej. "busca" sin nada), devuelve `None` y decide el LLM
- **Capa 2 (embeddings)**: similitud coseno sobre `descripcion` + `frases` del registry con `model2vec` estático multilingüe. **Desactivada por defecto** (`ROUTER_EMBEDDINGS_ACTIVO = False`): la calibración 2026-09 mostró que el coseno zero-shot no separa (ruido "¿qué hora es?" 0.61 vs "si llueve" 0.29) y el clasificador entrenado de `model2vec` exige PyTorch
- **Respuesta**: `ejecutar()` corre el handler y devuelve **texto fijo** determinista (clima, titulares, búsqueda, salida de opencode), sin narración del LLM
- **Interruptor**: `ROUTER_ACTIVO = False` restaura el comportamiento previo (todo al LLM)

**Interfaz**:
```python
RouterIntenciones(registro, encoder=None, ...) -> decidir(texto: str) -> Decision | None
RouterIntenciones(...) -> ejecutar(decision: Decision) -> str
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

### Opción 3: **Segundo plano** (app.py)
- Bandeja de sistema (`pystray`) + hotkeys globales: **Ctrl+F7** push-to-talk, **Ctrl+F8** activate/deactivate wake word
- **Wake word JARVIS** (openWakeWord, ONNX local): di "hey jarvis" para hablar. Modelos descargados automáticamente al primer uso (~3.7 MB); umbral ajustable en `config.py`
- Máquina de estados `IDLE → GRABANDO → TRANSCRIBIENDO → PENSANDO → HABLANDO → IDLE` procesada por un único hilo (`modules/cola.py`); hotkeys, bandeja y wake word solo encolan eventos
- Instancia única, logging rotatorio a `logs/josesito.log`, arranque sin consola compatible con `pythonw.exe`
- `python app.py --debug` simula la máquina de estados por consola
- **Grabación por VAD reutilizable** (`modules/recorder.py`): al decir "hey jarvis" o mantener Ctrl+F7, el mismo micrófono de la wake word acumula audio y corta por silencio; la transcripción Whisper corre en un hilo y encola el texto (hasta el estado PENSANDO; la conversación Brain→TTS es la sesión 5, ver `TAREAS_PENDIENTES.md`)

---

## 🛠️ Stack Tecnológico

### Dependencias (`requirements.txt`, pineadas con `==`)
```
groq==1.2.0               # LLM streaming + transcripción Whisper (GPT / Groq)
requests               # HTTP para APIs y RSS
feedparser             # Parsing de feeds RSS
ddgs                   # Búsqueda web DuckDuckGo
edge-tts               # Síntesis de voz neural
pygame                 # Reproducción de audio
sounddevice            # Captura de audio desde micrófono
numpy                  # Procesamiento de señales (RMS)
scipy                  # Escritura de archivos WAV
python-dotenv          # Variables de entorno
pytest                 # Tests
model2vec              # Router, capa 2 de embeddings estáticos (opcional, desactivada por defecto)
pynput==1.8.2          # Hotkeys globales del segundo plano
pystray==0.19.5        # Bandeja de sistema del segundo plano
Pillow==12.3.0         # Icono de la bandeja
openwakeword==0.6.0    # Wake word JARVIS (modelos ONNX descargados al primer uso)
onnxruntime==1.30.0    # Motor ONNX de openWakeWord
```

### APIs Externas
1. **Groq (consola gratuita, sin tarjeta)** — LLM y transcripción
   - Modelos: `qwen/qwen3.8-27b` (LLM) y `whisper-large-v3-turbo` (STT); endpoint OpenAI-compatible
   - API Key: variable de entorno `GROQ_API_KEY` (formato `gsk_…`)
   - Límites plan gratis: ~30 RPM, ~1.000 req/día; ante `429` se respeta `retry-after`
2. **Open-Meteo API** (clima, sin auth)
3. **Edge-TTS** (voz, sin key)
4. **DuckDuckGo** (búsqueda, sin key)
5. **opencode CLI** (local) para `ejecutar_opencode`

---

## 🚀 Instalación y Configuración

### Prerrequisitos
- Python 3.8+
- Windows 10/11 (modo micrófono)
- API Key de Groq (console.groq.com/keys, plan gratuito)
- `opencode` en el PATH (solo para la tool `ejecutar_opencode`)

### Pasos

```bash
# 1. Crear entorno virtual
python -m venv venv
venv\Scripts\activate  # Windows (source venv/bin/activate en Linux/Mac)

# 2. Instalar dependencias (pinneadas)
pip install -r requirements.txt

# 3. Crear el .env con tu clave de Groq
# (console.groq.com/keys -> Create API Key)
echo GROQ_API_KEY=tu_clave_aqui > .env

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
GROQ_API_KEY=tu_clave_de_groq
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

- **119 tests** en `tests/` (`test_weather.py`, `test_news.py`, `test_search.py`, `test_tools_registry.py`, `test_brain.py`, `test_opencode_tool.py`, `test_router.py`, `test_estados.py`, `test_single_instance.py`, `test_hotkeys.py`, `test_cola.py`, `test_tray.py`, `test_wakeword.py`, `test_audio_stream.py`, `test_recorder.py`, `test_flujo_audio.py`).
- Cubren: mapeo WMO, filtro de 24 h y caps de noticias, dedup de búsqueda, formato de tools OpenAIA/Groq (`Brain._tools_openai`), formateo del contexto prefetch, recorte de memoria por pares, dispatch de herramientas, el ciclo de `OpenCodeRunner` (confirmación, timeout, truncado) y el router (reglas, negación, extracción de slots, umbral de embeddings con encoder falso, formato de respuestas). Más el segundo plano: máquina de estados, cola, hotkeys, bandeja, wake word, capturador y grabación VAD (corte por silencio/tope/PTT, WAV en temp) con flujos E2E de `WAKE→transcripción` — todo mockeado, sin red ni descarga de modelos.
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
1. **Texto streaming por turno en Groq**: la Live API de Google tardaba ~50 s en emitir su primer token y sufría `503` frecuentes; pasar el cerebro a **Groq** (hardware LPU) con `qwen/qwen3.8-27b` en streaming entrega el primer token en < 1 s (turno completo con prefetch ~4-6 s).
2. **Prefetch de clima/noticias en paralelo**: elimina el round-trip de tools más caro y hace el turno de una sola llamada al modelo en el caso común.
3. **Registry declarativo** sobre dispatch manual: añadir una tool = una `Herramienta`, sin tocar `Brain`
4. **Envelope `{status, data|mensaje}`** como contrato único: el LLM siempre recibe datos o un mensaje parseable
5. **Recorte por pares** resolvió el bug del trim impreciso (tool calls huérfanas)
6. **Edge-TTS + pygame lazy**: gratuito y sin dependencia de audio si se corre headless
7. **opencode con confirmación + allowlist**: la única tool con efectos sobre el sistema de archivos
8. **Retries 429/5xx + fallback de tools**: resiliencia ante rate-limit y picos del API sin degradar la conversación a silencios
9. **Migración completa a Groq (2026-09)**: se eliminó `google-genai` y `websockets`; el cerebro usa `chat.completions` streaming y el STT usa Whisper de Groq. Los modelos `llama-3.*` no existen en esta cuenta gratis: el cerebro es `qwen/qwen3.8-27b`.
10. **Router local antes del LLM (2026-09)**: los comandos triviales se resuelven con una cascada local barata (reglas en español) y respuestas fijas, sin round-trip al modelo. La capa de embeddings quedó **desactivada** tras medirla: con `potion-multilingual-128M` el coseno zero-shot no discrimina y el clasificador entrenado de `model2vec` requiere PyTorch. La vía preferida si se quiere ML local es un clasificador liviano (p. ej. regresión logística sobre los embeddings con scikit-learn) o un modelo System One open.

### Limitaciones Conocidas
- Modo micrófono solo en Windows (`msvcrt`)
- Router sin capa ML activa: los parafraseos que no casan con una regla caen al LLM (la capa de embeddings está desactivada por precisión)
- Memoria no persiste entre sesiones
- Sin interfaz gráfica
- `ejecutar_opencode` depende de que el CLI `opencode` esté autenticado en el equipo

---

## 🔗 Referencias

- [Groq console y docs](https://console.groq.com)
- [Edge-TTS](https://github.com/rany2/edge-tts)
- [Open-Meteo API](https://open-meteo.com/en/docs)
- [ddgs (DuckDuckGo Search)](https://github.com/fourleif/ddgs)

---

**Última actualización**: Septiembre 2026
**Versión**: 3.5.0 (segundo plano: wake word JARVIS + transcripción de voz por VAD sobre la máquina de estados + hotkeys + bandeja)