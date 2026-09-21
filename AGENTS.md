# AGENTS.md

Proyecto personal "Josesito" (asistente de voz/texto con briefings matutinos en español neutro, personalidad de locutor satírico de Melipilla). Docs, comentarios y commits en **español**. Especificación completa: `README.md`.

## Ejecución

- `python main.py` (necesita `.env` con `GOOGLE_API_KEY`; sin la key aborta al inicio).
- Muestra un menú interactivo: opción 1 = modo texto (multiplataforma), opción 2 = modo micrófono (**Windows-only**, usa `msvcrt` y `sounddevice`).
- Salir en modo texto: `exit` / `quit` / `salir`. En modo mic: `ESPACIO` graba, `ESC` apaga.
- **Tests**: `python -m pytest` (53 tests), todo mockeado sin red.
- **`requirements.txt` está pineado** (`google-genai==2.24.0`, `ddgs==9.14.4`, `edge-tts==7.2.8`, etc.) y sincronizado con lo real — NO usar Groq (eliminado).
- **No hay venv en el repo**: dependencias instaladas en el `python` del PATH.
- `main.py` importa `modules.*` como namespace package (sin `__init__.py`): ejecuta siempre desde la raíz del repo con `python main.py`, nunca por ruta absoluta/otro cwd.

## Arquitectura

- `main.py` = orquestador central con **inyección de dependencias**; `config.py` = constantes y allowlist `OPENCODE_PROYECTOS`; módulos en `modules/`.
- **Motor**: `modules/summarizer.py` → clase `Brain`. Usa **Gemini Live API** (`gemini-3.1-flash-live-preview`) con **sesión por turno**: `send_client_content(turns=semilla, turn_complete=True)` + `history_config.initial_history_in_client_content=True`; los function calls se responden con `send_tool_response(FunctionResponse(name, id, response={"result": ...}))`. `generate_response()` es síncrono por fuera (`asyncio.run`).
- **Modo de salida**: el modelo rechaza `response_modalities=["TEXT"]` (error 1007). Usa `["AUDIO"]` + `output_audio_transcription`; el texto se lee de `server_content.output_transcription` (objeto `Transcription`, usar `.text`), concatenando los chunks del turno.
- **Tool registry** (`modules/tools/registry.py`): cada capacidad es una `Herramienta(nombre, descripcion, parametros_schema, handler, requerido)`. `construir_registro(weather=, news=, search=, opencode=)` arma el dict. `a_declaracion()` devuelve el **FunctionDeclaration plano** (`{name, description, parameters}`) — NO el wrapper `{"type":"function","function":...}` de la REST API; ese wrapper rompe la validación del `LiveConnectConfig`.
- **Contrato de respuestas** (`modules/contract.py`): envelope `{"status":"ok","data":...}` / `{"status":"error","mensaje":"..."}`. Los errores llegan al LLM como strings parseables, nunca excepciones. El detalle técnico va solo a consola.
- Herramientas expuestas (nombres estables, no renombrarlas sin actualizar el prompt):

| Herramienta | Handler | Params |
|---|---|---|
| `get_weather_data` | `WeatherProvider.get_weather()` | — |
| `get_news_data` | `NewsFetcher.get_top_news()` | — |
| `search_internet_data` | `WebSearcher.search_internet(query)` | `query` (req) |
| `ejecutar_opencode` | `OpenCodeRunner.ejecutar(proyecto=, peticion=)` | `proyecto` (enum allowlist) + `peticion` (req) |

- **Memoria**: pares user/model únicamente (nunca roles tool sueltos), recorte por turnos completos en `Brain._guardar_en_historial`. MAX_HISTORIAL_TURNOS=12.
- **Datos fijos** en `config.py`: coordenadas Melipilla, 13 RSS, vocabulario para transcripción, allowlist opencode.
- **Noticias (`modules/news.py`)**: descarga las fuentes en paralelo (`NOTICIAS_WORKERS=6`, ThreadPoolExecutor), reintento simple ante `429/5xx`, dedup por título y mini-caché en memoria (`NOTICIAS_CACHE_TTL=120` s, por instancia). No re-introducir sleeps seriales entre requests.

## Gotchas

- **`ejecutar_opencode`**: ejecuta `opencode run --dir <ruta> "<peticion>"` vía `subprocess`. Requiere callback de confirmación (`pedir_confirmacion_opencode` en `main.py`) — no quitar. `OpenCodeRunner` expone `.proyectos` (lo lee `construir_registro`). En Windows usa `CREATE_NO_WINDOW`; timeout 300 s; salida truncada a `OPENCODE_SALIDA_MAX`.
- **Audios temporales**: `voice.py` usa `tempfile` (`speech_<pid>.mp3`) y `ear.py` escribe `user_command.wav` en cwd; ambos se limpian en `finally`. Si quedan residuos tras un crash, bórralos (ya gitignored).
- **`voice.py`**: `pygame.mixer` se inicializa perezoso y tolerante a fallos; sin audio, responde solo texto.
- **`ear.py`**: ESC aborta la grabación; `record_audio()` devuelve `None` en aborto/sin voz. Transcripción con `gemini-3.5-transcribe` + `AudioTranscriptionConfig`.
- **`key AQ.*`**: la `GOOGLE_API_KEY` actual del `.env` tiene formato `AQ.…` (anómalo vs `AIza…`). Si la Live API la rechaza, regenerar clave en AI Studio.
- **No hay `__init__.py` en `modules/`** (namespace package por diseño).
- `.env` existe en el repo y está gitignored — no lo comitees ni lo expongas.
- Sin lint/typecheck configurados; estilo: PEP8 básico + ruff (no configurado).