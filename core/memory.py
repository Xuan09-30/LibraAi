import os
import json

class MemoryCore:
    def __init__(self, filename="assets/user_memory.json"):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.file_path = os.path.join(project_root, filename)
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        self.memory = self.load_memory()

    def load_memory(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "user_preferences": {},
            "music_taste": [],
            "custom_facts": []
        }

    def save_memory(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=4)
        except Exception as e:
            print(f"[Memory Save Error]: {e}")

    def update_music_taste(self, artists_or_tracks: list):
        for item in artists_or_tracks:
            if item not in self.memory["music_taste"]:
                self.memory["music_taste"].append(item)
        self.memory["music_taste"] = self.memory["music_taste"][-25:]  # Keep top 25
        self.save_memory()

    def add_fact(self, fact: str):
        if fact not in self.memory["custom_facts"]:
            self.memory["custom_facts"].append(fact)
            self.save_memory()

    def get_context_summary(self) -> str:
        taste = ", ".join(self.memory.get("music_taste", []))
        facts = "; ".join(self.memory.get("custom_facts", []))
        summary = ""
        if taste:
            summary += f"\nKnown Music Preferences: {taste}"
        if facts:
            summary += f"\nSaved User Facts: {facts}"
        return summary