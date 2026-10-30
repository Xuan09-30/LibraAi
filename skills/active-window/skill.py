from tools.window_context import ActiveWindowEngine


def execute(args: dict, context: dict) -> dict:
    engine = ActiveWindowEngine()
    return engine.summarize_active_window(dry_run=bool(args.get("dry_run", False)))
