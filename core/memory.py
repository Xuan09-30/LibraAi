import os
import json
import sqlite3
import re
from datetime import datetime


class MemoryCore:
    def __init__(self, db_filename="assets/libra_memory.db", legacy_json="assets/user_memory.json"):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.db_path = os.path.join(project_root, db_filename)
        self.legacy_json_path = os.path.join(project_root, legacy_json)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._init_db()
        self._migrate_legacy_json()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initializes tables for structured facts and user preferences."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT DEFAULT 'general',
                    fact_text TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    pref_key TEXT PRIMARY KEY,
                    pref_value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _migrate_legacy_json(self):
        """One-time migration: imports existing assets/user_memory.json data into SQLite."""
        if os.path.exists(self.legacy_json_path):
            try:
                with open(self.legacy_json_path, "r", encoding="utf-8") as f:
                    legacy_data = json.load(f)

                # Migrate custom facts
                for fact in legacy_data.get("custom_facts", []):
                    self.add_fact(fact, category="imported")

                # Migrate music taste
                for music in legacy_data.get("music_taste", []):
                    self.add_fact(f"Likes music/artist: {music}", category="music")

                # Rename legacy file to avoid repeated migration
                os.rename(self.legacy_json_path, self.legacy_json_path + ".migrated")
                print("[Memory Core] Successfully migrated legacy JSON memory to SQLite.")
            except Exception as e:
                print(f"[Memory Migration Warning]: {e}")

    def add_fact(self, fact: str, category: str = "general") -> bool:
        """Stores a unique fact into SQLite, auto-categorizing if necessary."""
        clean_fact = fact.strip()
        if not clean_fact:
            return False

        # Auto-detect category from text
        f_lower = clean_fact.lower()
        if any(w in f_lower for w in ["music", "song", "band", "artist", "track"]):
            category = "music"
        elif any(w in f_lower for w in ["prefer", "like", "favorite", "love", "hate", "dislike"]):
            category = "preference"
        elif any(w in f_lower for w in ["name is", "live in", "work as", "study", "birthday"]):
            category = "profile"

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO facts (category, fact_text, created_at)
                    VALUES (?, ?, ?)
                """, (category, clean_fact, datetime.now().isoformat()))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"[Memory Insert Error]: {e}")
            return False

    def remove_fact(self, fact_query: str) -> bool:
        """Removes facts matching search words (e.g. 'forget my hobby')."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM facts WHERE fact_text LIKE ?
                """, (f"%{fact_query.strip()}%",))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"[Memory Delete Error]: {e}")
            return False

    def set_preference(self, key: str, value: str):
        """Sets or updates a key-value user preference."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO preferences (pref_key, pref_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(pref_key) DO UPDATE SET
                    pref_value=excluded.pref_value,
                    updated_at=excluded.updated_at
            """, (key.strip(), value.strip(), datetime.now().isoformat()))
            conn.commit()

    def get_context_summary(self, current_query: str = "") -> str:
        """
        Retrieves memory context.
        If current_query is provided, ranks facts by relevance to prevent context bloat.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Fetch fixed profile & preferences
            cursor.execute("SELECT pref_key, pref_value FROM preferences")
            prefs = [f"{k}: {v}" for k, v in cursor.fetchall()]

            # 2. Fetch all facts
            cursor.execute("SELECT category, fact_text FROM facts ORDER BY id DESC")
            all_facts = cursor.fetchall()

        if not all_facts and not prefs:
            return "No prior user preferences recorded."

        relevant_facts = []

        if current_query:
            # Extract keywords from the query
            words = set(re.findall(r"\w+", current_query.lower()))
            # Filter out common stop words
            words = {w for w in words if w not in {"what", "who", "where", "when", "how", "the", "a", "is", "my", "me", "can", "you", "tell"}}

            scored_facts = []
            for category, text in all_facts:
                fact_words = set(re.findall(r"\w+", text.lower()))
                overlap = len(words.intersection(fact_words))
                scored_facts.append((overlap, text))

            # Sort by keyword overlap descending, keep top 5
            scored_facts.sort(key=lambda x: x[0], reverse=True)
            relevant_facts = [text for score, text in scored_facts[:5] if score > 0]

        # If no specific query overlap, keep the 6 most recent facts
        if not relevant_facts:
            relevant_facts = [text for _, text in all_facts[:6]]

        summary_parts = []
        if prefs:
            summary_parts.append("Active Preferences: " + "; ".join(prefs))
        if relevant_facts:
            summary_parts.append("Relevant Stored Facts: " + "; ".join(relevant_facts))

        return "\n".join(summary_parts)