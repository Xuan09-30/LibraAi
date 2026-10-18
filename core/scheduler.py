import os
import re
import sys
import sqlite3
import time
import threading
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import pytz
import dateparser


class ReminderEngine:
    """
    Timezone-aware Reminder, Timer & Alarm Engine with Native Windows 11 Action Center Toasts (v10.0).
    Handles natural language time parsing ('in 45 minutes', 'at 5 PM', '15 minute timer'),
    persistence in SQLite, missed reminder sweeps on startup, Windows 11 Action Center toast notifications,
    and a background daemon thread for triggering due events with Kokoro TTS announcements.
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
        self.toast_history: List[Dict[str, Any]] = []

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

    def send_windows_toast(
        self,
        title: str,
        message: str,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Dispatches a native Windows 11 Action Center Toast Notification with sound
        using built-in WinRT ToastNotificationManager via headless PowerShell.
        Requires zero external paid dependencies or C++ compilation.
        """
        clean_title = (title or "Libra Reminder").replace("'", "").replace('"', "").strip()
        clean_msg = (message or "Your scheduled reminder is due.").replace("'", "").replace('"', "").strip()

        record = {
            "title": clean_title,
            "message": clean_msg,
            "timestamp": datetime.now(self.tz).isoformat(),
            "dry_run": dry_run,
        }
        self.toast_history.append(record)

        if dry_run or sys.platform != "win32":
            return {
                "status": "toast_sent",
                "mode": "dry_run",
                "title": clean_title,
                "message": clean_msg,
            }

        ps_script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null; "
            "$template = '<toast><visual><binding template=\"ToastGeneric\">"
            f"<text>{clean_title}</text><text>{clean_msg}</text>"
            "</binding></visual><audio src=\"ms-winsoundevent:Notification.Reminder\"/></toast>'; "
            "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; "
            "$xml.LoadXml($template); "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($toast);"
        )

        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            return {
                "status": "toast_sent",
                "mode": "winrt_native",
                "title": clean_title,
                "message": clean_msg,
            }
        except Exception as e:
            print(f"[ReminderEngine Toast Warning]: {e}")
            return {
                "status": "toast_fallback",
                "error": str(e),
                "title": clean_title,
                "message": clean_msg,
            }

    @staticmethod
    def parse_reminder_request(prompt: str) -> Optional[Dict[str, str]]:
        """
        Extracts {'task': ..., 'time': ...} from natural language reminder/timer/alarm requests:
          - 'Remind me to take a break in 45 minutes'
          - 'Remind me in 15 minutes to check the oven'
          - 'Set a timer for 15 minutes' / 'Set a 10 minute timer for laundry'
          - 'Remind me at 5 PM to check the build'
          - 'Wake me up at 8 AM' / 'Set an alarm for 7:30 AM'
        """
        # Punctuation normalization: replace commas/semicolons with spaces
        q = (prompt or "").strip().rstrip(".?!")
        q_norm = re.sub(r"[,;]+", " ", q).strip()
        q_low = q_norm.lower()

        # Clean conversational prefixes: "okay now i want you to", "can you please", "hey libra"
        q_clean = re.sub(
            r"^(?:(?:okay|alright|hey\s+libra|libra|uhh|now|first|please|can\s+you(?:\s+please)?|could\s+you(?:\s+please)?|can\s+i(?:\s+please)?|could\s+i(?:\s+please)?|i\s+want\s+you\s+to|i\s+want\s+to|i\s+need\s+you\s+to|would\s+you(?:\s+please)?|i\s+want\s+a|let\'s\s+set|let\'s|i|we)\s+)+",
            "",
            q_low,
        ).strip()

        # Strip trailing conversational politeness / filler
        q_clean = re.sub(r"\s+(?:please|for\s+me|thanks|thank\s+you|again)[\.\?!]*$", "", q_clean, flags=re.IGNORECASE).strip()

        for target_str in [q_clean, q_low]:
            # 1. "Set [a/the] [duration] timer [for task / for me]"
            m_timer_alt = re.search(
                r"^(?:please\s+)?(?:set|start)\s+(?:a|the)?\s*([0-9]+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?))\s+timer(?:\s+(?:for|to)\s+(.+))?[\.\?!]*$",
                target_str,
            )
            if m_timer_alt:
                dur = m_timer_alt.group(1).strip()
                raw_task = (m_timer_alt.group(2) or "Timer").strip()
                task = "Timer" if raw_task.lower() in ["me", "for me", "us", "please", "again"] else raw_task
                return {"task": task, "time": f"in {dur}"}

            # 2. "Set [a/the] timer [for me] [for/to/of] [duration] [for/to task]" / "timer [duration]"
            m_timer = re.search(
                r"^(?:please\s+)?(?:(?:set|start)\s+(?:a|the)?\s*timer|timer)\s+(?:for\s+me\s+)?(?:for|to|of)?\s*([0-9]+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)(?:\s+and\s+[0-9]+\s*(?:seconds?|secs?|minutes?|mins?))?)(?:\s+(?:for|to)\s+(.+))?[\.\?!]*$",
                target_str,
            )
            if m_timer:
                dur = m_timer.group(1).strip()
                raw_task = (m_timer.group(2) or "Timer").strip()
                task = "Timer" if raw_task.lower() in ["me", "for me", "us", "please", "again"] else raw_task
                return {"task": task, "time": f"in {dur}"}

            # 3. "Set an alarm for [time]" / "Wake me up at/in [time]"
            m_alarm = re.search(
                r"^(?:please\s+)?(?:set\s+(?:an|the)?\s*alarm\s+for|wake\s+me\s+up\s+(?:at|in))\s+(.+)$",
                target_str,
            )
            if m_alarm:
                raw_t = m_alarm.group(1).strip()
                if re.match(r"^[0-9]+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)", raw_t):
                    raw_t = f"in {raw_t}"
                return {"task": "Alarm", "time": raw_t}

            # 4. "Remind me in [duration] to [task]"
            m_in_first = re.search(
                r"^(?:please\s+)?remind\s+me\s+in\s+([0-9]+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?))\s+(?:to\s+)?(.+)?$",
                target_str,
            )
            if m_in_first:
                dur = m_in_first.group(1).strip()
                task = (m_in_first.group(2) or "Reminder").strip()
                return {
                    "time": f"in {dur}",
                    "task": task,
                }

            # 5. "Remind me at [time] to [task]"
            m_at_first = re.search(
                r"^(?:please\s+)?remind\s+me\s+(?:at|on)\s+([0-9:apm\s]+?)\s+to\s+(.+)$",
                target_str,
            )
            if m_at_first:
                return {
                    "time": m_at_first.group(1).strip(),
                    "task": m_at_first.group(2).strip(),
                }

            # 6. "Remind me to [task] in [duration]"
            m_to_in = re.search(
                r"^(?:please\s+)?remind\s+me\s+to\s+(.+?)\s+in\s+([0-9]+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?))$",
                target_str,
            )
            if m_to_in:
                return {
                    "task": m_to_in.group(1).strip(),
                    "time": f"in {m_to_in.group(2).strip()}",
                }

            # 7. "Remind me to [task] at [time]"
            m_to_at = re.search(
                r"^(?:please\s+)?remind\s+me\s+to\s+(.+?)\s+at\s+([0-9:apm\s]+)$",
                target_str,
            )
            if m_to_at:
                return {
                    "task": m_to_at.group(1).strip(),
                    "time": m_to_at.group(2).strip(),
                }

            # 8. Generic "Remind me to [task]"
            m_generic = re.search(r"^(?:please\s+)?remind\s+me\s+to\s+(.+)$", target_str)
            if m_generic:
                return {
                    "task": m_generic.group(1).strip(),
                    "time": "in 1 hour",
                }

        return None

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
        elif re.match(r"^[0-9]+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)$", raw, re.IGNORECASE):
            raw = f"in {raw}"

        now = datetime.now(self.tz)

        # Fast-path relative duration parser ("in 45 minutes", "in 15 mins", "in 2 hours", "in 30 seconds")
        rel_match = re.match(
            r"^in\s+([0-9]+(?:\.[0-9]+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)$",
            raw.strip(),
            re.IGNORECASE,
        )
        if rel_match:
            val = float(rel_match.group(1))
            unit = rel_match.group(2).lower()
            if unit.startswith("sec"):
                delta = timedelta(seconds=val)
            elif unit.startswith("min"):
                delta = timedelta(minutes=val)
            else:
                delta = timedelta(hours=val)
            return float((now + delta).timestamp())

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

    def add_reminder(self, task: str, natural_time_str: str, show_toast: bool = False, dry_run: bool = False) -> dict:
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
        short_time = target_dt.strftime("%I:%M %p").lstrip("0")

        reminder_id = 0
        if not dry_run:
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

        if show_toast:
            self.send_windows_toast(
                title="Libra Reminder Scheduled",
                message=f"{clean_task.capitalize()} — set for {short_time}",
                dry_run=dry_run,
            )

        if clean_task.lower() == "timer":
            spoken = f"Timer set for {natural_time_str.replace('in ', '')} (triggers at {short_time})."
        else:
            spoken = f"Got it — I'll remind you to {clean_task} at {short_time}."

        return {
            "success": True,
            "id": reminder_id,
            "task": clean_task,
            "trigger_epoch": epoch,
            "target_time_str": formatted_target,
            "short_time": short_time,
            "natural_time_str": natural_time_str,
            "status": "pending",
            "message": spoken,
        }

    def list_pending_reminders(self) -> List[Dict[str, Any]]:
        """Returns all active pending reminders ordered by trigger time."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, task, trigger_epoch, target_time_str, created_at
            FROM reminders
            WHERE status = 'pending'
            ORDER BY trigger_epoch ASC
            """
        )
        rows = cursor.fetchall()
        if self.db_path != ":memory:":
            conn.close()

        items = []
        for r in rows:
            items.append({
                "id": r[0],
                "task": r[1],
                "trigger_epoch": r[2],
                "target_time_str": r[3],
                "status": "pending",
                "created_at": r[4],
            })
        return items

    def cancel_reminders(self, target: str = "all") -> Dict[str, Any]:
        """Cancels pending reminders (all or matching a task keyword)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        if not target or target.lower() in ["all", "everything", "timers", "reminders", "my reminders", "my timers"]:
            cursor.execute("UPDATE reminders SET status = 'cancelled' WHERE status = 'pending'")
        else:
            cursor.execute(
                "UPDATE reminders SET status = 'cancelled' WHERE status = 'pending' AND LOWER(task) LIKE ?",
                (f"%{target.lower()}%",),
            )
        count = cursor.rowcount
        conn.commit()
        if self.db_path != ":memory:":
            conn.close()

        if count > 0:
            msg = f"Cleared {count} pending reminder{'s' if count > 1 else ''}."
        else:
            msg = "You don't have any active reminders to cancel."
        return {"status": "success", "cancelled_count": count, "voice_response": msg}

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

    def get_due_reminders(self, trigger_toast: bool = True, dry_run: bool = False) -> list[dict]:
        """
        Queries trigger_epoch <= now_epoch AND status='pending'.
        Marks matched rows as 'completed', dispatches Windows 11 Action Center toast notifications,
        and returns them for immediate voice announcement.
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
                item = {
                    "id": r[0],
                    "task": r[1],
                    "trigger_epoch": r[2],
                    "target_time_str": r[3],
                    "status": "completed",
                    "created_at": r[4],
                }
                due.append(item)
                if trigger_toast:
                    is_timer = "timer" in str(r[1]).lower()
                    t_title = "Libra Timer Finished" if is_timer else "Libra Reminder"
                    t_msg = f"Hold up, your {r[1]} went off right now!" if is_timer else f"Hold up, it's time to {r[1]}."
                    self.send_windows_toast(
                        title=t_title,
                        message=t_msg,
                        dry_run=dry_run,
                    )

        if self.db_path != ":memory:":
            conn.close()

        return due

    def start_watchdog(self, notify_callback, check_interval_sec: float = 1.0):
        """
        Runs a daemon background thread that sleeps and checks get_due_reminders().
        If due reminders exist, fires a Windows 11 toast and calls notify_callback(task_dict).
        """
        if self._watchdog_running:
            return

        self._watchdog_running = True

        def _watchdog_loop():
            while self._watchdog_running:
                try:
                    due = self.get_due_reminders(trigger_toast=True, dry_run=False)
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
