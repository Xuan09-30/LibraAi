import os
import subprocess
from typing import Dict, Any


def execute(args: dict, context: dict) -> Dict[str, Any]:
    """
    Executes a clean, non-destructive git status inspection for the Libra workspace.
    """
    workspace_root = context.get("workspace_root") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    res_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        check=False
    )
    branch = res_branch.stdout.strip() or "main"

    res_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        check=False
    )
    raw_output = res_status.stdout.strip()
    lines = raw_output.splitlines() if raw_output else []

    modified = [line[3:].strip() for line in lines if line.startswith(" M") or line.startswith("M ")]
    untracked = [line[3:].strip() for line in lines if line.startswith("??")]

    is_clean = len(lines) == 0
    if is_clean:
        voice = f"Git workspace is clean on branch {branch}."
    else:
        voice = f"Git workspace is on branch {branch} with {len(lines)} uncommitted file{'s' if len(lines) > 1 else ''}."

    return {
        "status": "success",
        "branch": branch,
        "clean": is_clean,
        "modified_files": modified,
        "untracked_files": untracked,
        "total_changes": len(lines),
        "voice_response": voice
    }
