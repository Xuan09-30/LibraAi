from core.scheduler import ReminderEngine


def execute(args: dict, context: dict) -> dict:
    engine = ReminderEngine()
    pending = engine.list_pending_reminders()
    if not pending:
        voice = "You have no pending reminders or active timers right now."
    else:
        summaries = [f"{r['task']} at {r['target_time_str']}" for r in pending[:3]]
        voice = f"You have {len(pending)} active reminder{'s' if len(pending) > 1 else ''}: " + "; ".join(summaries) + "."
    return {
        "status": "success",
        "pending_reminders": pending,
        "voice_response": voice,
    }
