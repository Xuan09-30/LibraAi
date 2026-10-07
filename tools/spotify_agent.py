import os
import json
import spotipy
from spotipy.oauth2 import SpotifyOAuth

class SpotifyAgent:
    def __init__(self, config_path="config.json"):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.config_path = os.path.join(project_root, config_path)
        self.sp = None
        self._init_spotify()

    def _init_spotify(self):
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                client_id = cfg.get("2568993b08c34120a63cc5285a1fc856")
                client_secret = cfg.get("885f7c83afff4434a13463871e854033")
                redirect_uri = cfg.get("spotify_redirect_uri", "http://127.0.0.1:8888/callback")

            if client_id and client_secret:
                scope = "user-top-read user-read-recently-played playlist-read-private"
                self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uri=redirect_uri,
                    scope=scope,
                    open_browser=True
                ))
        except Exception as e:
            print(f"[Spotify Init Note]: {e}")

    def get_favorite_artists(self):
        """Fetches top artists and tracks from your active Spotify profile."""
        if not self.sp:
            return []
        try:
            top_artists = self.sp.current_user_top_artists(limit=8, time_range="medium_term")
            artists = [item['name'] for item in top_artists.get('items', [])]
            return artists
        except Exception as e:
            print(f"[Spotify Read Error]: {e}")
            return []