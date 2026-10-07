import wikipedia
import requests

# MediaWiki requires a descriptive User-Agent header to avoid 403 blocks
wikipedia.set_lang("en")
session = requests.Session()
session.headers.update({"User-Agent": "LibraAI_Assistant/1.0 (local_assistant@localhost)"})
wikipedia.requests = session

def get_entity_summary(entity_name: str) -> str:
    """Fetches a clean 2-sentence summary directly from Wikipedia."""
    try:
        results = wikipedia.search(entity_name)
        if not results:
            return ""
        # Get page summary directly
        page = wikipedia.page(results[0], auto_suggest=False)
        return wikipedia.summary(page.title, sentences=2, auto_suggest=False).strip()
    except Exception as e:
        print(f"[Knowledge Agent Error]: {e}")
        return ""