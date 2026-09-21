# Tareas Pendientes — Josesito (Josesito Home Assistant)

Documento de trabajo con el roadmap y las decisiones ya tomadas. Especificación técnica: `README.md`. Convenciones: español, commits convencionales. Estado actual (2026-09): **v3.4.0** con cerebro Groq (`qwen/qwen3.8-27b`), STT Whisper (`whisper-large-v3-turbo`), **router de intenciones por reglas** y **segundo plano con wake word JARVIS activa** (107 tests verdes).

> Marca con `[x]` lo que vaya quedando listo.

## Plan de sesiones (dosificación)

Cada sesión deja el proyecto en estado funcional y testeable.

| Sesión | Estado | Contenido |
|---|---|---|
| 1 | ✅ **Terminada** | Base del segundo plano: `app.py` + `modules/estados.py` (máquina pura), `modules/logging_setup.py` (rotatorio), `modules/single_instance.py` (lock), modo `--debug` de simulación, tests. **88 tests verdes.** |
| 2 | ✅ **Terminada** | Hotkeys (`modules/hotkeys.py` + `DetectorHotkeys` puro) + bandeja (`modules/tray.py`, `pystray` + `Pillow`) + `modules/cola.py` (eventos → un hilo) + menú opción 3 en `main.py`. Deps pineadas. **98 tests verdes.** |
| 3 | ✅ **Terminada** | Wake word **JARVIS**: `modules/wakeword.py` (`WakeWordDetector` + factoría con descarga automática de modelos ONNX desde GitHub Releases), `modules/audio_stream.py` (InputStream 16 kHz continuo), gating de eco (`Compartido.hablando`), `Evento.WAKE` → cola. Modelo preentrenado "hey jarvis". **107 tests verdes.** |
| 4 | ⏳ Siguiente | `modules/ear.py`: `grabar_hasta_silencio(stream)` reutilizable + `user_command.wav` a `tempfile` + la máquina graba desde el mismo `Capturador` (VAD) y transpone Whisper → `Evento.FIN_AUDIO`/`AUDIO_ABORTADO`. |
| 4 | | `modules/ear.py`: `grabar_hasta_silencio(stream)` reutilizable + `user_command.wav` a `tempfile` + test E2E del bucle con chunks simulados. |
| 5+ | | Chateo remoto (Telegram recomendado), `pc_actions`, memoria RAG, Home Assistant. |

---

## 1. Modo segundo plano (bandeja + hotkey + wake word)

Objetivo: que Josesito viva en segundo plano (sin consola), activable con **hotkey global** y con **wake word**. Decisión: **ambas activaciones están disponibles**. Windows primero; wake word y hotkey escritos de forma agnóstica para migrar a Linux/Mac después.

Arquitectura acordada: un único `sounddevice.InputStream` de 16 kHz siempre abierto, máquina de estados `IDLE → GRABANDO → TRANSCRIBIENDO → PENSANDO → HABLANDO → IDLE`, bandeja en el hilo principal (pystray) y workers para audio/control.

### Sesión 1 — Base (terminada)
- [x] `app.py`: entrypoint de segundo plano (`python app.py` / `pythonw app.py`, `--debug` = consola de simulación sin triggers).
- [x] `modules/estados.py`: `MaquinaEstados` pura + `Estado`/`Evento`/`TRANSICIONES`; transiciones inválidas se ignoran; manejadores inyectados por estado; fallo de un manejador → IDLE.
- [x] `modules/logging_setup.py`: `RotatingFileHandler` → `logs/josesito.log` (1 MB × 3 backups) + consola.
- [x] `modules/single_instance.py`: lock por archivo en temp (módulo Windows `msvcrt.LK_NBLCK` / POSIX `flock`); escribir el pid dispara `PermissionError` cuando otra instancia ya bloquea → rechazo.
- [x] `config.py`: `NOMBRE_INSTANCIA`, `LOG_DIR/LOG_ARCHIVO/LOG_NIVEL`.
- [x] Tests: `tests/test_estados.py` (9) + `tests/test_single_instance.py` (2). `logs/` y `*.lock` en `.gitignore`.

### Sesión 2 — Hotkeys + bandeja (terminada)
- [x] `modules/hotkeys.py`: `DetectorHotkeys` (lógica pura por nombres de tecla: PTT por mantención, toggle wake una vez por pulsación) + `Hotkeys` (conecta `pynput.keyboard.Listener`). Combos en `config.HOTKEY_PTT=['ctrl','f7']` y `HOTKEY_WAKE_TOGGLE=['ctrl','f8']`.
- [x] `modules/tray.py`: `Bandeja` con `pystray` + `Pillow` (icono generado en caliente, sin asset). Menú: Escuchar / Wake word / En pausa / Salir. Corre en el main thread (requisito Windows).
- [x] `modules/cola.py`: `ColaEventos` → un único hilo procesa los `Evento` contra la máquina (que no es thread-safe). Hotkeys y bandeja solo **encolan**.
- [x] `main.py`: agregada **opción 3 "Segundo plano"** (reutiliza `app.main([])`).
- [x] Dependencias pineadas: `pynput==1.8.2`, `pystray==0.19.5`, `Pillow==12.3.0`.
- [x] Tests: `tests/test_hotkeys.py` (6) + `tests/test_cola.py` (2) + `tests/test_tray.py` (2).

**Pendiente derivado**: arranque sin consola con `pythonw.exe` + autostart opcional (`shell:startup`) — quedó **libre**; se decide junto a la fase de empaquetado (PyInstaller) o tras la sesión 3.

### Sesión 3 — Wake word JARVIS (terminada)
- [x] `modules/wakeword.py`: `WakeWordDetector` (histéresis + retroceso de disparo + gating de eco vía `esta_hablando`), `_clave_prediccion` elige la etiqueta de jarvis, `crear_detector()` con **degradación elegante** (None si falta la dep o falla el modelo).
- [x] Descarga automática de modelos: openWakeWord **no empaqueta** los `.onnx`; `_asegurar_modelos()` los baja una sola vez de GitHub Releases v0.5.1 (`embedding_model.onnx`, `melspectrogram.onnx`, `hey_jarvis_v0.1.onnx`, ~3.7 MB). `Model(wakeword_models=["hey jarvis"], inference_framework="onnx")` — un `Model()` sin nombre carga TODO y falla.
- [x] `modules/audio_stream.py`: `Capturador` (InputStream 16 kHz, int16, bloques 1280 = 80 ms) con suscriptores y stream inyectable para tests.
- [x] `app.py`: micrófono continuo alimenta el detector solo si `Compartido.wake_activa`; `Evento.WAKE` → cola cuando dispara; `Compartido.hablando` se setea en los manejadores HABLANDO/IDLE (gating de eco); toggle unificado (Ctrl+F8 **y** bandeja) con `detector.reset()`.
- [x] `config.py`: `WAKE_WORD_MODELO/ARCHIVO/UMBRAL/HISTERESIS`, `STREAM_TASA/BLOQUE`. Deps pineadas: `openwakeword==0.6.0`, `onnxruntime==1.30.0` (trae `scikit-learn==1.9.1` como dependencia transitiva → la capa 2 ML del router vuelve a ser viable con regresión logística).
- [x] Tests: `tests/test_wakeword.py` (6) + `tests/test_audio_stream.py` (3).

**Ojo (medido 2026-09)**: en terreno, "hey jarvis" preentrenado puede disparar en falso o no oírte; calibrar `WAKE_WORD_UMBRAL` y, si falla, entrenar un **"jarvis" corto** (grabaciones reales + Piper + negativos ~1-3 h, ~840 KB ONNX) con las vías del doc de la sección 2.

### Sesión 4 — Audio para transcripción (pendiente)
- [ ] `modules/ear.py`: extraer `grabar_hasta_silencio(stream, ...)` reutilizable y mover `user_command.wav` a `tempfile.gettempdir()` (hoy escribe en cwd).
- [ ] Grabación desde el mismo `Capturador` de la sesión 3: cuando la máquina entra en GRABANDO se acumulan bloques con VAD (RMS), se corta con `FIN_AUDIO`/`AUDIO_ABORTADO` y se transcribe con Whisper (Groq) → `Evento.TEXTO_LISTO`.
- [ ] Test E2E con chunks simulados (sin mic real): `WAKE` → audio simulado → `FIN_AUDIO` → `TEXTO_LISTO`; gating mientras `hablando`.

**Nota**: esto elimina `msvcrt` del flujo de mic → resuelve de facto el pendiente de **AudioEar multiplataforma**.

---

## 2. Wake word "JARVIS"

Decisión: usar **JARVIS** como wake word. `openWakeWord` ya trae un modelo preentrenado "hey jarvis" (valida el pipeline sin entrenar). Si la frase corta "jarvis" funciona mejor (4 sílabas vs 6), se fine-tunea un modelo custom.

- [x] Validar el modelo preentrenado **"hey jarvis"** de `openWakeWord` (carga ONNX, predice, integrado al pipeline). **Pendiente de validación en terreno** (hablarle; ajustar falso positivo).
- [ ] Probar frase corta "jarvis" vs "hey jarvis" y elegir.
- [ ] Si hace falta, entrenar modelo custom (grabaciones reales + voces Piper + negativos; vías: `openwakeword.com` Training Center o entrenadores locales tipo `jota-wake-trainer` / `custom-wakeword-trainer`, ~840 KB ONNX).
- [ ] Ajustar `WAKE_WORD_UMBRAL` (bajo → deja de oír; alto → se dispara solo).
- [ ] (Opcional) Barge-in: interrumpir a Josesito diciendo la wake word mientras habla.

**Descartado**: Porcupine/Picovoice (terminó su tier gratuito el 2026-06-30).

---

## 3. Chateo remoto desde el celular (idea de Gabriel)

Objetivo: **chatear con Josesito desde el celular y que ejecute acciones en el PC de forma remota** (abrir apps, buscar, correr opencode, y más adelante domótica). Reusa el router + registry que ya existen: los comandos remotos pasan por la misma cascada (reglas → Brain) y ejecutan los handlers locales.

### Canal (pendiente de decidir)
- [ ] **Telegram bot** *(recomendado: gratis, push, muy simple, combina con Groq ya existente; ~1 día)*.
- [ ] **Web propia** (FastAPI) servida por el PC + túnel (`Tailscale` / Cloudflare Tunnel) — más control, más trabajo.
- [ ] WhatsApp: descartado por ahora (no oficial, frágil).

### Tolva de tareas del canal
- [ ] Servidor/cola de mensajes siempre corriendo (ideal: integrado al proceso de segundo plano de la sección 1).
- [ ] Autenticación (token o bot key); **nunca** exponer el endpoint sin auth.
- [ ] Mapeo mensaje → `router.decidir()` / `Brain` (reutilización directa).
- [ ] Confirmación remota para acciones peligrosas (ej. `ejecutar_opencode`) — patrón ya existente en `main.py` (`pedir_confirmacion_opencode`).
- [ ] Devolver el resultado/respuesta por el mismo canal (texto; opcional TTS).
- [ ] Registrar en `TAREAS_PENDIENTES` cualquier dato personal que se loguee (ideal: nada).
- [ ] Prueba en red local primero; luego túnel para uso remoto real.

### Decisión pendiente
- ¿Misma instancia que el segundo plano (un solo proceso escucha mic + telegram) o un proceso separado? *(ver sección 4 antes de decidir)*

---

## 4. Acciones sobre el PC (base de lo que Josesito puede ejecutar, local y remoto)

Viene del plan de "router/JEV para PC": catálogo declarativo de acciones de sistema. Es el pilar para que el chateo remoto sea útil.

- [ ] `modules/pc_actions.py`: catálogo de acciones → abrir apps/URLs, buscar en navegador, control de teclado/mouse (`pyautogui`) y control básico del sistema.
- [ ] `config.py`: `ACCIONES_PC` (catálogo), allowlist estricta.
- [ ] Confirmación previa a **cada** acción (patrón del `confirmador` de `OpenCodeRunner`).
- [ ] Resolución de slots ("busca lofi" → `query=lofi`) sin LLM cuando sea posible; si no, micro-llamada a Groq.
- [ ] **Seguridad remota**: desde el celular, solo un subconjunto de acciones marcadas como "seguras remotamente"; acciones destructivas solo con doble confirmación y allowlist.
- [ ] (Más adelante) Home Assistant: `modules/home_assistant.py` (REST + long-lived token) para domótica.

---

## 5. Mejoras colaterales (arrastradas de planes anteriores)

- [ ] **Memoria RAG persistente**: `modules/memory.py` con SQLite + FTS5 primero (BM25, sin ML); embeddings como fase 2.
- [ ] **Router, capa 2 ML honesta**: el coseno zero-shot quedó **descartado por medición** ("¿qué hora es?" 0.61 vs "si llueve" 0.29) y `model2vec` entrenado **requiere torch**. Siguiente intento: **regresión logística (scikit-learn, ya instalado como dependencia de openWakeWord) sobre los embeddings de potion** (28 clases E/U). Ya no hace falta instalar nada.
- [ ] **Empaquetado**: PyInstaller `--windowed --onedir` + icono + instalador (fase posterior al segundo plano).
- [ ] Autostart del segundo plano en el arranque de Windows (a confirmar: ¿siempre o bajo demanda?).

---

## Decisiones registradas

| Fecha | Decisión |
|---|---|
| 2026-09 | Wake word: **JARVIS** (`openWakeWord`; validar con "hey jarvis" preentrenado, fine-tune "jarvis" si hace falta). |
| 2026-09 | Activación: **wake word + hotkey global**, ambos disponibles; wake word descartable en runtime. |
| 2026-09 | Chateo remoto desde el celular: objetivo nuevo; canal **por decidir** (Telegram recomendado). |
| 2026-09 | Empaquetado `.exe`: más adelante; primero correr con `pythonw`. |
| 2026-09 | Windows primero, but wake word/hotkey agnósticos para Linux/Mac. |
| 2026-09 | Router: capa 1 (reglas) es la fiable y la única activa; capa 2 embeddings OFF por medición. |
| 2026-09 | Modelos Groq disponibles para esta cuenta: qwen/qwen3.8-27b (cerebro), gpt-oss-20b/120b, compound, whisper-large-v3(-turbo). No hay llama-3.*. |

## Descartado a propósito

- Porcupine (Picovoice): tier gratuito terminó el 2026-06-30.
- `model2vec[train]` / `StaticModelForClassification`: exige PyTorch; choca con "sin torch".
- Servicio de Windows: la aislamiento de Session 0 bloquea micrófono/parlantes; debe ser proceso de usuario + bandeja.
- Canal de WhatsApp para el chateo remoto: no oficial y frágil.