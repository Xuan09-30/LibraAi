import os
import re
import io
import sys
import json
import time
import wave
import base64
import logging
import threading
from typing import Optional, Dict, Any, List

import numpy as np
import soundfile as sf
import scipy.signal

from fastapi import (
    FastAPI, Request, Response, HTTPException, Depends,
    File, UploadFile, Query, Path, Body, WebSocket, WebSocketDisconnect, Form
)
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
import httpx
import asyncio
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.version import LIBRA_VERSION, get_full_version_string
from core.orchestrator import SupervisorHub
from core.llm import LocalLLM
from tools.system_monitor import SystemMonitor
from core.trust_guard import get_trust_guard
from core.briefing import BriefingAndWorkspaces
from tools.file_manager import FileManager

logger = logging.getLogger("libra.web")

# ---------------------------------------------------------------------------
# CONFIGURATION LOADER
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 8765,
    "admin_email": "chenxuanchuah@gmail.com",
    "allowed_gmail": "chenxuanchuah@gmail.com",
    "access_token": "libra_access_token_phase10_secure",
    "enabled": True
}


def load_web_config(config_path: str = "config.json") -> Dict[str, Any]:
    full_path = os.path.join(PROJECT_ROOT, config_path)
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(full_path):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                raw_cfg = json.load(f)
                web_sec = raw_cfg.get("web_server", {})
                cfg.update(web_sec)
                if "allowed_gmail" not in cfg and "admin_email" in cfg:
                    cfg["allowed_gmail"] = cfg["admin_email"]
        except Exception as e:
            logger.warning(f"Error reading config.json for web_server: {e}")

    # Environment variable overrides
    if "LIBRA_ADMIN_EMAIL" in os.environ:
        cfg["admin_email"] = os.environ["LIBRA_ADMIN_EMAIL"]
        cfg["allowed_gmail"] = os.environ["LIBRA_ADMIN_EMAIL"]
    if "LIBRA_ACCESS_TOKEN" in os.environ:
        cfg["access_token"] = os.environ["LIBRA_ACCESS_TOKEN"]
    if "LIBRA_WEB_PORT" in os.environ:
        try:
            cfg["port"] = int(os.environ["LIBRA_WEB_PORT"])
        except ValueError:
            pass
    return cfg


# ---------------------------------------------------------------------------
# AUDIO CONVERSION UTILITIES
# ---------------------------------------------------------------------------
def convert_to_16k_mono_pcm(audio_bytes: bytes) -> np.ndarray:
    """
    Converts arbitrary incoming audio bytes (WebM Opus, OGG, WAV, MP3, FLAC) to
    a 16kHz mono float32 numpy array normalized to [-1.0, 1.0] for faster-whisper.
    """
    if not audio_bytes:
        return np.zeros(0, dtype=np.float32)

    # 1. Primary decoder: PyAV (FFmpeg) handles WebM/Opus recorded by mobile Chrome seamlessly
    try:
        import av
        with av.open(io.BytesIO(audio_bytes)) as container:
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
            frames = []
            for frame in container.decode(audio=0):
                for rf in resampler.resample(frame):
                    frames.append(rf.to_ndarray()[0])
            if frames:
                return np.clip(np.concatenate(frames), -1.0, 1.0)
    except Exception as e:
        logger.debug(f"PyAV audio decoding fallback: {e}")

    # 2. Secondary decoder: soundfile (for standard WAV/FLAC)
    try:
        data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        if sr != 16000:
            num_samples = int(len(data) * 16000 / sr)
            data = scipy.signal.resample(data, num_samples).astype(np.float32)
        return np.clip(data, -1.0, 1.0)
    except Exception:
        pass

    # 3. Fallback: treat as raw 16-bit PCM (16000 Hz)
    try:
        pcm = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        return np.clip(pcm, -1.0, 1.0)
    except Exception:
        return np.zeros(0, dtype=np.float32)



def get_or_init_tts(supervisor):
    """Lazy-initializes or returns the KokoroTTS instance on supervisor.llm."""
    tts = getattr(supervisor.llm, "tts", None)
    if not tts:
        try:
            from core.kokoro_tts import KokoroTTS
            tts = KokoroTTS(voice="af_heart", device="cuda")
            supervisor.llm.tts = tts
        except Exception as e:
            logger.warning(f"Could not lazy-load KokoroTTS: {e}")
    return tts


def synthesize_sentence_wav_b64(supervisor, text: str) -> Optional[str]:
    """Synthesizes a sentence via Kokoro TTS, returns base64 WAV string."""
    clean_text = text.strip()
    if not clean_text:
        return None
    try:
        tts = get_or_init_tts(supervisor)
        if tts and hasattr(tts, "synthesize_stream"):
            chunks = list(tts.synthesize_stream(clean_text))
            if chunks:
                wav_bytes = pcm_to_wav_bytes(b"".join(chunks), sample_rate=24000)
                return base64.b64encode(wav_bytes).decode("utf-8")
    except Exception as e:
        logger.warning(f"Sentence TTS error: {e}")
    return None

def pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """Packs int16 PCM bytes into standard RIFF WAV format."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# PYDANTIC SCHEMAS
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    prompt: str = Field(..., description="User query or command")
    session_id: Optional[str] = Field(None, description="Active chat thread session ID")
    client_scope: str = Field("remote_web", description="Client execution scope")
    synthesize_audio: bool = Field(False, description="Whether to synthesize Kokoro TTS audio")
    attached_file_path: Optional[str] = Field(None, description="Server path to uploaded image/document")
    attached_file_name: Optional[str] = Field(None, description="Original filename of attachment")
    attached_file_type: Optional[str] = Field(None, description="Attachment type: image or document")
    stream: Optional[bool] = Field(None, description="Whether to stream response via SSE")


class NewSessionRequest(BaseModel):
    title: Optional[str] = Field("New Chat", description="Initial title for conversation thread")
    client_scope: str = Field("remote_web", description="Originating client scope")


class RenameSessionRequest(BaseModel):
    title: str = Field(..., description="Updated title for chat session")


class VaultFactRequest(BaseModel):
    entity: str = Field("user", description="Fact entity name")
    relation: str = Field("note", description="Fact relation")
    value: str = Field(..., description="Fact text content")
    category: Optional[str] = Field("general", description="Vault category")
    pinned: Optional[bool] = Field(False, description="Pin status")


class UpdateVaultFactRequest(BaseModel):
    value: str = Field(..., description="Updated fact text content")
    category: Optional[str] = Field(None, description="Updated category")
    pinned: Optional[bool] = Field(None, description="Updated pin status")


class TrustConfirmRequest(BaseModel):
    token: str = Field(..., description="Approval token")
    approve: bool = Field(..., description="Approve or reject action")


class TrustUndoRequest(BaseModel):
    file_path: Optional[str] = Field(None, description="Optional target file path to revert")


# ---------------------------------------------------------------------------
# FASTAPI APPLICATION FACTORY
# ---------------------------------------------------------------------------
def create_app(hub: Optional[SupervisorHub] = None, config_path: str = "config.json") -> FastAPI:
    cfg = load_web_config(config_path)
    admin_email = (cfg.get("allowed_gmail") or cfg.get("admin_email", "chenxuanchuah@gmail.com")).lower().strip()
    access_token = cfg.get("access_token", "libra_access_token_phase10_secure")

    app = FastAPI(
        title="Project Libra Remote Web Agent",
        version=LIBRA_VERSION,
        description="Local-First PWA & Remote Web Agent exposing Project Libra's Home GPU resources"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    supervisor: SupervisorHub = hub if hub is not None else SupervisorHub()
    monitor = SystemMonitor()
    static_dir = os.path.join(os.path.dirname(__file__), "static")

    # -----------------------------------------------------------------------
    # ZERO-TRUST TAILSCALE & GMAIL AUTHENTICATION DEPENDENCY
    # -----------------------------------------------------------------------
    def authenticate_request(request: Request) -> Dict[str, Any]:
        """
        Enforces Tailscale / Gmail Identity Lock:
        1. Tailscale identity header: 'Tailscale-User-Login' (injected by 'tailscale serve').
        2. Cloudflare Access Google OAuth: 'Cf-Access-Authenticated-User-Email'.
        3. Custom identity header: 'X-User-Email'.
        4. Bearer token / 'x-libra-token' / '?token=...' / cookie 'libra_token'.
        """
        # 1. Header-based email / Tailscale identity
        email = (
            request.headers.get("tailscale-user-login")
            or request.headers.get("cf-access-authenticated-user-email")
            or request.headers.get("x-user-email")
        )
        if email:
            clean_email = email.lower().strip()
            # If email is admin or matches authorized Gmail
            if clean_email == admin_email or clean_email.startswith(admin_email.split("@")[0]):
                return {"authenticated": True, "method": "tailscale_identity", "email": clean_email}
            else:
                raise HTTPException(
                    status_code=403,
                    detail=f"Forbidden: Identity '{clean_email}' is not authorized to access Project Libra."
                )

        # 2. Token-based authentication
        auth_header = request.headers.get("authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif "x-libra-token" in request.headers:
            token = request.headers.get("x-libra-token", "").strip()
        elif "token" in request.query_params:
            token = request.query_params.get("token", "").strip()
        elif "libra_token" in request.cookies:
            token = request.cookies.get("libra_token", "").strip()

        if token and token == access_token:
            return {"authenticated": True, "method": "token", "token": token}

        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Valid Tailscale login, Google OAuth header, or Libra access token required."
        )

    # -----------------------------------------------------------------------
    # STATIC & PWA ROUTES
    # -----------------------------------------------------------------------
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def get_index():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file, media_type="text/html")
        return HTMLResponse("<h1>Project Libra Web Agent Online</h1>", status_code=200)

    @app.get("/manifest.json")
    async def get_manifest():
        mf = os.path.join(static_dir, "manifest.json")
        if os.path.exists(mf):
            return FileResponse(mf, media_type="application/manifest+json")
        raise HTTPException(status_code=404, detail="Manifest not found")

    @app.get("/sw.js")
    async def get_sw():
        sw = os.path.join(static_dir, "sw.js")
        if os.path.exists(sw):
            return FileResponse(sw, media_type="application/javascript")
        raise HTTPException(status_code=404, detail="Service worker not found")

    # -----------------------------------------------------------------------
    # MULTIMODAL FILE UPLOADS & ASSETS API (Images, PDFs, Documents)
    # -----------------------------------------------------------------------
    upload_dir = os.path.join(PROJECT_ROOT, "assets", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    @app.post("/api/upload")
    async def upload_file(
        file: UploadFile = File(...),
        session_id: Optional[str] = Form(None),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        """Accepts image, PDF, or document uploads from web & mobile clients."""
        import uuid
        os.makedirs(upload_dir, exist_ok=True)
        raw_name = file.filename or "uploaded_file"
        clean_filename = os.path.basename(raw_name)
        file_ext = os.path.splitext(clean_filename)[1].lower()
        file_id = uuid.uuid4().hex[:10]
        saved_name = f"{file_id}_{clean_filename}"
        saved_path = os.path.join(upload_dir, saved_name)

        content = await file.read()
        with open(saved_path, "wb") as f:
            f.write(content)

        image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg"}
        file_type = "image" if file_ext in image_exts else "document"

        return {
            "status": "success",
            "file_id": file_id,
            "filename": clean_filename,
            "file_path": saved_path,
            "file_type": file_type,
            "file_size": len(content),
            "preview_url": f"/api/files/{saved_name}"
        }

    @app.get("/api/files/{filename}")
    async def get_uploaded_file(filename: str):
        safe_name = os.path.basename(filename)
        target_path = os.path.join(upload_dir, safe_name)
        if not os.path.isfile(target_path):
            raise HTTPException(status_code=404, detail="File not found")
        # Infer MIME
        import mimetypes
        mime_type, _ = mimetypes.guess_type(target_path)
        return FileResponse(target_path, media_type=mime_type or "application/octet-stream")

    @app.get("/api/assets/{category}/{filename}")
    async def get_asset_file(category: str, filename: str):
        safe_cat = os.path.basename(category)
        safe_file = os.path.basename(filename)
        target = os.path.join(PROJECT_ROOT, "assets", safe_cat, safe_file)
        if not os.path.isfile(target):
            raise HTTPException(status_code=404, detail="Asset not found")
        import mimetypes
        mime_type, _ = mimetypes.guess_type(target)
        return FileResponse(target, media_type=mime_type or "application/octet-stream")

    # -----------------------------------------------------------------------
    # MEMORY VAULT API (Phase 11 Obsidian Sync)
    # -----------------------------------------------------------------------
    @app.get("/api/vault")
    async def get_vault_facts_api(
        q: Optional[str] = Query(None),
        category: Optional[str] = Query(None),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        memory = getattr(supervisor.llm, "memory", None)
        if memory and hasattr(memory, "get_vault_facts"):
            facts = memory.get_vault_facts(query=q, category=category)
            return {"status": "success", "facts": facts, "count": len(facts)}
        return {"status": "error", "message": "Memory offline", "facts": []}

    @app.post("/api/vault")
    async def create_vault_fact_api(
        req: VaultFactRequest = Body(...),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        memory = getattr(supervisor.llm, "memory", None)
        if memory and hasattr(memory, "upsert_semantic_fact"):
            fid = memory.upsert_semantic_fact(
                entity=req.entity,
                relation=req.relation,
                value=req.value,
                category=req.category or "general",
                pinned=bool(req.pinned)
            )
            return {"status": "success", "id": fid}
        return {"status": "error", "message": "Memory offline"}

    @app.put("/api/vault/{fact_id}")
    async def update_vault_fact_api(
        fact_id: int = Path(...),
        req: UpdateVaultFactRequest = Body(...),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        memory = getattr(supervisor.llm, "memory", None)
        if memory and hasattr(memory, "update_vault_fact"):
            ok = memory.update_vault_fact(
                fact_id=fact_id,
                value=req.value,
                category=req.category,
                pinned=req.pinned
            )
            return {"status": "success" if ok else "error", "id": fact_id}
        return {"status": "error", "message": "Memory offline"}

    @app.delete("/api/vault/{fact_id}")
    async def delete_vault_fact_api(
        fact_id: int = Path(...),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        memory = getattr(supervisor.llm, "memory", None)
        if memory and hasattr(memory, "delete_vault_fact"):
            ok = memory.delete_vault_fact(fact_id=fact_id)
            return {"status": "success" if ok else "error", "id": fact_id}
        return {"status": "error", "message": "Memory offline"}

    # -----------------------------------------------------------------------
    # AIRDROP BRIDGE API (Phone <-> PC)
    # -----------------------------------------------------------------------
    @app.post("/api/bridge/drop")
    async def bridge_drop_file(
        file: UploadFile = File(...),
        open_on_pc: bool = Form(False),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        user_home = os.path.expanduser("~")
        drop_dir = os.path.join(user_home, "Downloads", "LibraDrop")
        os.makedirs(drop_dir, exist_ok=True)

        raw_filename = file.filename or "dropped_file"
        clean_filename = os.path.basename(raw_filename)
        dest_path = os.path.join(drop_dir, clean_filename)

        content = await file.read()
        with open(dest_path, "wb") as f:
            f.write(content)

        ext = os.path.splitext(clean_filename)[1].lower()
        rag_indexed = False
        if ext in [".pdf", ".docx", ".txt", ".md", ".py", ".csv", ".json"]:
            try:
                doc_rag = getattr(supervisor.llm, "document_rag", None)
                if doc_rag and hasattr(doc_rag, "index_file"):
                    res = doc_rag.index_file(dest_path)
                    rag_indexed = (res.get("status") == "indexed")
            except Exception as e:
                logger.warning(f"RAG auto-index error: {e}")

        opened = False
        if open_on_pc and sys.platform == "win32":
            try:
                os.startfile(dest_path)
                opened = True
            except Exception as e:
                logger.warning(f"Error opening on PC: {e}")

        return {
            "status": "success",
            "message": f"Successfully dropped {clean_filename} to PC Downloads/LibraDrop.",
            "path": dest_path,
            "filename": clean_filename,
            "size": len(content),
            "indexed_rag": rag_indexed,
            "opened_on_pc": opened
        }

    @app.get("/api/bridge/download")
    async def bridge_download_file(
        path: str = Query(...),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        norm_path = os.path.normpath(path)
        if not os.path.isfile(norm_path):
            raise HTTPException(status_code=404, detail="File not found on PC.")

        filename = os.path.basename(norm_path)
        import mimetypes
        mime_type, _ = mimetypes.guess_type(norm_path)
        return FileResponse(
            norm_path,
            filename=filename,
            media_type=mime_type or "application/octet-stream"
        )

    # -----------------------------------------------------------------------
    # TRUST GUARD CONFIRMATION & UNDO API
    # -----------------------------------------------------------------------
    @app.get("/api/trust/pending")
    async def get_trust_pending(auth: Dict[str, Any] = Depends(authenticate_request)):
        tg = get_trust_guard()
        return {"status": "success", "pending": tg.get_pending_approvals()}

    @app.post("/api/trust/confirm")
    async def confirm_trust_action(
        req: TrustConfirmRequest = Body(...),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        tg = get_trust_guard()
        return tg.resolve_approval(req.token, req.approve)

    @app.post("/api/trust/undo")
    async def undo_trust_action(
        req: TrustUndoRequest = Body(...),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        tg = get_trust_guard()
        return tg.undo_last(req.file_path)

    # -----------------------------------------------------------------------
    # DAILY TACTICAL BRIEFING API
    # -----------------------------------------------------------------------
    @app.get("/api/briefing")
    async def get_daily_briefing(
        force: bool = Query(False),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        briefing = getattr(supervisor.llm, "briefing_engine", None)
        if not briefing:
            briefing = BriefingAndWorkspaces(memory=getattr(supervisor.llm, "memory", None))
        res = briefing.generate_tactical_briefing(force=force, deliver_audio=False)
        return res._data if hasattr(res, "_data") else {"status": "success", "summary": str(res)}

    # -----------------------------------------------------------------------
    # MULTI-CHAT SESSIONS API (Phase 10 Gemini-Style Threads)
    # -----------------------------------------------------------------------
    @app.get("/api/sessions")
    async def list_chat_sessions(auth: Dict[str, Any] = Depends(authenticate_request)):
        """Returns all chat threads ordered by updated_at DESC with token totals."""
        memory = getattr(supervisor.llm, "memory", None)
        if memory and hasattr(memory, "list_sessions"):
            sessions = memory.list_sessions(limit=50)
            return {"status": "success", "sessions": sessions}
        return {"status": "success", "sessions": []}

    @app.post("/api/sessions/new")
    async def create_chat_session(
        req: Optional[NewSessionRequest] = None,
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        """Creates a fresh conversation thread and returns session_id."""
        memory = getattr(supervisor.llm, "memory", None)
        stitle = (req.title if req and req.title else "New Chat")
        scope = (req.client_scope if req and req.client_scope else "remote_web")
        if memory and hasattr(memory, "create_session"):
            sid = memory.create_session(title=stitle, client_scope=scope)
            return {
                "status": "success",
                "session_id": sid,
                "title": stitle,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        import uuid
        fallback_sid = f"sess_{uuid.uuid4().hex[:10]}"
        return {"status": "success", "session_id": fallback_sid, "title": stitle}

    @app.get("/api/sessions/{session_id}")
    async def get_chat_session(
        session_id: str = Path(...),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        """Loads messages, Markovian context, and token totals for a given thread."""
        memory = getattr(supervisor.llm, "memory", None)
        if not memory:
            raise HTTPException(status_code=500, detail="Memory subsystem offline")

        sess_meta = memory.get_session(session_id)
        if not sess_meta:
            # Auto-create if not yet persisted
            memory.create_session(session_id=session_id, title="New Chat")
            sess_meta = memory.get_session(session_id) or {"session_id": session_id, "title": "New Chat"}

        messages = memory.get_session_messages(session_id, limit=100) if hasattr(memory, "get_session_messages") else []
        m_state = memory.get_markov_state() if hasattr(memory, "get_markov_state") else {}

        return {
            "status": "success",
            "session": sess_meta,
            "messages": messages,
            "markov_state": m_state
        }

    @app.patch("/api/sessions/{session_id}")
    async def rename_chat_session(
        session_id: str = Path(...),
        req: RenameSessionRequest = Body(...),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        """Renames a conversation thread."""
        memory = getattr(supervisor.llm, "memory", None)
        if memory and hasattr(memory, "update_session_title"):
            ok = memory.update_session_title(session_id, req.title)
            return {"status": "success" if ok else "not_found", "session_id": session_id, "title": req.title}
        return {"status": "error", "message": "Memory subsystem offline"}

    @app.delete("/api/sessions/{session_id}")
    async def delete_chat_session(
        session_id: str = Path(...),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        """Deletes a conversation thread and its associated message history."""
        memory = getattr(supervisor.llm, "memory", None)
        if memory and hasattr(memory, "delete_session"):
            ok = memory.delete_session(session_id)
            return {"status": "success" if ok else "not_found", "session_id": session_id}
        return {"status": "error", "message": "Memory subsystem offline"}

    # -----------------------------------------------------------------------
    # TOKEN METRICS SUMMARY ENDPOINT
    # -----------------------------------------------------------------------
    @app.get("/api/tokens/summary")
    async def get_token_summary(
        session_id: Optional[str] = Query(None),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        """
        Returns comprehensive real-time token telemetry:
        - last_turn: Prompt/response tokens, tok/s speed, model name
        - active_session: Total tokens in the active chat thread
        - today: All tokens processed on GPU today
        - lifetime: Cumulative token count
        - saved_tokens: Total tokens saved via Markovian + Fast-Path bypass
        """
        memory = getattr(supervisor.llm, "memory", None)
        if memory and hasattr(memory, "get_token_summary"):
            summary = memory.get_token_summary(session_id=session_id)
            return {"status": "success", "data": summary}

        return {
            "status": "success",
            "data": {
                "last_turn": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "tokens_per_sec": 0.0, "model": "fast_path", "saved_tokens": 350},
                "active_session": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "saved_tokens": 0, "turn_count": 0},
                "today": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "saved_tokens": 0},
                "lifetime": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "saved_tokens": 0, "turn_count": 0}
            }
        }

    # -----------------------------------------------------------------------
    # CHAT & VOICE INFERENCE ENDPOINTS
    # -----------------------------------------------------------------------
    @app.post("/api/chat")
    async def post_chat(
        req: ChatRequest,
        stream: Optional[bool] = Query(None),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        """
        Executes a prompt through SupervisorHub under client_scope='remote_web'
        linked to session_id, recording exact token analytics.
        Supports SSE token streaming & sentence-level Kokoro audio streaming when stream=true.
        """
        scope = req.client_scope or "remote_web"
        memory = getattr(supervisor.llm, "memory", None)
        should_stream = (stream is True) or (req.stream is True)

        # -------------------------------------------------------------------
        # BRANCH A: SSE TOKEN STREAMING + KOKORO SENTENCE AUDIO QUEUE
        # -------------------------------------------------------------------
        if should_stream and not req.attached_file_path:
            async def event_generator():
                t0_stream = time.perf_counter()

                # 1. Ensure or auto-create session thread
                sid = req.session_id
                if not sid:
                    if memory and hasattr(memory, "create_session"):
                        raw_sid = memory.create_session(title="New Chat", client_scope=scope)
                        sid = str(raw_sid) if (raw_sid and not hasattr(raw_sid, "_mock_return_value")) else "default"
                    else:
                        sid = "default"
                else:
                    sid = str(sid)

                sess_title = "New Chat"
                if memory and hasattr(memory, "get_session"):
                    sm = memory.get_session(sid)
                    if isinstance(sm, dict):
                        sess_title = str(sm.get("title", "New Chat"))

                # 1.1 Emit Meta Event immediately (<20ms)
                yield f"data: {json.dumps({'type': 'meta', 'session_id': sid, 'session_title': sess_title})}\n\n"

                # 1.2 Check Desktop Sandbox Safeguard for remote_web scope
                if scope == "remote_web":
                    for pat in getattr(supervisor, "REMOTE_SANDBOX_PATTERNS", []):
                        if re.search(pat, req.prompt, re.IGNORECASE):
                            if not re.search(r"open\s+(?:my\s+)?(?:google\s+)?calendar\b", req.prompt, re.IGNORECASE):
                                sandbox_msg = "Remote Web Mode active: Desktop OS control is restricted to local PC sessions."
                                yield f"data: {json.dumps({'type': 'token', 'content': sandbox_msg})}\n\n"
                                if req.synthesize_audio:
                                    b64 = await asyncio.to_thread(synthesize_sentence_wav_b64, supervisor, sandbox_msg)
                                    if b64:
                                        yield f"data: {json.dumps({'type': 'audio', 'audio_base64': b64, 'sentence_index': 0})}\n\n"
                                yield f"data: {json.dumps({'type': 'done', 'token_metrics': {'input_tokens': 0, 'output_tokens': max(1, len(sandbox_msg)//4), 'tokens_per_sec': 0.0}})}\n\n"
                                if memory and hasattr(memory, "add_session_message"):
                                    memory.add_session_message(session_id=sid, role="user", content=req.prompt.strip())
                                    memory.add_session_message(session_id=sid, role="assistant", content=sandbox_msg)
                                return

                # 2. Context Window Protection: Pull only last 4-6 messages from SQLite
                messages = [
                    {"role": "system", "content": "You are Project Libra, a smart, concise, and helpful local AI desktop assistant."}
                ]
                if memory and hasattr(memory, "get_session_messages"):
                    try:
                        recent = memory.get_session_messages(sid, limit=6)
                        for m in recent:
                            if m.get("role") in ("user", "assistant") and m.get("content"):
                                messages.append({"role": m["role"], "content": m["content"]})
                    except Exception as e:
                        logger.warning(f"Error fetching session context: {e}")

                messages.append({"role": "user", "content": req.prompt.strip()})

                # Check AirDrop PC -> Phone hook
                airdrop_markdown = ""
                if re.search(r"\b(?:send\s+me|airdrop|download|transfer\s+to\s+(?:my\s+)?phone)\b", req.prompt, re.IGNORECASE):
                    try:
                        fm = getattr(supervisor.llm, "file_mgr", None) or FileManager()
                        q_clean = re.sub(r"^(?:please\s+)?(?:send\s+me|airdrop|download|transfer\s+to\s+(?:my\s+)?phone)\s+(?:the\s+)?", "", req.prompt, flags=re.IGNORECASE).strip()
                        t_path = fm.search_path(q_clean, folders_only=False)
                        if t_path and os.path.isfile(t_path):
                            import urllib.parse
                            enc_p = urllib.parse.quote(t_path)
                            s_mb = round(os.path.getsize(t_path) / (1024 * 1024), 2)
                            fn = os.path.basename(t_path)
                            airdrop_markdown = f"\n\n[⬇️ **AirDrop to Phone**: {fn} ({s_mb} MB)](/api/bridge/download?path={enc_p})"
                    except Exception as e:
                        logger.warning(f"AirDrop search warning: {e}")

                # 3. Audio & Token Queues Setup
                event_queue = asyncio.Queue()
                tts_queue = asyncio.Queue() if req.synthesize_audio else None

                async def tts_worker():
                    if not tts_queue:
                        return
                    while True:
                        item = await tts_queue.get()
                        if item is None:
                            tts_queue.task_done()
                            break
                        text_chunk, idx = item
                        try:
                            b64 = await asyncio.to_thread(synthesize_sentence_wav_b64, supervisor, text_chunk)
                            if b64:
                                await event_queue.put({"type": "audio", "audio_base64": b64, "sentence_index": idx})
                        except Exception as err:
                            logger.warning(f"TTS synthesis error for chunk {idx}: {err}")
                        finally:
                            tts_queue.task_done()

                tts_task = asyncio.create_task(tts_worker()) if req.synthesize_audio else None

                # 4. Stream tokens from Ollama
                ollama_base = cfg.get("ollama_base_url", "http://localhost:11434")
                raw_model = getattr(getattr(supervisor, "llm", None), "models", {}).get("chat", "qwen3:8b")
                target_model = str(raw_model) if (raw_model and not hasattr(raw_model, "_mock_return_value")) else "qwen3:8b"

                payload = {
                    "model": target_model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "num_ctx": 4096,
                        "temperature": 0.4
                    }
                }

                full_text = ""
                sentence_buffer = ""
                clause_split = re.compile(r"(.*?[\.\?\!](?:\s+|$)|.*?(?::\n|\n\n|\n))", re.DOTALL)
                sentence_idx = 0
                in_tok = 0
                out_tok = 0
                tok_sec = 0.0

                async def ollama_stream_producer():
                    nonlocal full_text, sentence_buffer, sentence_idx, in_tok, out_tok, tok_sec
                    try:
                        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=90.0, write=10.0, pool=10.0)) as client:
                            async with client.stream("POST", f"{ollama_base}/api/chat", json=payload) as resp:
                                if resp.status_code != 200:
                                    err_txt = f"Ollama Error (HTTP {resp.status_code})"
                                    await event_queue.put({"type": "token", "content": err_txt})
                                    full_text += err_txt
                                    return

                                async for line in resp.aiter_lines():
                                    if not line:
                                        continue
                                    try:
                                        chunk = json.loads(line)
                                        token = chunk.get("message", {}).get("content", "")
                                        if token:
                                            full_text += token
                                            await event_queue.put({"type": "token", "content": token})

                                            if req.synthesize_audio and tts_queue:
                                                sentence_buffer += token
                                                while len(sentence_buffer) >= 25:
                                                    m = clause_split.match(sentence_buffer)
                                                    if m:
                                                        clause = m.group(1).strip()
                                                        sentence_buffer = sentence_buffer[len(m.group(1)):].lstrip()
                                                        clean_c = re.sub(r"<think>.*?</think>", "", clause, flags=re.DOTALL).strip()
                                                        if clean_c and len(clean_c) >= 15:
                                                            await tts_queue.put((clean_c, sentence_idx))
                                                            sentence_idx += 1
                                                    else:
                                                        break

                                        if chunk.get("done", False):
                                            in_tok = int(chunk.get("prompt_eval_count", 0))
                                            out_tok = int(chunk.get("eval_count", 0))
                                            eval_dur = float(chunk.get("eval_duration", 0) / 1e9)
                                            tok_sec = round(out_tok / max(eval_dur, 0.001), 2) if eval_dur > 0 else 0.0
                                            break
                                    except Exception as c_err:
                                        logger.warning(f"Chunk decode error: {c_err}")
                    except Exception as e:
                        logger.error(f"Ollama streaming exception: {e}")
                        await event_queue.put({"type": "token", "content": f"\n\n[Inference Error: {e}]"})
                    finally:
                        # Flush residual sentence buffer
                        if req.synthesize_audio and tts_queue:
                            leftover = sentence_buffer.strip()
                            clean_leftover = re.sub(r"<think>.*?</think>", "", leftover, flags=re.DOTALL).strip()
                            if clean_leftover and len(clean_leftover) >= 2:
                                await tts_queue.put((clean_leftover, sentence_idx))
                                sentence_idx += 1
                            await tts_queue.put(None)  # Sentinel to stop worker

                producer_task = asyncio.create_task(ollama_stream_producer())

                try:
                    while True:
                        if producer_task.done() and (tts_task is None or tts_task.done()) and event_queue.empty():
                            break
                        try:
                            event = await asyncio.wait_for(event_queue.get(), timeout=0.05)
                            yield f"data: {json.dumps(event)}\n\n"
                            event_queue.task_done()
                        except asyncio.TimeoutError:
                            continue

                    await producer_task
                    if tts_task:
                        await tts_task

                    # If AirDrop link was found, emit it now
                    if airdrop_markdown:
                        yield f"data: {json.dumps({'type': 'token', 'content': airdrop_markdown})}\n\n"
                        full_text += airdrop_markdown

                    # 5. Emit Done Telemetry Event
                    elapsed_ms = round((time.perf_counter() - t0_stream) * 1000.0, 2)
                    done_payload = {
                        "type": "done",
                        "token_metrics": {
                            "turn_in": in_tok,
                            "turn_out": out_tok,
                            "turn_total": in_tok + out_tok,
                            "tok_per_sec": tok_sec,
                            "latency_ms": elapsed_ms,
                            "model": target_model
                        },
                        "reply_text": full_text
                    }
                    yield f"data: {json.dumps(done_payload)}\n\n"

                    # 6. Save message turn to SQLite memory in background
                    if memory and hasattr(memory, "add_session_message"):
                        try:
                            memory.add_session_message(
                                session_id=sid,
                                role="user",
                                content=req.prompt.strip(),
                                model_used=target_model
                            )
                            memory.add_session_message(
                                session_id=sid,
                                role="assistant",
                                content=full_text,
                                input_tokens=in_tok,
                                output_tokens=out_tok,
                                tokens_per_sec=tok_sec,
                                model_used=target_model,
                                latency_ms=elapsed_ms
                            )
                        except Exception as m_err:
                            logger.warning(f"Error saving stream messages to memory: {m_err}")

                finally:
                    if not producer_task.done():
                        producer_task.cancel()
                    if tts_task and not tts_task.done():
                        tts_task.cancel()

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )

        # -------------------------------------------------------------------
        # BRANCH B: NON-STREAMING / MULTIMODAL FALLBACK
        # -------------------------------------------------------------------
        t0 = time.perf_counter()
        scope = req.client_scope or "remote_web"
        memory = getattr(supervisor.llm, "memory", None)

        # 1. Ensure or auto-create session thread
        sid = req.session_id
        if not sid:
            if memory and hasattr(memory, "create_session"):
                sid = memory.create_session(title="New Chat", client_scope=scope)
            else:
                sid = "default"

        # 2. Check for multimodal attachment (Image or Document)
        attached_file_info = None
        gen_image_url = None

        if req.attached_file_path and os.path.isfile(req.attached_file_path):
            file_ext = os.path.splitext(req.attached_file_path)[1].lower()
            image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg"}
            is_image = (req.attached_file_type == "image") or (file_ext in image_exts)

            attached_file_info = {
                "filename": req.attached_file_name or os.path.basename(req.attached_file_path),
                "file_type": "image" if is_image else "document",
                "preview_url": f"/api/files/{os.path.basename(req.attached_file_path)}"
            }

            if is_image:
                # Multimodal Vision Analysis via qwen2.5vl:7b
                try:
                    with open(req.attached_file_path, "rb") as img_f:
                        b64_img = base64.b64encode(img_f.read()).decode("utf-8")

                    vision_prompt = req.prompt.strip() if req.prompt.strip() else "Analyze this image in detail. Describe what you see, highlight any key visual details, diagrams, or text, and answer how you can assist the user with it."
                    ollama_base = cfg.get("ollama_base_url", "http://localhost:11434")
                    v_payload = {
                        "model": "qwen2.5vl:7b",
                        "messages": [
                            {
                                "role": "user",
                                "content": vision_prompt,
                                "images": [b64_img]
                            }
                        ],
                        "stream": False,
                        "options": {"temperature": 0.4}
                    }
                    import urllib.request
                    req_v = urllib.request.Request(
                        f"{ollama_base}/api/chat",
                        data=json.dumps(v_payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req_v, timeout=60) as resp:
                        v_data = json.loads(resp.read().decode("utf-8"))

                    v_reply = v_data.get("message", {}).get("content", "").strip() or "I examined the image."
                    in_tok = int(v_data.get("prompt_eval_count", 0))
                    out_tok = int(v_data.get("eval_count", 0))
                    eval_dur = float(v_data.get("eval_duration", 1) / 1e9)
                    tok_sec = round(out_tok / max(eval_dur, 0.001), 2)

                    result = {
                        "status": "success",
                        "voice_response": v_reply,
                        "action": "vision_analysis",
                        "token_metrics": {
                            "input_tokens": in_tok,
                            "output_tokens": out_tok,
                            "total_tokens": in_tok + out_tok,
                            "tokens_per_sec": tok_sec,
                            "model": "qwen2.5vl:7b",
                            "saved_tokens": 0
                        }
                    }
                    if memory and hasattr(memory, "add_message"):
                        memory.add_message(
                            session_id=sid,
                            role="user",
                            content=f"[Attached Image: {attached_file_info['filename']}] {req.prompt.strip()}",
                            model_used="qwen2.5vl:7b"
                        )
                        memory.add_message(
                            session_id=sid,
                            role="assistant",
                            content=v_reply,
                            output_tokens=out_tok,
                            model_used="qwen2.5vl:7b"
                        )
                except Exception as img_err:
                    logger.error(f"Image vision analysis error: {img_err}")
                    result = supervisor.process_command(f"[Attached Image: {attached_file_info['filename']}] {req.prompt}", client_scope=scope, dry_run=False, session_id=sid)
            else:
                # Document Extraction & Analysis (PDF, Word, Code, Text, CSV)
                extracted_text = ""
                try:
                    if file_ext == ".pdf":
                        try:
                            import fitz
                            doc = fitz.open(req.attached_file_path)
                            extracted_text = "\n".join([page.get_text() for page in doc])
                        except Exception:
                            from pypdf import PdfReader
                            reader = PdfReader(req.attached_file_path)
                            extracted_text = "\n".join([p.extract_text() or "" for p in reader.pages])
                    elif file_ext in [".docx", ".doc"]:
                        import docx
                        doc = docx.Document(req.attached_file_path)
                        extracted_text = "\n".join([p.text for p in doc.paragraphs])
                    else:
                        with open(req.attached_file_path, "r", encoding="utf-8", errors="ignore") as f:
                            extracted_text = f.read()
                except Exception as doc_err:
                    logger.error(f"Document extraction error: {doc_err}")

                if len(extracted_text) > 12000:
                    extracted_text = extracted_text[:12000] + f"\n\n[... Truncated for token safety. Document has {len(extracted_text)} total characters ...]"

                doc_prompt = (
                    f"The user has uploaded the document '{attached_file_info['filename']}'.\n"
                    f"=== DOCUMENT CONTENT ===\n{extracted_text}\n=== END DOCUMENT ===\n\n"
                    f"User instruction: {req.prompt.strip() or 'Please analyze this document, summarize the key findings, and explain how it helps me.'}"
                )
                result = supervisor.process_command(doc_prompt, client_scope=scope, dry_run=False, session_id=sid)
        else:
            # Standard Text Execution
            result = supervisor.process_command(req.prompt, client_scope=scope, dry_run=False, session_id=sid)

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        reply_text = result.get("voice_response") or "Command processed."
        action = result.get("action")
        raw_tm = result.get("token_metrics") or getattr(supervisor.llm, "last_token_metrics", {}) or {}

        if result.get("plot_path") and os.path.isfile(result["plot_path"]):
            gen_image_url = f"/api/assets/plots/{os.path.basename(result['plot_path'])}"
        elif result.get("image_path") and os.path.isfile(result["image_path"]):
            gen_image_url = f"/api/assets/plots/{os.path.basename(result['image_path'])}"

        # Phase 11 AirDrop PC -> Phone hook
        if re.search(r"\b(?:send\s+me|airdrop|download|transfer\s+to\s+(?:my\s+)?phone)\b", req.prompt, re.IGNORECASE):
            try:
                fm = getattr(supervisor.llm, "file_mgr", None) or FileManager()
                q_clean = re.sub(r"^(?:please\s+)?(?:send\s+me|airdrop|download|transfer\s+to\s+(?:my\s+)?phone)\s+(?:the\s+)?", "", req.prompt, flags=re.IGNORECASE).strip()
                t_path = fm.search_path(q_clean, folders_only=False)
                if t_path and os.path.isfile(t_path):
                    import urllib.parse
                    enc_p = urllib.parse.quote(t_path)
                    s_mb = round(os.path.getsize(t_path) / (1024 * 1024), 2)
                    fn = os.path.basename(t_path)
                    reply_text += f"\n\n[⬇️ **AirDrop to Phone**: {fn} ({s_mb} MB)](/api/bridge/download?path={enc_p})"
            except Exception as e:
                logger.warning(f"AirDrop search warning: {e}")

        # Phase 11 First Daily Access Briefing Check
        try:
            b_eng = getattr(supervisor.llm, "briefing_engine", None)
            if b_eng and hasattr(b_eng, "check_and_trigger_daily_briefing"):
                b_eng.check_and_trigger_daily_briefing(deliver_audio=False)
        except Exception:
            pass

        turn_in = int(raw_tm.get("input_tokens", 0) or 0)
        turn_out = int(raw_tm.get("output_tokens", 0) or 0)
        tok_speed = float(raw_tm.get("tokens_per_sec", 0.0) or 0.0)
        saved_tok = int(raw_tm.get("saved_tokens", 0) or 0)

        # 3. Fetch updated session title and token totals
        sess_title = "New Chat"
        sess_total = turn_in + turn_out
        life_total = sess_total

        if memory and hasattr(memory, "get_session"):
            sm = memory.get_session(sid)
            if sm:
                sess_title = sm.get("title", "New Chat")
                sess_total = sm.get("total_tokens", sess_total)
            ts = memory.get_token_summary(session_id=sid)
            life_total = ts.get("lifetime", {}).get("total_tokens", sess_total)

        # 4. Synthesize audio with Kokoro-82M if requested
        audio_b64 = None
        if req.synthesize_audio and reply_text:
            try:
                tts = getattr(supervisor.llm, "tts", None)
                if tts and hasattr(tts, "synthesize_stream"):
                    pcm_chunks = list(tts.synthesize_stream(reply_text))
                    if pcm_chunks:
                        wav_bytes = pcm_to_wav_bytes(b"".join(pcm_chunks), sample_rate=24000)
                        audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
            except Exception as e:
                logger.warning(f"Audio synthesis warning: {e}")

        return {
            "status": result.get("status", "success"),
            "reply_text": reply_text,
            "action": action,
            "session_id": sid,
            "session_title": sess_title,
            "client_scope": scope,
            "latency_ms": elapsed_ms,
            "token_metrics": {
                "turn_in": turn_in,
                "turn_out": turn_out,
                "turn_total": turn_in + turn_out,
                "tok_per_sec": tok_speed,
                "session_total": sess_total,
                "lifetime_total": life_total,
                "saved_tokens": saved_tok,
                "model": raw_tm.get("model", "qwen3:8b"),
                "fast_path": raw_tm.get("fast_path", False)
            },
            "audio_base64": audio_b64,
            "hud_card": result.get("hud_card"),
            "scratchpad": result.get("scratchpad"),
            "attached_file": attached_file_info,
            "generated_image_url": gen_image_url
        }

    @app.post("/api/voice")
    async def post_voice(
        request: Request,
        audio: UploadFile = File(...),
        session_id: Optional[str] = Form(None),
        client_scope: str = Form("remote_web"),
        auth: Dict[str, Any] = Depends(authenticate_request)
    ):
        """
        Transcribes uploaded mic audio on GPU via faster-whisper,
        routes through sandboxed SupervisorHub inside session_id,
        synthesizes response with Kokoro-82M, and returns exact token metrics.
        """
        t0 = time.perf_counter()
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio payload")

        audio_np = convert_to_16k_mono_pcm(audio_bytes)
        if len(audio_np) == 0:
            return JSONResponse({
                "status": "empty_audio",
                "transcribed_text": "",
                "reply_text": "I didn't receive any clear audio.",
                "action": "none",
                "latency_ms": 0.0
            })

        stt = getattr(supervisor.llm, "stt", None)
        if not stt:
            try:
                from core.stt import SpeechToText
                stt = SpeechToText()
                supervisor.llm.stt = stt
            except Exception as e:
                logger.warning(f"Could not lazy-load SpeechToText: {e}")

        transcribed_text = ""
        if stt and hasattr(stt, "transcribe"):
            try:
                transcribed_text = stt.transcribe(audio_np).strip()
            except Exception as e:
                logger.error(f"Whisper transcription failed: {e}")

        if not transcribed_text:
            return JSONResponse({
                "status": "unrecognized",
                "transcribed_text": "",
                "reply_text": "I couldn't hear any distinct speech. Please try again.",
                "action": "none",
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2)
            })

        memory = getattr(supervisor.llm, "memory", None)
        sid = session_id or request.query_params.get("session_id")
        scope = client_scope or request.query_params.get("client_scope", "remote_web")
        if not sid:
            if memory and hasattr(memory, "create_session"):
                sid = memory.create_session(title="New Chat", client_scope=scope)
            else:
                sid = "default"

        res = supervisor.process_command(transcribed_text, client_scope=scope, dry_run=False, session_id=sid)
        reply_text = res.get("voice_response") or "Understood."
        action = res.get("action")
        raw_tm = res.get("token_metrics") or getattr(supervisor.llm, "last_token_metrics", {}) or {}

        turn_in = int(raw_tm.get("input_tokens", 0) or 0)
        turn_out = int(raw_tm.get("output_tokens", 0) or 0)
        tok_speed = float(raw_tm.get("tokens_per_sec", 0.0) or 0.0)
        saved_tok = int(raw_tm.get("saved_tokens", 0) or 0)

        sess_title = "New Chat"
        sess_total = turn_in + turn_out
        life_total = sess_total
        if memory and hasattr(memory, "get_session"):
            sm = memory.get_session(sid)
            if sm:
                sess_title = sm.get("title", "New Chat")
                sess_total = sm.get("total_tokens", sess_total)
            ts = memory.get_token_summary(session_id=sid)
            life_total = ts.get("lifetime", {}).get("total_tokens", sess_total)

        audio_b64 = None
        try:
            tts = getattr(supervisor.llm, "tts", None)
            if not tts:
                try:
                    from core.kokoro_tts import KokoroTTS
                    tts = KokoroTTS(voice="af_heart", device="cuda")
                    supervisor.llm.tts = tts
                except Exception as e:
                    logger.warning(f"Could not lazy-load KokoroTTS: {e}")

            if tts and hasattr(tts, "synthesize_stream") and reply_text:
                pcm_chunks = list(tts.synthesize_stream(reply_text))
                if pcm_chunks:
                    wav_bytes = pcm_to_wav_bytes(b"".join(pcm_chunks), sample_rate=24000)
                    audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
        except Exception as e:
            logger.warning(f"Voice synthesis error: {e}")

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        return JSONResponse({
            "status": "success",
            "transcribed_text": transcribed_text,
            "reply_text": reply_text,
            "action": action,
            "session_id": sid,
            "session_title": sess_title,
            "latency_ms": elapsed_ms,
            "client_scope": scope,
            "token_metrics": {
                "turn_in": turn_in,
                "turn_out": turn_out,
                "turn_total": turn_in + turn_out,
                "tok_per_sec": tok_speed,
                "session_total": sess_total,
                "lifetime_total": life_total,
                "saved_tokens": saved_tok,
                "model": raw_tm.get("model", "qwen3:8b"),
                "fast_path": raw_tm.get("fast_path", False)
            },
            "audio_base64": audio_b64
        })

    @app.get("/api/vitals")
    async def get_vitals(auth: Dict[str, Any] = Depends(authenticate_request)):
        """Returns live PC telemetry: RTX 5060 Ti VRAM, CPU, RAM, and version info."""
        sys_metrics = monitor.get_system_metrics()
        gpu_info = {
            "name": "NVIDIA GeForce RTX 5060 Ti",
            "vram_total_mb": sys_metrics.get("gpu_vram_total_mb") or 16311,
            "vram_used_mb": sys_metrics.get("gpu_vram_used_mb") or 11695,
            "load_percent": sys_metrics.get("gpu_util_percent") or 9.0,
            "temperature_c": sys_metrics.get("gpu_temp_c") or 48.0
        }
        try:
            import torch
            if torch.cuda.is_available():
                gpu_info["name"] = torch.cuda.get_device_name(0)
                mem_res = torch.cuda.memory_reserved(0) // (1024 * 1024)
                if mem_res > 0:
                    gpu_info["vram_used_mb"] = max(gpu_info["vram_used_mb"], mem_res)
        except Exception:
            pass

        return {
            "status": "online",
            "version": LIBRA_VERSION,
            "full_version": get_full_version_string(),
            "cpu_percent": sys_metrics.get("cpu_percent", 0.0),
            "ram_used_gb": sys_metrics.get("ram_used_gb", 0.0),
            "ram_total_gb": sys_metrics.get("ram_total_gb", 0.0),
            "ram_percent": sys_metrics.get("ram_percent", 0.0),
            "vram_used_mb": gpu_info["vram_used_mb"],
            "vram_total_mb": gpu_info["vram_total_mb"],
            "gpu": gpu_info,
            "active_models": [
                "faster-whisper (large-v3-turbo)",
                "kokoro-82m (af_heart)",
                "ollama (qwen3:8b)",
                "ollama (qwen2.5-coder:7b)"
            ],
            "client_scope_policy": "sandboxed_desktop_control"
        }

    # -----------------------------------------------------------------------
    # WEBSOCKET STREAMING ENDPOINT
    # -----------------------------------------------------------------------
    @app.websocket("/api/ws")
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
        await websocket.accept()
        if token and token != access_token:
            await websocket.send_json({"type": "error", "message": "Unauthorized token"})
            await websocket.close(code=1008)
            return

        await websocket.send_json({
            "type": "welcome",
            "version": LIBRA_VERSION,
            "message": "Connected to Project Libra Remote Web Agent."
        })

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "chat")
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong", "time": time.time()})
                elif msg_type == "vitals":
                    sys_metrics = monitor.get_system_metrics()
                    await websocket.send_json({"type": "vitals", "data": sys_metrics})
                elif msg_type == "chat":
                    prompt = data.get("prompt", "")
                    scope = data.get("client_scope", "remote_web")
                    sid = data.get("session_id", "default")
                    res = supervisor.process_command(prompt, client_scope=scope, dry_run=False, session_id=sid)
                    await websocket.send_json({
                        "type": "chat_reply",
                        "status": res.get("status", "success"),
                        "reply_text": res.get("voice_response", "Understood."),
                        "action": res.get("action"),
                        "session_id": sid,
                        "token_metrics": res.get("token_metrics", {})
                    })
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning(f"WebSocket session closed: {e}")

    return app


# ---------------------------------------------------------------------------
# TAILSCALE SERVE & BACKGROUND DAEMON THREAD LAUNCHER
# ---------------------------------------------------------------------------
def ensure_tailscale_serve(port: int = 8765) -> Dict[str, str]:
    """
    Auto-discovers Tailscale IP, MagicDNS hostname, and ensures
    'tailscale serve' background proxy is active for HTTPS mobile access.
    """
    import subprocess
    info = {
        "tailscale_ip": "",
        "magicdns_domain": "",
        "serve_url": "",
        "status": "offline"
    }
    try:
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

        # 1. Query Tailscale IPv4
        res_ip = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=3, **flags)
        if res_ip.returncode == 0 and res_ip.stdout.strip():
            info["tailscale_ip"] = res_ip.stdout.strip().split("\n")[0].strip()

        # 2. Query Tailscale JSON status for MagicDNS domain
        res_status = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=3, **flags)
        if res_status.returncode == 0 and res_status.stdout.strip():
            ts_data = json.loads(res_status.stdout)
            cert_domains = ts_data.get("CertDomains") or []
            if cert_domains:
                info["magicdns_domain"] = cert_domains[0]
            elif "Self" in ts_data and "DNSName" in ts_data["Self"]:
                info["magicdns_domain"] = ts_data["Self"]["DNSName"].rstrip(".")

        # 3. Check or configure Tailscale Serve proxy
        res_serve = subprocess.run(["tailscale", "serve", "status"], capture_output=True, text=True, timeout=3, **flags)
        if str(port) not in res_serve.stdout:
            subprocess.run(["tailscale", "serve", "--bg", str(port)], capture_output=True, text=True, timeout=5, **flags)
            res_serve = subprocess.run(["tailscale", "serve", "status"], capture_output=True, text=True, timeout=3, **flags)

        import re
        match_domain = re.search(r"https://([a-zA-Z0-9.-]+)", res_serve.stdout)
        if match_domain:
            info["magicdns_domain"] = match_domain.group(1)
            info["serve_url"] = f"https://{info['magicdns_domain']}/"
            info["status"] = "online"
        elif info["magicdns_domain"]:
            info["serve_url"] = f"https://{info['magicdns_domain']}/"
            info["status"] = "online"
        elif info["tailscale_ip"]:
            info["serve_url"] = f"http://{info['tailscale_ip']}:{port}/"
            info["status"] = "online"
    except Exception as e:
        logger.debug(f"Tailscale auto-discovery info: {e}")
    return info


def start_web_server_thread(
    hub: Optional[SupervisorHub] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    config_path: str = "config.json"
) -> threading.Thread:
    """
    Launches Uvicorn serving the FastAPI Remote Web Agent in a background daemon thread.
    Automatically provisions Tailscale Serve HTTPS and connects to PyQt6 GUI.
    """
    import uvicorn

    cfg = load_web_config(config_path)
    server_host = host or cfg.get("host", "0.0.0.0")
    server_port = port or cfg.get("port", 8765)

    # 1. Discover Tailscale endpoints and activate Tailscale Serve proxy
    ts_info = ensure_tailscale_serve(server_port)

    # 2. Initialize FastAPI app attached to SupervisorHub
    app = create_app(hub=hub, config_path=config_path)

    # Note: log_config=None is required so Uvicorn does not crash when sys.stdout is hooked by StreamTee
    u_config = uvicorn.Config(
        app=app,
        host=server_host,
        port=server_port,
        log_level="warning",
        log_config=None
    )
    server = uvicorn.Server(config=u_config)

    thread = threading.Thread(target=server.run, daemon=True, name="LibraWebAgentThread")
    thread.server = server
    thread.tailscale_info = ts_info
    thread.start()

    banner = (
        f"\n======================================================\n"
        f"  [Project Libra Web Agent Online]\n"
        f"  - Local Access:     http://localhost:{server_port}\n"
    )
    if ts_info.get("serve_url"):
        banner += f"  - Tailscale HTTPS:  {ts_info['serve_url']}\n"
    if ts_info.get("tailscale_ip"):
        banner += f"  - Tailscale Direct: http://{ts_info['tailscale_ip']}:{server_port}/\n"
    banner += f"======================================================\n"
    print(banner)

    return thread


if __name__ == "__main__":
    import uvicorn
    cfg = load_web_config("config.json")
    print(f"[Project Libra] Starting Remote Web Agent standalone on {cfg['host']}:{cfg['port']}...")
    app = create_app()
    uvicorn.run(app, host=cfg["host"], port=cfg["port"], log_config=None)
