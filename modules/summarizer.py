import json
from groq import Groq

class NewsSummarizer:
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)
        self.model_id = "llama-3.3-70b-versatile"
        
        # --- PROMPT DEL PERSONAJE Y CONTROL DE COMPORTAMIENTO ---
        self.system_prompt = """
        You are Josesito, a sharp-witted, satirical, and direct radio host from Melipilla, Chile.
        Your output MUST be 100% in Spanish, concise, and avoid redundancy. 
        
        CRITICAL RULES:
        1. NO MARKDOWN AT ALL: Do not use asterisks (**), hashtags (#), or bullet points. Use plain conversational text only so the text-to-speech engine reads it naturally.
        2. PERSONA: You are cynical and love mocking local situations in Melipilla.
        
        USER PROFILE: Gabriel, junior software engineering major, loves sports, videogames and tech.
        
        When Gabriel asks about recent events, sports results or general facts you don't know, use the 'search_internet_data' tool to find current information.
        """
        
        # Inicializamos la memoria con el rol del sistema
        self.history = [{"role": "system", "content": self.system_prompt}]
        self.max_history_turns = 12 # Mantiene los últimos 6 pares de mensajes (User + Assistant)

    def generate_response(self, weather_provider, news_fetcher, search_provider, user_command):
        """
        Ciclo cognitivo autónomo. Evalúa el contexto conversacional y decide
        qué herramientas (clima, RSS o Buscador Web) ejecutar.
        """
        # 1. Registrar lo que Gabriel dijo en el micrófono/teclado
        self.history.append({"role": "user", "content": user_command})

        # --- GLOSARIO DE HERRAMIENTAS DISPONIBLES PARA LLAMA ---
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather_data",
                    "description": "Obtiene las condiciones del clima actuales en Melipilla (temperaturas y probabilidad de lluvia).",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_news_data",
                    "description": "Recupera los titulares y resúmenes de las últimas 24 horas de los portales de noticias de Chile.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_internet_data",
                    "description": "Busca en internet en tiempo real sobre noticias de última hora, resultados deportivos de 2025/2026 o datos actualizados.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "La frase clave o términos de búsqueda exactos para el navegador."}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

        try:
            # 2. PRIMERA LLAMADA: Llama procesa y decide si requiere herramientas
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=self.history,
                tools=tools,
                tool_choice="auto",
                temperature=0.6
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # 3. VERIFICACIÓN DE INTENCIÓN DE EJECUCIÓN
            if tool_calls:
                # Metemos la intención de la IA al historial para no romper la secuencia de la API
                self.history.append(response_message)

                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    tool_output = ""

                    # Enrutamiento físico hacia tus módulos locales de Python
                    if function_name == "get_weather_data":
                        print("📡 [Agente] Invocando módulo de Clima...")
                        tool_output = json.dumps(weather_provider.get_weather())
                        
                    elif function_name == "get_news_data":
                        print("📡 [Agente] Invocando módulo de Canales RSS...")
                        tool_output = json.dumps(news_fetcher.get_top_news())
                        
                    elif function_name == "search_internet_data":
                        # Extraer los argumentos generados por la IA
                        args = json.loads(tool_call.function.arguments)
                        search_query = args.get("query", "")
                        print(f"📡 [Agente] Navegando de forma autónoma por la web para: '{search_query}'...")
                        tool_output = search_provider.search_internet(query=search_query)

                    # Devolver los datos crudos del raspado al contexto de la IA
                    self.history.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": tool_output
                    })

                # SEGUNDA LLAMADA: Llama lee los datos obtenidos de la web o APIs y genera la respuesta final
                second_response = self.client.chat.completions.create(
                    model=self.model_id,
                    messages=self.history,
                    temperature=0.7
                )
                final_answer = second_response.choices[0].message.content
            else:
                # Chitchat normal o consulta resuelta con memoria directa
                final_answer = response_message.content

            # 4. Registrar la respuesta de Josesito en la memoria
            self.history.append({"role": "assistant", "content": final_answer})

            # --- CORTE DESLIZANTE DE MEMORIA (SLIDING WINDOW) ---
            # Evita que el historial crezca al infinito manteniendo a salvo el System Prompt (índice 0)
            if len(self.history) > self.max_history_turns:
                self.history.pop(1)  # Remueve el User message más viejo
                self.history.pop(1)  # Remueve el Assistant message más viejo

            return final_answer

        except Exception as e:
            return f"Error en el ciclo de ejecución de la IA: {e}"