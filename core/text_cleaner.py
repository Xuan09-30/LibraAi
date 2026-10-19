import re
import unicodedata


def normalize_for_tts(text: str) -> str:
    """
    Normalizes conversational text into phonemization-ready text for Kokoro-82M TTS.
    Expands URLs, temperatures, distances, currencies, symbols, strips markdown/XML artifacts,
    and collapses whitespace.
    """
    if not text or not isinstance(text, str):
        return ""

    t = text

    # 1. Strip XML / HTML tags (e.g. <untrusted_web_search_results>, <user_context>)
    t = re.sub(r"<[^>]+>", " ", t)

    # 2. URLs: Replace https?://... or www.... with 'link'
    t = re.sub(r"https?://[^\s,]+|www\.[^\s,]+", "link", t)

    # 3. Currencies: RM and $
    t = re.sub(r"\bRM\s*(\d+(?:\.\d+)?)\b", r"\1 ringgit", t, flags=re.IGNORECASE)
    t = re.sub(r"\$\s*(\d+(?:\.\d+)?)\b", r"\1 dollars", t)

    # 4. Temperatures: Celsius and Fahrenheit
    t = re.sub(r"(\d+(?:\.\d+)?)\s*°?\s*C\b", r"\1 degrees Celsius", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*°?\s*F\b", r"\1 degrees Fahrenheit", t)

    # 5. Distances / Units: kilometers and meters
    t = re.sub(r"(\d+(?:\.\d+)?)\s*km\b", r"\1 kilometers", t, flags=re.IGNORECASE)
    # Match meters e.g. '500m' or '500 m' without matching 'am' / 'pm'
    t = re.sub(r"(?<![a-zA-Z])(\d+(?:\.\d+)?)\s*m\b(?![a-zA-Z])", r"\1 meters", t)

    # 6. Symbols
    t = t.replace("&", " and ")
    t = t.replace("%", " percent ")
    t = t.replace("@", " at ")
    t = t.replace("#", " number ")
    t = t.replace("°", " degrees ")

    # 7. Markdown and citation bracket stripping
    # Remove code blocks
    t = re.sub(r"```.*?```", " ", t, flags=re.DOTALL)
    # Strip citation brackets e.g. [TechPowerUp] -> TechPowerUp, [Source] -> web sources
    t = re.sub(r"\[\s*Source\s*\]", "web sources", t, flags=re.IGNORECASE)
    t = re.sub(r"\[\s*([^\]]+?)\s*\]", r"\1", t)
    # Remove inline backticks, asterisks, hashes, blockquotes, bullets
    t = re.sub(r"[`*#_>]", " ", t)
    t = re.sub(r"^\s*[-+]\s+", " ", t, flags=re.MULTILINE)

    # 8. Collapse whitespace and redundant punctuation spaces
    t = re.sub(r"\s+", " ", t).strip()
    # Clean up double punctuation spaces (e.g., " . " -> ". ")
    t = re.sub(r"\s+([,\.!\?])", r"\1", t)

    # 9. Transliterate non-ASCII accents/diacritics to safe ASCII
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode('utf-8')

    return t
