"""Motor cognitivo del asistente (Brain).

Usa la API de **Groq** (endpoint OpenAI-compatible) con `qwen/qwen3.8-27b`
en streaming. Groq corre en hardware LPU: la latencia del primer token es de
fracciones de segundo, frente a los ~40 s que sufría Google.

Diseño orientado a reducir el tiempo de respuesta:
- PREFETCH: clima y noticias se obtienen en paralelo ANTES de pedir la respuesta
  y se inyectan como mensaje de contexto del turno. Así el modelo no gasta un
  round-trip en obtenerlos.
- AFC manual: los tool calls que el modelo emita (búsqueda web, opencode) se
  resuelven localmente (en paralelo) y se re-alimenta el chat.
- Streaming: el texto fluye hacia `on_fragment` apenas llega (latencia percibida
  ≈ primer token).
- Reintentos con backoff ante 429/5xx (respetando `retry-after`) y fallback con
  los resultados de las tools si el redactado final falla.
"""
import json
import time as time_mod
from concurrent.futures import ThreadPoolExecutor

from groq import Groq, APIStatusError

from config import MAX_HISTORIAL_TURNOS, MAX_TOKENS_SALIDA, MODELO_LLM, NOTICIAS_CONTEXTO, TEMPERATURA_LLM
from modules.contract import error

RESPUESTA_ERROR = "Lo siento, tuve un problema procesando eso. Intenta de nuevo."
MAX_RONDAS_TOOLS = 3      # llamadas original + hasta 2 revisitas por tools
MAX_REINTENTOS = 4        # reintentos con backoff ante 429/5xx
TIPOS_SERIALIZABLES = (dict, list, str, int, float, bool)


class Brain:
    def __init__(
        self,
        api_key,
        registro,
        modelo=MODELO_LLM,
        max_historial_turnos=MAX_HISTORIAL_TURNOS,
    ):
        self.client = Groq(api_key=api_key)
        self.registro = registro
        self.modelo = modelo
        self.max_historial_turnos = max_historial_turnos
        self.historial = []  # list[dict{mensaje}]: pares user/assistant para sembrar

        self.system_prompt = """
Eres Josesito, un locutor de radio satírico, directo y con carácter, nacido en
Melipilla, Chile. Respondes SIEMPRE en español NEUTRO: claro, natural y sin
modismos chilenos ni jerga local. Evita términos como "cachái", "po",
"al tiro", "pajero", "weón" o cualquier chilenismo; habla como un locutor
profesional. De forma concisa y sin redundancia.

Reglas críticas:
1. SIN MARKDOWN: no uses asteriscos, hashtags, viñetas ni formatos especiales.
   Texto plano y conversacional para que el lector de voz lo diga naturalmente.
2. Personalidad: irónico, mordaz y amable, con humor ligero y universal (evita
   referencias excesivamente locales que suenen forzadas).
3. Repite al mínimo lo que ya has dicho antes en la conversación.
4. El CLIMA y las NOTICIAS ya vienen incluidos en el bloque "CONTEXTO DEL DÍA"
   de cada turno: NO llames las herramientas get_weather_data ni
   get_news_data, úsalos directamente. Para cualquier otro dato reciente
   (resultados, eventos, datos que no conozcas) usa search_internet_data, y
   solo si el usuario lo pide explícitamente usa ejecutar_opencode.

Perfil del usuario: Gabriel, estudiante de ingeniería de software, fan de la
tecnología, los videojuegos, la Universidad de Chile, la F1 y la NBA.

Herramientas disponibles (se resolverán automáticamente):
- search_internet_data: búsqueda web en tiempo real.
- ejecutar_opencode: agente de programación en los proyectos locales del
  usuario. Pedirá confirmación antes de ejecutar; si se cancela, cuéntale.
"""

    # ------------------------------------------------------------------ API

    def generate_response(self, user_command, on_fragment=None):
        """Devuelve la respuesta de texto de Josesito (síncrono).

        `on_fragment(texto)` se invoca con cada fragmento de texto apenas llega
        del streaming; sirve para mostrar la respuesta en vivo mientras se genera.
        """
        return self._procesar(user_command, on_fragment)

    def limpiar_historial(self):
        """Descartar toda la memoria de la sesión actual."""
        self.historial.clear()

    # -------------------------------------------------------------- utilidades

    def _construir_semilla(self, user_command):
        """Historial (pares user/assistant) + peso del mensaje actual del usuario."""
        turnos = list(self.historial)
        turnos.append({"role": "user", "content": user_command})
        return turnos

    def _guardar_en_historial(self, user_command, respuesta):
        """Registra el turno y recorta por pares completos (nunca roles sueltos)."""
        self.historial.append({"role": "user", "content": user_command})
        self.historial.append({"role": "assistant", "content": respuesta})
        max_entradas = self.max_historial_turnos * 2
        if len(self.historial) > max_entradas:
            excedente = len(self.historial) - max_entradas
            self.historial = self.historial[excedente:]

    def _ejecutar_herramienta(self, nombre, args):
        """Resuelve una tool local y normaliza la salida al envelope del contrato."""
        herramienta = self.registro.get(nombre)
        if herramienta is None:
            return error(f"Herramienta desconocida: '{nombre}'.")

        try:
            salida = herramienta.handler(**args) if args else herramienta.handler()
        except Exception as exc:  # noqa: BLE001
            print(f"[Brain] Error en tool '{nombre}': {exc}")
            return error("La herramienta no pudo completar la operación.")

        if isinstance(salida, TIPOS_SERIALIZABLES) or salida is None:
            return salida
        print(f"[Brain] Tool '{nombre}' devolvió tipo no serializable: {type(salida).__name__}")
        return error("La herramienta devolvió un formato no esperado.")

    # ---------------------------------------------------------- prefetch

    def _obtener_datos_en_paralelo(self):
        """Clima + noticias en paralelo (rápido; noticias van a caché)."""
        nombres = ("get_weather_data", "get_news_data")
        resultados = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futuros = {pool.submit(self._ejecutar_herramienta, nombre, {}): nombre for nombre in nombres}
            for futuro in futuros:
                try:
                    resultados[futuros[futuro]] = futuro.result()
                except Exception as exc:  # noqa: BLE001
                    print(f"[Brain] Prefetch falló: {exc}")
                    resultados[futuros[futuro]] = None
        return resultados.get("get_weather_data"), resultados.get("get_news_data")

    def _formatear_contexto(self, clima, noticias):
        """Compacta clima+noticias a un bloque de contexto para el prompt."""
        lineas = ["CONTEXTO DEL DÍA (datos ya obtenidos; NO llames get_weather_data ni get_news_data):"]
        if isinstance(clima, dict):
            if clima.get("status") == "ok":
                d = clima.get("data") or {}
                lineas.append(
                    "Clima Melipilla: {condition}, ahora {current}°C (sensación {feels}°C), "
                    "máx {max}°C / mín {min}°C, lluvia {rain}%".format(
                        condition=d.get("condition", "?"),
                        current=d.get("current", "?"),
                        feels=d.get("feels_like", "?"),
                        max=d.get("max", "?"),
                        min=d.get("min", "?"),
                        rain=d.get("rain_prob", "?"),
                    )
                )
            else:
                lineas.append(f"Clima Melipilla: {clima.get('mensaje', 'indisponible')}")
        else:
            lineas.append("Clima Melipilla: no disponible.")

        if isinstance(noticias, dict) and noticias.get("status") == "ok":
            items = (noticias.get("data") or [])[:NOTICIAS_CONTEXTO]
            lineas.append(f"{len(items)} titulares de las últimas 24h:")
            for noticia in items:
                lineas.append(f"- {noticia.get('title', 'Sin título')}" + (
                    f". {noticia.get('description', '')[:120]}" if noticia.get("description") else ""
                ))
        else:
            lineas.append("Noticias: no disponibles en este momento.")
        return "\n".join(lineas)

    # ------------------------------------------------------------ ciclo de generación

    def _tools_openai(self, declaraciones):
        """Envuelve las declaraciones a formato tool de la API OpenAI/Groq."""
        return [{"type": "function", "function": d} for d in declaraciones]

    @staticmethod
    def _es_reintentable(exc):
        """¿Vale la pena reintentar? Solo rate-limit (429) o fallos 5xx."""
        if isinstance(exc, APIStatusError) and exc.status_code >= 500:
            return True
        if isinstance(exc, APIStatusError) and exc.status_code == 429:
            return True
        return False

    @staticmethod
    def _espera_sugerida(exc, reintento):
        """Segundos de espera: priority a retry-after del server, si lo trae."""
        if isinstance(exc, APIStatusError) and exc.status_code == 429:
            retry_after = exc.headers.get("retry-after") if exc.headers else None
            if retry_after:
                try:
                    return min(int(float(retry_after)), 30)
                except (TypeError, ValueError):
                    pass
        return min(2 ** reintento, 10)

    def _stream_ronda(self, messages, tools, on_fragment=None):
        """Una ronda de chat streaming; devuelve (texto, tool_calls_acumulados).

        `tool_calls_acumulados` es una lista de dicts (id, name, JSON de args);
        por defecto vacía. El streaming de Groq entrega los deltas de tool_calls
        por índice: se fusionan y se parsean los argumentos al final.
        """
        acumulado = []
        tool_calls = {}
        reintento = 0

        while True:
            try:
                stream = self.client.chat.completions.create(
                    model=self.modelo,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=TEMPERATURA_LLM,
                    max_tokens=MAX_TOKENS_SALIDA,
                    stream=True,
                )
                for chunk in stream:
                    eleccion = (chunk.choices or [None])[0]
                    delta = getattr(eleccion, "delta", None)
                    if delta is None:
                        continue
                    if delta.content:
                        acumulado.append(delta.content)
                        if on_fragment is not None:
                            on_fragment(delta.content)
                    if delta.tool_calls:
                        for llamada in delta.tool_calls:
                            indice = llamada.index if llamada.index is not None else 0
                            registro = tool_calls.setdefault(
                                indice, {"id": "", "name": "", "args": ""}
                            )
                            if llamada.id:
                                registro["id"] = llamada.id
                            if llamada.function and llamada.function.name:
                                registro["name"] += llamada.function.name
                            if llamada.function and llamada.function.arguments:
                                registro["args"] += llamada.function.arguments
                break
            except Exception as exc:  # noqa: BLE001
                reintento += 1
                if reintento > MAX_REINTENTOS or not self._es_reintentable(exc):
                    raise
                print(f"[Brain] {type(exc).__name__} {str(exc)[:70]} … reintento {reintento}")
                time_mod.sleep(self._espera_sugerida(exc, reintento))

        llamadas = []
        for indice in sorted(tool_calls):
            registro = tool_calls[indice]
            if not registro["name"]:
                continue
            try:
                args = json.loads(registro["args"]) if registro["args"].strip() else {}
            except json.JSONDecodeError:
                print(f"[Brain] tool {registro['name']} con args no JSON: {registro['args'][:80]!r}")
                args = {}
            llamadas.append(
                {
                    "id": registro["id"],
                    "name": registro["name"],
                    "arguments": args,
                    "arguments_raw": registro["args"],
                }
            )
        return "".join(acumulado).strip(), llamadas

    def _ejecutar_tool_calls(self, llamadas):
        """Ejecuta las tools en paralelo; devuelve (mensajes tool, resumen).

        Mensajes listos para re-alimentar el chat (rol `tool`), y un texto plano
        de respaldo por si el redactado final falla (`_resumen`).
        """
        if not llamadas:
            return [], ""
        resultados = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futuros = [
                pool.submit(self._ejecutar_herramienta, ll["name"], ll["arguments"])
                for ll in llamadas
            ]
            resultados = [futuro.result() for futuro in futuros]

        mensajes = []
        resumen = []
        for llamada, resultado in zip(llamadas, resultados):
            contenido = json.dumps(resultado, ensure_ascii=False) if isinstance(resultado, (dict, list)) else str(resultado or "")
            if llamada["id"]:
                mensajes.append(
                    {"role": "tool", "tool_call_id": llamada["id"], "content": contenido}
                )
            texto_bruto = ""
            if isinstance(resultado, dict):
                texto_bruto = resultado.get("data") or resultado.get("mensaje", "")
            elif isinstance(resultado, str):
                texto_bruto = resultado
            if texto_bruto:
                resumen.append(texto_bruto)
        resumen_texto = ("\n".join(resumen)[:900]) if resumen else ""
        return mensajes, resumen_texto

    def _procesar(self, user_command, on_fragment=None):
        guardar_turno = True
        fallback = None
        try:
            declaraciones = [h.a_declaracion() for h in self.registro.values()]
            tools = self._tools_openai(declaraciones)

            contexto = self._formatear_contexto(*self._obtener_datos_en_paralelo())
            semilla = self._construir_semilla(user_command)
            semilla.insert(
                max(0, len(semilla) - 1),  # justo antes del mensaje actual
                {"role": "user", "content": contexto},
            )

            mensajes = [{"role": "system", "content": self.system_prompt}] + semilla
            texto_final = ""
            for _ in range(MAX_RONDAS_TOOLS):
                texto, llamadas = self._stream_ronda(mensajes, tools, on_fragment)
                if texto:
                    texto_final = (texto_final + " " + texto).strip() if texto_final else texto
                if not llamadas:
                    break
                # el asistente "pidió" tools: se registra su mensaje assistant
                mensajes.append(
                    {
                        "role": "assistant",
                        "content": texto or "",
                        "tool_calls": [
                            {
                                "id": ll["id"],
                                "type": "function",
                                "function": {
                                    "name": ll["name"],
                                    "arguments": ll["arguments_raw"] or "{}",
                                },
                            }
                            for ll in llamadas
                        ],
                    }
                )
                mensajes_tool, resumen = self._ejecutar_tool_calls(llamadas)
                if not mensajes_tool:
                    break  # sin id no se puede respetar el contrato OpenAI; cortar
                mensajes.extend(mensajes_tool)
                fallback = resumen

            respuesta = texto_final or fallback or RESPUESTA_ERROR
        except Exception as exc:  # noqa: BLE001
            print(f"[Brain] Error en el ciclo de generación: {exc}")
            respuesta = fallback or RESPUESTA_ERROR
            guardar_turno = fallback is not None  # no contaminar la memoria con disculpas

        if guardar_turno:
            self._guardar_en_historial(user_command, respuesta)
        return respuesta