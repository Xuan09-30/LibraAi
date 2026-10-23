import os
import sys
import json
import time
import shutil
import uuid
from enum import Enum
from typing import Optional, Dict, Any, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class RiskTier(str, Enum):
    GREEN = "green"  # Auto-run: read-only queries, search, weather, RAG, vitals
    AMBER = "amber"  # Notify & Undo: file writes/modifications, git commit
    RED = "red"      # Block & Prompt: file deletion, directory cleanup, terminal shell exec, git reset/clean


class ApprovalTicket(dict):
    """
    Approval ticket representing a blocked RED tier action awaiting approval.
    Supports both dict indexing (ticket['token']) and object methods (ticket.approve()).
    """
    def __init__(self, guard, token: str, action: str, target: str, description: str, diff_preview: str = "", callback=None):
        data = {
            "token": token,
            "tier": RiskTier.RED.value,
            "action": action,
            "target": target,
            "description": description,
            "diff_preview": diff_preview,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "pending_approval"
        }
        super().__init__(data)
        self.guard = guard
        self.token = token
        self.tier = RiskTier.RED
        self.action = action
        self.target = target
        self.description = description
        self.diff_preview = diff_preview
        self.callback = callback
        self.status = "pending_approval"

    def approve(self):
        res = self.guard.resolve_approval(self.token, True)
        self["status"] = "approved"
        self.status = "approved"
        return res

    def reject(self):
        res = self.guard.resolve_approval(self.token, False)
        self["status"] = "rejected"
        self.status = "rejected"
        return res


class TrustGuard:
    """
    Permissioned Risk Badges & Undo Snapshots Engine (v11.0 / Phase 11).
    Enforces a 3-tier execution policy:
      - Green: Auto-run without prompts.
      - Amber: Auto-snapshots file to .libra_trash/{filename}.{timestamp}.bak before write,
               allows instant undo.
      - Red: Intercepts destructive actions (deletions, shell exec, git resets),
             generates a confirmation card with diff preview, and waits for explicit approval.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(TrustGuard, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, trash_dir: Optional[str] = None):
        if getattr(self, "_initialized", False):
            if trash_dir is not None:
                self.trash_dir = trash_dir
                os.makedirs(self.trash_dir, exist_ok=True)
                self.manifest_file = os.path.join(self.trash_dir, "manifest.json")
                self._init_manifest()
            return
        self.trash_dir = trash_dir or os.path.join(PROJECT_ROOT, ".libra_trash")
        os.makedirs(self.trash_dir, exist_ok=True)
        self.manifest_file = os.path.join(self.trash_dir, "manifest.json")
        self.pending_approvals: Dict[str, Dict[str, Any]] = {}
        self.approval_callbacks: Dict[str, Any] = {}
        self._init_manifest()
        self._initialized = True

    def _init_manifest(self):
        if not os.path.exists(self.manifest_file):
            try:
                with open(self.manifest_file, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=2)
            except Exception as e:
                print(f"[TrustGuard Init Warning]: {e}")

    def _load_manifest(self) -> List[Dict[str, Any]]:
        try:
            if os.path.exists(self.manifest_file):
                with open(self.manifest_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_manifest(self, manifest: List[Dict[str, Any]]):
        try:
            with open(self.manifest_file, "w", encoding="utf-8") as f:
                json.dump(manifest[-200:], f, indent=2)  # Keep last 200 operations
        except Exception as e:
            print(f"[TrustGuard Save Manifest Error]: {e}")

    def classify_operation(self, op_type: str, target: str = "") -> RiskTier:
        """Classifies an operation into Green, Amber, or Red."""
        clean_op = (op_type or "").strip().lower()
        clean_target = (target or "").strip().lower()

        # Red: Destructive actions
        if any(k in clean_op for k in ["delete", "remove", "unlink", "rmtree", "clean", "reset", "shell_exec", "terminal", "kill"]):
            return RiskTier.RED
        if "git" in clean_op and any(k in clean_op for k in ["reset", "clean", "rebase", "checkout -f"]):
            return RiskTier.RED

        # Amber: Modifications, file creation, git commits
        if any(k in clean_op for k in ["write", "modify", "edit", "append", "touch", "create", "commit"]):
            return RiskTier.AMBER

        # Green: Read-only, search, weather, RAG, queries
        return RiskTier.GREEN

    def snapshot_file(self, file_path: str, op_name: str = "modify") -> Optional[str]:
        """
        Snapshots target file to .libra_trash/{filename}.{timestamp}.bak before modification.
        Returns the snapshot backup path, or None if file didn't exist yet.
        """
        if not file_path or not os.path.isfile(file_path):
            return None

        abs_path = os.path.abspath(file_path)
        base_name = os.path.basename(abs_path)
        timestamp = int(time.time() * 1000)
        bak_name = f"{base_name}.{timestamp}.bak"
        bak_path = os.path.join(self.trash_dir, bak_name)

        try:
            shutil.copy2(abs_path, bak_path)
            manifest = self._load_manifest()
            entry = {
                "id": str(uuid.uuid4())[:8],
                "original_path": abs_path,
                "bak_name": bak_name,
                "bak_path": bak_path,
                "timestamp": timestamp,
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "op": op_name
            }
            manifest.append(entry)
            self._save_manifest(manifest)
            return bak_path
        except Exception as e:
            print(f"[TrustGuard Snapshot Error]: {e}")
            return None

    def undo_last(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Reverts the latest .bak snapshot from .libra_trash/.
        If file_path is given, reverts the latest backup for that specific file.
        Otherwise reverts the most recent snapshot overall.
        """
        manifest = self._load_manifest()
        if not manifest:
            return {"status": "error", "message": "No undo history available."}

        target_entry = None
        target_idx = -1

        if file_path:
            abs_target = os.path.abspath(file_path)
            for i in range(len(manifest) - 1, -1, -1):
                if manifest[i]["original_path"] == abs_target:
                    target_entry = manifest[i]
                    target_idx = i
                    break
        else:
            target_entry = manifest[-1]
            target_idx = len(manifest) - 1

        if not target_entry:
            return {
                "status": "error",
                "message": f"No backup found for {file_path or 'recent operations'}."
            }

        bak_path = target_entry.get("bak_path")
        orig_path = target_entry.get("original_path")

        if not bak_path or not os.path.isfile(bak_path):
            return {"status": "error", "message": f"Backup file {bak_path} is missing."}

        try:
            # Ensure parent dir exists
            os.makedirs(os.path.dirname(orig_path), exist_ok=True)
            shutil.copy2(bak_path, orig_path)
            # Remove from manifest once undone
            manifest.pop(target_idx)
            self._save_manifest(manifest)

            return {
                "status": "success",
                "message": f"Successfully restored {orig_path} to snapshot from {target_entry.get('time_str')}.",
                "restored_path": orig_path,
                "timestamp": target_entry.get("time_str")
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to restore backup: {e}"}

    def request_red_approval(
        self,
        action_name: str,
        target: str,
        description: str,
        diff_preview: str = "",
        callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Registers a RED tier operation requiring explicit user confirmation.
        Returns ticket details containing a secure confirmation token.
        """
        token = str(uuid.uuid4())
        ticket = ApprovalTicket(
            guard=self,
            token=token,
            action=action_name,
            target=target,
            description=description,
            diff_preview=diff_preview,
            callback=callback
        )
        self.pending_approvals[token] = ticket
        if callback:
            self.approval_callbacks[token] = callback

        return ticket

    def resolve_approval(self, token: str, approved: bool) -> Dict[str, Any]:
        """Approves or rejects a pending RED tier operation."""
        ticket = self.pending_approvals.get(token)
        if not ticket:
            return {"status": "error", "message": "Invalid or expired approval token."}

        ticket["status"] = "approved" if approved else "rejected"
        callback = self.approval_callbacks.pop(token, None)

        res = {
            "status": "success",
            "approved": approved,
            "action": ticket["action"],
            "target": ticket["target"]
        }

        if approved and callback and callable(callback):
            try:
                cb_res = callback()
                res["callback_result"] = cb_res
            except Exception as e:
                res["callback_error"] = str(e)

        del self.pending_approvals[token]
        return res

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Returns list of currently pending RED approval requests."""
        return list(self.pending_approvals.values())

    def execute_with_guard(
        self,
        op_name: str,
        target: str,
        action_func: Any,
        description: str = "",
        diff_preview: str = ""
    ) -> Any:
        """
        Executes an operation through the TrustGuard 3-tier policy:
          - GREEN: Executes immediately.
          - AMBER: Automatically snapshots target file if it exists, then executes.
          - RED: Halts execution, returns pending ApprovalTicket awaiting ticket.approve().
        """
        tier = self.classify_operation(op_name, target)

        if tier == RiskTier.GREEN:
            return action_func() if callable(action_func) else None

        if tier == RiskTier.AMBER:
            if target and os.path.isfile(target):
                self.snapshot_file(target, op_name=op_name)
            return action_func() if callable(action_func) else None

        # Red Tier: Block & Prompt
        return self.request_red_approval(
            action_name=op_name,
            target=target,
            description=description or f"Destructive operation: {op_name}",
            diff_preview=diff_preview,
            callback=action_func
        )


# Singleton instance accessor
def get_trust_guard() -> TrustGuard:
    return TrustGuard()
