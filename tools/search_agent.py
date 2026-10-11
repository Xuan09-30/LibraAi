import warnings
from ddgs import DDGS

warnings.filterwarnings("ignore")


def search_live_web(query: str, max_results: int = 4) -> str:
    """
    Queries DuckDuckGo silently in the background and aggregates concise snippets.
    Imported by core.llm and ui.gui for live research.
    """
    clean_query = query.strip().strip('"').strip("'")
    if not clean_query:
        return ""

    context_snippets = []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(clean_query, max_results=max_results))
            for res in results:
                title = res.get("title", "")
                body = res.get("body", "")
                if body:
                    context_snippets.append(f"{title}: {body}")
    except Exception as e:
        print(f"[Search Engine Warning]: {e}")
        return ""

    return "\n".join(context_snippets)


# Alias in case another module calls perform_live_search
perform_live_search = search_live_web