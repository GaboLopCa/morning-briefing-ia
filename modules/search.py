from ddgs import DDGS

class WebSearcher:
    def __init__(self):
        # No necesitamos llaves de API ni credenciales aquí. Gratis y libre.
        pass

    def search_internet(self, query, max_results=4):
        """
        Busca en internet la consulta solicitada y devuelve un resumen
        en texto plano con los títulos y fragmentos encontrados.
        """
        try:
            # Instanciamos el buscador nativo de la librería
            with DDGS() as ddgs:
                # Usamos text() para buscar páginas web estándar.
                # region="cl-es" le dice a DuckDuckGo que priorice resultados de Chile en español.
                results = ddgs.text(query, region="cl-es", max_results=max_results)
                
                if not results:
                    return f"No se encontraron resultados en internet para: '{query}'"
                
                # Vamos a empaquetar los resultados en un solo string limpio
                context_string = "RESULTADOS ENCONTRADOS EN INTERNET:\n"
                for index, result in enumerate(results, 1):
                    title = result.get('title', 'Sin título')
                    snippet = result.get('body', 'Sin descripción')
                    
                    # Estructuramos el texto para que Llama lo entienda fácilmente
                    context_string += f"[{index}] Fuente: {title}\n    Información: {snippet}\n\n"
                    
                return context_string
                
        except Exception as e:
            return f"Error físico al buscar en internet: {e}"