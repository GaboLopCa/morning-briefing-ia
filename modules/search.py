from ddgs import DDGS

from config import SNIPPET_MAX
from modules.contract import error, ok


class WebSearcher:
    def __init__(self, max_results=4):
        self.max_results = max_results

    def search_internet(self, query):
        """Busca en DDG con región chilena y devuelve un bloque de texto plano."""
        try:
            with DDGS() as ddgs:
                results = ddgs.text(query, region="cl-es", max_results=self.max_results)

            if not results:
                return ok(f"No se encontraron resultados en internet para: '{query}'")

            contexto = ["RESULTADOS ENCONTRADOS EN INTERNET:"]
            vistos = set()
            for indice, resultado in enumerate(results, 1):
                titulo = str(resultado.get("title", "") or "Sin título").strip()
                if titulo in vistos:
                    continue
                vistos.add(titulo)
                snippet = " ".join(str(resultado.get("body", "") or "").split())[:SNIPPET_MAX]
                contexto.append(f"[{indice}] Fuente: {titulo}\n    Información: {snippet}")

            return ok("\n\n".join(contexto))
        except Exception as exc:  # noqa: BLE001
            print(f"[WebSearcher] Error interno: {exc}")
            return error("No fue posible realizar la búsqueda en internet.")