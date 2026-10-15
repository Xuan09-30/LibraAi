import os
import sys
import shutil
import subprocess
import webbrowser
from typing import Dict, Any, Optional, List

from core.dispatcher import SafeOSDispatcher
from core.scheduler import ReminderEngine
from core.model_manager import ModelManager
from tools.file_manager import FileManager

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class WorkspaceManager:
    """
    One-Command Workspace Profiles for Project Libra.
    Configures PC state for dedicated workflows:
    - 'coding': Opens code editor / project workspace and developer browser.
    - 'study': Opens notes directory and schedules a 45-minute Pomodoro timer.
    - 'gaming': Evicts LLM/VRAM models via Game Mode and launches Steam.
    - 'reset' / 'exit': Clears active profile and restores default state.
    """

    PROFILES = {"coding", "code", "dev", "study", "studying", "focus", "gaming", "game", "reset", "exit", "normal"}

    def __init__(
        self,
        dispatcher: Optional[SafeOSDispatcher] = None,
        scheduler: Optional[ReminderEngine] = None,
        model_mgr: Optional[ModelManager] = None,
        file_mgr: Optional[FileManager] = None
    ):
        self.dispatcher = dispatcher if dispatcher is not None else SafeOSDispatcher()
        self.scheduler = scheduler if scheduler is not None else ReminderEngine()
        self.model_mgr = model_mgr if model_mgr is not None else ModelManager()
        self.file_mgr = file_mgr if file_mgr is not None else FileManager()
        self.active_profile: Optional[str] = None

    def activate_profile(self, profile: str, dry_run: bool = False) -> Dict[str, Any]:
        """Activates a predefined workspace profile."""
        clean_profile = (profile or "").strip().lower()

        # Map aliases
        canonical_profile = clean_profile
        if clean_profile in ["coding", "code", "dev", "developer"]:
            canonical_profile = "coding"
        elif clean_profile in ["study", "studying", "focus", "read"]:
            canonical_profile = "study"
        elif clean_profile in ["gaming", "game", "gamer"]:
            canonical_profile = "gaming"
        elif clean_profile in ["reset", "exit", "normal", "default"]:
            canonical_profile = "reset"
        else:
            return {
                "status": "unknown_profile",
                "profile": clean_profile,
                "voice_response": f"I don't recognize the workspace profile '{clean_profile}'. Available profiles are coding, study, and gaming."
            }

        actions_taken: List[str] = []

        # 1. CODING PROFILE
        if canonical_profile == "coding":
            # Check for VS Code or editor
            vscode_bin = shutil.which("code.cmd") or shutil.which("code")
            if not dry_run:
                if vscode_bin:
                    try:
                        subprocess.Popen([vscode_bin, PROJECT_ROOT], shell=True)
                        actions_taken.append("launched_vscode")
                    except Exception:
                        pass
                else:
                    self.file_mgr.open_folder(PROJECT_ROOT)
                    actions_taken.append("opened_workspace_folder")

                # Open developer documentation / GitHub
                webbrowser.open("https://github.com")
                actions_taken.append("opened_dev_browser")
            else:
                actions_taken.extend(["launch_editor", "open_dev_browser"])

            self.active_profile = "coding"
            voice = "Coding workspace activated. Opened your workspace and developer browser."
            return {
                "status": "activated",
                "profile": "coding",
                "actions_taken": actions_taken,
                "voice_response": voice
            }

        # 2. STUDY PROFILE
        if canonical_profile == "study":
            docs_dir = self.file_mgr.known_dirs.get("documents", os.path.expanduser("~/Documents"))
            if not dry_run:
                self.file_mgr.open_folder(docs_dir)
                actions_taken.append("opened_documents_folder")

                # Set 45-minute Pomodoro timer
                try:
                    self.scheduler.schedule_reminder(
                        task="Pomodoro study focus complete. Take a break!",
                        natural_time="45 minutes"
                    )
                    actions_taken.append("scheduled_pomodoro_timer")
                except Exception:
                    actions_taken.append("timer_schedule_attempted")
            else:
                actions_taken.extend(["open_documents_folder", "schedule_pomodoro_timer"])

            self.active_profile = "study"
            voice = "Study workspace activated. Opened your documents and set a 45-minute focus timer."
            return {
                "status": "activated",
                "profile": "study",
                "actions_taken": actions_taken,
                "voice_response": voice
            }

        # 3. GAMING PROFILE
        if canonical_profile == "gaming":
            if not dry_run:
                # Evict Ollama models to free up GPU VRAM
                evict_res = self.model_mgr.evict_all_models()
                actions_taken.append("evicted_models_vram")

                # Launch Steam via SafeOSDispatcher
                self.dispatcher.launch_app("steam")
                actions_taken.append("launched_steam")
            else:
                actions_taken.extend(["evict_models_vram", "launch_steam"])

            self.active_profile = "gaming"
            voice = "Gaming workspace activated. Cleared GPU VRAM and launched Steam."
            return {
                "status": "activated",
                "profile": "gaming",
                "actions_taken": actions_taken,
                "voice_response": voice
            }

        # 4. RESET / EXIT
        self.active_profile = None
        actions_taken.append("reset_profile")
        voice = "Workspace profile exited. Restored normal desktop operations."
        return {
            "status": "deactivated",
            "profile": "normal",
            "actions_taken": actions_taken,
            "voice_response": voice
        }
