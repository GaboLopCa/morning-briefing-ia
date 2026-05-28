from modules.weather import WeatherProvider
from modules.news import NewsFetcher
from modules.summarizer import NewsSummarizer
from modules.voice import VoiceAssistant
from datetime import datetime

API_KEY = "***REMOVED***"
rss_urls = [
    # --- NACIONAL Y POLÍTICA (Chile) ---
    "https://www.biobiochile.cl/lista/tag/chile/feed",
    "https://www.latercera.com/arc/outboundfeeds/rss/?outputType=xml",
    "https://www.elmostrador.cl/destacado/feed/",
    "https://www.cooperativa.cl/noticias/site/tax/port/all/rss_5_6_1.xml",

    # --- DEPORTES (El Bulla y más) ---
    "https://www.alairelibre.cl/noticias/site/tax/port/all/rss_2_0.xml",
    "https://redgol.cl/rss/tag/universidad-de-chile", # <--- Específico de la U
    "https://www.adnradio.cl/category/deportes/feed/",
    "https://as.com/rss/pro/internacional.xml",

    # --- TECNOLOGÍA Y CIENCIA ---
    "https://www.xataka.com/feed",
    "https://hipertextual.com/feed",
    "https://www.fayerwayer.com/feed/",

    # --- INTERNACIONAL Y CURIOSIDADES ---
    "https://feeds.bbci.co.uk/mundo/rss.xml",
    "https://elpais.com/rss/el-pais/portada.xml",
    "https://nmas1.org/rss"
]
weather_service = WeatherProvider(-33.6895, -71.2146)
news_service = NewsFetcher(rss_urls)
ai_service = NewsSummarizer(API_KEY)
fecha_actual = datetime.now().strftime("%d de %B, %Y")

voice_service = VoiceAssistant(speed=1.3)

# 2. ---Execution---
print("📡 Fetching weather and news...")
current_weather = weather_service.get_weather()
current_news = news_service.get_top_news()

print("🤖 Groq is thinking...")
briefing = ai_service.generate_briefing(current_weather, current_news, fecha_actual)

# 3. ---Final Result---
print("-" * 30)
print(briefing)
print("-" * 30)

# Esto ahora funcionará fluido y con acento chileno
voice_service.speak(briefing)