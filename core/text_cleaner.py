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


def clean_for_dictation(text: str) -> str:
    """
    Cleans and structures transcribed speech for direct cursor dictation typing.
    1. Strips verbal filler words ('um', 'uh', 'wait no', 'ah', 'er').
    2. Translates spoken case conversions ('camel case user profile' -> userProfile).
    3. Normalizes technical terms ('pyqt six' -> PyQt6, 'c plus plus' -> C++).
    4. Converts spoken punctuation commands ('new line' -> newline, 'comma' -> ,).
    """
    if not text or not isinstance(text, str):
        return ""

    t = text.strip()

    # 1. Handle spoken "wait no" (erases preceding thought if near start/comma)
    t = re.sub(r"^.*?\bwait(?:,\s*|\s+)no\b\s*", "", t, flags=re.IGNORECASE)

    # 2. Convert spoken punctuation commands first so boundaries are punctuation
    punct_map = [
        (r"\b(?:new\s*paragraph)\b", "\n\n"),
        (r"\b(?:new\s*line|newline)\b", "\n"),
        (r"\b(?:comma)\b", ","),
        (r"\b(?:period|full\s*stop)\b", "."),
        (r"\b(?:question\s*mark)\b", "?"),
        (r"\b(?:exclamation\s*mark|exclamation\s*point)\b", "!"),
        (r"\b(?:colon)\b", ":"),
        (r"\b(?:semicolon)\b", ";"),
        (r"\b(?:open\s*parenthesis|open\s*paren)\b", "("),
        (r"\b(?:close\s*parenthesis|close\s*paren)\b", ")"),
        (r"\b(?:open\s*bracket)\b", "["),
        (r"\b(?:close\s*bracket)\b", "]"),
        (r"\b(?:open\s*brace|open\s*curly)\b", "{"),
        (r"\b(?:close\s*brace|close\s*curly)\b", "}"),
    ]
    for pattern, rep in punct_map:
        t = re.sub(pattern, rep, t, flags=re.IGNORECASE)

    # 3. Strip verbal fillers
    filler_patterns = [
        r"\b(?:um+|uh+|er+|ah+|like\s+um|like\s+uh)\b",
        r"\b(?:you\s+know\s+what\s+i\s+mean)\b",
    ]
    for fp in filler_patterns:
        t = re.sub(fp, "", t, flags=re.IGNORECASE)

    # 4. Spoken case converters:
    PUNCT_OR_END = r"(?=[,\.\?!:;\(\)\[\]\{\}\n]|$)"
    def _to_camel_case(match):
        raw_words = match.group(1).strip().split()
        if not raw_words:
            return ""
        first = raw_words[0].lower()
        rest = "".join(w.capitalize() for w in raw_words[1:])
        return first + rest

    t = re.sub(
        r"\b(?:camel\s*case)\s+([a-zA-Z0-9_\s]+?)" + PUNCT_OR_END,
        _to_camel_case,
        t,
        flags=re.IGNORECASE
    )

    # snake case word1 word2 ...
    def _to_snake_case(match):
        raw_words = match.group(1).strip().split()
        return "_".join(w.lower() for w in raw_words)

    t = re.sub(
        r"\b(?:snake\s*case)\s+([a-zA-Z0-9_\s]+?)" + PUNCT_OR_END,
        _to_snake_case,
        t,
        flags=re.IGNORECASE
    )

    # kebab case word1 word2 ...
    def _to_kebab_case(match):
        raw_words = match.group(1).strip().split()
        return "-".join(w.lower() for w in raw_words)

    t = re.sub(
        r"\b(?:kebab\s*case)\s+([a-zA-Z0-9_\s]+?)" + PUNCT_OR_END,
        _to_kebab_case,
        t,
        flags=re.IGNORECASE
    )

    # pascal case word1 word2 ...
    def _to_pascal_case(match):
        raw_words = match.group(1).strip().split()
        return "".join(w.capitalize() for w in raw_words)

    t = re.sub(
        r"\b(?:pascal\s*case)\s+([a-zA-Z0-9_\s]+?)" + PUNCT_OR_END,
        _to_pascal_case,
        t,
        flags=re.IGNORECASE
    )

    # 5. Technical vocabulary heuristics
    tech_replacements = [
        (r"\b(?:pyqt\s*six|pyqt\s*6|pie\s*cue\s*tee\s*six|pie\s*cute\s*six)\b", "PyQt6"),
        (r"\b(?:pyqt\s*five|pyqt\s*5|pie\s*cue\s*tee\s*five|pie\s*cute\s*five)\b", "PyQt5"),
        (r"\bc\s*plus\s*plus\b", "C++"),
        (r"\bc\s*sharp\b", "C#"),
        (r"\bdot\s*net\b", ".NET"),
        (r"\b(?:node\s*j\s*s|node\s*js)\b", "Node.js"),
        (r"\b(?:next\s*j\s*s|next\s*js)\b", "Next.js"),
        (r"\b(?:react\s*j\s*s|react\s*js)\b", "React"),
        (r"\btype\s*script\b", "TypeScript"),
        (r"\bjava\s*script\b", "JavaScript"),
        (r"\bopen\s*ai\b", "OpenAI"),
        (r"\bfast\s*api\b", "FastAPI"),
        (r"\bgit\s*hub\b", "GitHub"),
        (r"\bv\s*ram\b", "VRAM"),
        (r"\br\s*t\s*x\b", "RTX"),
        (r"\bg\s*p\s*u\b", "GPU"),
        (r"\bc\s*p\s*u\b", "CPU"),
        (r"\br\s*a\s*m\b", "RAM"),
        (r"\bs\s*q\s*l\s*lite\b", "SQLite"),
        (r"\bsqlite\s*3\b", "SQLite3"),
    ]
    for pattern, rep in tech_replacements:
        t = re.sub(pattern, rep, t, flags=re.IGNORECASE)

    # Clean whitespace around punctuation
    t = re.sub(r"\s+([,\.\?!:;\)])", r"\1", t)
    t = re.sub(r"([\(\[\{])\s+", r"\1", t)
    t = re.sub(r"[ \t]+", " ", t).strip(" \t\r")

    return t



class DictationCleaner:
    @staticmethod
    def normalize(text: str) -> str:
        return clean_for_dictation(text)
