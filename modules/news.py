import requests
import feedparser

class NewsFetcher:
    def __init__(self, sources):
        self.sources = sources

    def get_top_news(self):
        all_news = []
        
        for url in self.sources:
            feed = feedparser.parse(url)

            for entry in feed.entries[:3]:
                new_info = {
                    "title": entry.title,
                    "link": entry.link
                }
                all_news.append(new_info)
        
        return all_news