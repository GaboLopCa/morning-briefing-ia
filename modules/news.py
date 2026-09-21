"""Agregador de noticias RSS, con descarga en paralelo.

Cada fuente se descarga en un worker propio (ThreadPoolExecutor) y luego se
combinan deduplicando por título y respetando los límites configurables.
"""
import calendar
import time as time_mod
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from config import (
    DESCRIPCION_MAX,
    MAX_NOTICIAS_TOTAL,
    NOTICIAS_CACHE_TTL,
    NOTICIAS_WORKERS,
    TIMEOUT_HTTP,
)
from modules.contract import ok

POR_FUENTE = 8


def _fecha_utc(entry):
    """Devuelve datetime UTC de la publicación, o None si no hay fecha utilizable."""
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(parsed[:6]), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _valor(entry, clave, fallback=""):
    """Lee un campo tolerando entradas tipo dict (feedparser) u objeto."""
    if isinstance(entry, dict):
        return entry.get(clave, fallback)
    return getattr(entry, clave, fallback)


def _acortar(texto, maximo):
    """Normaliza a str y recorta añadiendo '...' solo si realmente truncó."""
    limpio = " ".join(str(texto or "").split())
    if len(limpio) <= maximo:
        return limpio
    return limpio[:maximo].rstrip() + "..."


class NewsFetcher:
    def __init__(
        self,
        sources,
        max_total=MAX_NOTICIAS_TOTAL,
        por_fuente=POR_FUENTE,
        workers=NOTICIAS_WORKERS,
    ):
        self.sources = sources
        self.max_total = max_total
        self.por_fuente = por_fuente
        self.workers = workers
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
        }
        self._cache = {}  # {"timestamp": float, "data": [...]}

    # ------------------------------------------------------------ internos

    def _fetch_fuente(self, url, hace_24h):
        """Descarga y parsea UNA fuente; devuelve su lista de noticias ([] si falla)."""
        noticias = []
        try:
            response = requests.get(url, headers=self.headers, timeout=(5, TIMEOUT_HTTP))
            # Reintento simple solo ante sobrecarga del servidor (429/5xx)
            if response.status_code in (429,) or response.status_code >= 500:
                response = requests.get(url, headers=self.headers, timeout=(5, TIMEOUT_HTTP))
            if response.status_code != 200:
                return noticias
            feed = feedparser.parse(response.content)
            for entry in feed.entries[: self.por_fuente]:
                pub = _fecha_utc(entry)
                if pub is None or pub < hace_24h:
                    continue  # sin fecha o muy vieja → se descarta
                noticias.append(
                    {
                        "title": str(_valor(entry, "title")).strip() or "Sin título",
                        "description": _acortar(
                            _valor(entry, "summary") or _valor(entry, "description"),
                            DESCRIPCION_MAX,
                        ),
                        "category": str(_valor(entry, "category")) or "General",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ Saltando fuente por error: {url}")
            print(f"[NewsFetcher] Detalle: {exc}")
        return noticias

    def _desde_cache(self):
        cache = self._cache
        if cache and time_mod.time() - cache["timestamp"] <= NOTICIAS_CACHE_TTL:
            return cache["data"]
        return None

    # ------------------------------------------------------------------- API

    def get_top_news(self):
        cached = self._desde_cache()
        if cached is not None:
            return ok(cached)

        hace_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            resultados = pool.map(
                lambda url: self._fetch_fuente(url, hace_24h),
                self.sources,
            )

        all_news = []
        vistos = set()
        for lista in resultados:
            if len(all_news) >= self.max_total:
                break
            for noticia in lista:
                if len(all_news) >= self.max_total:
                    break
                clave = noticia["title"].strip().lower()
                if clave in vistos:
                    continue  # dedup por título entre fuentes
                vistos.add(clave)
                all_news.append(noticia)

        self._cache = {"timestamp": time_mod.time(), "data": all_news}
        return ok(all_news)