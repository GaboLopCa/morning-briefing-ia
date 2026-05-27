from modules.weather import WeatherProvider
from modules.news import NewsFetcher

clima_melipilla = WeatherProvider(-33.6895,-71.2146)
print(clima_melipilla.get_weather())

URLs = ["https://feeds.bbci.co.uk/mundo/temas/tecnologia/rss.xml"]

noticias = NewsFetcher(URLs)

feed = noticias.get_top_news()

print("")

for n in feed:
    print(f"📰 {n['title']}")
    print(f"🔗 Link: {n['link']}\n")