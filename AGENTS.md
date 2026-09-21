# AGENTS.md

Proyecto personal "Josesito" (asistente de voz/texto con briefings matutinos en español neutro, personalidad de locutor satírico de Melipilla). Docs, comentarios y commits en **español**. Especificación completa: `README.md`.

## Ejecución

- `python main.py` (necesita `.env` con `GROQ_API_KEY`; sin la key aborta al inicio).
- Muestra un menú interactivo: opción 1 = modo texto (multiplataforma), opción 2 = modo micrófono (**Windows-only**, usa `msvcrt` y `sounddevice`).
- Salir en modo texto: `exit` / `quit` / `salir`. En modo mic: `ESPACIO` graba, `ESC` apaga.
- **Tests**: `python -m pytest` (56 tests), todo mockeado sin red.
- **`requirements.txt` está pineado** (`groq==1.2.0`, `ddgs==9.14.4`, `edge-tts==7.2.8`, etc.) y sincronizado con lo real. **Google fue eliminado por completo** (`google-genai` y `websockets` ya no se usan ni se instalan).
- **No hay venv en el repo**: dependencias instaladas en el `python` del PATH.
- `main.py` importa `modules.*` como namespace package (sin `__init__.py`): ejecuta siempre desde la raíz del repo con `python main.py`, nunca por ruta absoluta/otro cwd.

## Arquitectura

- `main.py` = orquestador central con **inyección de dependencias**; `config.py` = constantes y allowlist `OPENCODE_PROYECTOS`; módulos en `modules/`.
- **Motor**: `modules/summarizer.py` → clase `Brain`. Usa **`qwen/qwen3.8-27b` en streaming** vía `groq` SDK (endpoint OpenAI-compatible, `chat.completions.create(..., stream=True)`) con **mensajes por turno**: system + pares user/assistant + mensaje actual como `messages`. Clima y noticias se **pre-obtienen en paralelo** y se inyectan como mensaje `user` con bloque `CONTEXTO DEL DÍA` justo antes del mensaje actual (el modelo NO llama `get_weather_data`/`get_news_data`). Si el modelo emite `tool_calls` (search/opencode), se resuelven en `ThreadPoolExecutor` y se re-alimenta el stream con mensajes `role:"tool"` (AFC manual, hasta `MAX_RONDAS_TOOLS=3`). Reintentos con backoff ante `429/5xx` (`_es_reintentable`, respeta header `retry-after`). `generate_response()` es síncrono y acepta `on_fragment=fn` para volcar el texto en vivo; el fallback si el redactado final falla es el resumen plano de las tools.
- **Config de generación**: `Brain._tools_openai(declaraciones)` envuelve cada `FunctionDeclaration` al formato OpenAI `{"type":"function","function":{...}}`; testeado offline en `test_brain.py`. La request lleva temperatura 0.7 y `max_tokens=MAX_TOKENS_SALIDA`. **Elstreaming de `gpt-oss-*` emite `delta.reasoning`** (razonamiento intermedio): el Brain solo consume `delta.content` y los `delta.tool_calls` (se fusionan por `index` y se parsean al final).
- **Tool registry** (`modules/tools/registry.py`): cada capacidad es una `Herramienta(nombre, descripcion, parametros_schema, handler, requerido)`. `construir_registro(weather=, news=, search=, opencode=)` arma el dict. `a_declaracion()` devuelve el **FunctionDeclaration plano** (`{name, description, parameters}`); el wrapper OpenAI `{"type":"function","function":...}` se aplica solo en `Brain._tools_openai`.
- **Contrato de respuestas** (`modules/contract.py`): envelope `{"status":"ok","data":...}` / `{"status":"error","mensaje":"..."}`. Los errores llegan al LLM como strings parseables, nunca excepciones. El detalle técnico va solo a consola.
- Herramientas expuestas (nombres estables, no renombrarlas sin actualizar el prompt):

| Herramienta | Handler | Params |
|---|---|---|
| `get_weather_data` | `WeatherProvider.get_weather()` | — |
| `get_news_data` | `NewsFetcher.get_top_news()` | — |
| `search_internet_data` | `WebSearcher.search_internet(query)` | `query` (req) |
| `ejecutar_opencode` | `OpenCodeRunner.ejecutar(proyecto=, peticion=)` | `proyecto` (enum allowlist) + `peticion` (req) |

- **Memoria**: pares user/model únicamente (nunca roles tool sueltos), recorte por turnos completos en `Brain._guardar_en_historial`. MAX_HISTORIAL_TURNOS=12.
- **Datos fijos** en `config.py`: coordenadas Melipilla, 13 RSS, allowlist opencode. (El vocabulario para transcripción que tenía Google ya no aplica: Whisper no soporta custom vocabulary.)
- **Noticias (`modules/news.py`)**: descarga las fuentes en paralelo (`NOTICIAS_WORKERS=6`, ThreadPoolExecutor), reintento simple ante `429/5xx`, dedup por título y mini-caché en memoria (`NOTICIAS_CACHE_TTL=120` s, por instancia). No re-introducir sleeps seriales entre requests.

## Gotchas

- **Modelos de esta cuenta Groq (trial gratis)**: `qwen/qwen3.8-27b`, `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `groq/compound(-mini)`, `whisper-large-v3(-turbo)`. **NO están** `llama-3.3-70b-versatile` ni `llama-3.1-8b-instant` → no reintroducir esos ids. Límites del plan gratis: ~30 RPM, ~1.000 req/día; ante `429` respetar `retry-after`. `qwen/qwen3.8-27b` es el cerebro por defecto (primer token < 1 s, tools OK, buen español); `gpt-oss-120b` es más capaz pero razona en `delta.reasoning` (más lento) y tiende a rechazar tareas sin tools → solo como respaldo manual cambiando `MODELO_LLM`.
- **`ejecutar_opencode`**: ejecuta `opencode run --dir <ruta> "<peticion>"` vía `subprocess`. Requiere callback de confirmación (`pedir_confirmacion_opencode` en `main.py`) — no quitar. `OpenCodeRunner` expone `.proyectos` (lo lee `construir_registro`). En Windows usa `CREATE_NO_WINDOW`; timeout 300 s; salida truncada a `OPENCODE_SALIDA_MAX`.
- **Audios temporales**: `voice.py` usa `tempfile` (`speech_<pid>.mp3`) y `ear.py` escribe `user_command.wav` en cwd; ambos se limpian en `finally`. Si quedan residuos tras un crash, bórralos (ya gitignored).
- **`voice.py`**: `pygame.mixer` se inicializa perezoso y tolerante a fallos; sin audio, responde solo texto.
- **`ear.py`**: ESC aborta la grabación; `record_audio()` devuelve `None` en aborto/sin voz. Transcripción con `whisper-large-v3-turbo` (Groq) vía `client.audio.transcriptions.create(file=(nombre, archivo, "audio/wav"), language="es", response_format="text")`; respuesta tipo `str`.
- **Tiempos medidos (migración Groq, 2026-09)**: brief con prefetch ~4-6 s total (cuello de botella: clima API + 13 RSS en paralelo); turno con búsqueda web ~17 s (domina `ddgs` + ronda final). `gpt-oss-120b` con tool calls llegaba a ~35 s por el reasoning.
- **No hay `__init__.py` en `modules/`** (namespace package por diseño).
- `.env` existe en el repo y está gitignored — no lo comitees ni lo expongas.
- Sin lint/typecheck configurados; estilo: PEP8 básico + ruff (no configurado).