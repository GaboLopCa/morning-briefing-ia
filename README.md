# Josesito Home Assistant

## 📋 Visión del Proyecto

**Josesito Home Assistant** es un asistente personal inteligente de voz y texto, diseñado como un "briefing matutino" personalizado para Gabriel, estudiante de ingeniería de software. El sistema combina múltiples fuentes de información en tiempo real (clima, noticias, búsqueda web) con una personalidad única de presentador de radio chileno, satírico y directo, originario de Melipilla.

### Objetivo Principal
Proporcionar un resumen diario personalizado y conversacional de información relevante, permitiendo interacción por voz o texto, con capacidades de búsqueda en tiempo real y memoria contextual.

---

## 🏗️ Arquitectura del Sistema

### Patrón de Diseño: **Orquestación Modular con Pipeline Central**

El sistema sigue una arquitectura de **microservicios locales** donde un orquestador central (`main.py`) coordina módulos especializados independientes.

```
┌─────────────────────────────────────────────────────────────┐
│                    main.py (Orquestador)                     │
│  - Menú de selección de entrada (Texto/Micrófono)            │
│  - Ciclo de vida de la aplicación                            │
│  - Coordinación de módulos                                   │
└──────────┬──────────────────────────────────────────────────┘
           │
           ├──► modules/weather.py      (WeatherProvider)
           ├──► modules/news.py          (NewsFetcher)
           ├──► modules/search.py        (WebSearcher)
           ├──► modules/summarizer.py    (NewsSummarizer)
           ├──► modules/voice.py         (VoiceAssistant)
           └──► modules/ear.py           (AudioEar)
```

### Flujo de Datos

```
ENTRADA (Texto/Mic)
        │
        ▼
┌───────────────────────────────────────┐
│   AudioEar (si es voz)                │
│   - Grabación con VAD (RMS)           │
│   - Transcripción con Whisper         │
└───────────────┬───────────────────────┘
                │
                ▼
┌───────────────────────────────────────┐
│   NewsSummarizer (Motor de IA)        │
│   - Procesamiento con Llama 3.3 70B   │
│   - Function Calling (Groq)           │
│   - Memoria conversacional (12 turnos)│
└───────────────┬───────────────────────┘
                │
        ┌───────┴────────┐
        │                │
        ▼                ▼
   [Tools]          [Chitchat]
        │                │
        ▼                ▼
┌──────────────┐  ┌──────────────┐
│ WeatherProv  │  │ Respuesta    │
│ NewsFetcher  │  │ directa      │
│ WebSearcher  │  └──────┬───────┘
└──────┬──────┘         │
       │                │
       └────────┬───────┘
                ▼
       ┌────────────────┐
       │ VoiceAssistant │
       │ - Edge-TTS     │
       │ - Síntesis voz │
       └────────────────┘
```

---

## 🧩 Módulos del Sistema

### 1. **WeatherProvider** (`modules/weather.py`)
**Responsabilidad**: Obtención de datos meteorológicos en tiempo real.

**Características**:
- API: Open-Meteo (sin autenticación requerida)
- Ubicación: Melipilla, Chile (-33.6895, -71.2146), coordenadas hardcodeadas en `main.py`
- Datos proporcionados:
  - Temperatura actual y sensación térmica
  - Máxima y mínima del día
  - Probabilidad de precipitación
  - Condición del cielo (despejado, parcialmente nublado, nublado, lluvia) mapeada desde `weather_code`

**Interfaz**:
```python
get_weather() -> dict
# Retorna: {'max': float, 'min': float, 'current': float, 'feels_like': float, 'rain_prob': int, 'condition': str}
```

---

### 2. **NewsFetcher** (`modules/news.py`)
**Responsabilidad**: Agregación de noticias desde múltiples fuentes RSS chilenas y latinoamericanas.

**Características**:
- 14 fuentes RSS configuradas en `main.py` (Biobío, La Tercera, El Mostrador, Cooperativa, ADN, BBC Mundo, Xataka, etc.)
- Filtrado de noticias de las últimas 24 horas
- Límite de 8 noticias por fuente para optimizar tokens
- Descripciones truncadas a 200 caracteres
- Pausas de 0.5s entre requests y timeout de 10s por fuente (evita error 10054)
- User-Agent de navegador para evitar bloqueos

**Interfaz**:
```python
get_top_news() -> list[dict]
# Retorna: [{'title': str, 'description': str, 'category': str}]
```

---

### 3. **WebSearcher** (`modules/search.py`)
**Responsabilidad**: Búsqueda en internet en tiempo real para información actualizada.

**Características**:
- Motor: DuckDuckGo (vía librería `ddgs`)
- Región: Chile (`region="cl-es"`)
- Sin API keys requeridas
- Máximo 4 resultados por búsqueda
- Formato estructurado en texto plano para facilitar su lectura por la IA

**Interfaz**:
```python
search_internet(query: str, max_results: int = 4) -> str
# Retorna: bloque de texto con títulos y fragmentos, o string de error
```

---

### 4. **NewsSummarizer** (`modules/summarizer.py`)
**Responsabilidad**: Motor cognitivo central con IA conversacional.

**Características**:
- **Modelo**: Llama 3.3 70B Versatile (vía Groq API)
- **Function Calling**: El LLM decide qué herramientas invocar (`tool_choice="auto"`)
- **Herramientas disponibles**:
  1. `get_weather_data()` - Clima actual
  2. `get_news_data()` - Noticias RSS
  3. `search_internet_data(query)` - Búsqueda web
- **Memoria**: Sliding window de 12 turnos
- **Personalidad**: Josesito, presentador satírico chileno
- **Restricciones de salida**: 100% español, sin markdown ni formato especial (para que el TTS lo lea naturalmente)
- **Errores de módulos**: se devuelven como strings dentro del JSON que recibe el LLM (no se lanzan excepciones)

**Interfaz**:
```python
generate_response(weather_provider, news_fetcher, search_provider, user_command) -> str
```

---

### 5. **VoiceAssistant** (`modules/voice.py`)
**Responsabilidad**: Síntesis de voz y reproducción de respuestas.

**Características**:
- Motor: Edge-TTS (Microsoft Neural TTS)
- Voz: `es-CL-LorenzoNeural` (español chileno masculino)
- Velocidad configurable (default: 1.2x)
- Limpieza de texto (URLs, asteriscos, hashtags) antes de sintetizar
- Reproducción con pygame mixer
- Archivo temporal `speech_output.mp3` eliminado tras la reproducción

**Interfaz**:
```python
speak(text: str) -> None
```

---

### 6. **AudioEar** (`modules/ear.py`)
**Responsabilidad**: Captura de audio, procesamiento de voz y transcripción.

**Características**:
- **VAD (Voice Activity Detection)**: Casero basado en RMS
- **Grabación**: Stream continuo con detección automática de silencio
- **Calibración dinámica**: Ajusta umbral según ruido ambiental (factor de seguridad x1.5, mínimo 0.005)
- **Transcripción**: Whisper Large V3 (vía Groq API)
- **Parámetros configurables**:
  - `threshold`: 0.02 inicial (ajustado en calibración)
  - `silence_limit`: 1.5 segundos
  - `chunk_size`: 1024 muestras
  - `sample_rate`: 16000 Hz
- Archivo temporal `user_command.wav` eliminado tras la transcripción

**Interfaz**:
```python
record_audio() -> str  # Retorna path del archivo WAV
transcribe_audio(file_path: str) -> str
calibrate_ambient_noise(duration: float = 2.0) -> None
```

---

## 🔄 Modos de Operación

Al iniciar, `main.py` muestra un menú interactivo (`seleccionar_modo_interfaz()`) para elegir la entrada. No existe una constante de configuración; la selección se hace en cada ejecución.

### Opción 1: **Modo Texto**
- Entrada por consola con prompt `Gabriel >>>`
- Comandos de salida: `exit`, `quit`, `salir`
- Ideal para entornos silenciosos (clases, oficinas)
- Multiplataforma (no requiere `msvcrt`)

### Opción 2: **Modo Micrófono**
- Entrada por voz con detección automática de actividad (VAD por RMS)
- Calibración inicial de ruido ambiental (2 segundos)
- Controles:
  - **ESPACIO**: Iniciar grabación
  - **ESC**: Apagar sistema
- **Solo Windows**: usa el teclado nativo `msvcrt`
- Una vez transcrito el audio, el pipeline de procesamiento es idéntico al modo texto

---

## 🛠️ Stack Tecnológico

### Lenguaje
- **Python 3.8+**

### Dependencias Principales (`requirements.txt`)
```
groq                # API de Llama (LLM) y Whisper (STT)
requests            # HTTP requests para APIs y RSS
feedparser          # Parsing de feeds RSS
ddgs                # Búsqueda web DuckDuckGo
edge-tts            # Síntesis de voz neural
pygame              # Reproducción de audio
sounddevice         # Captura de audio desde micrófono
numpy               # Procesamiento de señales (RMS)
scipy               # Escritura de archivos WAV
python-dotenv       # Gestión de variables de entorno
```

### APIs Externas
1. **Groq API** (IA y transcripción)
   - Modelo LLM: `llama-3.3-70b-versatile`
   - Modelo STT: `whisper-large-v3`
   - API Key: Variable de entorno `GROQ_API_KEY`

2. **Open-Meteo API** (Clima)
   - Sin autenticación
   - Endpoint: `https://api.open-meteo.com/v1/forecast`

3. **Edge-TTS** (Voz)
   - Servicio gratuito de Microsoft
   - Sin API key requerida

4. **DuckDuckGo** (Búsqueda)
   - Sin API key requerida
   - Región: Chile (`cl-es`)

---

## 📊 Estado de Desarrollo

### Funcionalidades Implementadas ✅

- [x] **Arquitectura modular completa** con 6 módulos especializados
- [x] **Dual mode de entrada**: Texto y Micrófono con VAD
- [x] **Motor de IA conversacional** con Llama 3.3 70B
- [x] **Function Calling** para herramientas externas
- [x] **Memoria contextual** con sliding window (12 turnos)
- [x] **Personalidad definida** (Josesito, presentador chileno)
- [x] **Agregación de noticias** desde 14 fuentes RSS chilenas
- [x] **Búsqueda web en tiempo real** con DuckDuckGo
- [x] **Síntesis de voz** en español chileno (Edge-TTS)
- [x] **Transcripción de voz** con Whisper Large V3
- [x] **Calibración dinámica** de ruido ambiental
- [x] **VAD casero** basado en RMS
- [x] **Manejo de errores** robusto en todos los módulos
- [x] **Variables de entorno** para configuración segura

### Roadmap / En Desarrollo 🚧

- [ ] **Persistencia de memoria** (actualmente solo en sesión)
- [ ] **Historial de conversaciones** en base de datos
- [ ] **Configuración de ubicación** dinámica (no hardcodeada)
- [ ] **Soporte multi-usuario** (perfiles personalizados)
- [ ] **Integración con calendarios** (Google Calendar, Outlook)
- [ ] **Recordatorios y alarmas** inteligentes
- [ ] **Control de dispositivos smart home**
- [ ] **API REST** para integración con otras aplicaciones
- [ ] **Dockerización** del proyecto
- [ ] **Tests unitarios** y de integración
- [ ] **Logs estructurados** para debugging
- [ ] **Métricas y analytics** de uso

### Bugs Conocidos 🐛

- Dependencia de `msvcrt` limita el modo micrófono a Windows
- Archivos temporales de audio (`speech_output.mp3`, `user_command.wav`) pueden dejar residuos si hay crashes (no están gitignored)

---

## 🚀 Instalación y Configuración

### Prerrequisitos
- Python 3.8 o superior
- Windows 10/11 (para modo micrófono con `msvcrt`)
- Micrófono (opcional, para modo voz)
- API Key de Groq (https://console.groq.com/)

### Pasos de Instalación

```bash
# 1. Clonar el repositorio
git clone <repository-url>
cd morning-briefing-ia

# 2. Crear entorno virtual
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
# Crear archivo .env en la raíz del proyecto
echo GROQ_API_KEY=tu_clave_aqui > .env

# 5. Ejecutar el asistente
python main.py
```

> Nota: `main.py` importa los módulos como namespace package (no hay `__init__.py`); ejecuta siempre desde la raíz del proyecto.

### Configuración de `.env`
```env
GROQ_API_KEY=tu_clave_de_groq_aqui
```

---

## 🎯 Casos de Uso

### 1. Briefing Matutino
```
Usuario: "Buenos días Josesito, ¿qué hay para hoy?"
Josesito: [Proporciona clima, noticias destacadas y eventos relevantes]
```

### 2. Consulta de Clima
```
Usuario: "¿Cómo está el clima en Melipilla?"
Josesito: "En Melipilla hay 18 grados, se siente como 16, cielo despejado.
           Máxima de 22, mínima de 14, sin probabilidad de lluvia."
```

### 3. Noticias Deportivas
```
Usuario: "¿Qué pasó con la U ayer?"
Josesito: [Busca noticias recientes y proporciona resumen satírico]
```

### 4. Búsqueda en Tiempo Real
```
Usuario: "¿Cuándo es el próximo partido de la Roja?"
Josesito: [Busca en internet y proporciona información actualizada]
```

---

## 🧪 Testing

### Pruebas Manuales Recomendadas

1. **Modo Texto (opción 1)**:
   - Saludos casuales ("Hola", "¿Cómo estás?")
   - Consulta de clima
   - Solicitud de noticias
   - Búsqueda web ("¿Noticias de F1?")
   - Chitchat con memoria ("¿Recuerdas mi nombre?")

2. **Modo Micrófono (opción 2, Windows)**:
   - Calibración de ruido ambiental
   - Activación por voz (VAD)
   - Transcripción precisa
   - Detección de silencio
   - Comandos por teclado (ESPACIO, ESC)

3. **Casos Edge**:
   - Sin conexión a internet
   - API Key inválida
   - Micrófono no disponible
   - Respuestas largas (memoria)

---

## 📈 Métricas de Performance

### Optimizaciones Implementadas
- **Límite de noticias**: 8 por fuente para controlar tokens
- **Pausas entre requests**: 0.5s y timeout 10s para evitar rate limits / error 10054
- **Sliding window**: Memoria limitada a 12 turnos
- **Filtrado temporal**: Solo noticias de últimas 24h
- **Truncado de descripciones**: 200 caracteres por noticia
- **Limpieza de texto**: Reduce tokens en síntesis de voz
- **Temperatura LLM**: 0.6 en primera llamada, 0.7 en la segunda (balance creatividad/coherencia)

### Costos (Groq)
- **Pago por uso**: tarifas vigentes en https://console.groq.com/pricing
- **Uso personal típico**: del orden de $5-15 USD al mes con uso moderado

---

## 🔒 Seguridad

- API Key almacenada en variables de entorno (no en código)
- No se almacenan datos sensibles en disco
- Transcripciones de audio se eliminan después de procesamiento
- Archivos temporales de voz se limpian automáticamente
- Sin envío de datos a servicios no autorizados

---

## 👤 Perfil de Usuario

**Nombre**: Gabriel
**Rol**: Estudiante de Ingeniería de Software
**Intereses**:
- Tecnología y programación
- Deportes (Universidad de Chile, F1, NBA)
- Videojuegos
- Modismos chilenos

**Ubicación**: Melipilla, Chile

---

## 📝 Notas de Desarrollo

### Decisiones de Diseño

1. **Groq sobre OpenAI**: Mayor velocidad de inferencia y menor costo
2. **Edge-TTS sobre otras soluciones**: Gratuito, voz natural en español chileno
3. **VAD casero sobre librerías externas**: Sin dependencias adicionales, suficiente para uso personal
4. **RSS sobre APIs de noticias**: Sin límites de rate, fuentes curadas localmente
5. **DuckDuckGo sobre Google**: Sin API key, respeto a privacidad
6. **Memoria en memoria**: Simplicidad sobre persistencia (fase actual)
7. **Errores como datos**: Los módulos devuelven strings de error dentro del JSON al LLM (no excepciones), manteniendo el contrato de function calling estable

### Limitaciones Conocidas

- Modo micrófono solo funciona en Windows (`msvcrt`)
- Memoria no persiste entre sesiones
- No soporta múltiples usuarios
- Personalidad fija (no configurable por usuario)
- Sin interfaz gráfica (solo consola)
- El trim de la sliding window asume 1 user + 1 assistant por turno; con tool calls el historial crece más y el recorte queda impreciso

---

## 🔗 Referencias

- [Groq API Documentation](https://console.groq.com/docs)
- [Groq Pricing](https://console.groq.com/pricing)
- [Llama 3.3 Model Card](https://huggingface.co/meta-llama/Llama-3.3-70B)
- [Edge-TTS](https://github.com/rany2/edge-tts)
- [Open-Meteo API](https://open-meteo.com/en/docs)
- [ddgs (DuckDuckGo Search en Python)](https://github.com/fourleif/ddgs)
- [OpenAI Whisper Large V3](https://huggingface.co/openai/whisper-large-v3)

---

**Última actualización**: Septiembre 2026
**Versión**: 1.1.0