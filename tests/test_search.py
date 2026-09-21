from modules.search import WebSearcher


class DDGSFake:
    def __init__(self, resultados):
        self.resultados = resultados

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def text(self, query, region, max_results):
        return self.resultados


class TestWebSearcher:
    def test_devuelve_bloque_con_resultados(self, monkeypatch):
        resultados = [
            {"title": "Resultado A", "body": "Información de A " * 50},
            {"title": "Resultado B", "body": "Info B"},
        ]
        monkeypatch.setattr("modules.search.DDGS", lambda: DDGSFake(resultados))

        searcher = WebSearcher(max_results=4)
        resultado = searcher.search_internet("mate")

        assert resultado["status"] == "ok"
        assert "Resultado A" in resultado["data"]
        assert "Resultado B" in resultado["data"]

    def test_resultados_vacios_devuelve_mensaje(self, monkeypatch):
        monkeypatch.setattr("modules.search.DDGS", lambda: DDGSFake([]))

        searcher = WebSearcher(max_results=4)
        resultado = searcher.search_internet("algo raro")

        assert resultado["status"] == "ok"
        assert "No se encontraron" in resultado["data"]

    def test_dedup_por_titulo(self, monkeypatch):
        resultados = [
            {"title": "Duplicado", "body": "primera"},
            {"title": "Duplicado", "body": "segunda"},
            {"title": "Único", "body": "tercera"},
        ]
        monkeypatch.setattr("modules.search.DDGS", lambda: DDGSFake(resultados))

        searcher = WebSearcher(max_results=4)
        resultado = searcher.search_internet("test")

        assert resultado["status"] == "ok"
        assert resultado["data"].count("[") == 2  # solo 2 resultados tras dedup

    def test_error_queda_en_envelope(self, monkeypatch):
        class DDGSFalla:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def text(self, *args, **kwargs):
                raise RuntimeError("búsqueda caída")

        monkeypatch.setattr("modules.search.DDGS", lambda: DDGSFalla())

        searcher = WebSearcher(max_results=4)
        resultado = searcher.search_internet("test")

        assert resultado["status"] == "error"
        assert "búsqueda" in resultado["mensaje"]