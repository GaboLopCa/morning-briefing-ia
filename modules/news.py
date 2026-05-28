import requests
import feedparser
import time
from datetime import datetime, timedelta

class NewsFetcher:
    def __init__(self, sources):
        self.sources = sources
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def get_top_news(self):
        all_news = []
        hace_24h = datetime.now() - timedelta(hours=24)
        
        for url in self.sources:
            try:
                # Aumentamos un poco el tiempo de espera para evitar el error 10054
                response = requests.get(url, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    feed = feedparser.parse(response.content)
                    
                    # Limitamos a las 8 más nuevas por fuente para no saturar a Groq
                    for entry in feed.entries[:8]: 
                        dt_publicacion = None
                        if hasattr(entry, 'published_parsed'):
                            dt_publicacion = datetime(*entry.published_parsed[:6])
                        
                        if dt_publicacion is None or dt_publicacion > hace_24h:
                            all_news.append({
                                'title': entry.title,
                                # Limitar el largo de la descripción ayuda MUCHO a no gastar tokens
                                'description': entry.get('summary', entry.get('description', ''))[:200] + "...",
                                'category': entry.get('category', 'General')
                            })
                
                time.sleep(0.5) # Pausa más larga para que Emol no se enoje
            except Exception as e:
                print(f"⚠️ Saltando fuente por error: {url}")
                continue
                
        return all_news