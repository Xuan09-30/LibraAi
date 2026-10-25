import requests
import urllib.parse

# Wikimedia Foundation User-Agent Policy requires an explicit identifier and contact/app info
HEADERS = {
    "User-Agent": "LibraAI_Assistant/1.0 (https://github.com/libra; contact@localhost)"
}

def get_entity_summary(entity_name: str) -> str:
    """
    Fetches a clean summary directly from Wikipedia's official REST API endpoint.
    Bypasses legacy wikipedia library JSONDecodeErrors and 403 blocks.
    """
    if not entity_name or not entity_name.strip():
        return ""

    # Guard against weather queries polluting Wikipedia knowledge searches
    weather_keywords = {"weather", "forecast", "rain", "temperature", "cloudy", "sunny", "precipitation"}
    if any(k in entity_name.lower() for k in weather_keywords):
        return ""

    clean_entity = entity_name.strip().replace(" ", "_")
    encoded_title = urllib.parse.quote(clean_entity)
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=6)
        
        # 1. Direct page match
        if response.status_code == 200:
            data = response.json()
            extract = data.get("extract", "").strip()
            if extract:
                return extract

        # 2. If direct title 404s, query OpenSearch to find the closest page title
        search_url = (
            f"https://en.wikipedia.org/w/api.php?action=opensearch&search="
            f"{urllib.parse.quote(entity_name)}&limit=1&namespace=0&format=json"
        )
        search_resp = requests.get(search_url, headers=HEADERS, timeout=6)
        
        if search_resp.status_code == 200:
            search_data = search_resp.json()
            if len(search_data) > 1 and search_data[1]:
                matched_title = search_data[1][0].replace(" ", "_")
                fallback_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(matched_title)}"
                fb_resp = requests.get(fallback_url, headers=HEADERS, timeout=6)
                if fb_resp.status_code == 200:
                    return fb_resp.json().get("extract", "").strip()

    except Exception as e:
        print(f"[Knowledge Agent Error]: {e}")

    return ""