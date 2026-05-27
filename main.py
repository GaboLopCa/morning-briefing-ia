from modules.weather import WeatherProvider
from modules.news import NewsFetcher
from modules.summarizer import NewsSummarizer

# 1. ---Setup---

API_KEY = "YOUR_API_KEY"
rss_urls = ["https://feeds.bbci.co.uk/mundo/temas/tecnologia/rss.xml"]

weather_service = WeatherProvider(-33.6895, -71.2146)
news_service = NewsFetcher(rss_urls)
ai_service = NewsSummarizer(API_KEY)

# 2. ---Execution---
print("📡 Fetching weather and news...")
current_weather = weather_service.get_weather()
current_news = news_service.get_top_news()

print("🤖 Groq is thinking...")
# We pass the data we collected to the AI
briefing = ai_service.generate_briefing(current_weather, current_news)

# 3. ---Final Result---
print("-" * 30)
print(briefing)
print("-" * 30)