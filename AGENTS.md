# AGENTS.md

Proyecto personal "Josesito" (asistente de voz/texto con briefings matutinos en español chileno). Docs, comentarios y commits en **español**. Especificación completa: `README.md`.

## Ejecución

- `python main.py` (necesita `.env` con `GROQ_API_KEY`; sin la key aborta al inicio).
- Muestra un menú interactivo: opción 1 = modo texto (multiplataforma), opción 2 = modo micrófono (**Windows-only**, usa `msvcrt` y `sounddevice`).
- Salir en modo texto: `exit` / `quit` / `salir`. En modo mic: `ESPACIO` graba, `ESC` apaga.
- **`requirements.txt` ya está sincronizado** con las dependencias reales (`groq`, `requests`, `feedparser`, `ddgs`, `edge-tts`, `pygame`, `sounddevice`, `numpy`, `scipy`, `python-dotenv`) — `google-genai` fue eliminado (nunca se usó).
- **No hay venv en el repo**: las dependencias ya están instaladas en el `python` del PATH.
- `main.py` importa `modules.*` como namespace package (sin `__init__.py`): ejecuta siempre desde la raíz del repo con `python main.py`, nunca por ruta absoluta/otro cwd.

## Arquitectura

- `main.py` = orquestador central; `modules/` = 6 clases independientes (clima, noticias, búsqueda, IA, voz, micrófono).
- `modules/summarizer.py` es el núcleo: usa **function calling de Groq** — el LLM decide qué herramienta llamar. Las 3 herramientas expuestas (`get_weather_data`, `get_news_data`, `search_internet_data`) y sus contratos están acoplados con los módulos:

| Herramienta | Módulo | Retorno |
|---|---|---|
| `get_weather_data` | `weather.get_weather()` | `dict` con `max`, `min`, `current`, `feels_like`, `rain_prob`, `condition` |
| `get_news_data` | `news.get_top_news()` | `list[dict]` ({`title`, `description`, `category`}) |
| `search_internet_data` | `search.search_internet(query)` | `str` con bloque de resultados |

- Errores de módulos se devuelven como strings dentro del JSON que recibe el LLM (no se lanzan). Mantén los nombres/formatos de salida estables al modificar módulos.
- Memoria en sesión (sliding window, 12 turnos). El recorte en `summarizer.py` asume 1 user+1 assistant por turno: con tool calls el historial crece más, así que el trim puede quedar impreciso.
- Datos fijos: coordenadas de Melipilla hardcodeadas en `main.py`; 14 fuentes RSS hardcodeadas.

## Gotchas

- Archivos temporales en cwd: `speech_output.mp3` (voz) y `user_command.wav` (mic). Se auto-limpian; en crashes pueden quedar residuos. **No están gitignored** — si aparecen en `git status`, bórralos.
- `git` muy desincronizado vs el commit `4987aa3` ("feat: implement AI briefing"): 5 archivos sin trackear (`modules/ear.py`, `modules/search.py`, `modules/voice.py`, `README.md`, `AGENTS.md`) y 7 modificados (`main.py`, `modules/news.py`, `modules/summarizer.py`, `modules/weather.py`, `requirements.txt`, `.gitignore`, `LICENSE`). El historial NO contiene modo micrófono ni buscador; no hagas `git checkout`/`git stash` esperando recuperar estado funcional.
- `.env` existe en el repo y está gitignored — no lo comitees ni lo expongas.
- Sin tests, sin lint/typecheck configurados. Verificación manual: ejecutar modo texto y preguntar clima/noticias/búsqueda.