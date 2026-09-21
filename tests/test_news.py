import calendar
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from modules.news import NewsFetcher, _acortar, _fecha_utc, DESCRIPCION_MAX, POR_FUENTE

HACE_UN_HORA = time.time() - 3600
HACE_DOS_DIAS = time.time() - 172800


def _entrada(titulo, timestamp_estructura, resumen):
    """Crea un entry feedparser-compatible."""
    entrada = SimpleNamespace(
        title=titulo,
        summary=resumen,
        description=resumen,
        category="Nacional",
        published_parsed=time.gmtime(timestamp_estructura),
        updated_parsed=time.gmtime(timestamp_estructura),
    )
    return entrada


def _feed(entradas):
    return SimpleNamespace(entries=entradas)


class FakeRespuestaRSS:
    def __init__(self, cuerpo):
        self.status_code = 200
        self.content = cuerpo


class TestFechaUtc:
    def test_devuelve_datetime_utc(self):
        fecha = _fecha_utc(_entrada("x", HACE_UN_HORA, "r"))
        assert fecha.tzinfo == timezone.utc

    def test_sin_fecha_devuelve_none(self):
        entrada = SimpleNamespace(title="x")
        assert _fecha_utc(entrada) is None


class TestAcortar:
    def test_no_trunca_si_cabe(self):
        texto = "corto"
        assert _acortar(texto, 10) == "corto"

    def test_trunca_y_agrega_ellipsis(self):
        texto = "a" * 300
        recortado = _acortar(texto, DESCRIPCION_MAX)
        assert len(recortado) <= DESCRIPCION_MAX + 3
        assert recortado.endswith("...")

    def test_None_se_convierte_en_vacio(self):
        assert _acortar(None, 10) == ""


class TestNewsFetcher:
    def _con_http_fake(self, monkeypatch, feed):
        respuestas = [FakeRespuestaRSS(b"contenido")]

        def fake_get(*args, **kwargs):
            return respuestas.pop(0)

        def fake_parse(contenido):
            return feed

        monkeypatch.setattr("modules.news.requests.get", fake_get)
        monkeypatch.setattr("modules.news.feedparser.parse", fake_parse)

    def test_filtra_ultimas_24_horas(self, monkeypatch):
        noticia_vieja = _entrada("noticia vieja", HACE_DOS_DIAS, "detalle")
        noticia_nueva = _entrada("noticia nueva", HACE_UN_HORA, "detalle")

        feed = _feed([noticia_vieja, noticia_nueva])
        self._con_http_fake(monkeypatch, feed)

        fetcher = NewsFetcher(["http://fuente.cl/feed"], max_total=40, por_fuente=8)
        resultado = fetcher.get_top_news()

        assert resultado["status"] == "ok"
        titulos = [n["title"] for n in resultado["data"]]
        assert "noticia nueva" in titulos
        assert "noticia vieja" not in titulos

    def test_descripcion_se_trunca(self, monkeypatch):
        entrada = _entrada("titulo", HACE_UN_HORA, "x" * 500)
        self._con_http_fake(monkeypatch, _feed([entrada]))

        fetcher = NewsFetcher(["http://fuente.cl/feed"], max_total=40, por_fuente=8)
        resultado = fetcher.get_top_news()

        assert resultado["status"] == "ok"
        descripcion = resultado["data"][0]["description"]
        assert len(descripcion) <= DESCRIPCION_MAX + 3
        assert descripcion.endswith("...")

    def test_max_total_respetado(self, monkeypatch):
        muchas = [_entrada(f"n{i}", HACE_UN_HORA, "r") for i in range(20)]
        self._con_http_fake(monkeypatch, _feed(muchas))

        fetcher = NewsFetcher(["http://fuente.cl/feed"], max_total=5, por_fuente=20)
        resultado = fetcher.get_top_news()

        assert len(resultado["data"]) == 5

    def test_fuente_fallida_no_rompe(self, monkeypatch):
        def fake_get(*args, **kwargs):
            raise RuntimeError("caída")

        monkeypatch.setattr("modules.news.requests.get", fake_get)

        fetcher = NewsFetcher(["http://fuente-cae.cl/feed"], max_total=40, por_fuente=8)
        resultado = fetcher.get_top_news()

        assert resultado["status"] == "ok"
        assert resultado["data"] == []  # envuelve la lista vacía, no lanza