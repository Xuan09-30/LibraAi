from tools.spotify_agent import SpotifyAgent


def execute(args: dict, context: dict) -> dict:
    agent = SpotifyAgent()
    return agent.get_now_playing(dry_run=bool(args.get("dry_run", False)))
