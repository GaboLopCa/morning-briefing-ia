from groq import Groq

class NewsSummarizer:
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)
        self.model_id = "llama-3.3-70b-versatile" # One of the best free models

    def generate_briefing(self, weather_data, news_data):
        prompt = f"""
        You are a smart morning assistant. Create a briefing in Spanish.
        Context:
        - Weather: {weather_data}
        - News: {news_data}
        
        Guidelines: Friendly tone, brief summary of weather and top 3 news for Melipilla.
        """
        try:
            chat_completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_id,
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            return f"Error connecting to Groq: {e}"