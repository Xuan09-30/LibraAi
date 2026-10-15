import os
import json
import sqlite3
import sqlite_vec
import requests
from datetime import datetime


class SemanticMemory:
    """
    Hardened semantic vector memory powered by sqlite-vec and Ollama's nomic-embed-text.
    Maintains a SQLite database with facts and vec0 virtual table for low-latency KNN searches.
    """

    def __init__(
        self,
        db_filename: str = "assets/libra_memory.db",
        ollama_base_url: str = "http://localhost:11434",
        embed_model: str = "nomic-embed-text",
        dim: int = 768,
    ):
        if db_filename == ":memory:":
            self.db_path = ":memory:"
            self._shared_conn = None
        else:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            self.db_path = os.path.join(project_root, db_filename)
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._shared_conn = None

        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.embed_model = embed_model
        self.dim = dim

        self._init_db()
        self._backfill_missing_embeddings()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._shared_conn is None:
                conn = sqlite3.connect(":memory:")
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
                self._shared_conn = conn
            return self._shared_conn

        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn

    def _init_db(self):
        """Initializes tables for structured facts and vector index."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Check existing table schema and migrate if needed
        table_info = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='facts'"
        ).fetchone()
        if table_info:
            cols = [col[1] for col in cursor.execute("PRAGMA table_info(facts)").fetchall()]
            if "fact_text" in cols and "content" not in cols:
                cursor.execute("ALTER TABLE facts RENAME COLUMN fact_text TO content")

        # 1. Regular facts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Vector virtual table using vec0
        cursor.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_facts USING vec0(
                fact_id INTEGER PRIMARY KEY,
                embedding float[{self.dim}] distance_metric=cosine
            )
        """)

        # 3. Preferences table for key-value backwards compatibility
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                pref_key TEXT PRIMARY KEY,
                pref_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. Episodic conversation logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_text TEXT NOT NULL,
                assistant_text TEXT NOT NULL,
                route TEXT DEFAULT 'chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 5. Episodic vector index table using vec0
        cursor.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_episodes USING vec0(
                episode_id INTEGER PRIMARY KEY,
                embedding float[{self.dim}] distance_metric=cosine
            )
        """)

        conn.commit()
        if self.db_path != ":memory:":
            conn.close()

    def _backfill_missing_embeddings(self):
        """Checks if existing rows in `facts` lack an embedding in `vec_facts`. If so, embed and backfill them automatically."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.id, f.content
                FROM facts f
                LEFT JOIN vec_facts v ON f.id = v.fact_id
                WHERE v.fact_id IS NULL
            """)
            missing = cursor.fetchall()
            if missing:
                for fact_id, content in missing:
                    clean = (content or "").strip()
                    if clean:
                        emb = self.embed_text(clean)
                        if emb and any(emb):
                            cursor.execute(
                                "INSERT INTO vec_facts (fact_id, embedding) VALUES (?, ?)",
                                (fact_id, sqlite_vec.serialize_float32(emb))
                            )
                conn.commit()
            if self.db_path != ":memory:":
                conn.close()
        except Exception as e:
            print(f"[SemanticMemory Backfill Warning]: {e}")

    def embed_text(self, text: str) -> list[float]:
        """Queries Ollama /api/embeddings with model nomic-embed-text."""
        clean_text = text.strip()
        if not clean_text:
            return [0.0] * self.dim
        try:
            resp = requests.post(
                f"{self.ollama_base_url}/api/embeddings",
                json={
                    "model": self.embed_model,
                    "prompt": clean_text,
                    "keep_alive": "60m"
                },
                timeout=25
            )
            if resp.status_code == 200:
                data = resp.json()
                emb = data.get("embedding", [])
                if emb and len(emb) == self.dim:
                    return emb
            print(f"[SemanticMemory Embedding Warning]: HTTP {resp.status_code} - {resp.text}")
            return [0.0] * self.dim
        except Exception as e:
            print(f"[SemanticMemory Embedding Error]: {e}")
            return [0.0] * self.dim

    def remember_fact(self, fact: str, category: str = "user_fact") -> int:
        """Stores fact in `facts` and embedding in `vec_facts`. Returns inserted fact id."""
        clean_fact = fact.strip()
        if not clean_fact:
            return -1

        emb = self.embed_text(clean_fact)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO facts (content, category, created_at) VALUES (?, ?, ?)",
            (clean_fact, category, datetime.now().isoformat())
        )
        fact_id = cursor.lastrowid

        if emb and any(emb):
            cursor.execute(
                "INSERT INTO vec_facts (fact_id, embedding) VALUES (?, ?)",
                (fact_id, sqlite_vec.serialize_float32(emb))
            )
        conn.commit()
        if self.db_path != ":memory:":
            conn.close()
        return fact_id

    def recall_relevant(self, query: str, limit: int = 3, distance_threshold: float = 0.75) -> list[dict]:
        """Runs KNN vector search against `vec_facts` JOIN `facts` ORDER BY distance LIMIT k."""
        clean_query = query.strip()
        if not clean_query:
            return []

        emb = self.embed_text(clean_query)
        if not emb or not any(emb):
            return []

        conn = self._get_connection()
        cursor = conn.cursor()
        sql = """
            SELECT
                f.id,
                f.content,
                f.category,
                f.created_at,
                v.distance
            FROM vec_facts v
            JOIN facts f ON f.id = v.fact_id
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance ASC
        """
        cursor.execute(sql, (sqlite_vec.serialize_float32(emb), limit))
        rows = cursor.fetchall()

        results = []
        for r in rows:
            dist = float(r[4])
            if dist <= distance_threshold:
                results.append({
                    "id": r[0],
                    "content": r[1],
                    "category": r[2],
                    "created_at": r[3],
                    "distance": dist
                })

        if self.db_path != ":memory:":
            conn.close()
        return results

    def forget_fact(self, query: str, distance_threshold: float = 0.75) -> str | None:
        """Finds closest matching fact in `vec_facts`. If distance <= threshold, deletes the record from both tables and returns the purged text."""
        clean_query = query.strip()
        if not clean_query:
            return None

        emb = self.embed_text(clean_query)
        conn = self._get_connection()
        cursor = conn.cursor()

        purged_text = None

        if emb and any(emb):
            sql = """
                SELECT f.id, f.content, v.distance
                FROM vec_facts v
                JOIN facts f ON f.id = v.fact_id
                WHERE v.embedding MATCH ? AND k = 1
                ORDER BY v.distance ASC
            """
            cursor.execute(sql, (sqlite_vec.serialize_float32(emb),))
            match = cursor.fetchone()
            if match:
                fact_id, content, dist = match
                if dist <= distance_threshold:
                    cursor.execute("DELETE FROM vec_facts WHERE fact_id = ?", (fact_id,))
                    cursor.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
                    conn.commit()
                    purged_text = content

        # Substring / exact fallback if vector match was slightly above threshold or empty
        if purged_text is None:
            cursor.execute("SELECT id, content FROM facts WHERE content LIKE ? LIMIT 1", (f"%{clean_query}%",))
            sub_match = cursor.fetchone()
            if sub_match:
                fact_id, content = sub_match
                cursor.execute("DELETE FROM vec_facts WHERE fact_id = ?", (fact_id,))
                cursor.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
                conn.commit()
                purged_text = content

        if self.db_path != ":memory:":
            conn.close()
        return purged_text

    def get_profile_summary(self, limit: int = 10) -> list[str]:
        """Returns the most recent facts stored about the user."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM facts ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            if self.db_path != ":memory:":
                conn.close()
            return [r[0] for r in rows]
        except Exception as e:
            print(f"[SemanticMemory Profile Error]: {e}")
            return []

    def log_episode(self, user_text: str, assistant_text: str, route: str = "chat") -> int:
        """
        Logs a full conversational turn into the episodic memory database
        and indexes its embedding for semantic conversational recall.
        """
        clean_user = (user_text or "").strip()
        clean_asst = (assistant_text or "").strip()
        if not clean_user and not clean_asst:
            return -1

        summary_text = f"User: {clean_user} | Assistant: {clean_asst}"
        emb = self.embed_text(summary_text)

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO episodes (user_text, assistant_text, route) VALUES (?, ?, ?)",
                (clean_user, clean_asst, route)
            )
            episode_id = cursor.lastrowid
            if emb and any(emb):
                cursor.execute(
                    "INSERT INTO vec_episodes (episode_id, embedding) VALUES (?, ?)",
                    (episode_id, sqlite_vec.serialize_float32(emb))
                )
            conn.commit()
            return episode_id
        except Exception as e:
            print(f"[SemanticMemory Log Episode Error]: {e}")
            return -1
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def recall_episodes(self, query: str, limit: int = 2, distance_threshold: float = 0.65) -> list[dict]:
        """
        Retrieves the most semantically relevant past conversational episodes.
        """
        clean_q = (query or "").strip()
        if not clean_q:
            return []

        emb = self.embed_text(clean_q)
        if not emb or not any(emb):
            return []

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                SELECT e.id, e.user_text, e.assistant_text, e.route, v.distance, e.created_at
                FROM vec_episodes v
                JOIN episodes e ON e.id = v.episode_id
                WHERE v.embedding MATCH ? AND k = ?
            """, (sqlite_vec.serialize_float32(emb), limit * 2))
            rows = cursor.fetchall()

            episodes = []
            for r in rows:
                dist = float(r[4])
                if dist <= distance_threshold:
                    episodes.append({
                        "id": r[0],
                        "user_text": r[1],
                        "assistant_text": r[2],
                        "route": r[3],
                        "distance": dist,
                        "created_at": r[5]
                    })
                if len(episodes) >= limit:
                    break
            return episodes
        except Exception as e:
            print(f"[SemanticMemory Recall Episodes Error]: {e}")
            return []
        finally:
            if self.db_path != ":memory:":
                conn.close()

    # Backwards compatibility methods
    def add_fact(self, fact: str, category: str = "general") -> bool:
        fid = self.remember_fact(fact, category)
        return fid > 0

    def remove_fact(self, fact_query: str) -> bool:
        purged = self.forget_fact(fact_query)
        return purged is not None

    def get_context_summary(self, current_query: str = "") -> str:
        if current_query:
            relevant = self.recall_relevant(current_query, limit=3)
            facts = [r["content"] for r in relevant]
            if not facts:
                facts = self.get_profile_summary(limit=3)
        else:
            facts = self.get_profile_summary(limit=6)

        if not facts:
            return "No prior user preferences recorded."
        return "Relevant Stored Facts: " + "; ".join(facts)

    def set_preference(self, key: str, value: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO preferences (pref_key, pref_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(pref_key) DO UPDATE SET
                pref_value=excluded.pref_value,
                updated_at=excluded.updated_at
        """, (key.strip(), value.strip(), datetime.now().isoformat()))
        conn.commit()
        if self.db_path != ":memory:":
            conn.close()


# Backward compatibility alias
MemoryCore = SemanticMemory