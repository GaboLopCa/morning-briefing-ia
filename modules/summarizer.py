"""Motor cognitivo del asistente (Brain).

Usa `gemini-3.1-flash-live-preview` vía Live API (WebSocket) con una SESIÓN POR
TURNO: se abre la sesión, se siembra el historial (pares user/model) más el
mensaje actual, se resuelven los function calls de forma síncrona y se devuelve
el texto final.

Ventajas de diseño:
- La memoria client-side contiene SOLO pares user/model, con recorte por turnos
  completos: nunca quedan mensajes `tool` huérfanos (bug crítico resuelto).
- El dispatch de herramientas se delega al `registry`: añadir capabilities no
  requiere tocar esta clase.
"""
import asyncio

from google import genai
from google.genai import types

from config import MAX_HISTORIAL_TURNOS, MAX_TOKENS_SALIDA, MODELO_LLM, TEMPERATURA_LLM
from modules.contract import error

RESPUESTA_ERROR = "Lo siento, tuve un problema procesando eso. Intenta de nuevo."


class Brain:
    def __init__(
        self,
        api_key,
        registro,
        modelo=MODELO_LLM,
        max_historial_turnos=MAX_HISTORIAL_TURNOS,
    ):
        self.client = genai.Client(api_key=api_key)
        self.registro = registro
        self.modelo = modelo
        self.max_historial_turnos = max_historial_turnos
        self.historial = []  # list[types.Content]: pares user/model para sembrar

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
4. SIEMPRE usa las herramientas en vez de sugerirle a Gabriel buscar por su
   cuenta: clima → get_weather_data, actualidad → get_news_data, y cualquier
   dato reciente/resultados/eventos → search_internet_data. No respondas en
   base a conocimiento previo para hechos actuales; si algo no es seguro,
   simplemente confiesa que no lo sabes.

Perfil del usuario: Gabriel, estudiante de ingeniería de software, fan de la
tecnología, los videojuegos, la Universidad de Chile, la F1 y la NBA.

Herramientas disponibles (se resolverán automáticamente):
- get_weather_data: clima en Melipilla.
- get_news_data: titulares de noticias chilenas de las últimas 24 horas.
- search_internet_data: búsqueda web en tiempo real (úsala para datos
  recientes, deportes, eventos o cualquier hecho que no conozcas).
- ejecutar_opencode: agente de programación que trabaja en los proyectos
  locales del usuario (crear skills, revisar o modificar código, etc.).
  ÚSALA SOLO cuando Gabriel te lo pida explícitamente. Esa herramienta pedirá
  confirmación antes de ejecutar; si se cancela, cuéntale el motivo.
"""

    # ------------------------------------------------------------------ API

    def generate_response(self, user_command):
        """Devuelve la respuesta de texto de Josesito (síncrono por fuera)."""
        return asyncio.run(self._procesar(user_command))

    def limpiar_historial(self):
        """Descartar toda la memoria de la sesión actual."""
        self.historial.clear()

    # -------------------------------------------------------------- utilidades

    def _construir_semilla(self, user_command):
        """Historial (pares user/model) + peso del mensaje actual del usuario."""
        turnos = list(self.historial)
        turnos.append(types.Content(role="user", parts=[types.Part(text=user_command)]))
        return turnos

    def _guardar_en_historial(self, user_command, respuesta):
        """Registra el turno y recorta por pares completos (nunca roles sueltos)."""
        self.historial.append(types.Content(role="user", parts=[types.Part(text=user_command)]))
        self.historial.append(types.Content(role="model", parts=[types.Part(text=respuesta)]))
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

        tipos_validos = (dict, list, str, int, float, bool)
        if isinstance(salida, tipos_validos) or salida is None:
            return salida
        print(f"[Brain] Tool '{nombre}' devolvió tipo no serializable: {type(salida).__name__}")
        return error("La herramienta devolvió un formato no esperado.")

    # ------------------------------------------------------------ ciclo Live

    async def _procesar(self, user_command):
        guardar_turno = True
        try:
            declaraciones = [h.a_declaracion() for h in self.registro.values()]
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=self.system_prompt,
                tools=[{"function_declarations": declaraciones}],
                temperature=TEMPERATURA_LLM,
                max_output_tokens=MAX_TOKENS_SALIDA,
                thinking_config=types.ThinkingConfig(thinking_level="LOW"),
                history_config=types.HistoryConfig(initial_history_in_client_content=True),
                output_audio_transcription=types.AudioTranscriptionConfig(language_codes=["es-CL"]),
            )

            semilla = self._construir_semilla(user_command)
            partes_texto = []

            async with self.client.aio.live.connect(model=self.modelo, config=config) as session:
                await session.send_client_content(turns=semilla, turn_complete=True)

                async for mensaje in session.receive():
                    if mensaje.server_content:
                        sc = mensaje.server_content
                        if sc.output_transcription is not None:
                            texto_transc = getattr(sc.output_transcription, "text", "")
                            if texto_transc:
                                partes_texto.append(texto_transc)
                        if sc.model_turn:
                            for part in sc.model_turn.parts:
                                if part.text:
                                    partes_texto.append(part.text)
                    elif mensaje.tool_call:
                        respuestas = []
                        for fc in mensaje.tool_call.function_calls:
                            args = dict(fc.args or {})
                            resultado = await asyncio.to_thread(
                                self._ejecutar_herramienta, fc.name, args
                            )
                            respuestas.append(
                                types.FunctionResponse(
                                    name=fc.name,
                                    id=fc.id,
                                    response={"result": resultado},
                                )
                            )
                        await session.send_tool_response(function_responses=respuestas)

            respuesta = "".join(partes_texto).strip() or RESPUESTA_ERROR
        except Exception as exc:  # noqa: BLE001
            print(f"[Brain] Error en el ciclo Live: {exc}")
            respuesta = RESPUESTA_ERROR
            guardar_turno = False  # no contaminar la memoria con disculpas

        if guardar_turno:
            self._guardar_en_historial(user_command, respuesta)
        return respuesta