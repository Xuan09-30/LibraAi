import os
import re
import sqlite3
import datetime
import collections
from typing import Dict, Any, Optional, List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class HabitLearner:
    """
    User Habit & Command-Chain Pattern Learner for Project Libra.
    Logs action sequences and temporal routines into SQLite (assets/libra_memory.db),
    detects recurring sequential/temporal habits, syncs discoveries to assets/USER.md,
    and produces high-confidence proactive suggestions.
    """

    def __init__(
        self,
        db_path: str = "assets/libra_memory.db",
        user_md_path: str = "assets/USER.md"
    ):
        if db_path == ":memory:":
            self.db_path = ":memory:"
            self._shared_conn = None
        else:
            self.db_path = os.path.join(PROJECT_ROOT, db_path) if not os.path.isabs(db_path) else db_path
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._shared_conn = None

        self.user_md_path = os.path.join(PROJECT_ROOT, user_md_path) if not os.path.isabs(user_md_path) else user_md_path
        self.last_action: Optional[str] = None
        self.last_target: Optional[str] = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._shared_conn is None:
                self._shared_conn = sqlite3.connect(":memory:")
            return self._shared_conn
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Creates user_habits table in the database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                target TEXT DEFAULT '',
                hour_of_day INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL,
                previous_action TEXT DEFAULT '',
                previous_target TEXT DEFAULT '',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        if self.db_path != ":memory:":
            conn.close()

    def record_action(self, action: str, target: str = ""):
        """
        Logs an executed action and its preceding action/target context.
        Updates internal tracking for next sequential transition.
        """
        if not action or action in ["chat", "list_skills"]:
            return

        now = datetime.datetime.now()
        hour = now.hour
        day = now.weekday()

        prev_act = self.last_action or ""
        prev_tgt = self.last_target or ""

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_habits (action, target, hour_of_day, day_of_week, previous_action, previous_target)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (action.strip().lower(), (target or "").strip().lower(), hour, day, prev_act, prev_tgt))
        conn.commit()
        if self.db_path != ":memory:":
            conn.close()

        self.last_action = action.strip().lower()
        self.last_target = (target or "").strip().lower()

    def detect_patterns(self) -> Dict[str, Any]:
        """
        Analyzes logged actions to extract high-confidence sequential and temporal routines.
        Automatically updates assets/USER.md with discovered patterns.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 1. Sequential Habit Analysis
        cursor.execute("""
            SELECT previous_action, previous_target, action, target, COUNT(*) as cnt
            FROM user_habits
            WHERE previous_action != ''
            GROUP BY previous_action, previous_target, action, target
            HAVING cnt >= 3
            ORDER BY cnt DESC
        """)
        seq_rows = cursor.fetchall()

        sequential_habits = []
        for p_act, p_tgt, act, tgt, count in seq_rows:
            # Calculate total transitions from (p_act, p_tgt)
            cursor.execute("""
                SELECT COUNT(*) FROM user_habits
                WHERE previous_action = ? AND previous_target = ?
            """, (p_act, p_tgt))
            total = cursor.fetchone()[0] or 1
            confidence = count / total
            if confidence >= 0.60:
                sequential_habits.append({
                    "from_action": p_act,
                    "from_target": p_tgt,
                    "to_action": act,
                    "to_target": tgt,
                    "count": count,
                    "confidence": round(confidence, 2)
                })

        # 2. Temporal Habit Analysis (hour of day)
        cursor.execute("""
            SELECT action, target, hour_of_day, COUNT(*) as cnt
            FROM user_habits
            GROUP BY action, target, hour_of_day
            HAVING cnt >= 3
            ORDER BY cnt DESC
        """)
        temp_rows = cursor.fetchall()
        temporal_habits = []
        for act, tgt, hour, count in temp_rows:
            temporal_habits.append({
                "action": act,
                "target": tgt,
                "hour": hour,
                "count": count
            })

        if self.db_path != ":memory:":
            conn.close()

        patterns = {
            "sequential": sequential_habits,
            "temporal": temporal_habits
        }

        self._sync_to_user_md(patterns)
        return patterns

    def _sync_to_user_md(self, patterns: Dict[str, Any]):
        """Syncs discovered habits into the ## Learned Habits & Routines section in assets/USER.md."""
        if not os.path.exists(self.user_md_path):
            return

        try:
            with open(self.user_md_path, "r", encoding="utf-8") as f:
                content = f.read()

            lines = []
            if patterns["sequential"]:
                for s in patterns["sequential"]:
                    src = f"{s['from_action']}:{s['from_target']}" if s['from_target'] else s['from_action']
                    dst = f"{s['to_action']}:{s['to_target']}" if s['to_target'] else s['to_action']
                    lines.append(f"- **Sequential Flow**: After `{src}`, frequently triggers `{dst}` ({s['count']}x, {int(s['confidence']*100)}% confidence).")

            if patterns["temporal"]:
                for t in patterns["temporal"]:
                    act_str = f"{t['action']}:{t['target']}" if t['target'] else t['action']
                    lines.append(f"- **Time Routine**: Often runs `{act_str}` around {t['hour']:02d}:00 ({t['count']} occurrences).")

            if not lines:
                lines.append("- *No verified routines meeting confidence threshold (>=3 instances, >=60% confidence).*")

            new_habits_block = "## Learned Habits & Routines\n" + "\n".join(lines) + "\n"

            if "## Learned Habits & Routines" in content:
                updated = re.sub(
                    r"## Learned Habits & Routines.*?(?=\n## |\Z)",
                    new_habits_block.strip() + "\n",
                    content,
                    flags=re.DOTALL
                )
            else:
                updated = content.rstrip() + "\n\n" + new_habits_block

            with open(self.user_md_path, "w", encoding="utf-8") as f:
                f.write(updated)
        except Exception as e:
            print(f"[HabitLearner Sync Warning]: {e}")

    def get_proactive_suggestion(
        self,
        current_action: str,
        current_target: str = ""
    ) -> Optional[str]:
        """
        Evaluates whether a high-confidence next action is predicted after the current action.
        Returns a friendly, proactive suggestion string or None.
        """
        c_act = (current_action or "").strip().lower()
        c_tgt = (current_target or "").strip().lower()

        if not c_act:
            return None

        conn = self._get_connection()
        cursor = conn.cursor()

        # Find most common next action from this exact state
        cursor.execute("""
            SELECT action, target, COUNT(*) as cnt
            FROM user_habits
            WHERE previous_action = ? AND previous_target = ?
            GROUP BY action, target
            ORDER BY cnt DESC
            LIMIT 1
        """, (c_act, c_tgt))
        row = cursor.fetchone()

        if not row:
            if self.db_path != ":memory:":
                conn.close()
            return None

        next_act, next_tgt, count = row[0], row[1], row[2]

        # Calculate confidence
        cursor.execute("""
            SELECT COUNT(*) FROM user_habits
            WHERE previous_action = ? AND previous_target = ?
        """, (c_act, c_tgt))
        total = cursor.fetchone()[0] or 1

        if self.db_path != ":memory:":
            conn.close()

        confidence = count / total
        if count < 3 or confidence < 0.60:
            return None

        # Build natural, high-signal proactive suggestions
        if next_act == "launch_workspace":
            mode_name = next_tgt or "coding"
            return f"By the way, you usually switch to {mode_name} mode after this - want me to start it?"
        elif next_act == "open_app":
            app_name = next_tgt or "your next application"
            return f"You often launch {app_name} after this - should I open it for you?"
        elif next_act == "system_status":
            return "You often check system telemetry around this step - want a quick hardware status report?"
        elif next_act == "media_control":
            return "Would you like me to adjust your music playback as well?"
        elif next_act == "spotify_play":
            return "Want me to start up your Spotify playlist too?"

        action_display = next_act.replace("_", " ")
        tgt_display = f" {next_tgt}" if next_tgt else ""
        return f"By the way, you usually {action_display}{tgt_display} after this - should I run that?"
