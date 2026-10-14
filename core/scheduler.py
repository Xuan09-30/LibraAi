import os
import sqlite3
import time
import threading
from datetime import datetime, timedelta
import pytz
import dateparser


class ReminderEngine:
    """
    Timezone-aware reminder engine and background watchdog for Libra AI.
    Handles natural language time parsing, persistence in SQLite, missed reminder sweeps on startup,
    and a background daemon thread for triggering due events.
    """

    def __init__(
        self,
        db_filename: str = "assets/libra_memory.db",
        timezone_str: str = "Asia/Kuala_Lumpur",
    ):
        self.timezone_str = timezone_str
        self.tz = pytz.timezone(timezone_str)

        if db_filename == ":memory:":
            self.db_path = ":memory:"
            self._shared_conn = None
        else:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            self.db_path = os.path.join(project_root, db_filename)
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._shared_conn = None

        self._watchdog_thread = None
        self._watchdog_running = False

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._shared_conn is None:
                self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            return self._shared_conn
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initializes the reminders table if not exists."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                trigger_epoch REAL NOT NULL,
                target_time_str TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        if self.db_path != ":memory:":
            conn.close()

    def parse_target_time(self, natural_time_str: str) -> float | None:
        """
        Parses natural language time string into a Unix epoch timestamp (float).
        Settings enforce timezone-awareness ('Asia/Kuala_Lumpur') and prefer future dates.
        Rejects historical times (dt <= now).
        """
        if not natural_time_str or not str(natural_time_str).strip():
            return None

        raw = str(natural_time_str).strip()
        if raw.isdigit():
            raw = f"in {raw} minutes"

        now = datetime.now(self.tz)
        settings = {
            "TIMEZONE": self.timezone_str,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
            "RELATIVE_BASE": now.replace(tzinfo=None),
        }

        parsed = dateparser.parse(raw, settings=settings)
        if not parsed:
            return None

        # Ensure timezone localized
        if parsed.tzinfo is None:
            parsed = self.tz.localize(parsed)
        else:
            parsed = parsed.astimezone(self.tz)

        epoch = parsed.timestamp()
        if epoch <= now.timestamp():
            return None

        return float(epoch)

    def add_reminder(self, task: str, natural_time_str: str) -> dict:
        """
        Parses natural time string, writes row with status='pending',
        and returns scheduled confirmation details.
        """
        clean_task = (task or "Reminder").strip()
        epoch = self.parse_target_time(natural_time_str)

        if epoch is None:
            return {
                "success": False,
                "error": f"Could not parse valid future time from '{natural_time_str}'",
                "task": clean_task,
                "time_str": natural_time_str,
            }

        target_dt = datetime.fromtimestamp(epoch, tz=self.tz)
        formatted_target = target_dt.strftime("%Y-%m-%d %I:%M %p")

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reminders (task, trigger_epoch, target_time_str, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (clean_task, epoch, formatted_target, datetime.now(self.tz).isoformat()),
        )
        reminder_id = cursor.lastrowid
        conn.commit()
        if self.db_path != ":memory:":
            conn.close()

        return {
            "success": True,
            "id": reminder_id,
            "task": clean_task,
            "trigger_epoch": epoch,
            "target_time_str": formatted_target,
            "natural_time_str": natural_time_str,
            "status": "pending",
            "message": f"Reminder set for {formatted_target} to {clean_task}.",
        }

    def check_missed_on_startup(self) -> list[dict]:
        """
        Sweeps database for trigger_epoch <= now_epoch AND status='pending'.
        Updates their status to 'missed' and returns the list of missed events.
        """
        now_epoch = time.time()
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, task, trigger_epoch, target_time_str, created_at
            FROM reminders
            WHERE trigger_epoch <= ? AND status = 'pending'
            ORDER BY trigger_epoch ASC
            """,
            (now_epoch,),
        )
        rows = cursor.fetchall()
        missed = []

        if rows:
            ids = [r[0] for r in rows]
            cursor.execute(
                f"UPDATE reminders SET status = 'missed' WHERE id IN ({','.join(['?']*len(ids))})",
                ids,
            )
            conn.commit()

            for r in rows:
                missed.append({
                    "id": r[0],
                    "task": r[1],
                    "trigger_epoch": r[2],
                    "target_time_str": r[3],
                    "status": "missed",
                    "created_at": r[4],
                })

        if self.db_path != ":memory:":
            conn.close()

        return missed

    def get_due_reminders(self) -> list[dict]:
        """
        Queries trigger_epoch <= now_epoch AND status='pending'.
        Marks matched rows as 'completed' and returns them for immediate notification.
        """
        now_epoch = time.time()
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, task, trigger_epoch, target_time_str, created_at
            FROM reminders
            WHERE trigger_epoch <= ? AND status = 'pending'
            ORDER BY trigger_epoch ASC
            """,
            (now_epoch,),
        )
        rows = cursor.fetchall()
        due = []

        if rows:
            ids = [r[0] for r in rows]
            cursor.execute(
                f"UPDATE reminders SET status = 'completed' WHERE id IN ({','.join(['?']*len(ids))})",
                ids,
            )
            conn.commit()

            for r in rows:
                due.append({
                    "id": r[0],
                    "task": r[1],
                    "trigger_epoch": r[2],
                    "target_time_str": r[3],
                    "status": "completed",
                    "created_at": r[4],
                })

        if self.db_path != ":memory:":
            conn.close()

        return due

    def start_watchdog(self, notify_callback, check_interval_sec: float = 10.0):
        """
        Runs a daemon background thread that sleeps and checks get_due_reminders().
        If due reminders exist, calls notify_callback(task_dict).
        """
        if self._watchdog_running:
            return

        self._watchdog_running = True

        def _watchdog_loop():
            while self._watchdog_running:
                try:
                    due = self.get_due_reminders()
                    for item in due:
                        if notify_callback:
                            notify_callback(item)
                except Exception as e:
                    print(f"[Reminder Watchdog Error]: {e}")
                time.sleep(check_interval_sec)

        self._watchdog_thread = threading.Thread(
            target=_watchdog_loop,
            daemon=True,
            name="LibraReminderWatchdog",
        )
        self._watchdog_thread.start()

    def stop_watchdog(self):
        """Stops the watchdog background thread."""
        self._watchdog_running = False
