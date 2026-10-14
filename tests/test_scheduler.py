import os
import sys
import time
import sqlite3
from datetime import datetime, timedelta
import pytz

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.scheduler import ReminderEngine


def run_scheduler_tests():
    print("\n" + "=" * 60)
    print("   LIBRA AI - SCHEDULER & BACKGROUND WATCHDOG TESTS")
    print("=" * 60)

    test_db = "assets/test_scheduler.db"
    test_db_full_path = os.path.join(PROJECT_ROOT, test_db)
    if os.path.exists(test_db_full_path):
        try:
            os.remove(test_db_full_path)
        except Exception:
            pass

    engine = ReminderEngine(db_filename=test_db, timezone_str="Asia/Kuala_Lumpur")
    passed = 0
    total = 3
    tz = pytz.timezone("Asia/Kuala_Lumpur")

    # -------------------------------------------------------------
    # Test 1: Natural Language Time Parsing
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 1: Natural Language Time Parsing...")
    test_expressions = ["in 15 minutes", "tomorrow at 10 am", "5:00 PM"]
    test1_pass = True
    now_epoch = time.time()

    for expr in test_expressions:
        epoch = engine.parse_target_time(expr)
        if epoch is None:
            print(f"  [FAIL] Failed to parse: '{expr}'")
            test1_pass = False
            continue

        dt = datetime.fromtimestamp(epoch, tz=tz)
        offset = dt.utcoffset()
        is_future = epoch > now_epoch
        is_kl_tz = (offset == timedelta(hours=8))

        print(f"  [Parsed]: '{expr}' -> {dt.strftime('%Y-%m-%d %I:%M %p %Z')} (epoch={epoch:.2f}, future={is_future}, offset={offset})")

        if not (is_future and is_kl_tz):
            print(f"  [FAIL] Expression '{expr}' validation failed (future={is_future}, kl_tz={is_kl_tz})")
            test1_pass = False

    if test1_pass:
        passed += 1
        print("  [PASS] Test 1: Natural language time parsing verified. All datetimes are future and match Asia/Kuala_Lumpur offset (+08:00).")
    else:
        print("  [FAIL] Test 1: Time parsing validation failed.")

    # -------------------------------------------------------------
    # Test 2: Due Trigger Execution
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 2: Due Trigger Execution...")
    rem_task = "Quick due trigger test"
    rem_info = engine.add_reminder(rem_task, "in 1 second")
    print(f"  [Inserted]: ID={rem_info.get('id')}, Task='{rem_task}', TriggerEpoch={rem_info.get('trigger_epoch')}")

    print("  [Sleeping 1.5 seconds to elapse trigger]...")
    time.sleep(1.5)

    due_reminders = engine.get_due_reminders()
    print(f"  [Due Reminders Retrieved]: {len(due_reminders)}")
    for d in due_reminders:
        print(f"    - ID={d['id']}, Task='{d['task']}', Status='{d['status']}'")

    matched_due = [d for d in due_reminders if d["id"] == rem_info.get("id")]
    test2_pass = (
        len(matched_due) == 1
        and matched_due[0]["status"] == "completed"
    )

    if test2_pass:
        passed += 1
        print("  [PASS] Test 2: Due trigger execution verified. Reminder transitioned to 'completed'.")
    else:
        print(f"  [FAIL] Test 2: Due trigger execution failed. matched={matched_due}")

    # -------------------------------------------------------------
    # Test 3: Offline Catchup Sweep
    # -------------------------------------------------------------
    print("\n[RUNNING] Test 3: Offline Catchup Sweep...")
    past_epoch = time.time() - 600  # 10 minutes ago
    past_dt_str = datetime.fromtimestamp(past_epoch, tz=tz).strftime("%Y-%m-%d %I:%M %p")

    # Manually insert historical pending reminder into database
    conn = engine._get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO reminders (task, trigger_epoch, target_time_str, status, created_at)
        VALUES (?, ?, ?, 'pending', ?)
        """,
        ("Catchup missed task", past_epoch, past_dt_str, datetime.now(tz).isoformat()),
    )
    missed_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(f"  [Simulated Offline Pending Reminder]: ID={missed_id}, TriggerEpoch={past_epoch:.2f} (10m in past)")

    # Execute check_missed_on_startup()
    missed_events = engine.check_missed_on_startup()
    print(f"  [Missed Events Found]: {len(missed_events)}")
    for m in missed_events:
        print(f"    - ID={m['id']}, Task='{m['task']}', Status='{m['status']}'")

    matched_missed = [m for m in missed_events if m["id"] == missed_id]
    test3_pass = (
        len(matched_missed) == 1
        and matched_missed[0]["status"] == "missed"
    )

    if test3_pass:
        passed += 1
        print("  [PASS] Test 3: Offline catchup sweep verified. Past pending reminder transitioned to 'missed'.")
    else:
        print(f"  [FAIL] Test 3: Offline catchup sweep failed. matched={matched_missed}")

    # Cleanup test db
    if os.path.exists(test_db_full_path):
        try:
            os.remove(test_db_full_path)
        except Exception:
            pass

    # Summary
    print("\n" + "=" * 60)
    score_pct = (passed / total) * 100
    print(f"Scheduler Suite Score: {passed}/{total} Passed ({score_pct:.1f}%)")
    print("=" * 60 + "\n")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    run_scheduler_tests()
