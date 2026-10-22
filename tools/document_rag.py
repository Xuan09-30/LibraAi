import os
import sys
import re
import json
import sqlite3
from typing import List, Dict, Any, Optional

try:
    import sqlite_vec
    SQLITE_VEC_AVAILABLE = True
except ImportError:
    SQLITE_VEC_AVAILABLE = False

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

try:
    import pymupdf
    PYMUPDF_AVAILABLE = True
except ImportError:
    try:
        import fitz as pymupdf
        PYMUPDF_AVAILABLE = True
    except ImportError:
        PYMUPDF_AVAILABLE = False

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

import requests
from tools.file_manager import FileManager
from tools.security_scanner import SecurityScanner

try:
    from flashrank import Ranker, RerankRequest
    FLASHRANK_AVAILABLE = True
except ImportError:
    Ranker = None
    RerankRequest = None
    FLASHRANK_AVAILABLE = False

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class DocumentRAGEngine:
    """
    Local Document RAG ("Chat with Your Files").
    Combines Voidtools Everything file location, multi-layer security pre-scanning,
    multi-format text extractors (PDF via pypdf/PyMuPDF, DOCX via python-docx,
    code/markdown via text reader), sliding window chunking, and sqlite-vec
    vector search for grounded Q&A.
    """

    def __init__(
        self,
        db_filename: str = "assets/libra_rag.db",
        file_mgr: Optional[FileManager] = None,
        ollama_base_url: str = "http://localhost:11434",
        embed_model: str = "nomic-embed-text",
        dim: int = 768,
        db_path: Optional[str] = None
    ):
        if db_path is not None:
            db_filename = db_path
        self.file_mgr = file_mgr if file_mgr is not None else FileManager()
        self.security_scanner = SecurityScanner(file_mgr=self.file_mgr)
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.embed_model = embed_model
        self.dim = dim
        self.ranker = None
        if FLASHRANK_AVAILABLE:
            try:
                self.ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir=os.path.join(PROJECT_ROOT, "assets", "flashrank_cache"))
            except Exception:
                self.ranker = None

        if db_filename == ":memory:":
            self.db_path = ":memory:"
            self._shared_conn = None
        else:
            self.db_path = os.path.join(PROJECT_ROOT, db_filename)
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._shared_conn = None

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._shared_conn is None:
                conn = sqlite3.connect(":memory:")
                if SQLITE_VEC_AVAILABLE:
                    try:
                        conn.enable_load_extension(True)
                        sqlite_vec.load(conn)
                        conn.enable_load_extension(False)
                    except Exception as e:
                        print(f"[DocumentRAG sqlite-vec Warning]: {e}")
                self._shared_conn = conn
            return self._shared_conn

        conn = sqlite3.connect(self.db_path)
        if SQLITE_VEC_AVAILABLE:
            try:
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
            except Exception as e:
                print(f"[DocumentRAG sqlite-vec Warning]: {e}")
        return conn

    def _init_db(self):
        """Initializes tables for documents, chunks, and vector index."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE,
                file_name TEXT,
                mtime REAL,
                chunk_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER,
                chunk_idx INTEGER,
                content TEXT NOT NULL,
                FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        """)

        if SQLITE_VEC_AVAILABLE:
            try:
                cursor.execute(f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
                        chunk_id INTEGER PRIMARY KEY,
                        embedding float[{self.dim}] distance_metric=cosine
                    )
                """)
            except Exception as e:
                print(f"[DocumentRAG vec0 Virtual Table Init Warning]: {e}")

        # FTS5 Full-Text Search Table for Hybrid RAG (Phase 4)
        try:
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
                    chunk_id UNINDEXED,
                    doc_id UNINDEXED,
                    content,
                    tokenize = 'porter unicode61'
                )
            """)
        except Exception as e:
            print(f"[DocumentRAG FTS5 Init Warning]: {e}")

        conn.commit()
        if self.db_path != ":memory:":
            conn.close()

    def extract_text(self, file_path: str) -> str:
        """Extracts text from PDF, DOCX, TXT, MD, Python, and other plain text formats."""
        if not os.path.isfile(file_path):
            return ""

        ext = os.path.splitext(file_path)[1].lower()

        # 1. PDF extraction
        if ext == ".pdf":
            if PYPDF_AVAILABLE:
                try:
                    reader = pypdf.PdfReader(file_path)
                    pages = []
                    for page in reader.pages:
                        txt = page.extract_text()
                        if txt:
                            pages.append(txt)
                    if pages:
                        return "\n\n".join(pages)
                except Exception as e:
                    pass

            if PYMUPDF_AVAILABLE:
                try:
                    doc = pymupdf.open(file_path)
                    pages = []
                    for page in doc:
                        txt = page.get_text()
                        if txt:
                            pages.append(txt)
                    doc.close()
                    return "\n\n".join(pages)
                except Exception as e:
                    return f"Error extracting PDF: {e}"

            return "Error: Neither pypdf nor PyMuPDF is available for PDF reading."

        # 2. DOCX extraction
        if ext in [".docx", ".doc"]:
            if not DOCX_AVAILABLE:
                return "Error: python-docx is not installed for DOCX reading."
            try:
                doc = docx.Document(file_path)
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                for table in doc.tables:
                    for row in table.rows:
                        row_txt = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                        if row_txt:
                            paragraphs.append(row_txt)
                return "\n".join(paragraphs)
            except Exception as e:
                return f"Error extracting DOCX: {e}"

        # 3. Plaintext, Markdown, Code, JSON, Logs
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            return f"Error reading text file: {e}"

    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 80) -> List[str]:
        """Splits long text into overlapping chunks, respecting paragraphs where possible."""
        clean_text = text.strip()
        if not clean_text:
            return []

        if len(clean_text) <= chunk_size:
            return [clean_text]

        chunks: List[str] = []
        step = max(50, chunk_size - overlap)
        start = 0

        while start < len(clean_text):
            end = start + chunk_size
            chunk = clean_text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += step

        return chunks

    def embed_text(self, text: str) -> List[float]:
        """Queries nomic-embed-text via Ollama."""
        clean = (text or "").strip()
        if not clean:
            return [0.0] * self.dim

        try:
            resp = requests.post(
                f"{self.ollama_base_url}/api/embeddings",
                json={
                    "model": self.embed_model,
                    "prompt": clean,
                    "keep_alive": "60m"
                },
                timeout=20
            )
            if resp.status_code == 200:
                emb = resp.json().get("embedding", [])
                if emb and len(emb) == self.dim:
                    return emb
            return [0.0] * self.dim
        except Exception:
            return [0.0] * self.dim

    def index_file(self, file_path: str, dry_run: bool = False) -> Dict[str, Any]:
        """Extracts, chunks, and indexes a file into sqlite-vec."""
        abs_path = os.path.abspath(file_path)
        if not os.path.isfile(abs_path):
            return {"status": "error", "error": f"File not found: {abs_path}"}

        mtime = os.path.getmtime(abs_path)
        file_name = os.path.basename(abs_path)

        conn = self._get_connection()
        cursor = conn.cursor()

        # Check if already indexed with matching mtime
        cursor.execute("SELECT id, mtime, chunk_count FROM documents WHERE file_path = ?", (abs_path,))
        row = cursor.fetchone()
        if row and abs(row[1] - mtime) < 0.001 and row[2] > 0:
            if self.db_path != ":memory:":
                conn.close()
            return {
                "status": "cached",
                "doc_id": row[0],
                "file_path": abs_path,
                "file_name": file_name,
                "chunk_count": row[2]
            }

        # If existing record with outdated mtime, clear old chunks
        if row:
            doc_id = row[0]
            cursor.execute("SELECT id FROM chunks WHERE doc_id = ?", (doc_id,))
            old_chunk_ids = [r[0] for r in cursor.fetchall()]
            cursor.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            try:
                cursor.execute("DELETE FROM fts_chunks WHERE doc_id = ?", (doc_id,))
            except Exception:
                pass
            if SQLITE_VEC_AVAILABLE and old_chunk_ids:
                for cid in old_chunk_ids:
                    try:
                        cursor.execute("DELETE FROM vec_chunks WHERE chunk_id = ?", (cid,))
                    except Exception:
                        pass
        else:
            cursor.execute(
                "INSERT INTO documents (file_path, file_name, mtime, chunk_count) VALUES (?, ?, ?, 0)",
                (abs_path, file_name, mtime)
            )
            doc_id = cursor.lastrowid

        text = self.extract_text(abs_path)
        chunks = self.chunk_text(text)

        if not chunks:
            conn.commit()
            if self.db_path != ":memory:":
                conn.close()
            return {
                "status": "empty",
                "doc_id": doc_id,
                "file_path": abs_path,
                "file_name": file_name,
                "chunk_count": 0
            }

        # Store chunks and vector embeddings + FTS5 index
        for idx, chunk_content in enumerate(chunks):
            cursor.execute(
                "INSERT INTO chunks (doc_id, chunk_idx, content) VALUES (?, ?, ?)",
                (doc_id, idx, chunk_content)
            )
            chunk_id = cursor.lastrowid

            try:
                cursor.execute(
                    "INSERT INTO fts_chunks (chunk_id, doc_id, content) VALUES (?, ?, ?)",
                    (chunk_id, doc_id, chunk_content)
                )
            except Exception:
                pass

            if not dry_run and SQLITE_VEC_AVAILABLE:
                emb = self.embed_text(chunk_content)
                if emb and any(emb):
                    try:
                        cursor.execute(
                            "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
                            (chunk_id, sqlite_vec.serialize_float32(emb))
                        )
                    except Exception as e:
                        print(f"[DocumentRAG Index Vector Warning]: {e}")

        cursor.execute("UPDATE documents SET mtime = ?, chunk_count = ? WHERE id = ?", (mtime, len(chunks), doc_id))
        conn.commit()
        if self.db_path != ":memory:":
            conn.close()

        return {
            "status": "indexed",
            "doc_id": doc_id,
            "file_path": abs_path,
            "file_name": file_name,
            "chunk_count": len(chunks)
        }

    def search_relevant_chunks(
        self,
        doc_id: Any = None,
        query: Optional[str] = None,
        top_k: int = 3,
        dry_run: bool = False
    ) -> List[str]:
        """
        Hybrid SQLite RAG (Phase 4):
        FTS5 BM25 keyword matching + sqlite-vec vector KNN combined via Reciprocal Rank Fusion (RRF),
        followed by FlashRank cross-encoder reranking (Phase 9).
        """
        if isinstance(doc_id, str) and query is None:
            query = doc_id
            doc_id = None
        elif isinstance(doc_id, str) and isinstance(query, (int, type(None))):
            doc_id, query = query, doc_id

        if not query:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        fts_results: List[Tuple[int, str]] = []  # (chunk_id, content)
        vec_results: List[Tuple[int, str]] = []  # (chunk_id, content)

        # 1. FTS5 BM25 Keyword Search
        try:
            tokens = [re.sub(r"[^\w]", "", t) for t in query.split() if len(t) >= 2]
            if tokens:
                fts_query = " OR ".join(tokens[:10])
                if doc_id is not None:
                    cursor.execute("""
                        SELECT c.id, c.content
                        FROM fts_chunks f
                        JOIN chunks c ON f.chunk_id = c.id
                        WHERE f.doc_id = ? AND fts_chunks MATCH ?
                        ORDER BY rank
                        LIMIT 15
                    """, (doc_id, fts_query))
                else:
                    cursor.execute("""
                        SELECT c.id, c.content
                        FROM fts_chunks f
                        JOIN chunks c ON f.chunk_id = c.id
                        WHERE fts_chunks MATCH ?
                        ORDER BY rank
                        LIMIT 15
                    """, (fts_query,))
                fts_results = [(r[0], r[1]) for r in cursor.fetchall()]
        except Exception:
            pass

        # 2. Vector Semantic KNN Search
        if not dry_run and SQLITE_VEC_AVAILABLE:
            query_emb = self.embed_text(query)
            if any(query_emb):
                try:
                    if doc_id is not None:
                        cursor.execute("""
                            SELECT c.id, c.content, v.distance
                            FROM vec_chunks v
                            JOIN chunks c ON v.chunk_id = c.id
                            WHERE c.doc_id = ? AND v.embedding MATCH ? AND k = 15
                            ORDER BY v.distance ASC
                        """, (doc_id, sqlite_vec.serialize_float32(query_emb)))
                    else:
                        cursor.execute("""
                            SELECT c.id, c.content, v.distance
                            FROM vec_chunks v
                            JOIN chunks c ON v.chunk_id = c.id
                            WHERE v.embedding MATCH ? AND k = 15
                            ORDER BY v.distance ASC
                        """, (sqlite_vec.serialize_float32(query_emb),))
                    vec_results = [(r[0], r[1]) for r in cursor.fetchall()]
                except Exception:
                    pass

        # If neither yielded results, fallback to sequential or lexical chunk scan
        if not fts_results and not vec_results:
            if doc_id is not None:
                cursor.execute("SELECT id, content FROM chunks WHERE doc_id = ? ORDER BY chunk_idx ASC", (doc_id,))
            else:
                cursor.execute("SELECT id, content FROM chunks ORDER BY chunk_idx ASC LIMIT 20")
            all_rows = cursor.fetchall()
            if self.db_path != ":memory:":
                conn.close()
            if not all_rows:
                return []

            q_terms = set(re.findall(r"\w+", query.lower())) - {"what", "is", "in", "the", "this", "file", "document", "to", "and", "a"}
            scored = []
            for cid, ch in all_rows:
                overlap = len(q_terms.intersection(set(re.findall(r"\w+", ch.lower()))))
                scored.append((overlap, ch))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [x[1] for x in scored[:top_k]]

        if self.db_path != ":memory:":
            conn.close()

        # 3. Reciprocal Rank Fusion (RRF)
        # Score(d) = sum( 1.0 / (60 + rank_i) )
        rrf_scores: Dict[int, float] = {}
        chunk_map: Dict[int, str] = {}

        for rank, (cid, content) in enumerate(fts_results, start=1):
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (60.0 + rank))
            chunk_map[cid] = content

        for rank, (cid, content) in enumerate(vec_results, start=1):
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (60.0 + rank))
            chunk_map[cid] = content

        sorted_cids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
        rrf_passages = [chunk_map[cid] for cid in sorted_cids[:15]]

        # Overview query handling: ensure beginning chunk is included if relevant
        query_lower = query.lower()
        is_overview = any(w in query_lower for w in ["inside", "summary", "summarize", "explain", "overview", "what is this", "what's this", "what is in", "about", "content"])
        if is_overview:
            conn2 = self._get_connection()
            c2 = conn2.cursor()
            c2.execute("SELECT content FROM chunks WHERE doc_id = ? ORDER BY chunk_idx ASC LIMIT 1", (doc_id,))
            first_row = c2.fetchone()
            if self.db_path != ":memory:":
                conn2.close()
            if first_row and first_row[0] not in rrf_passages:
                rrf_passages = [first_row[0]] + rrf_passages

        # 4. FlashRank Cross-Encoder Reranker (Phase 9)
        if FLASHRANK_AVAILABLE and self.ranker is not None and len(rrf_passages) > 1:
            try:
                passages_payload = [{"id": i, "text": p} for i, p in enumerate(rrf_passages[:12])]
                req = RerankRequest(query=query, passages=passages_payload)
                reranked = self.ranker.rerank(req)
                return [p["text"] for p in reranked[:top_k]]
            except Exception as e:
                print(f"[DocumentRAG FlashRank Warning]: {e}")

        return rrf_passages[:top_k]

    def query_document(
        self,
        file_query: str,
        question: str,
        llm_callback: Optional[Any] = None,
        dry_run: bool = False,
        llm: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Locates the file using Voidtools Everything, runs auto-security pre-scan,
        indexes if needed, retrieves matching context chunks, and synthesizes an answer.
        """
        clean_file_q = (file_query or "").strip()
        clean_question = (question or "").strip()

        # 1. Locate file
        target_path = None
        if os.path.isfile(clean_file_q):
            target_path = os.path.abspath(clean_file_q)
        else:
            found = self.file_mgr.search_path(clean_file_q, folders_only=False)
            if found and os.path.isfile(found):
                target_path = found

        if not target_path:
            msg = f"I couldn't find any file matching '{clean_file_q}' on your computer."
            return {
                "status": "not_found",
                "file_query": clean_file_q,
                "file_path": None,
                "voice_response": msg
            }

        file_name = os.path.basename(target_path)

        # 2. Auto-Security Pre-Check Gate
        sec_report = self.security_scanner.static_inspect(target_path)
        if sec_report.get("status") in ["threat_detected", "suspicious"] or sec_report.get("is_threat") or sec_report.get("is_suspicious"):
            return {
                "status": sec_report.get("status", "threat_detected"),
                "file_path": target_path,
                "file_name": file_name,
                "issues": sec_report.get("issues", []),
                "voice_response": f"Security alert: Document ingestion refused for {file_name}. A high-risk security threat was detected."
            }

        # 3. Index file
        idx_res = self.index_file(target_path, dry_run=dry_run)
        doc_id = idx_res.get("doc_id", 1)

        # 4. Retrieve relevant chunks
        chunks = self.search_relevant_chunks(
            doc_id=doc_id,
            query=clean_question or "summary",
            top_k=3,
            dry_run=dry_run
        )

        if not chunks:
            msg = f"Document {file_name} appears to be empty or contains no readable text."
            return {
                "status": "empty",
                "file_path": target_path,
                "file_name": file_name,
                "voice_response": msg
            }

        # 5. Dry-run synthesis
        active_llm = llm or llm_callback
        if dry_run or active_llm is None:
            snippet = chunks[0].replace("\n", " ").strip()
            if len(snippet) > 140:
                snippet = snippet[:140] + "..."
            voice_resp = f"According to {file_name}: {snippet}"
            return {
                "status": "success",
                "file_path": target_path,
                "file_name": file_name,
                "chunks": chunks,
                "answer": snippet,
                "voice_response": voice_resp
            }

        # 6. Live LLM synthesis
        context_block = "\n---\n".join(chunks)
        system_instruction = (
            "You are an expert document assistant. Answer the user's question concisely in 1-2 spoken sentences "
            "using ONLY the provided document context. Do not use markdown, bullet points, asterisks, or code blocks. "
            "If the answer is not in the context, say you could not find that information in the file."
        )
        user_prompt = f"Document context:\n{context_block}\n\nQuestion: {clean_question}"

        if callable(llm_callback):
            answer = llm_callback(user_prompt)
        elif hasattr(active_llm, "call_ollama"):
            answer = active_llm.call_ollama(
                model="qwen3:8b",
                prompt=user_prompt,
                system_prompt=system_instruction,
                as_json=False,
                timeout=30
            )
        else:
            answer = str(active_llm)

        clean_answer = (answer or "").strip()
        if not clean_answer:
            clean_answer = f"Found relevant information in {file_name} regarding your question."

        return {
            "status": "success",
            "file_path": target_path,
            "file_name": file_name,
            "chunks": chunks,
            "answer": clean_answer,
            "voice_response": clean_answer
        }
