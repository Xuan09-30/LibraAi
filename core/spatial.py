import os
import json
import math
from typing import Tuple, Dict, Any, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_PROFILE = {
    "user_name": "Chen Xuan",
    "home_anchor": {
        "neighborhood": "Taman Bukit Maluri",
        "area": "Kepong",
        "city": "Kuala Lumpur",
        "country": "Malaysia",
        "latitude": 3.2014,
        "longitude": 101.6328
    }
}


class SpatialGroundingEngine:
    """
    Grounds spatial reasoning, handles coordinate lookups, and calculates Haversine distances
    in pure Python to prevent LLM arithmetic errors.
    """

    def __init__(self, profile_path: Optional[str] = None):
        if profile_path is None:
            profile_path = os.path.join(PROJECT_ROOT, "assets", "user_profile.json")
        self.profile_path = profile_path
        self.profile = self._load_profile()
        self.home_anchor = self.profile.get("home_anchor", DEFAULT_PROFILE["home_anchor"])

    def _load_profile(self) -> Dict[str, Any]:
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[SpatialGroundingEngine Warning] Could not read {self.profile_path}: {e}")

        example_path = os.path.join(PROJECT_ROOT, "assets", "user_profile.json.example")
        if os.path.exists(example_path):
            try:
                with open(example_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        return DEFAULT_PROFILE

    def haversine_distance(self, coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """
        Calculates the great-circle distance between two geographic coordinates in kilometers
        using the Haversine formula.
        coord = (latitude, longitude)
        """
        lat1, lon1 = coord1
        lat2, lon2 = coord2

        earth_radius_km = 6371.0

        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)

        a = (
            math.sin(d_lat / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

        return earth_radius_km * c

    def distance_from_home(self, lat: float, lon: float) -> float:
        """
        Returns the distance in kilometers from the user's home anchor, rounded to 1 decimal place.
        """
        home_lat = float(self.home_anchor.get("latitude", 3.2014))
        home_lon = float(self.home_anchor.get("longitude", 101.6328))
        dist = self.haversine_distance((home_lat, home_lon), (lat, lon))
        return round(dist, 1)

    def resolve_anchor(self, text: str) -> Dict[str, Any]:
        """
        Detects relative spatial anchors ('near me', 'around here', 'from home', etc.)
        and returns the anchored metadata.
        """
        t_lower = text.lower()
        anchor_patterns = [
            "near me",
            "around here",
            "from home",
            "near home",
            "closest to me",
            "close to me",
            "nearby",
            "near my place",
            "from here",
            "around my area"
        ]

        for pat in anchor_patterns:
            if pat in t_lower:
                return {
                    "detected": True,
                    "anchor_type": "home",
                    "matched_pattern": pat,
                    "neighborhood": self.home_anchor.get("neighborhood", "Taman Bukit Maluri"),
                    "area": self.home_anchor.get("area", "Kepong"),
                    "city": self.home_anchor.get("city", "Kuala Lumpur"),
                    "latitude": float(self.home_anchor.get("latitude", 3.2014)),
                    "longitude": float(self.home_anchor.get("longitude", 101.6328)),
                }

        return {
            "detected": False,
            "anchor_type": None,
            "matched_pattern": None,
            "neighborhood": self.home_anchor.get("neighborhood", "Taman Bukit Maluri"),
            "area": self.home_anchor.get("area", "Kepong"),
            "city": self.home_anchor.get("city", "Kuala Lumpur"),
            "latitude": float(self.home_anchor.get("latitude", 3.2014)),
            "longitude": float(self.home_anchor.get("longitude", 101.6328)),
        }
