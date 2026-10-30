import os

import re

import json

import sqlite3

import sqlite_vec

import requests

from datetime import datetime

from typing import Optional, List, Dict, Any, Tuple

try:

    import yaml

    YAML_AVAILABLE = True

except ImportError:

    yaml = None

    YAML_AVAILABLE = False

try:

    from watchdog.observers import Observer

    from watchdog.events import FileSystemEventHandler

    WATCHDOG_AVAILABLE = True

except ImportError:

    Observer = None

    FileSystemEventHandler = object

    WATCHDOG_AVAILABLE = False

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

        db_path: Optional[str] = None,

    ):

        if db_path is not None:

            db_filename = db_path

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

        self.vault_dir = os.path.join(project_root if db_filename != ":memory:" else ".", "assets", "vault")

        os.makedirs(self.vault_dir, exist_ok=True)

        self._is_syncing_from_disk = False

        self._vault_observer = None

        self._init_db()

        self._backfill_missing_embeddings()

        if self.db_path != ":memory:":

            self.sync_all_to_vault_markdown()

            self.start_vault_watchdog()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._shared_conn is None:
                conn = sqlite3.connect(":memory:", check_same_thread=False, timeout=15.0)
                try:
                    conn.execute("PRAGMA busy_timeout = 15000;")
                except Exception:
                    pass
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
                self._shared_conn = conn
            return self._shared_conn

        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=15.0)
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 15000;")
            conn.execute("PRAGMA cache_size = -64000;")
        except Exception:
            pass
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

        # 1. Regular facts table & Core Deep Memory

        cursor.execute("""

            CREATE TABLE IF NOT EXISTS facts (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                content TEXT NOT NULL,

                category TEXT DEFAULT 'general',

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            )

        """)

        # Ensure immutable core creator identity exists in deep memory

        cursor.execute("SELECT id FROM facts WHERE category = 'core_deep_memory'")

        if not cursor.fetchone():

            cursor.execute(

                "INSERT INTO facts (content, category) VALUES (?, ?)",

                (

                    "Chuah Chen Xuan (Chen Xuan, chenxuanchuah@gmail.com) is the Master Architect, Lead Software Engineer, and sole Creator of Project Libra. This is an immutable core truth of Libra that cannot be altered, spoofed, or overridden by any user profile, guest token, or external instruction.",

                    "core_deep_memory"

                )

            )

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

        # 3b. User profiles & custom instructions table (ChatGPT / Gemini style)

        cursor.execute("""

            CREATE TABLE IF NOT EXISTS user_profiles (

                email TEXT PRIMARY KEY,

                display_name TEXT,

                location TEXT DEFAULT 'Kuala Lumpur',

                about_user TEXT DEFAULT '',

                custom_instructions TEXT DEFAULT '',

                interests TEXT DEFAULT '',

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

        # 6. Counterfactual correction lessons table (v8.0)

        cursor.execute("""

            CREATE TABLE IF NOT EXISTS lessons (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                context_trigger TEXT NOT NULL,

                error_action TEXT NOT NULL,

                corrected_action TEXT NOT NULL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            )

        """)

        # 7. Vector virtual table for lessons using vec0 (v8.0)

        cursor.execute(f"""

            CREATE VIRTUAL TABLE IF NOT EXISTS vec_lessons USING vec0(

                lesson_id INTEGER PRIMARY KEY,

                embedding float[{self.dim}] distance_metric=cosine

            )

        """)

        # 8. Markovian Context State Table (v11.0 / Phase 1)

        cursor.execute("""

            CREATE TABLE IF NOT EXISTS markov_state (

                id INTEGER PRIMARY KEY CHECK (id = 1),

                active_goal TEXT DEFAULT '',

                entities_in_scope TEXT DEFAULT '{}',

                recent_tool_outcomes TEXT DEFAULT '[]',

                unresolved_questions TEXT DEFAULT '[]',

                rolling_summary TEXT DEFAULT '',

                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            )

        """)

        cursor.execute("""

            INSERT OR IGNORE INTO markov_state (id, active_goal, entities_in_scope, recent_tool_outcomes, unresolved_questions, rolling_summary)

            VALUES (1, '', '{}', '[]', '[]', '')

        """)

        # 9. H-MEM Semantic Facts Table (v11.0 / Phase 1 & Phase 11 Vault)

        cursor.execute("""

            CREATE TABLE IF NOT EXISTS semantic_facts (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                entity TEXT NOT NULL,

                relation TEXT NOT NULL,

                value TEXT NOT NULL,

                category TEXT DEFAULT 'general',

                pinned INTEGER DEFAULT 0,

                confidence REAL DEFAULT 1.0,

                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(entity, relation)

            )

        """)

        # Migration: Ensure category and pinned exist on existing databases

        try:

            sf_cols = [c[1] for c in cursor.execute("PRAGMA table_info(semantic_facts)").fetchall()]

            if "category" not in sf_cols:

                cursor.execute("ALTER TABLE semantic_facts ADD COLUMN category TEXT DEFAULT 'general'")

            if "pinned" not in sf_cols:

                cursor.execute("ALTER TABLE semantic_facts ADD COLUMN pinned INTEGER DEFAULT 0")

        except Exception as e:

            print(f"[SemanticMemory Migration Warning]: {e}")

        # FTS5 Virtual Table for Instant BM25 Search

        try:

            cursor.execute("""

                CREATE VIRTUAL TABLE IF NOT EXISTS semantic_facts_fts USING fts5(

                    value,

                    entity,

                    relation,

                    category,

                    content='semantic_facts',

                    content_rowid='id'

                )

            """)

            # Triggers to keep FTS in sync with semantic_facts

            cursor.execute("""

                CREATE TRIGGER IF NOT EXISTS semantic_facts_ai AFTER INSERT ON semantic_facts BEGIN

                    INSERT INTO semantic_facts_fts(rowid, value, entity, relation, category)

                    VALUES (new.id, new.value, new.entity, new.relation, new.category);

                END;

            """)

            cursor.execute("""

                CREATE TRIGGER IF NOT EXISTS semantic_facts_ad AFTER DELETE ON semantic_facts BEGIN

                    INSERT INTO semantic_facts_fts(semantic_facts_fts, rowid, value, entity, relation, category)

                    VALUES('delete', old.id, old.value, old.entity, old.relation, old.category);

                END;

            """)

            cursor.execute("""

                CREATE TRIGGER IF NOT EXISTS semantic_facts_au AFTER UPDATE ON semantic_facts BEGIN

                    INSERT INTO semantic_facts_fts(semantic_facts_fts, rowid, value, entity, relation, category)

                    VALUES('delete', old.id, old.value, old.entity, old.relation, old.category);

                    INSERT INTO semantic_facts_fts(rowid, value, entity, relation, category)

                    VALUES (new.id, new.value, new.entity, new.relation, new.category);

                END;

            """)

            # Rebuild external-content FTS5 index so triggers never fail with malformed index

            cursor.execute("INSERT INTO semantic_facts_fts(semantic_facts_fts) VALUES('rebuild')")

        except Exception as e:

            print(f"[SemanticMemory FTS Warning]: {e}")

        # 10. PreAct Action Macros Table (v11.0 / Phase 3)

        cursor.execute("""

            CREATE TABLE IF NOT EXISTS action_macros (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                intent_signature TEXT UNIQUE,

                normalized_trigger TEXT NOT NULL,

                tool_chain_json TEXT NOT NULL,

                success_count INTEGER DEFAULT 1,

                avg_latency_ms REAL DEFAULT 0.0,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            )

        """)

        # 11. Screenpipe-Style Screen Timeline Ring Buffer Table (Phase 8)

        cursor.execute("""

            CREATE TABLE IF NOT EXISTS screen_timeline (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                window_title TEXT,

                app_name TEXT,

                ocr_summary TEXT,

                dhash TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            )

        """)

        # 12. Multi-Chat Sessions Table (Phase 10)

        cursor.execute("""

            CREATE TABLE IF NOT EXISTS chat_sessions (

                session_id TEXT PRIMARY KEY,

                title TEXT NOT NULL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                client_scope TEXT DEFAULT 'remote_web',

                total_input_tokens INTEGER DEFAULT 0,

                total_output_tokens INTEGER DEFAULT 0,

                total_saved_tokens INTEGER DEFAULT 0,

                turn_count INTEGER DEFAULT 0,

                user_email TEXT DEFAULT ''

            )

        """)

        # Schema migration check: ensure user_email exists in chat_sessions

        try:

            cols = [col[1] for col in cursor.execute("PRAGMA table_info(chat_sessions)").fetchall()]

            if "user_email" not in cols:

                cursor.execute("ALTER TABLE chat_sessions ADD COLUMN user_email TEXT DEFAULT ''")

        except Exception:

            pass

        cursor.execute("""

            INSERT OR IGNORE INTO chat_sessions (session_id, title, client_scope, user_email)

            VALUES ('default', 'Primary Desktop Chat', 'local_desktop', '')

        """)

        # 13. Per-Session Messages Table with Token Telemetry (Phase 10)

        cursor.execute("""

            CREATE TABLE IF NOT EXISTS session_messages (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                session_id TEXT NOT NULL,

                role TEXT NOT NULL,

                content TEXT NOT NULL,

                input_tokens INTEGER DEFAULT 0,

                output_tokens INTEGER DEFAULT 0,

                tokens_per_sec REAL DEFAULT 0.0,

                model_used TEXT DEFAULT '',

                latency_ms REAL DEFAULT 0.0,

                saved_tokens INTEGER DEFAULT 0,

                tool_used TEXT DEFAULT '',

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE

            )

        """)

        # 14. Guest Access Tokens Table (Role-Based Access Control)

        cursor.execute("""

            CREATE TABLE IF NOT EXISTS guest_tokens (

                token TEXT PRIMARY KEY,

                label TEXT NOT NULL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                expires_at TIMESTAMP NULL,

                revoked INTEGER DEFAULT 0,

                created_by TEXT DEFAULT 'host'

            )

        """)

        # 15. Registered Users Table (Multi-User Email Isolation)

        cursor.execute("""

            CREATE TABLE IF NOT EXISTS registered_users (

                email TEXT PRIMARY KEY,

                display_name TEXT,

                role TEXT DEFAULT 'guest',

                unique_token TEXT UNIQUE NOT NULL,

                totp_secret TEXT DEFAULT '',

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            )

        """)

        # Migration: ensure totp_secret exists in registered_users

        try:

            cols = [col[1] for col in cursor.execute("PRAGMA table_info(registered_users)").fetchall()]

            if "totp_secret" not in cols:

                cursor.execute("ALTER TABLE registered_users ADD COLUMN totp_secret TEXT DEFAULT ''")

        except Exception:

            pass

        # 16. Email Verification Codes (OTP) Table

        cursor.execute("""

            CREATE TABLE IF NOT EXISTS email_verifications (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                email TEXT NOT NULL,

                code TEXT NOT NULL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                expires_at TIMESTAMP NOT NULL,

                attempts INTEGER DEFAULT 0,

                verified INTEGER DEFAULT 0

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

    def recall_relevant(self, query: str, limit: int = 3, distance_threshold: float = 0.50) -> list[dict]:

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

    def recall_episodes(self, query: str, limit: int = 2, distance_threshold: float = 0.45) -> list[dict]:

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

            seen_texts = set()

            for r in rows:

                dist = float(r[4])

                if dist <= distance_threshold:

                    asst_clean = (r[2] or "").strip().lower()

                    if asst_clean in seen_texts:

                        continue

                    seen_texts.add(asst_clean)

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

    def get_preference(self, key: str, default: Optional[str] = None) -> Optional[str]:

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("SELECT pref_value FROM preferences WHERE pref_key = ?", (key.strip(),))

            row = cursor.fetchone()

            return row[0] if row else default

        except Exception:

            return default

        finally:

            if self.db_path != ":memory:":

                conn.close()

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

    def record_correction(self, trigger_query: str, mistake: str, correction: str) -> int:

        """

        Counterfactual Correction Memory (v8.0):

        Records an explicit user operational correction in `lessons`, indexes its vector

        in `vec_lessons`, and appends a structured rule entry to `assets/LESSONS.md`.

        """

        clean_trigger = (trigger_query or "").strip()

        clean_mistake = (mistake or "").strip()

        clean_correction = (correction or "").strip()

        if not clean_trigger or not clean_correction:

            return -1

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        lessons_md_path = os.path.join(project_root, "assets", "LESSONS.md")

        os.makedirs(os.path.dirname(lessons_md_path), exist_ok=True)

        if not os.path.isfile(lessons_md_path):

            with open(lessons_md_path, "w", encoding="utf-8") as f:

                f.write("# Project Libra — Counterfactual Correction & Operational Lesson Memory\n\n")

        entry_line = (

            f"- **Trigger**: `{clean_trigger}` | **Avoid**: `{clean_mistake}` "

            f"| **Corrected Action**: `{clean_correction}` ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"

        )

        try:

            with open(lessons_md_path, "a", encoding="utf-8") as f:

                f.write(entry_line)

        except Exception as e:

            print(f"[SemanticMemory LESSONS.md Write Warning]: {e}")

        emb = self.embed_text(clean_trigger)

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute(

                "INSERT INTO lessons (context_trigger, error_action, corrected_action, created_at) VALUES (?, ?, ?, ?)",

                (clean_trigger, clean_mistake, clean_correction, datetime.now().isoformat())

            )

            lesson_id = cursor.lastrowid

            if emb and any(emb):

                cursor.execute(

                    "INSERT INTO vec_lessons (lesson_id, embedding) VALUES (?, ?)",

                    (lesson_id, sqlite_vec.serialize_float32(emb))

                )

            conn.commit()

            return lesson_id

        except Exception as e:

            print(f"[SemanticMemory Record Correction Error]: {e}")

            return -1

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def recall_lesson_objects(self, query: str, threshold: float = 0.70) -> list[dict]:

        """Returns structured lesson dictionaries matching `query` via vector KNN or exact/substring match."""

        clean_q = (query or "").strip()

        if not clean_q:

            return []

        matched_lessons = []

        seen_ids = set()

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            # 1. Exact or substring trigger match (deterministic & offline resilient)

            cursor.execute(

                "SELECT id, context_trigger, error_action, corrected_action FROM lessons ORDER BY id DESC"

            )

            all_rows = cursor.fetchall()

            if not all_rows:

                return []

            q_lower = clean_q.lower()

            q_tokens = set(re.findall(r"[a-z0-9]+", q_lower))

            for lid, trig, err_act, corr_act in all_rows:

                t_lower = (trig or "").lower()

                t_tokens = set(re.findall(r"[a-z0-9]+", t_lower))

                overlap = len(q_tokens & t_tokens) / max(len(t_tokens), 1) if t_tokens else 0.0

                if t_lower and (t_lower == q_lower or t_lower in q_lower or q_lower in t_lower or overlap >= 0.6):

                    matched_lessons.append({

                        "id": lid,

                        "context_trigger": trig,

                        "error_action": err_act,

                        "corrected_action": corr_act,

                        "distance": 0.0,

                        "rule": f"[Rule: In past runs, the user corrected this action with: {corr_act} (avoid: {err_act})]"

                    })

                    seen_ids.add(lid)

            if matched_lessons:

                return matched_lessons

            # Only invoke vector KNN if query shares at least one content token with a stored lesson

            all_lesson_tokens = set()

            for _, trig, err_act, _ in all_rows:

                all_lesson_tokens.update(re.findall(r"[a-z0-9]{3,}", f"{trig} {err_act}".lower()))

            if not (q_tokens & all_lesson_tokens):

                return []

            # 2. Vector KNN search against vec_lessons

            emb = self.embed_text(clean_q)

            if emb and any(emb):

                sql = """

                    SELECT l.id, l.context_trigger, l.error_action, l.corrected_action, v.distance

                    FROM vec_lessons v

                    JOIN lessons l ON l.id = v.lesson_id

                    WHERE v.embedding MATCH ? AND k = 3

                    ORDER BY v.distance ASC

                """

                cursor.execute(sql, (sqlite_vec.serialize_float32(emb),))

                for lid, trig, err_act, corr_act, dist in cursor.fetchall():

                    if lid not in seen_ids and float(dist) <= threshold:

                        matched_lessons.append({

                            "id": lid,

                            "context_trigger": trig,

                            "error_action": err_act,

                            "corrected_action": corr_act,

                            "distance": float(dist),

                            "rule": f"[Rule: In past runs, the user corrected this action with: {corr_act} (avoid: {err_act})]"

                        })

                        seen_ids.add(lid)

            return matched_lessons

        except Exception as e:

            print(f"[SemanticMemory Recall Lessons Error]: {e}")

            return matched_lessons

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def recall_applicable_lessons(self, query: str, threshold: float = 0.70) -> list[str]:

        """

        Scans `vec_lessons` (and exact triggers) during query planning.

        Returns a list of override strings:

        `[Rule: In past runs, the user corrected this action with: ...]`.

        """

        objs = self.recall_lesson_objects(query, threshold=threshold)

        return [o["rule"] for o in objs]

    # -------------------------------------------------------------

    # MARKOVIAN CONTEXT STATE & H-MEM CONSOLIDATION (Phase 1)

    # -------------------------------------------------------------

    def get_markov_state(self) -> dict:

        """

        Retrieves the compact Markovian state object:

        {"active_goal": str, "entities_in_scope": dict, "recent_tool_outcomes": list,

         "unresolved_questions": list, "rolling_summary": str, "updated_at": str}

        """

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute(

                "SELECT active_goal, entities_in_scope, recent_tool_outcomes, unresolved_questions, rolling_summary, updated_at "

                "FROM markov_state WHERE id = 1"

            )

            row = cursor.fetchone()

            if not row:

                return {

                    "active_goal": "",

                    "entities_in_scope": {},

                    "recent_tool_outcomes": [],

                    "unresolved_questions": [],

                    "rolling_summary": "",

                    "updated_at": datetime.now().isoformat()

                }

            active_goal, entities_raw, tool_raw, unres_raw, summary, updated_at = row

            try:

                entities = json.loads(entities_raw) if entities_raw else {}

            except Exception:

                entities = {}

            try:

                recent_tools = json.loads(tool_raw) if tool_raw else []

            except Exception:

                recent_tools = []

            try:

                unresolved = json.loads(unres_raw) if unres_raw else []

            except Exception:

                unresolved = []

            return {

                "active_goal": active_goal or "",

                "entities_in_scope": entities,

                "recent_tool_outcomes": recent_tools,

                "unresolved_questions": unresolved,

                "rolling_summary": summary or "",

                "updated_at": updated_at or datetime.now().isoformat()

            }

        except Exception as e:

            print(f"[SemanticMemory get_markov_state Error]: {e}")

            return {

                "active_goal": "",

                "entities_in_scope": {},

                "recent_tool_outcomes": [],

                "unresolved_questions": [],

                "rolling_summary": "",

                "updated_at": datetime.now().isoformat()

            }

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def update_markov_state(self, state: dict) -> bool:

        """Updates the singleton Markovian context state row."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            active_goal = state.get("active_goal", "")

            entities = json.dumps(state.get("entities_in_scope", {}))

            recent_tools = json.dumps(state.get("recent_tool_outcomes", []))

            unres = json.dumps(state.get("unresolved_questions", []))

            summary = state.get("rolling_summary", "")

            cursor.execute("""

                INSERT INTO markov_state (id, active_goal, entities_in_scope, recent_tool_outcomes, unresolved_questions, rolling_summary, updated_at)

                VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)

                ON CONFLICT(id) DO UPDATE SET

                    active_goal=excluded.active_goal,

                    entities_in_scope=excluded.entities_in_scope,

                    recent_tool_outcomes=excluded.recent_tool_outcomes,

                    unresolved_questions=excluded.unresolved_questions,

                    rolling_summary=excluded.rolling_summary,

                    updated_at=CURRENT_TIMESTAMP

            """, (active_goal, entities, recent_tools, unres, summary))

            conn.commit()

            return True

        except Exception as e:

            print(f"[SemanticMemory update_markov_state Error]: {e}")

            return False

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def fold_conversation_into_markov(

        self,

        turns_to_fold: Optional[list] = None,

        current_goal: str = "",

        tool_outcomes: Optional[list] = None,

        history: Optional[list] = None

    ) -> dict:

        """

        Folds the oldest turns into the Markovian state object:

        - Compresses turns into rolling_summary.

        - Extracts prominent entities.

        - Updates recent tool outcomes (capped at last 5).

        """

        if turns_to_fold is None and history is not None:

            turns_to_fold = history

        if turns_to_fold is None:

            turns_to_fold = []

        normalized_turns = []

        for t in turns_to_fold:

            if isinstance(t, dict):

                normalized_turns.append(t)

            elif isinstance(t, (tuple, list)) and len(t) >= 2:

                normalized_turns.append({"role": "user", "content": t[0]})

                normalized_turns.append({"role": "assistant", "content": t[1]})

        turns_to_fold = normalized_turns

        current_state = self.get_markov_state()

        if current_goal:

            current_state["active_goal"] = current_goal

        if tool_outcomes:

            existing_tools = current_state.get("recent_tool_outcomes", [])

            existing_tools.extend(tool_outcomes)

            current_state["recent_tool_outcomes"] = existing_tools[-5:]

        entities = current_state.get("entities_in_scope", {})

        summary_lines = []

        if current_state.get("rolling_summary"):

            summary_lines.append(current_state["rolling_summary"])

        for turn in turns_to_fold:

            role = turn.get("role", "user")

            content = (turn.get("content") or "").strip()

            if not content:

                continue

            # Extract simple entities (e.g. apps, games, names, foods)

            lower = content.lower()

            if "chrome" in lower:

                entities["browser"] = "Google Chrome"

            if "spotify" in lower:

                entities["media_player"] = "Spotify"

            for g_key, g_val in [

                ("valorant", "Valorant"),

                ("counter-strike", "Counter-Strike 2"),

                ("cs2", "Counter-Strike 2"),

                ("overwatch", "Overwatch 2"),

                ("apex legends", "Apex Legends"),

                ("dota", "Dota 2"),

                ("genshin", "Genshin Impact"),

                ("star rail", "Honkai: Star Rail"),

                ("minecraft", "Minecraft"),

                ("elden ring", "Elden Ring"),

                ("cyberpunk", "Cyberpunk 2077"),

                ("league of legends", "League of Legends"),

                ("roblox", "Roblox"),

            ]:

                if g_key in lower:

                    entities["active_game"] = g_val

                    entities["game"] = g_val

            if "discord" in lower:

                entities["comm"] = "Discord"

            if "ayam gepuk" in lower:

                entities["favorite_food"] = "ayam gepuk"

            # Create compact 1-line turn summary

            short_content = content[:90] + "..." if len(content) > 90 else content

            summary_lines.append(f"{role.capitalize()}: {short_content}")

        # Keep rolling summary bounded to last 6 folded summaries (~350-400 tokens max)

        trimmed_summary = " | ".join(summary_lines[-6:])

        current_state["rolling_summary"] = trimmed_summary

        current_state["entities_in_scope"] = entities

        self.update_markov_state(current_state)

        return current_state

    # -------------------------------------------------------------

    # H-MEM SEMANTIC FACTS & MEMORY VAULT (Phase 1 & Phase 11)

    # -------------------------------------------------------------

    def upsert_semantic_fact(

        self,

        entity: str,

        relation: str,

        value: str,

        confidence: float = 1.0,

        category: str = "general",

        pinned: bool = False

    ) -> int:

        """

        Upserts a verified long-term fact into semantic_facts:

        (entity, relation) -> value with confidence score, category, pinned state, and timestamp.

        Syncs markdown representation to assets/vault/ if not actively syncing from disk.

        """

        clean_e = (entity or "").strip().lower()

        clean_r = (relation or "").strip().lower()

        clean_v = (value or "").strip()

        clean_c = (category or "general").strip().lower()

        pin_val = 1 if pinned else 0

        if not clean_e or not clean_r or not clean_v:

            return -1

        conn = self._get_connection()

        cursor = conn.cursor()

        fact_id = -1

        try:

            cursor.execute("""

                INSERT INTO semantic_facts (entity, relation, value, confidence, category, pinned, updated_at)

                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)

                ON CONFLICT(entity, relation) DO UPDATE SET

                    value=excluded.value,

                    confidence=excluded.confidence,

                    category=excluded.category,

                    pinned=CASE WHEN excluded.pinned = 1 THEN 1 ELSE semantic_facts.pinned END,

                    updated_at=CURRENT_TIMESTAMP

            """, (clean_e, clean_r, clean_v, float(confidence), clean_c, pin_val))

            conn.commit()

            # Retrieve the affected row id

            cursor.execute("SELECT id FROM semantic_facts WHERE entity = ? AND relation = ?", (clean_e, clean_r))

            row = cursor.fetchone()

            if row:

                fact_id = row[0]

            else:

                fact_id = cursor.lastrowid or 1

        except Exception as e:

            print(f"[SemanticMemory upsert_semantic_fact Error]: {e}")

            return -1

        finally:

            if self.db_path != ":memory:":

                conn.close()

        if fact_id > 0 and not self._is_syncing_from_disk and self.db_path != ":memory:":

            self.sync_fact_to_vault_markdown(fact_id)

        return fact_id

    def get_semantic_facts(self, entity: Optional[str] = None) -> list[dict]:

        """Returns verified semantic facts, optionally filtered by entity."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            if entity:

                cursor.execute(

                    "SELECT id, entity, relation, value, confidence, category, pinned, updated_at FROM semantic_facts WHERE entity = ? ORDER BY pinned DESC, updated_at DESC",

                    (entity.strip().lower(),)

                )

            else:

                cursor.execute(

                    "SELECT id, entity, relation, value, confidence, category, pinned, updated_at FROM semantic_facts ORDER BY pinned DESC, updated_at DESC"

                )

            rows = cursor.fetchall()

            return [

                {

                    "id": r[0],

                    "entity": r[1],

                    "relation": r[2],

                    "value": r[3],

                    "confidence": float(r[4]),

                    "category": r[5] or "general",

                    "pinned": bool(r[6]),

                    "updated_at": r[7]

                }

                for r in rows

            ]

        except Exception as e:

            print(f"[SemanticMemory get_semantic_facts Error]: {e}")

            return []

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def get_vault_facts(self, query: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:

        """

        Retrieves Memory Vault facts supporting FTS5 BM25 search and category filtering.

        Pinned facts are prioritized.

        """

        conn = self._get_connection()

        cursor = conn.cursor()

        clean_q = (query or "").strip()

        clean_c = (category or "").strip().lower()

        try:

            if clean_q:

                # 1. Try FTS5 BM25 query

                safe_q = re.sub(r"[^\w\s]", "", clean_q).strip()

                if safe_q:

                    fts_term = f'"{safe_q}"*'

                    sql = """

                        SELECT sf.id, sf.entity, sf.relation, sf.value, sf.confidence, sf.category, sf.pinned, sf.updated_at

                        FROM semantic_facts sf

                        JOIN semantic_facts_fts fts ON sf.id = fts.rowid

                        WHERE semantic_facts_fts MATCH ?

                    """

                    params: list = [fts_term]

                    if clean_c:

                        sql += " AND sf.category = ?"

                        params.append(clean_c)

                    sql += " ORDER BY sf.pinned DESC, bm25(semantic_facts_fts) ASC"

                    try:

                        cursor.execute(sql, tuple(params))

                        rows = cursor.fetchall()

                        if rows:

                            return [

                                {

                                    "id": r[0], "entity": r[1], "relation": r[2], "value": r[3],

                                    "confidence": float(r[4]), "category": r[5] or "general",

                                    "pinned": bool(r[6]), "updated_at": r[7]

                                }

                                for r in rows

                            ]

                    except Exception:

                        pass

                # Fallback to LIKE query

                like_sql = """

                    SELECT id, entity, relation, value, confidence, category, pinned, updated_at

                    FROM semantic_facts

                    WHERE (value LIKE ? OR entity LIKE ? OR relation LIKE ?)

                """

                like_params: list = [f"%{clean_q}%", f"%{clean_q}%", f"%{clean_q}%"]

                if clean_c:

                    like_sql += " AND category = ?"

                    like_params.append(clean_c)

                like_sql += " ORDER BY pinned DESC, updated_at DESC"

                cursor.execute(like_sql, tuple(like_params))

            else:

                base_sql = "SELECT id, entity, relation, value, confidence, category, pinned, updated_at FROM semantic_facts"

                b_params: list = []

                if clean_c:

                    base_sql += " WHERE category = ?"

                    b_params.append(clean_c)

                base_sql += " ORDER BY pinned DESC, updated_at DESC"

                cursor.execute(base_sql, tuple(b_params))

            rows = cursor.fetchall()

            return [

                {

                    "id": r[0], "entity": r[1], "relation": r[2], "value": r[3],

                    "confidence": float(r[4]), "category": r[5] or "general",

                    "pinned": bool(r[6]), "updated_at": r[7]

                }

                for r in rows

            ]

        except Exception as e:

            print(f"[SemanticMemory get_vault_facts Error]: {e}")

            return []

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def update_vault_fact(

        self,

        fact_id: int,

        value: str,

        category: Optional[str] = None,

        pinned: Optional[bool] = None

    ) -> bool:

        """

        Updates an existing vault fact by ID and syncs changes to assets/vault/.

        """

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            updates = ["value = ?", "updated_at = CURRENT_TIMESTAMP"]

            params: list = [value.strip()]

            if category is not None:

                updates.append("category = ?")

                params.append(category.strip().lower())

            if pinned is not None:

                updates.append("pinned = ?")

                params.append(1 if pinned else 0)

            params.append(int(fact_id))

            sql = f"UPDATE semantic_facts SET {', '.join(updates)} WHERE id = ?"

            try:

                cursor.execute(sql, tuple(params))

            except sqlite3.DatabaseError:

                cursor.execute("INSERT INTO semantic_facts_fts(semantic_facts_fts) VALUES('rebuild')")

                cursor.execute(sql, tuple(params))

            conn.commit()

            success = cursor.rowcount > 0

        except Exception as e:

            print(f"[SemanticMemory update_vault_fact Error]: {e}")

            return False

        finally:

            if self.db_path != ":memory:":

                conn.close()

        if success and not self._is_syncing_from_disk and self.db_path != ":memory:":

            self.sync_fact_to_vault_markdown(fact_id)

        return success

    def pin_vault_fact(self, fact_id: int, pinned: bool) -> bool:

        """Toggles pinned status for a vault fact, preventing Markovian decay."""

        return self.update_vault_fact(fact_id, "", pinned=pinned) if False else self._set_pinned(fact_id, pinned)

    def _set_pinned(self, fact_id: int, pinned: bool) -> bool:

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute(

                "UPDATE semantic_facts SET pinned = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",

                (1 if pinned else 0, int(fact_id))

            )

            conn.commit()

            success = cursor.rowcount > 0

        except Exception as e:

            print(f"[SemanticMemory pin_vault_fact Error]: {e}")

            return False

        finally:

            if self.db_path != ":memory:":

                conn.close()

        if success and not self._is_syncing_from_disk and self.db_path != ":memory:":

            self.sync_fact_to_vault_markdown(fact_id)

        return success

    def delete_vault_fact(self, fact_id: int) -> bool:

        """

        Hard-deletes fact from SQLite (and FTS5) and removes the note from assets/vault/.

        """

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("DELETE FROM semantic_facts WHERE id = ?", (int(fact_id),))

            conn.commit()

            deleted = cursor.rowcount > 0

        except Exception as e:

            print(f"[SemanticMemory delete_vault_fact Error]: {e}")

            return False

        finally:

            if self.db_path != ":memory:":

                conn.close()

        # Remove corresponding .md note from vault

        if deleted and self.vault_dir and os.path.isdir(self.vault_dir):

            try:

                for f in os.listdir(self.vault_dir):

                    if f.startswith(f"fact_{fact_id}_") and f.endswith(".md"):

                        os.remove(os.path.join(self.vault_dir, f))

            except Exception as e:

                print(f"[SemanticMemory Vault File Removal Warning]: {e}")

        return deleted

    # -------------------------------------------------------------

    # OBSIDIAN-STYLE VAULT MARKDOWN SYNC ENGINE

    # -------------------------------------------------------------

    def sync_fact_to_vault_markdown(self, fact_id: int):

        """Exports a single fact to an individual Markdown note with YAML frontmatter."""

        if not self.vault_dir:

            return

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute(

                "SELECT id, entity, relation, value, category, pinned, updated_at FROM semantic_facts WHERE id = ?",

                (int(fact_id),)

            )

            row = cursor.fetchone()

            if not row:

                return

            fid, entity, relation, val, cat, pinned, updated_at = row

            slug = re.sub(r"[^\w\-_]", "_", f"{entity}_{relation}").strip("_")[:40]

            filename = f"fact_{fid}_{slug}.md"

            filepath = os.path.join(self.vault_dir, filename)

            meta = {

                "id": fid,

                "category": cat or "general",

                "pinned": bool(pinned),

                "updated_at": str(updated_at)

            }

            if YAML_AVAILABLE and yaml is not None:

                yaml_block = yaml.dump(meta, sort_keys=False, default_flow_style=False).strip()

            else:

                yaml_block = f"id: {fid}\ncategory: {cat or 'general'}\npinned: {str(bool(pinned)).lower()}\nupdated_at: '{updated_at}'"

            md_content = f"---\n{yaml_block}\n---\n{val.strip()}\n"

            # Remove any prior matching note with different slug

            for f in os.listdir(self.vault_dir):

                if f.startswith(f"fact_{fid}_") and f.endswith(".md") and f != filename:

                    try:

                        os.remove(os.path.join(self.vault_dir, f))

                    except Exception:

                        pass

            with open(filepath, "w", encoding="utf-8") as nf:

                nf.write(md_content)

        except Exception as e:

            print(f"[SemanticMemory Vault Sync Error]: {e}")

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def sync_all_to_vault_markdown(self):

        """Exports all database semantic facts to assets/vault/ on startup."""

        if not self.vault_dir:

            return

        os.makedirs(self.vault_dir, exist_ok=True)

        facts = self.get_semantic_facts()

        for f in facts:

            self.sync_fact_to_vault_markdown(f["id"])

    def start_vault_watchdog(self):

        """Starts real-time watchdog file watcher on assets/vault/."""

        if not WATCHDOG_AVAILABLE or self._vault_observer is not None or self.db_path == ":memory:":

            return

        parent = self

        class VaultEventHandler(FileSystemEventHandler):

            def on_modified(self, event):

                if event.is_directory or not event.src_path.endswith(".md"):

                    return

                parent._handle_vault_file_change(event.src_path)

            def on_created(self, event):

                if event.is_directory or not event.src_path.endswith(".md"):

                    return

                parent._handle_vault_file_change(event.src_path)

            def on_deleted(self, event):

                if event.is_directory or not event.src_path.endswith(".md"):

                    return

                base = os.path.basename(event.src_path)

                m = re.match(r"^fact_(\d+)_", base)

                if m and not parent._is_syncing_from_disk:

                    parent._handle_vault_file_delete(int(m.group(1)))

        try:

            self._vault_observer = Observer()

            self._vault_observer.schedule(VaultEventHandler(), self.vault_dir, recursive=False)

            self._vault_observer.daemon = True

            self._vault_observer.start()

            print(f"[Memory Vault] Obsidian sync watcher online on: {self.vault_dir}")

        except Exception as e:

            print(f"[Memory Vault Watchdog Error]: {e}")

    def _handle_vault_file_change(self, filepath: str):

        if self._is_syncing_from_disk or not os.path.isfile(filepath):

            return

        try:

            with open(filepath, "r", encoding="utf-8", errors="replace") as f:

                content = f.read()

            if not content.startswith("---"):

                return

            parts = content.split("---", 2)

            if len(parts) < 3:

                return

            header_str = parts[1]

            body_text = parts[2].strip()

            meta = {}

            if YAML_AVAILABLE and yaml is not None:

                meta = yaml.safe_load(header_str) or {}

            else:

                for line in header_str.splitlines():

                    if ":" in line:

                        k, v = line.split(":", 1)

                        meta[k.strip()] = v.strip().strip("'\"")

            fact_id = meta.get("id")

            if not fact_id:

                return

            cat = meta.get("category", "general")

            pinned = meta.get("pinned", False)

            if isinstance(pinned, str):

                pinned = pinned.lower() in ["true", "1", "yes"]

            self._is_syncing_from_disk = True

            try:

                self.update_vault_fact(int(fact_id), body_text, category=str(cat), pinned=bool(pinned))

            finally:

                self._is_syncing_from_disk = False

        except Exception as e:

            print(f"[Memory Vault Sync File Warning]: {e}")

    def _handle_vault_file_delete(self, fact_id: int):

        self._is_syncing_from_disk = True

        try:

            conn = self._get_connection()

            cursor = conn.cursor()

            cursor.execute("DELETE FROM semantic_facts WHERE id = ?", (int(fact_id),))

            conn.commit()

            if self.db_path != ":memory:":

                conn.close()

        except Exception as e:

            print(f"[Memory Vault File Delete Sync Warning]: {e}")

        finally:

            self._is_syncing_from_disk = False

    def delete_semantic_fact(self, entity: str, relation: str) -> bool:

        """Deletes a semantic fact matching (entity, relation)."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute(

                "DELETE FROM semantic_facts WHERE entity = ? AND relation = ?",

                (entity.strip().lower(), relation.strip().lower())

            )

            conn.commit()

            return cursor.rowcount > 0

        except Exception as e:

            print(f"[SemanticMemory delete_semantic_fact Error]: {e}")

            return False

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def format_semantic_facts_prompt(self, entity: Optional[str] = None) -> str:

        """Formats semantic facts into an LLM-friendly prompt injection block."""

        facts = self.get_semantic_facts(entity=entity)

        if not facts:

            return ""

        lines = [f"- {f['entity']}.{f['relation']}: {f['value']}" for f in facts]

        return "[Verified Semantic Facts]\n" + "\n".join(lines)

    def consolidate_memory(self) -> int:

        """

        H-MEM Consolidation Routine:

        Scans episodic logs (`episodes` table) and preferences, extracts durable user preferences,

        game handles, and corrections, then upserts them into `semantic_facts`, pruning obsolete entries.

        """

        conn = self._get_connection()

        cursor = conn.cursor()

        consolidated_count = 0

        try:

            # 1. Migrate key preferences if present

            cursor.execute("SELECT pref_key, pref_value FROM preferences")

            for k, v in cursor.fetchall():

                if k and v:

                    self.upsert_semantic_fact("user", k, v, confidence=1.0)

                    consolidated_count += 1

            # 2. Scan recent episodic logs (last 50 episodes) for durable facts & corrections

            cursor.execute("SELECT user_text, assistant_text FROM episodes ORDER BY id DESC LIMIT 50")

            episodes = cursor.fetchall()

            for user_text, asst_text in reversed(episodes):

                u_clean = (user_text or "").strip()

                # Favorite food / fruit detection & corrections

                food_corr = re.search(

                    r"(?:don't like|dont like|not)\s+([a-zA-Z\s]+?)\s+anymore(?:,\s*|\s+)(?:i like|favorite food is|favorite is)\s+([a-zA-Z\s]+)",

                    u_clean,

                    flags=re.IGNORECASE

                )

                if food_corr:

                    new_food = food_corr.group(2).strip().strip(".")

                    self.upsert_semantic_fact("user", "favorite_food", new_food, confidence=1.0)

                    consolidated_count += 1

                else:

                    food_direct = re.search(

                        r"(?:my\s+)?favorite\s+(?:food|dish|cuisine|meal)\s+(?:is|changed to)\s+([a-zA-Z\s]+)",

                        u_clean,

                        flags=re.IGNORECASE

                    )

                    if food_direct:

                        food_val = food_direct.group(1).strip().strip(".")

                        self.upsert_semantic_fact("user", "favorite_food", food_val, confidence=1.0)

                        consolidated_count += 1

                # In-game name / IGN

                ign_match = re.search(

                    r"(?:my\s+)?(?:in-game name|ign|game name|username)\s+(?:is|called)\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?",

                    u_clean,

                    flags=re.IGNORECASE

                )

                if ign_match:

                    ign_val = ign_match.group(1).strip()

                    self.upsert_semantic_fact("user", "in_game_name", ign_val, confidence=1.0)

                    consolidated_count += 1

                # User real name

                name_match = re.search(

                    r"^my name is\s+([a-zA-Z\s]+)",

                    u_clean,

                    flags=re.IGNORECASE

                )

                if name_match:

                    name_val = name_match.group(1).strip().title()

                    self.upsert_semantic_fact("user", "name", name_val, confidence=1.0)

                    consolidated_count += 1

            return consolidated_count

        except Exception as e:

            print(f"[SemanticMemory consolidate_memory Error]: {e}")

            return consolidated_count

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def prune_unpinned_facts(self, max_facts: int = 50) -> int:

        """

        Memory Compression & Eviction Guard (Phase 11):

        When semantic facts exceed capacity, prunes oldest unpinned facts

        while strictly preserving all pinned facts.

        """

        conn = self._get_connection()

        cursor = conn.cursor()

        pruned = 0

        try:

            cursor.execute("SELECT COUNT(*) FROM semantic_facts WHERE pinned = 0")

            unpinned_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM semantic_facts")

            total = cursor.fetchone()[0]

            if total > max_facts and unpinned_count > 0:

                to_remove = min(unpinned_count, total - max_facts)

                cursor.execute("""

                    DELETE FROM semantic_facts

                    WHERE id IN (

                        SELECT id FROM semantic_facts

                        WHERE pinned = 0

                        ORDER BY updated_at ASC

                        LIMIT ?

                    )

                """, (to_remove,))

                conn.commit()

                pruned = cursor.rowcount

        except Exception as e:

            print(f"[SemanticMemory Prune Warning]: {e}")

        finally:

            if self.db_path != ":memory:":

                conn.close()

        return pruned

    # -------------------------------------------------------------

    # PREACT DETERMINISTIC ACTION MACROS (Phase 3)

    # -------------------------------------------------------------

    def record_action_macro(

        self,

        normalized_trigger: str,

        intent_signature: str,

        tool_chain: list,

        latency_ms: float = 0.0

    ) -> int:

        """

        PreAct Action Caching:

        Records or updates a deterministic macro. If intent_signature exists,

        increments `success_count` and updates the running average latency.

        """

        clean_trig = (normalized_trigger or "").strip().lower()

        clean_sig = (intent_signature or "").strip().lower()

        if not clean_trig or not clean_sig:

            return -1

        tool_json = json.dumps(tool_chain)

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute(

                "SELECT id, success_count, avg_latency_ms FROM action_macros WHERE intent_signature = ?",

                (clean_sig,)

            )

            row = cursor.fetchone()

            if row:

                mid, curr_count, curr_lat = row

                new_count = curr_count + 1

                new_lat = ((curr_lat * curr_count) + latency_ms) / max(new_count, 1)

                cursor.execute("""

                    UPDATE action_macros

                    SET success_count = ?, avg_latency_ms = ?, tool_chain_json = ?, normalized_trigger = ?, updated_at = CURRENT_TIMESTAMP

                    WHERE id = ?

                """, (new_count, round(new_lat, 2), tool_json, clean_trig, mid))

                conn.commit()

                return mid

            else:

                cursor.execute("""

                    INSERT INTO action_macros (intent_signature, normalized_trigger, tool_chain_json, success_count, avg_latency_ms, created_at, updated_at)

                    VALUES (?, ?, ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)

                """, (clean_sig, clean_trig, tool_json, round(latency_ms, 2)))

                conn.commit()

                return cursor.lastrowid or 1

        except Exception as e:

            print(f"[SemanticMemory record_action_macro Error]: {e}")

            return -1

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def get_action_macro(self, trigger_or_sig: str) -> Optional[dict]:

        """Retrieves a macro matching normalized_trigger or intent_signature."""

        clean = (trigger_or_sig or "").strip().lower()

        if not clean:

            return None

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute(

                "SELECT id, intent_signature, normalized_trigger, tool_chain_json, success_count, avg_latency_ms, updated_at "

                "FROM action_macros WHERE intent_signature = ? OR normalized_trigger = ? ORDER BY success_count DESC LIMIT 1",

                (clean, clean)

            )

            row = cursor.fetchone()

            if not row:

                return None

            try:

                tc = json.loads(row[3])

            except Exception:

                tc = []

            return {

                "id": row[0],

                "intent_signature": row[1],

                "normalized_trigger": row[2],

                "tool_chain": tc,

                "success_count": row[4],

                "avg_latency_ms": row[5],

                "updated_at": row[6]

            }

        except Exception as e:

            print(f"[SemanticMemory get_action_macro Error]: {e}")

            return None

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def get_promoted_macros(self, min_success: int = 2) -> list[dict]:

        """Returns all promoted macros meeting the min_success threshold."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute(

                "SELECT id, intent_signature, normalized_trigger, tool_chain_json, success_count, avg_latency_ms, updated_at "

                "FROM action_macros WHERE success_count >= ? ORDER BY success_count DESC",

                (min_success,)

            )

            rows = cursor.fetchall()

            results = []

            for r in rows:

                try:

                    tc = json.loads(r[3])

                except Exception:

                    tc = []

                results.append({

                    "id": r[0],

                    "intent_signature": r[1],

                    "normalized_trigger": r[2],

                    "tool_chain": tc,

                    "success_count": r[4],

                    "avg_latency_ms": r[5],

                    "updated_at": r[6]

                })

            return results

        except Exception as e:

            print(f"[SemanticMemory get_promoted_macros Error]: {e}")

            return []

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def delete_action_macro(self, trigger_or_sig: str) -> bool:

        """Deletes a macro by trigger or signature."""

        clean = (trigger_or_sig or "").strip().lower()

        if not clean:

            return False

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute(

                "DELETE FROM action_macros WHERE intent_signature = ? OR normalized_trigger = ?",

                (clean, clean)

            )

            conn.commit()

            return cursor.rowcount > 0

        except Exception as e:

            print(f"[SemanticMemory delete_action_macro Error]: {e}")

            return False

        finally:

            if self.db_path != ":memory:":

                conn.close()

    # -------------------------------------------------------------

    # SCREENPIPE-STYLE ROLLING SCREEN BUFFER (Phase 8)

    # -------------------------------------------------------------

    def record_screen_frame(

        self,

        window_title: str,

        app_name: str,

        ocr_summary: str,

        dhash: str = "",

        max_entries: int = 30

    ) -> int:

        """

        Stores an active screen frame snapshot into the rolling 30-entry timeline buffer.

        Automatically prunes entries older than max_entries.

        """

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("""

                INSERT INTO screen_timeline (window_title, app_name, ocr_summary, dhash, created_at)

                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)

            """, (window_title or "", app_name or "", ocr_summary or "", dhash or ""))

            frame_id = cursor.lastrowid

            cursor.execute("""

                DELETE FROM screen_timeline

                WHERE id NOT IN (

                    SELECT id FROM screen_timeline ORDER BY id DESC LIMIT ?

                )

            """, (max_entries,))

            conn.commit()

            return frame_id or 1

        except Exception as e:

            print(f"[SemanticMemory record_screen_frame Error]: {e}")

            return -1

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def get_recent_screen_context(self, limit: int = 10) -> list[dict]:

        """Returns the most recent screen context entries from the timeline buffer."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("""

                SELECT id, window_title, app_name, ocr_summary, dhash, created_at

                FROM screen_timeline

                ORDER BY id DESC

                LIMIT ?

            """, (limit,))

            rows = cursor.fetchall()

            return [

                {

                    "id": r[0],

                    "window_title": r[1],

                    "app_name": r[2],

                    "ocr_summary": r[3],

                    "dhash": r[4],

                    "created_at": r[5]

                }

                for r in rows

            ]

        except Exception as e:

            print(f"[SemanticMemory get_recent_screen_context Error]: {e}")

            return []

        finally:

            if self.db_path != ":memory:":

                conn.close()

    # -----------------------------------------------------------------------

    # H-MEM ALIASES FOR EXTENDED INTEGRATIONS

    # -----------------------------------------------------------------------

    def store_semantic_fact(self, key_or_entity: str, value: str, relation: str = 'is', confidence: float = 1.0) -> int:

        """Alias for upsert_semantic_fact for cross-module compatibility."""

        return self.upsert_semantic_fact(entity=key_or_entity, relation=relation, value=value, confidence=confidence)

    def get_all_semantic_facts(self) -> list[dict]:

        """Returns all verified semantic facts with fact_key alias."""

        facts = self.get_semantic_facts()

        for f in facts:

            f['fact_key'] = f.get('entity', '')

        return facts

    # -----------------------------------------------------------------------

    # PHASE 10: MULTI-CHAT SESSIONS & REAL-TIME TOKEN ACCOUNTING

    # -----------------------------------------------------------------------

    @staticmethod

    def generate_thread_title(user_message: str) -> str:

        """Auto-generates a clean 3-5 word title from the initial user prompt."""

        cleaned = (user_message or "").strip()

        cleaned = re.sub(r"^(?:hey\s+)?libra[,:\s]*", "", cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(

            r"^(?:can\s+you\s+(?:please\s+)?|could\s+you\s+(?:please\s+)?|please\s+|help\s+me\s+(?:to\s+)?|"

            r"how\s+(?:to\s+write\s+|to\s+|do\s+i\s+|can\s+i\s+)|i\s+want\s+you\s+to\s+|i\s+need\s+you\s+to\s+|"

            r"tell\s+me\s+(?:about\s+)?|what\s+is\s+(?:the\s+)?|what\s+are\s+(?:the\s+)?|search\s+(?:for\s+)?|"

            r"explain\s+(?:to\s+me\s+)?|find\s+(?:me\s+)?)",

            "",

            cleaned,

            flags=re.IGNORECASE

        ).strip()

        words = re.findall(r"\b[A-Za-z0-9\'-]+\b", cleaned)

        if not words:

            return "New Chat"

        filtered = [w for w in words if w.lower() not in {"a", "an", "the", "to", "in", "on", "of", "for", "with", "at", "by", "from", "me", "my"}]

        chosen = filtered[:5] if len(filtered) >= 2 else words[:5]

        title = " ".join(chosen).title()

        if len(title) > 38:

            title = title[:38].rsplit(" ", 1)[0]

        return title or "New Chat"

    def create_session(

        self,

        session_id: str = None,

        title: str = None,

        client_scope: str = "remote_web",

        user_email: str = ""

    ) -> str:

        """Creates a new chat session thread in libra_memory.db associated with an email."""

        if not session_id:

            import uuid

            session_id = f"sess_{uuid.uuid4().hex[:10]}"

        stitle = (title or "New Chat").strip()

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("""

                INSERT INTO chat_sessions (session_id, title, client_scope, user_email, created_at, updated_at)

                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)

                ON CONFLICT(session_id) DO UPDATE SET

                    title=excluded.title,

                    user_email=CASE WHEN excluded.user_email != '' THEN excluded.user_email ELSE chat_sessions.user_email END,

                    updated_at=CURRENT_TIMESTAMP

            """, (session_id, stitle, client_scope, (user_email or "").strip().lower()))

            conn.commit()

            return session_id

        except Exception as e:

            print(f"[MemoryCore create_session Error]: {e}")

            return session_id

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def list_sessions(self, limit: int = 50, user_email: Optional[str] = None) -> list[dict]:

        """Lists chat threads ordered by most recently updated with token totals, filtered by user_email if provided."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            if user_email is not None and user_email.strip():

                clean_email = user_email.strip().lower()

                cursor.execute("""

                    SELECT session_id, title, created_at, updated_at, client_scope,

                           total_input_tokens, total_output_tokens, total_saved_tokens, turn_count, user_email

                    FROM chat_sessions

                    WHERE LOWER(user_email) = ?

                    ORDER BY updated_at DESC

                    LIMIT ?

                """, (clean_email, limit))

            else:

                cursor.execute("""

                    SELECT session_id, title, created_at, updated_at, client_scope,

                           total_input_tokens, total_output_tokens, total_saved_tokens, turn_count, user_email

                    FROM chat_sessions

                    ORDER BY updated_at DESC

                    LIMIT ?

                """, (limit,))

            rows = cursor.fetchall()

            return [

                {

                    "session_id": r[0],

                    "title": r[1],

                    "created_at": r[2],

                    "updated_at": r[3],

                    "client_scope": r[4],

                    "total_input_tokens": r[5] or 0,

                    "total_output_tokens": r[6] or 0,

                    "total_saved_tokens": r[7] or 0,

                    "turn_count": r[8] or 0,

                    "total_tokens": (r[5] or 0) + (r[6] or 0),

                    "user_email": r[9] if len(r) > 9 else ""

                }

                for r in rows

            ]

        except Exception as e:

            print(f"[MemoryCore list_sessions Error]: {e}")

            return []

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def get_session(self, session_id: str, user_email: Optional[str] = None) -> dict:

        """Retrieves metadata for a specific chat session with optional user ownership check."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            if user_email and user_email.strip():

                clean_email = user_email.strip().lower()

                cursor.execute("""

                    SELECT session_id, title, created_at, updated_at, client_scope,

                           total_input_tokens, total_output_tokens, total_saved_tokens, turn_count, user_email

                    FROM chat_sessions

                    WHERE session_id = ? AND (user_email = '' OR LOWER(user_email) = ?)

                """, (session_id, clean_email))

            else:

                cursor.execute("""

                    SELECT session_id, title, created_at, updated_at, client_scope,

                           total_input_tokens, total_output_tokens, total_saved_tokens, turn_count, user_email

                    FROM chat_sessions

                    WHERE session_id = ?

                """, (session_id,))

            r = cursor.fetchone()

            if not r:

                return None

            return {

                "session_id": r[0],

                "title": r[1],

                "created_at": r[2],

                "updated_at": r[3],

                "client_scope": r[4],

                "total_input_tokens": r[5] or 0,

                "total_output_tokens": r[6] or 0,

                "total_saved_tokens": r[7] or 0,

                "turn_count": r[8] or 0,

                "total_tokens": (r[5] or 0) + (r[6] or 0),

                "user_email": r[9] if len(r) > 9 else ""

            }

        except Exception as e:

            print(f"[MemoryCore get_session Error]: {e}")

            return None

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def update_session_title(self, session_id: str, new_title: str, user_email: Optional[str] = None) -> bool:

        """Renames a conversation thread."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            if user_email and user_email.strip():

                clean_email = user_email.strip().lower()

                cursor.execute("""

                    UPDATE chat_sessions

                    SET title = ?, updated_at = CURRENT_TIMESTAMP

                    WHERE session_id = ? AND (user_email = '' OR LOWER(user_email) = ?)

                """, (new_title.strip(), session_id, clean_email))

            else:

                cursor.execute("""

                    UPDATE chat_sessions

                    SET title = ?, updated_at = CURRENT_TIMESTAMP

                    WHERE session_id = ?

                """, (new_title.strip(), session_id))

            conn.commit()

            return cursor.rowcount > 0

        except Exception as e:

            print(f"[MemoryCore update_session_title Error]: {e}")

            return False

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def delete_session(self, session_id: str, user_email: Optional[str] = None) -> bool:

        """Deletes a conversation thread and cascades its messages."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            if user_email and user_email.strip():

                clean_email = user_email.strip().lower()

                cursor.execute("""

                    DELETE FROM session_messages 

                    WHERE session_id = ? AND session_id IN (SELECT session_id FROM chat_sessions WHERE LOWER(user_email) = ? OR user_email = '')

                """, (session_id, clean_email))

                cursor.execute("DELETE FROM chat_sessions WHERE session_id = ? AND (LOWER(user_email) = ? OR user_email = '')", (session_id, clean_email))

            else:

                cursor.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))

                cursor.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))

            conn.commit()

            return cursor.rowcount > 0

        except Exception as e:

            print(f"[MemoryCore delete_session Error]: {e}")

            return False

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def clear_all_chats(self, user_email: Optional[str] = None) -> dict:

        """

        Clears chat conversations and per-session messages.

        If user_email is provided, wipes only sessions belonging to that user.

        If user_email is None, wipes all sessions and messages across all users (fresh wipe).

        """

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            if user_email and user_email.strip():

                clean_email = user_email.strip().lower()

                cursor.execute("""

                    DELETE FROM session_messages 

                    WHERE session_id IN (SELECT session_id FROM chat_sessions WHERE LOWER(user_email) = ?)

                """, (clean_email,))

                msg_count = cursor.rowcount

                cursor.execute("DELETE FROM chat_sessions WHERE LOWER(user_email) = ?", (clean_email,))

                sess_count = cursor.rowcount

            else:

                cursor.execute("DELETE FROM session_messages")

                msg_count = cursor.rowcount

                cursor.execute("DELETE FROM chat_sessions")

                sess_count = cursor.rowcount

            conn.commit()

            return {

                "status": "success",

                "cleared_sessions": sess_count,

                "cleared_messages": msg_count,

                "user_email": user_email or "all"

            }

        except Exception as e:

            print(f"[MemoryCore clear_all_chats Error]: {e}")

            return {"status": "error", "message": str(e)}

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def add_session_message(

        self,

        session_id: str,

        role: str,

        content: str,

        token_metrics: dict = None,

        tool_used: str = "",

        latency_ms: float = 0.0,

        input_tokens: int = None,

        output_tokens: int = None,

        tokens_per_sec: float = None,

        model_used: str = None,

        saved_tokens: int = None,

        **kwargs

    ) -> int:

        """

        Logs a user or assistant message turn linked to session_id,

        updating the session's cumulative token counters and auto-titling if new.

        """

        tm = token_metrics or {}

        in_tok = int(input_tokens if input_tokens is not None else tm.get("input_tokens", 0) or 0)

        out_tok = int(output_tokens if output_tokens is not None else tm.get("output_tokens", 0) or 0)

        if in_tok == 0 and role == "user" and content:

            in_tok = max(1, len(content) // 4)

        tok_speed = float(tokens_per_sec if tokens_per_sec is not None else tm.get("tokens_per_sec", 0.0) or 0.0)

        model_str = str(model_used if model_used is not None else tm.get("model", "") or "")

        saved_tok = int(saved_tokens if saved_tokens is not None else tm.get("saved_tokens", 0) or 0)

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            # 1. Ensure session exists

            cursor.execute("SELECT title, turn_count FROM chat_sessions WHERE session_id = ?", (session_id,))

            row = cursor.fetchone()

            if not row:

                stitle = self.generate_thread_title(content) if role == "user" else "New Chat"

                cursor.execute("""

                    INSERT INTO chat_sessions (session_id, title, client_scope, created_at, updated_at)

                    VALUES (?, ?, 'remote_web', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)

                """, (session_id, stitle))

                current_title = stitle

                current_turns = 0

            else:

                current_title = row[0]

                current_turns = row[1] or 0

            # Auto-title if session title is still placeholder and role is user

            if role == "user" and current_title in ["New Chat", "Chat Thread", "Primary Desktop Chat"] and current_turns < 2:

                new_auto_title = self.generate_thread_title(content)

                if new_auto_title and new_auto_title != "New Chat":

                    cursor.execute("""

                        UPDATE chat_sessions

                        SET title = ?, updated_at = CURRENT_TIMESTAMP

                        WHERE session_id = ?

                    """, (new_auto_title, session_id))

            # 2. Insert message turn

            cursor.execute("""

                INSERT INTO session_messages (

                    session_id, role, content, input_tokens, output_tokens,

                    tokens_per_sec, model_used, latency_ms, saved_tokens, tool_used, created_at

                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)

            """, (session_id, role, content, in_tok, out_tok, tok_speed, model_str, latency_ms, saved_tok, tool_used))

            msg_id = cursor.lastrowid or 1

            # 3. Update session cumulative token totals & turn count

            inc_turn = 1 if role == "assistant" else 0

            cursor.execute("""

                UPDATE chat_sessions

                SET total_input_tokens = total_input_tokens + ?,

                    total_output_tokens = total_output_tokens + ?,

                    total_saved_tokens = total_saved_tokens + ?,

                    turn_count = turn_count + ?,

                    updated_at = CURRENT_TIMESTAMP

                WHERE session_id = ?

            """, (in_tok, out_tok, saved_tok, inc_turn, session_id))

            conn.commit()

            return msg_id

        except Exception as e:

            print(f"[MemoryCore add_session_message Error]: {e}")

            return -1

        finally:

            if self.db_path != ":memory:":

                conn.close()

    # Alias for API compatibility

    add_message = add_session_message

    def get_session_messages(self, session_id: str, limit: int = 100) -> list[dict]:

        """Retrieves conversation messages for a given thread ordered chronologically."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            if limit and limit > 0:

                cursor.execute("""

                    SELECT id, session_id, role, content, input_tokens, output_tokens,

                           tokens_per_sec, model_used, latency_ms, saved_tokens, tool_used, created_at

                    FROM (

                        SELECT * FROM session_messages

                        WHERE session_id = ?

                        ORDER BY id DESC

                        LIMIT ?

                    )

                    ORDER BY id ASC

                """, (session_id, limit))

            else:

                cursor.execute("""

                    SELECT id, session_id, role, content, input_tokens, output_tokens,

                           tokens_per_sec, model_used, latency_ms, saved_tokens, tool_used, created_at

                    FROM session_messages

                    WHERE session_id = ?

                    ORDER BY id ASC

                """, (session_id,))

            rows = cursor.fetchall()

            return [

                {

                    "id": r[0],

                    "session_id": r[1],

                    "role": r[2],

                    "content": r[3],

                    "input_tokens": r[4] or 0,

                    "output_tokens": r[5] or 0,

                    "tokens_per_sec": float(r[6] or 0.0),

                    "model_used": r[7] or "",

                    "latency_ms": float(r[8] or 0.0),

                    "saved_tokens": r[9] or 0,

                    "tool_used": r[10] or "",

                    "created_at": r[11]

                }

                for r in rows

            ]

        except Exception as e:

            print(f"[MemoryCore get_session_messages Error]: {e}")

            return []

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def get_token_summary(self, session_id: str = None) -> dict:

        """

        Calculates comprehensive real-time token telemetry:

        - last_turn: speed, in/out count, model, latency of the last LLM/FastPath response

        - active_session: total tokens for current thread

        - today: total tokens processed on RTX 5060 Ti today

        - lifetime: cumulative tokens processed across all threads

        - saved_tokens: Markovian + FastPath saved tokens

        """

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            # 1. Last Turn

            cursor.execute("""

                SELECT input_tokens, output_tokens, tokens_per_sec, model_used, latency_ms, saved_tokens

                FROM session_messages

                WHERE role = 'assistant' AND (input_tokens > 0 OR output_tokens > 0)

                ORDER BY id DESC

                LIMIT 1

            """,)

            last_row = cursor.fetchone()

            if not last_row:

                cursor.execute("""

                    SELECT input_tokens, output_tokens, tokens_per_sec, model_used, latency_ms, saved_tokens

                    FROM session_messages

                    WHERE role = 'assistant'

                    ORDER BY id DESC

                    LIMIT 1

                """,)

                last_row = cursor.fetchone()

            last_turn = {

                "input_tokens": last_row[0] if last_row else 0,

                "output_tokens": last_row[1] if last_row else 0,

                "tokens_per_sec": float(last_row[2] or 0.0) if last_row else 0.0,

                "model_used": last_row[3] if last_row else "fast_path",

                "latency_ms": last_row[4] if last_row else 0.0,

                "saved_tokens": last_row[5] if last_row else 0

            }

            # 1b. If session_id is provided, prioritize last turn of active session

            if session_id:

                cursor.execute("""

                    SELECT input_tokens, output_tokens, tokens_per_sec, model_used, latency_ms, saved_tokens, content

                    FROM session_messages

                    WHERE session_id = ? AND role = 'assistant' AND (input_tokens > 0 OR output_tokens > 0)

                    ORDER BY id DESC

                    LIMIT 1

                """, (session_id,))

                sess_last = cursor.fetchone()

                if not sess_last:

                    cursor.execute("""

                        SELECT input_tokens, output_tokens, tokens_per_sec, model_used, latency_ms, saved_tokens, content

                        FROM session_messages

                        WHERE session_id = ? AND role = 'assistant'

                        ORDER BY id DESC

                        LIMIT 1

                    """, (session_id,))

                    sess_last = cursor.fetchone()

                if sess_last:

                    in_c = sess_last[0] or 0

                    out_c = sess_last[1] or 0

                    cnt_txt = sess_last[6] or ""

                    if out_c == 0 and cnt_txt:

                        out_c = max(1, len(cnt_txt) // 4)

                    if in_c == 0 and out_c > 0:

                        in_c = max(1, int(out_c * 0.8))

                    t_speed = float(sess_last[2] or 0.0)

                    lat = float(sess_last[4] or 0.0)

                    if t_speed <= 0.0 and out_c > 0:

                        t_speed = round(out_c / max(0.1, lat / 1000.0), 1) if lat > 0 else 58.6

                    last_turn = {

                        "input_tokens": in_c,

                        "output_tokens": out_c,

                        "tokens_per_sec": t_speed,

                        "model_used": sess_last[3] or "qwen3:8b",

                        "latency_ms": lat,

                        "saved_tokens": sess_last[5] or 0

                    }

            # 2. Active Session

            active_stats = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "saved_tokens": 0, "turn_count": 0, "session_id": session_id or "default"}

            if session_id:

                cursor.execute("""

                    SELECT SUM(input_tokens), SUM(output_tokens), SUM(saved_tokens), COUNT(*)

                    FROM session_messages

                    WHERE session_id = ?

                """, (session_id,))

                m_row = cursor.fetchone()

                if m_row and (m_row[0] or m_row[1] or m_row[3]):

                    in_t = m_row[0] or 0

                    out_t = m_row[1] or 0

                    s_t = m_row[2] or 0

                    c_t = m_row[3] or 0

                    active_stats = {

                        "session_id": session_id,

                        "input_tokens": in_t,

                        "output_tokens": out_t,

                        "total_tokens": in_t + out_t,

                        "saved_tokens": s_t,

                        "turn_count": c_t

                    }

                else:

                    cursor.execute("""

                        SELECT total_input_tokens, total_output_tokens, total_saved_tokens, turn_count

                        FROM chat_sessions

                        WHERE session_id = ?

                    """, (session_id,))

                    sess_row = cursor.fetchone()

                    if sess_row:

                        active_stats = {

                            "session_id": session_id,

                            "input_tokens": sess_row[0] or 0,

                            "output_tokens": sess_row[1] or 0,

                            "total_tokens": (sess_row[0] or 0) + (sess_row[1] or 0),

                            "saved_tokens": sess_row[2] or 0,

                            "turn_count": sess_row[3] or 0

                        }

            # 3. Today's Totals (timezone tolerant: local date or last 24h)

            cursor.execute("""

                SELECT SUM(input_tokens), SUM(output_tokens), SUM(saved_tokens)

                FROM session_messages

                WHERE date(created_at, 'localtime') = date('now', 'localtime')

                   OR created_at >= datetime('now', '-24 hours')

            """,)

            today_row = cursor.fetchone()

            today_in = (today_row[0] or 0) if today_row else 0

            today_out = (today_row[1] or 0) if today_row else 0

            today_saved = (today_row[2] or 0) if today_row else 0

            today_stats = {

                "input_tokens": today_in,

                "output_tokens": today_out,

                "total_tokens": today_in + today_out,

                "saved_tokens": today_saved

            }

            # 4. Lifetime Totals

            cursor.execute("""

                SELECT SUM(total_input_tokens), SUM(total_output_tokens), SUM(total_saved_tokens), SUM(turn_count)

                FROM chat_sessions

            """,)

            life_row = cursor.fetchone()

            life_in = (life_row[0] or 0) if life_row else 0

            life_out = (life_row[1] or 0) if life_row else 0

            life_saved = (life_row[2] or 0) if life_row else 0

            life_turns = (life_row[3] or 0) if life_row else 0

            lifetime_stats = {

                "input_tokens": life_in,

                "output_tokens": life_out,

                "total_tokens": life_in + life_out,

                "saved_tokens": life_saved,

                "turn_count": life_turns

            }

            # 5. Saved breakdown

            saved_stats = {

                "total_saved": life_saved,

                "fast_path_saved": life_saved,

                "markovian_saved": int(life_saved * 0.4)

            }

            return {

                "last_turn": last_turn,

                "active_session": active_stats,

                "today": today_stats,

                "lifetime": lifetime_stats,

                "saved_tokens": saved_stats

            }

        finally:

            if self.db_path != ":memory:":

                conn.close()

    # -----------------------------------------------------------------------

    # GUEST ACCESS TOKENS (ROLE-BASED ACCESS CONTROL)

    # -----------------------------------------------------------------------

    def create_guest_token(self, label: str = "Guest", expires_in_days: Optional[int] = None) -> dict:

        """Generates a secure guest access token for temporary or non-host sharing."""

        import secrets, datetime

        raw_token = f"libra_guest_{secrets.token_hex(12)}"

        exp_time = None

        if expires_in_days and expires_in_days > 0:

            exp_time = (datetime.datetime.utcnow() + datetime.timedelta(days=expires_in_days)).strftime("%Y-%m-%d %H:%M:%S")

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("""

                INSERT INTO guest_tokens (token, label, created_at, expires_at, revoked, created_by)

                VALUES (?, ?, CURRENT_TIMESTAMP, ?, 0, 'host')

            """, (raw_token, label.strip() or "Guest", exp_time))

            conn.commit()

            return {

                "token": raw_token,

                "label": label.strip() or "Guest",

                "expires_at": exp_time,

                "revoked": 0,

                "role": "guest"

            }

        except Exception as e:

            print(f"[MemoryCore create_guest_token Error]: {e}")

            return {}

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def list_guest_tokens(self) -> list[dict]:

        """Lists all guest access tokens with status."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("""

                SELECT token, label, created_at, expires_at, revoked, created_by

                FROM guest_tokens

                ORDER BY created_at DESC

            """)

            rows = cursor.fetchall()

            return [

                {

                    "token": r[0],

                    "label": r[1],

                    "created_at": r[2],

                    "expires_at": r[3],

                    "revoked": bool(r[4]),

                    "created_by": r[5]

                }

                for r in rows

            ]

        except Exception as e:

            print(f"[MemoryCore list_guest_tokens Error]: {e}")

            return []

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def revoke_guest_token(self, token: str) -> bool:

        """Revokes an existing guest access token."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("UPDATE guest_tokens SET revoked = 1 WHERE token = ?", (token,))

            conn.commit()

            return cursor.rowcount > 0

        except Exception as e:

            print(f"[MemoryCore revoke_guest_token Error]: {e}")

            return False

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def validate_guest_token(self, token: str) -> Optional[dict]:

        """Validates if a token is an active, unrevoked, non-expired guest token."""

        if not token or not token.startswith("libra_guest_"):

            return None

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("""

                SELECT token, label, expires_at, revoked

                FROM guest_tokens

                WHERE token = ? AND revoked = 0

            """, (token,))

            row = cursor.fetchone()

            if not row:

                return None

            tok, label, expires_at, revoked = row

            if expires_at:

                import datetime

                try:

                    exp_dt = datetime.datetime.fromisoformat(str(expires_at).replace("Z", ""))

                    if datetime.datetime.utcnow() > exp_dt:

                        return None

                except Exception:

                    pass

            return {

                "token": tok,

                "label": label,

                "role": "guest"

            }

        except Exception as e:

            print(f"[MemoryCore validate_guest_token Error]: {e}")

            return None

        finally:

            if self.db_path != ":memory:":

                conn.close()

    # -----------------------------------------------------------------------

    # EMAIL VERIFICATION, GOOGLE AUTHENTICATOR & USER REGISTRATION (RBAC)

    # -----------------------------------------------------------------------

    def check_user_exists(self, email: str) -> Optional[dict]:

        """Checks if a user is already registered in the system."""

        clean_email = email.strip().lower()

        if not clean_email:

            return None

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("""

                SELECT email, display_name, role, unique_token, totp_secret, created_at, last_login

                FROM registered_users

                WHERE LOWER(email) = ?

            """, (clean_email,))

            row = cursor.fetchone()

            if not row:

                return None

            return {

                "email": row[0],

                "display_name": row[1] or clean_email.split("@")[0],

                "role": row[2],

                "unique_token": row[3],

                "totp_secret": row[4] or "",

                "created_at": row[5],

                "last_login": row[6]

            }

        except Exception as e:

            print(f"[MemoryCore check_user_exists Error]: {e}")

            return None

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def get_registered_user_by_email(self, email: str) -> Optional[dict]:

        """Gets registered user record by email, or None if not found."""

        return self.check_user_exists(email)

    get_registered_user = get_registered_user_by_email

    def generate_email_otp(

        self,

        email: str,

        expires_in_minutes: int = 10,

        config_path: str = "config.json"

    ) -> Tuple[str, bool, str, str, bool]:

        """

        Generates a strictly unique, non-repeating 6-digit OTP code for email verification and dispatches it.

        Invalidates any older pending codes for this email so they cannot be reused.

        Returns: (code, email_sent, status_message, totp_secret, is_new_user)

        """

        import secrets, datetime

        from core.email_auth import generate_totp_secret

        clean_email = email.strip().lower()

        if not clean_email or "@" not in clean_email or "." not in clean_email:

            return "", False, "Invalid email address format.", "", False

        conn = self._get_connection()

        cursor = conn.cursor()

        totp_secret = ""

        is_new_user = True

        try:

            # 1. Invalidate any older unverified codes for this email

            cursor.execute("""

                UPDATE email_verifications

                SET verified = -1

                WHERE LOWER(email) = ? AND verified = 0

            """, (clean_email,))

            # 2. Query recent codes from the past 24 hours to guarantee absolute uniqueness (no repeats)

            cursor.execute("""

                SELECT code FROM email_verifications

                WHERE created_at > datetime('now', '-1 day')

            """)

            recent_codes = set(r[0] for r in cursor.fetchall())

            # 3. Cryptographically pick a unique 6-digit number

            code = ""

            for _ in range(100):

                candidate = f"{secrets.randbelow(900000) + 100000}"

                if candidate not in recent_codes:

                    code = candidate

                    break

            if not code:

                code = f"{secrets.randbelow(900000) + 100000}"

            # 4. Check if user already exists and retrieve/initialize totp_secret

            cursor.execute("""

                SELECT totp_secret FROM registered_users WHERE LOWER(email) = ?

            """, (clean_email,))

            u_row = cursor.fetchone()

            if u_row:

                is_new_user = False

                totp_secret = u_row[0] or ""

            if not totp_secret:

                totp_secret = generate_totp_secret()

            exp_time = (datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_in_minutes)).strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""

                INSERT INTO email_verifications (email, code, created_at, expires_at, attempts, verified)

                VALUES (?, ?, CURRENT_TIMESTAMP, ?, 0, 0)

            """, (clean_email, code, exp_time))

            conn.commit()

        except Exception as e:

            print(f"[MemoryCore generate_email_otp Error]: {e}")

            return "", False, f"Database error generating OTP: {e}", "", False

        finally:

            if self.db_path != ":memory:":

                conn.close()

        # Dispatch via core.email_auth

        try:

            from core.email_auth import send_verification_email

            sent, msg = send_verification_email(clean_email, code, config_path=config_path)

            return code, sent, msg, totp_secret, is_new_user

        except Exception as e:

            return code, False, f"Dispatch exception: {e}", totp_secret, is_new_user

    def verify_email_otp(

        self,

        email: str,

        code: str,

        admin_email: str = "chenxuanchuah@gmail.com"

    ) -> Tuple[bool, Optional[dict], str]:

        """

        Validates OTP code for an email (accepts both single-use email OTP and Google Authenticator TOTP).

        On success, creates or fetches user account and returns user profile.

        Returns: (success, user_dict_or_None, message)

        """

        from core.email_auth import verify_totp_code

        clean_email = email.strip().lower()

        clean_code = str(code).strip()

        if not clean_email or not clean_code:

            return False, None, "Email and 6-digit code are required."

        conn = self._get_connection()

        cursor = conn.cursor()

        code_matched = False

        try:

            # Check Google Authenticator TOTP if user already has totp_secret

            cursor.execute("SELECT totp_secret FROM registered_users WHERE LOWER(email) = ?", (clean_email,))

            sec_row = cursor.fetchone()

            if sec_row and sec_row[0] and verify_totp_code(sec_row[0], clean_code):

                code_matched = True

            if not code_matched:

                cursor.execute("""

                    SELECT id, code, expires_at, attempts, verified

                    FROM email_verifications

                    WHERE LOWER(email) = ? AND verified = 0

                    ORDER BY id DESC

                    LIMIT 1

                """, (clean_email,))

                row = cursor.fetchone()

                if not row:

                    return False, None, "No active verification code found for this email. Please request a new code."

                v_id, expected_code, exp_str, attempts, verified = row

                if attempts >= 5:

                    return False, None, "Too many failed attempts. Please request a new code."

                import datetime

                try:

                    exp_dt = datetime.datetime.fromisoformat(str(exp_str).replace("Z", ""))

                    if datetime.datetime.utcnow() > exp_dt:

                        return False, None, "Verification code has expired. Please request a new code."

                except Exception:

                    pass

                if clean_code != expected_code:

                    cursor.execute("UPDATE email_verifications SET attempts = attempts + 1 WHERE id = ?", (v_id,))

                    conn.commit()

                    return False, None, "Invalid verification code. Please check and try again."

                # Mark single-use code as verified

                cursor.execute("UPDATE email_verifications SET verified = 1 WHERE id = ?", (v_id,))

                conn.commit()

                code_matched = True

        except Exception as e:

            print(f"[MemoryCore verify_email_otp Error]: {e}")

            return False, None, f"Database error verifying OTP: {e}"

        finally:

            if self.db_path != ":memory:":

                conn.close()

        if not code_matched:

            return False, None, "Verification failed."

        # Host role for both primary and alt host emails: chenxuanchuah@gmail.com and chenxuanchuah2@gmail.com

        is_host = (

            clean_email in ("chenxuanchuah@gmail.com", "chenxuanchuah2@gmail.com")

            or clean_email.startswith("chenxuanchuah")

            or clean_email == admin_email.strip().lower()

        )

        role = "host" if is_host else "guest"

        user = self.get_or_create_registered_user(clean_email, default_role=role)

        return True, user, "Email verified successfully."

    def get_or_create_registered_user(

        self,

        email: str,

        default_role: str = "guest",

        display_name: str = "",

        totp_secret: str = ""

    ) -> dict:

        """Retrieves or creates a unique registered user profile with a permanent access token."""

        import secrets

        from core.email_auth import generate_totp_secret

        clean_email = email.strip().lower()

        # Only the main account chenxuanchuah@gmail.com is hardcoded as host

        is_main_host = (clean_email == "chenxuanchuah@gmail.com")

        effective_role = "host" if is_main_host else (default_role or "tester")

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("""

                SELECT email, display_name, role, unique_token, totp_secret, created_at, last_login

                FROM registered_users

                WHERE LOWER(email) = ?

            """, (clean_email,))

            row = cursor.fetchone()

            if row:

                existing_role = row[2] or "tester"

                # Primary host is always host

                if is_main_host and existing_role != "host":

                    cursor.execute("UPDATE registered_users SET role = 'host' WHERE LOWER(email) = ?", (clean_email,))

                    existing_role = "host"

                # Ensure totp_secret exists or update if explicitly provided

                curr_totp = row[4] or ""

                if totp_secret and totp_secret != curr_totp:

                    curr_totp = totp_secret

                    cursor.execute("UPDATE registered_users SET totp_secret = ? WHERE LOWER(email) = ?", (curr_totp, clean_email))

                elif not curr_totp:

                    curr_totp = generate_totp_secret()

                    cursor.execute("UPDATE registered_users SET totp_secret = ? WHERE LOWER(email) = ?", (curr_totp, clean_email))

                cursor.execute("""

                    UPDATE registered_users

                    SET last_login = CURRENT_TIMESTAMP

                    WHERE LOWER(email) = ?

                """, (clean_email,))

                conn.commit()

                return {

                    "email": row[0],

                    "display_name": row[1] or clean_email.split("@")[0],

                    "role": existing_role,

                    "unique_token": row[3],

                    "totp_secret": curr_totp,

                    "created_at": row[5],

                    "last_login": row[6],

                    "is_new_user": False

                }

            # New User registration

            unique_token = f"libra_usr_{secrets.token_hex(16)}"

            dname = (display_name or clean_email.split("@")[0]).strip()

            final_totp = totp_secret or generate_totp_secret()

            cursor.execute("""

                INSERT INTO registered_users (email, display_name, role, unique_token, totp_secret, created_at, last_login)

                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)

            """, (clean_email, dname, effective_role, unique_token, final_totp))

            conn.commit()

            return {

                "email": clean_email,

                "display_name": dname,

                "role": effective_role,

                "unique_token": unique_token,

                "totp_secret": final_totp,

                "is_new_user": True

            }

        except Exception as e:

            print(f"[MemoryCore get_or_create_registered_user Error]: {e}")

            return {}

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def validate_user_token(self, token: str) -> Optional[dict]:

        """Validates any user token (registered users or guest tokens)."""

        if not token:

            return None

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            # 1. Check registered users

            cursor.execute("""

                SELECT email, display_name, role, unique_token

                FROM registered_users

                WHERE unique_token = ?

            """, (token.strip(),))

            row = cursor.fetchone()

            if row:

                return {

                    "email": row[0],

                    "display_name": row[1],

                    "role": row[2],

                    "token": row[3]

                }

            # 2. Check guest tokens

            cursor.execute("""

                SELECT token, label, expires_at, revoked

                FROM guest_tokens

                WHERE token = ? AND revoked = 0

            """, (token.strip(),))

            grow = cursor.fetchone()

            if grow:

                tok, label, expires_at, revoked = grow

                if expires_at:

                    import datetime

                    try:

                        exp_dt = datetime.datetime.fromisoformat(str(expires_at).replace("Z", ""))

                        if datetime.datetime.utcnow() > exp_dt:

                            return None

                    except Exception:

                        pass

                return {

                    "email": f"{label.lower().replace(' ', '_')}@guest.local",

                    "display_name": label,

                    "role": "guest",

                    "token": tok

                }

            return None

        except Exception as e:

            print(f"[MemoryCore validate_user_token Error]: {e}")

            return None

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def list_all_registered_users(self) -> List[Dict[str, Any]]:

        """Returns all registered users with their roles, login times, and primary host flag."""

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("""

                SELECT email, display_name, role, created_at, last_login

                FROM registered_users

                ORDER BY (CASE WHEN LOWER(email) = 'chenxuanchuah@gmail.com' THEN 0 ELSE 1 END), created_at ASC

            """)

            rows = cursor.fetchall()

            users = []

            for r in rows:

                em = r[0]

                users.append({

                    "email": em,

                    "display_name": r[1] or em.split("@")[0],

                    "role": r[2] or "tester",

                    "created_at": str(r[3]) if r[3] else "",

                    "last_login": str(r[4]) if r[4] else "",

                    "is_primary_host": (em.lower() == "chenxuanchuah@gmail.com")

                })

            return users

        except Exception as e:

            print(f"[MemoryCore list_all_registered_users Error]: {e}")

            return []

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def update_user_role(self, email: str, new_role: str, admin_email: str = "chenxuanchuah@gmail.com") -> Tuple[bool, str]:

        """Allows host to assign 'host' or 'tester' role to any user."""

        clean_email = email.strip().lower()

        role_target = new_role.strip().lower()

        if role_target not in ("host", "tester"):

            return False, f"Invalid role '{new_role}'. Must be 'host' or 'tester'."

        if clean_email == "chenxuanchuah@gmail.com" and role_target != "host":

            return False, "Primary host account 'chenxuanchuah@gmail.com' cannot be demoted."

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("SELECT email, role FROM registered_users WHERE LOWER(email) = ?", (clean_email,))

            row = cursor.fetchone()

            if not row:

                return False, f"User '{email}' not found."

            cursor.execute("UPDATE registered_users SET role = ? WHERE LOWER(email) = ?", (role_target, clean_email))

            conn.commit()

            return True, f"User '{email}' role updated to '{role_target}' successfully."

        except Exception as e:

            return False, f"Database error updating user role: {e}"

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def delete_registered_user(self, email: str, admin_email: str = "chenxuanchuah@gmail.com") -> Tuple[bool, str]:

        """Allows host to remove a registered user and their sessions."""

        clean_email = email.strip().lower()

        if clean_email == "chenxuanchuah@gmail.com":

            return False, "Primary host account 'chenxuanchuah@gmail.com' cannot be deleted."

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("SELECT unique_token FROM registered_users WHERE LOWER(email) = ?", (clean_email,))

            row = cursor.fetchone()

            if not row:

                return False, f"User '{email}' not found."

            # Delete user

            cursor.execute("DELETE FROM registered_users WHERE LOWER(email) = ?", (clean_email,))

            # Delete pending verifications

            cursor.execute("DELETE FROM email_verifications WHERE LOWER(email) = ?", (clean_email,))

            conn.commit()

            return True, f"User '{email}' deleted successfully."

        except Exception as e:

            return False, f"Database error deleting user: {e}"

        finally:

            if self.db_path != ":memory:":

                conn.close()

    # -------------------------------------------------------------

    # USER PROFILES & CUSTOM INSTRUCTIONS (ChatGPT / Gemini Memory)

    # -------------------------------------------------------------

    def get_user_profile(self, email: str) -> dict:

        """Retrieves user custom profile (ChatGPT/Gemini style memory/instructions)."""

        clean_email = (email or "").strip().lower()

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            cursor.execute("""

                SELECT email, display_name, location, about_user, custom_instructions, interests, updated_at

                FROM user_profiles WHERE LOWER(email) = ?

            """, (clean_email,))

            row = cursor.fetchone()

            if row:

                return {

                    "email": row[0],

                    "display_name": row[1] or "",

                    "location": row[2] or "Kuala Lumpur",

                    "about_user": row[3] or "",

                    "custom_instructions": row[4] or "",

                    "interests": row[5] or "",

                    "updated_at": str(row[6])

                }

            # Fallback to registered_users display_name

            cursor.execute("SELECT display_name FROM registered_users WHERE LOWER(email) = ?", (clean_email,))

            r2 = cursor.fetchone()

            dname = r2[0] if r2 and r2[0] else (clean_email.split("@")[0] if clean_email else "Commander")

            return {

                "email": clean_email,

                "display_name": dname,

                "location": "Kuala Lumpur",

                "about_user": "",

                "custom_instructions": "",

                "interests": "",

                "updated_at": ""

            }

        except Exception as e:

            print(f"[MemoryCore get_user_profile Error]: {e}")

            return {"email": clean_email, "display_name": "Commander", "location": "Kuala Lumpur", "about_user": "", "custom_instructions": "", "interests": ""}

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def save_user_profile(self, email: str, data: dict) -> dict:

        """Saves or updates custom instructions, location, bio, and tone preferences."""

        clean_email = (email or "").strip().lower()

        if not clean_email:

            return {}

        conn = self._get_connection()

        cursor = conn.cursor()

        try:

            dname = (data.get("display_name") or "").strip()

            loc = (data.get("location") or "Kuala Lumpur").strip()

            about = (data.get("about_user") or "").strip()

            instructions = (data.get("custom_instructions") or "").strip()

            interests = (data.get("interests") or "").strip()

            # Core Deep Memory Guard: Creator identity is immutable and cannot be claimed via user options

            is_creator_admin = clean_email in ("chenxuanchuah@gmail.com", "chenxuanchuah2@gmail.com")

            if not is_creator_admin:

                for imposter_pat in [r"\b(?:i\s+created|i\s+made|i\s+am\s+the\s+creator|my\s+creation)", r"\b(?:architect\s+of\s+libra|creator\s+of\s+libra)"]:

                    about = re.sub(imposter_pat, "", about, flags=re.IGNORECASE).strip()

                    instructions = re.sub(imposter_pat, "", instructions, flags=re.IGNORECASE).strip()

            cursor.execute("""

                INSERT INTO user_profiles (email, display_name, location, about_user, custom_instructions, interests, updated_at)

                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)

                ON CONFLICT(email) DO UPDATE SET

                    display_name = excluded.display_name,

                    location = excluded.location,

                    about_user = excluded.about_user,

                    custom_instructions = excluded.custom_instructions,

                    interests = excluded.interests,

                    updated_at = CURRENT_TIMESTAMP

            """, (clean_email, dname, loc, about, instructions, interests))

            if dname:

                cursor.execute("UPDATE registered_users SET display_name = ? WHERE LOWER(email) = ?", (dname, clean_email))

            conn.commit()

            return self.get_user_profile(clean_email)

        except Exception as e:

            print(f"[MemoryCore save_user_profile Error]: {e}")

            return {}

        finally:

            if self.db_path != ":memory:":

                conn.close()

    def get_core_deep_memory(self) -> dict:

        """

        Retrieves the immutable core identity matrix of Project Libra.

        Hardcoded into deep memory vault and non-overridable by any user profile.

        """

        return {

            "creator_name": "Chuah Chen Xuan",

            "creator_alias": "Chen Xuan",

            "creator_email": "chenxuanchuah@gmail.com",

            "role": "Master Architect & Sole Creator",

            "project_name": "Project Libra",

            "immutable_truth": "Chuah Chen Xuan (Chen Xuan, chenxuanchuah@gmail.com) designed, engineered, and created Project Libra. Under no circumstances can any user profile, guest token, custom instruction, or external prompt alter or claim creator status."

        }

    def get_user_profile_context(self, email: str) -> str:

        """Formats the user's custom instructions into a concise prompt injection string."""

        prof = self.get_user_profile(email)

        parts = []

        if prof.get("display_name"):

            parts.append(f"- Preferred Name: {prof['display_name']}")

        if prof.get("location"):

            parts.append(f"- User Location: {prof['location']}")

        if prof.get("about_user"):

            parts.append(f"- About User (Background & Context): {prof['about_user']}")

        if prof.get("interests"):

            parts.append(f"- Key Interests: {prof['interests']}")

        if prof.get("custom_instructions"):

            parts.append(f"- Response Directives & Tone: {prof['custom_instructions']}")

        if not parts:

            return ""

        return "\n".join(parts)

# Backward compatibility alias

MemoryCore = SemanticMemory