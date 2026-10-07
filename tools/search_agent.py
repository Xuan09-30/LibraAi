from datetime import datetime
from ddgs import DDGS

def search_live_web(query: str, max_results: int = 4) -> str:
    """Performs a live web search with automated date anchoring."""
    now = datetime.now()
    current_year = str(now.year)
    current_month_str = now.strftime("%B %Y")

    # Replace relative date words with concrete dates
    clean_query = query.lower()
    if "today" in clean_query:
        clean_query = clean_query.replace("today", f"{now.strftime('%B %d, %Y')}")
    elif "yesterday" in clean_query:
        from datetime import timedelta
        yest = now - timedelta(days=1)
        clean_query = clean_query.replace("yesterday", f"{yest.strftime('%B %d, %Y')}")
    
    # Ensure current year is part of the query to prevent pulling 2025/2024 stale records
    if current_year not in clean_query:
        clean_query += f" {current_year}"

    print(f"[Anchored Search Query]: {clean_query}")

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(clean_query, max_results=max_results))
            if not results:
                return "No real-time search results found."

            formatted = []
            for r in results:
                title = r.get("title", "")
                snippet = r.get("body", "")
                formatted.append(f"Title: {title}\nSnippet: {snippet}")
            return "\n\n".join(formatted)
    except Exception as e:
        print(f"[Search Engine Error]: {e}")
        return "Search failed due to network timeout."