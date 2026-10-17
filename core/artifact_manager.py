import re
from typing import Tuple, List, Dict, Any, Optional
from tools.clipboard_agent import ClipboardAgent

LANGUAGE_LABELS = {
    "python": "Python script",
    "py": "Python script",
    "cpp": "C++ code",
    "c++": "C++ code",
    "c": "C code",
    "sql": "SQL query",
    "javascript": "JavaScript snippet",
    "js": "JavaScript snippet",
    "typescript": "TypeScript snippet",
    "ts": "TypeScript snippet",
    "html": "HTML markup",
    "css": "CSS styles",
    "json": "JSON payload",
    "bash": "shell script",
    "sh": "shell script",
    "powershell": "PowerShell script",
    "ps1": "PowerShell script",
}


class ArtifactManager:
    """
    Artifact & Code Block Separation Engine for Project Libra v6.0.
    Extracts fenced code blocks, Markdown tables, and long data lists from LLM responses,
    copies code directly to the system clipboard via ClipboardAgent, and returns clean,
    natural spoken summaries so raw code syntax is never read aloud by TTS.
    """

    def __init__(self, clipboard_agent: Optional[ClipboardAgent] = None):
        self.clipboard = clipboard_agent if clipboard_agent is not None else ClipboardAgent()
        self.last_artifacts: List[Dict[str, Any]] = []

    def process_response(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Detects code blocks, tables, and long bullet lists in `text`.
        Strips raw code from the spoken text, copies the artifact to the clipboard,
        and returns (clean_spoken_text, artifacts_list).
        """
        if not text:
            return "", []

        artifacts: List[Dict[str, Any]] = []
        working_text = text

        # 1. Extract fenced code blocks: ```lang ... ```
        code_pattern = re.compile(r"```([a-zA-Z0-9_\+\-\#]*)\s*\n?(.*?)```", re.DOTALL)
        for match in code_pattern.finditer(working_text):
            lang_raw = (match.group(1) or "").strip().lower()
            code_content = (match.group(2) or "").strip()
            if not code_content:
                continue

            label = LANGUAGE_LABELS.get(lang_raw, f"{lang_raw.upper()} code" if lang_raw else "code snippet")
            copied = self.clipboard.set_clipboard(code_content)
            artifacts.append({
                "type": "code",
                "language": lang_raw or "text",
                "label": label,
                "content": code_content,
                "copied_to_clipboard": copied
            })

        working_text = code_pattern.sub("", working_text)

        # 2. Extract Markdown tables (3+ consecutive lines with pipes | ... |)
        table_pattern = re.compile(r"(?:^\s*\|.+\|\s*$\n?){3,}", re.MULTILINE)
        for match in table_pattern.finditer(working_text):
            table_content = match.group(0).strip()
            copied = False
            if not artifacts:
                copied = self.clipboard.set_clipboard(table_content)
            artifacts.append({
                "type": "table",
                "language": "markdown",
                "label": "data table",
                "content": table_content,
                "copied_to_clipboard": copied
            })

        working_text = table_pattern.sub("", working_text)

        # 3. Extract long bulleted data lists (5+ consecutive bullet lines)
        list_pattern = re.compile(r"(?:^\s*(?:[\-\*\+]|\d+\.)\s+.+$\n?){5,}", re.MULTILINE)
        for match in list_pattern.finditer(working_text):
            list_content = match.group(0).strip()
            copied = False
            if not artifacts:
                copied = self.clipboard.set_clipboard(list_content)
            artifacts.append({
                "type": "list",
                "language": "markdown",
                "label": "structured list",
                "content": list_content,
                "copied_to_clipboard": copied
            })

        working_text = list_pattern.sub("", working_text)
        self.last_artifacts = artifacts

        if not artifacts:
            return text.strip(), []

        # Clean remaining prose for natural speech
        clean_prose = re.sub(r"`([^`]+)`", r"\1", working_text)
        clean_prose = re.sub(r"\s+", " ", clean_prose).strip()
        # Strip dangling colons at the end of intro sentences (e.g. "Here is the code:")
        clean_prose = re.sub(
            r"^(?:Here(?:'s|\s+is)\s+(?:the|a|your)\s+[^:\.]*[:\.]?\s*)",
            "",
            clean_prose,
            flags=re.IGNORECASE
        ).strip()
        clean_prose = clean_prose.rstrip(":")

        primary_label = artifacts[0].get("label", "code snippet")
        clipboard_notice = f"I've generated the {primary_label} for you and placed it on your clipboard."

        if clean_prose and len(clean_prose) > 8:
            # Keep at most 1 concise sentence of prose + the clipboard confirmation
            first_sent = re.split(r"(?<=[\.!\?])\s+", clean_prose)[0].strip()
            if not first_sent.endswith((".", "!", "?")):
                first_sent += "."
            spoken_summary = f"{first_sent} {clipboard_notice}"
        else:
            spoken_summary = clipboard_notice

        return spoken_summary, artifacts
