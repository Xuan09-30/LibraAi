import os
import sys
import re
import json
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class ClipboardAgent:
    """
    Clipboard Copilot & Semantic Clipboard History.
    Reads and sanitizes clipboard text via native Windows ctypes (or pyperclip fallback),
    diagnoses errors/tracebacks or summarizes code without context switching,
    and archives notes into SemanticMemory and logs/clipboard_history.jsonl.
    """

    def __init__(self):
        self.available = PYPERCLIP_AVAILABLE

    def get_clipboard_text(self) -> str:
        """
        Reads and sanitizes text from Windows clipboard using native ctypes,
        with pyperclip as a fallback. Zero heavy dependencies required.
        """
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                CF_UNICODETEXT = 13

                user32.OpenClipboard.argtypes = [wintypes.HWND]
                user32.OpenClipboard.restype = wintypes.BOOL
                user32.CloseClipboard.restype = wintypes.BOOL
                user32.GetClipboardData.argtypes = [wintypes.UINT]
                user32.GetClipboardData.restype = wintypes.HANDLE
                kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
                kernel32.GlobalLock.restype = wintypes.LPVOID
                kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
                kernel32.GlobalUnlock.restype = wintypes.BOOL

                if user32.OpenClipboard(None):
                    try:
                        h_clip = user32.GetClipboardData(CF_UNICODETEXT)
                        if h_clip:
                            ptr = kernel32.GlobalLock(h_clip)
                            if ptr:
                                try:
                                    text = ctypes.c_wchar_p(ptr).value
                                    if text is not None:
                                        return text.strip()
                                finally:
                                    kernel32.GlobalUnlock(h_clip)
                    finally:
                        user32.CloseClipboard()
            except Exception as e:
                print(f"[ClipboardAgent ctypes warning]: {e}")

        if self.available:
            try:
                return (pyperclip.paste() or "").strip()
            except Exception as e:
                print(f"[ClipboardAgent pyperclip warning]: {e}")

        return ""

    def get_clipboard(self) -> str:
        """Alias for get_clipboard_text."""
        return self.get_clipboard_text()

    def set_clipboard(self, text: str) -> bool:
        """Safely writes text to clipboard."""
        if not self.available:
            return False
        try:
            pyperclip.copy(text)
            return True
        except Exception as e:
            print(f"[ClipboardAgent Warning] copy failed: {e}")
            return False

    def explain_clipboard(
        self,
        llm_callback: Optional[Any] = None,
        text: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Reads current clipboard text (e.g. Python traceback, C++ error, or code snippet)
        and prompts the LLM to explain or debug it concisely in 2-3 spoken sentences.
        """
        raw_text = text if text is not None else self.get_clipboard_text()
        clean_text = (raw_text or "").strip()

        if not clean_text:
            return {
                "status": "empty",
                "error_type": "None",
                "voice_response": "Your clipboard is empty. Please copy an error or text snippet first."
            }

        # 1. Deterministic error classification
        error_type = "Code / Text Snippet"
        if "Traceback (most recent call last)" in clean_text or re.search(r"\b[A-Za-z]+Error:", clean_text):
            error_type = "Python Traceback"
        elif re.search(r":\s*error:\s*", clean_text, re.IGNORECASE) or "undefined reference" in clean_text:
            error_type = "C/C++ Compiler Error"
        elif "Uncaught TypeError" in clean_text or "ReferenceError" in clean_text:
            error_type = "JavaScript Error"
        elif "SQLException" in clean_text or "syntax error at or near" in clean_text.lower():
            error_type = "SQL Exception"

        # 2. Extract error message if present
        extracted_err = ""
        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
        for line in reversed(lines):
            if any(k in line for k in ["Error:", "Exception:", "error:", "fatal:"]):
                extracted_err = line
                break
        if not extracted_err and lines:
            extracted_err = lines[-1]

        # 3. Dry-run isolation
        if dry_run or llm_callback is None:
            if error_type != "Code / Text Snippet":
                explanation = f"Detected {error_type}: {extracted_err}. Check your syntax or variable definition at the referenced line."
            else:
                snippet = clean_text[:100].replace("\n", " ")
                explanation = f"Clipboard contains {len(clean_text.split())} words discussing: {snippet}."

            return {
                "status": "diagnosed",
                "error_type": error_type,
                "error_line": extracted_err,
                "explanation": explanation,
                "voice_response": explanation
            }

        # 4. Live LLM diagnosis/explanation
        system_instruction = (
            "You are an expert software engineer and debugger. "
            "Explain the root cause of this error or summarize the code snippet and give the exact fix "
            "in 2-3 concise spoken sentences. "
            "Do not use markdown formatting, bullet points, asterisks, or code blocks."
        )

        # Handle callable vs LocalLLM instance
        if callable(llm_callback) and not hasattr(llm_callback, "call_ollama"):
            try:
                diagnosis = llm_callback(f"Analyze clipboard content:\n{clean_text[:1200]}")
            except Exception:
                diagnosis = ""
        elif hasattr(llm_callback, "call_ollama"):
            diagnosis = llm_callback.call_ollama(
                model="qwen3:8b",
                prompt=f"Analyze clipboard content:\n{clean_text[:1200]}",
                system_prompt=system_instruction,
                timeout=30
            )
        else:
            diagnosis = ""

        response_voice = diagnosis or f"Detected {error_type}: {extracted_err}."
        return {
            "status": "diagnosed",
            "error_type": error_type,
            "error_line": extracted_err,
            "explanation": response_voice,
            "voice_response": response_voice
        }

    def explain_error(
        self,
        text: Optional[str] = None,
        llm: Optional[Any] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Backwards compatibility alias for explain_clipboard."""
        return self.explain_clipboard(llm_callback=llm, text=text, dry_run=dry_run)

    def summarize_clipboard(
        self,
        text: Optional[str] = None,
        llm: Optional[Any] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Summarizes copied clipboard content in 1-2 spoken sentences."""
        raw_text = text if text is not None else self.get_clipboard_text()
        clean_text = (raw_text or "").strip()

        if not clean_text:
            return {
                "status": "empty",
                "voice_response": "Your clipboard is empty. Please copy text first to summarize."
            }

        if dry_run or llm is None:
            snippet = clean_text[:120].replace("\n", " ")
            summary = f"Your clipboard contains {len(clean_text.split())} words discussing: {snippet}."
            return {
                "status": "summarized",
                "length": len(clean_text),
                "summary": summary,
                "voice_response": summary
            }

        system_instruction = (
            "Summarize the provided text directly and conversationally in 1-2 spoken sentences. "
            "Do not use markdown, bullet points, asterisks, or brackets."
        )
        summary = llm.call_ollama(
            model="qwen3:8b",
            prompt=f"Text to summarize:\n{clean_text[:1500]}",
            system_prompt=system_instruction,
            timeout=30
        )
        voice_msg = summary or f"Your clipboard contains: {clean_text[:100]}."
        return {
            "status": "summarized",
            "length": len(clean_text),
            "summary": voice_msg,
            "voice_response": voice_msg
        }

    def save_clipboard_note(
        self,
        tag: str = "clipboard",
        note_name: Optional[str] = None,
        title: Optional[str] = None,
        text: Optional[str] = None,
        memory: Optional[Any] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Saves clipboard content into SemanticMemory and appends to logs/clipboard_history.jsonl.
        """
        final_title = title or note_name or "Clipboard Note"
        raw_text = text if text is not None else self.get_clipboard_text()
        clean_text = (raw_text or "").strip()

        if not clean_text:
            return {
                "status": "empty",
                "tag": tag,
                "title": final_title,
                "note_name": final_title,
                "voice_response": "Your clipboard is empty. Nothing was saved."
            }

        formatted_fact = f"Note '{final_title}' (tag: {tag}): {clean_text[:500]}"

        # 1. Store in SemanticMemory
        if not dry_run and memory is not None and hasattr(memory, "remember_fact"):
            memory.remember_fact(formatted_fact, category="clipboard_notes")

        # 2. Append to logs/clipboard_history.jsonl
        if not dry_run:
            try:
                log_dir = os.path.join(PROJECT_ROOT, "logs")
                os.makedirs(log_dir, exist_ok=True)
                history_path = os.path.join(log_dir, "clipboard_history.jsonl")
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "tag": tag,
                    "title": final_title,
                    "char_count": len(clean_text),
                    "text": clean_text[:1000]
                }
                with open(history_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception as e:
                print(f"[ClipboardAgent Log Note]: {e}")

        voice_msg = f"Saved your clipboard contents to note titled {final_title}."
        return {
            "status": "saved",
            "tag": tag,
            "title": final_title,
            "note_name": final_title,
            "char_count": len(clean_text),
            "voice_response": voice_msg
        }
