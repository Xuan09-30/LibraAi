import re
from typing import List, Dict, Any, Optional


WORD_ORDINALS = {
    "first": 0,
    "second": 1,
    "third": 2,
    "fourth": 3,
    "fifth": 4,
    "sixth": 5,
    "seventh": 6,
    "eighth": 7,
    "ninth": 8,
    "tenth": 9,
}


class SessionManager:
    """
    Manages short-term conversation candidate stacks and resolves natural language ordinals
    into indexed candidate records.
    """

    def __init__(self, max_candidates: int = 10):
        self.max_candidates = max_candidates
        self.candidates: List[Dict[str, Any]] = []

    def update_candidates(self, items: List[Dict[str, Any]]):
        """
        Updates the short-term candidate memory with structured place/search items.
        Keeps up to max_candidates items.
        """
        if not items:
            return

        cleaned_items = []
        for idx, item in enumerate(items[:self.max_candidates]):
            c = dict(item)
            c["index"] = idx
            cleaned_items.append(c)

        self.candidates = cleaned_items

    def clear_candidates(self):
        """Clears candidate stack."""
        self.candidates.clear()

    def get_candidates(self) -> List[Dict[str, Any]]:
        """Returns the current candidate stack."""
        return list(self.candidates)

    def resolve_ordinals(self, text: str) -> List[Dict[str, Any]]:
        """
        Parses natural language ordinals and numbered references from user queries:
          - Words: 'first' (0), 'second' (1), 'third' (2), 'fourth' (3), 'last' (-1)
          - Numeric formats: '1st', '2nd', '3rd', '4th'
          - Number prefixes: 'number 1', 'number 2', '#1', '#2', 'no. 1', 'no. 2'
          - Keywords: 'both' (0, 1), 'all' (all candidates)
        Returns the resolved list of candidate dictionaries.
        """
        if not self.candidates:
            return []

        t_lower = text.lower()
        indices: List[int] = []

        # Handle 'both' or 'the two'
        if re.search(r"\b(both|the\s+two)\b", t_lower):
            if len(self.candidates) >= 2:
                indices.extend([0, 1])
            elif len(self.candidates) == 1:
                indices.append(0)

        # Handle 'all'
        elif re.search(r"\b(all|every|each)\b", t_lower) and not re.search(r"\b(first|second|third|last|\d+)\b", t_lower):
            return list(self.candidates)

        # 1. Match word ordinals ("first", "second", "third", ...)
        for word, idx in WORD_ORDINALS.items():
            if re.search(rf"\b{word}\b", t_lower):
                # Check position of word in text to maintain order
                for match in re.finditer(rf"\b{word}\b", t_lower):
                    indices.append((match.start(), idx))

        # 2. Match "last" or "last one" / "last option"
        for match in re.finditer(r"\blast(?:\s+(?:one|option|candidate|place|item))?\b", t_lower):
            indices.append((match.start(), -1))

        # 3. Match numeric ordinals ("1st", "2nd", "3rd", "4th", ...)
        for match in re.finditer(r"\b(\d+)(?:st|nd|rd|th)\b", t_lower):
            num = int(match.group(1))
            indices.append((match.start(), num - 1))

        # 4. Match numbered references ("number 1", "number 2", "#1", "#2", "no. 1")
        for match in re.finditer(r"(?:number|no\.?|num\.?|#)\s*(\d+)\b", t_lower):
            num = int(match.group(1))
            indices.append((match.start(), num - 1))

        # If indices was populated with (pos, idx) tuples, sort by appearance in the text
        if indices and isinstance(indices[0], tuple):
            indices.sort(key=lambda x: x[0])
            raw_indices = [idx for _, idx in indices]
        else:
            raw_indices = indices

        # Normalize negative / out of bounds indices and deduplicate
        resolved: List[Dict[str, Any]] = []
        seen_indices = set()
        n = len(self.candidates)

        for idx in raw_indices:
            actual_idx = idx if idx >= 0 else (n + idx)
            if 0 <= actual_idx < n and actual_idx not in seen_indices:
                seen_indices.add(actual_idx)
                resolved.append(self.candidates[actual_idx])

        return resolved
