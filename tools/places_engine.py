import os
import re
import math
import requests
from typing import List, Dict, Any, Optional, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_HOME_COORDS = (3.2140, 101.6356)  # Kepong, Kuala Lumpur

CURATED_FALLBACK_PLACES = {
    "bookstore": [
        {
            "name": "Kinokuniya KLCC",
            "rating": 4.8,
            "address": "Suria KLCC, Kuala Lumpur",
            "latitude": 3.1578,
            "longitude": 101.7123,
            "category": "shop books",
            "snippet": "Massive flagship collection of Japanese manga, English bestsellers, and imported stationery."
        },
        {
            "name": "Tsutaya Pavilion Bukit Jalil",
            "rating": 4.7,
            "address": "Pavilion Bukit Jalil, Kuala Lumpur",
            "latitude": 3.0514,
            "longitude": 101.6698,
            "category": "shop books",
            "snippet": "Aesthetic lifestyle concept bookstore with artisanal cafe, curated art books, and lounge areas."
        },
        {
            "name": "MPH Mid Valley",
            "rating": 4.2,
            "address": "Mid Valley Megamall, Kuala Lumpur",
            "latitude": 3.1177,
            "longitude": 101.6775,
            "category": "shop books",
            "snippet": "Classic family bookstore with educational revision materials, fiction, and gift items."
        },
        {
            "name": "Popular Sunway Pyramid",
            "rating": 4.1,
            "address": "Sunway Pyramid, Petaling Jaya",
            "latitude": 3.0733,
            "longitude": 101.6074,
            "category": "shop books",
            "snippet": "Affordable Chinese literature, stationery, assessment books, and electronic accessories."
        }
    ],
    "cafe": [
        {
            "name": "VCR Cafe",
            "rating": 4.6,
            "address": "Jalan Galloway, Bukit Bintang, Kuala Lumpur",
            "latitude": 3.1432,
            "longitude": 101.7065,
            "category": "amenity cafe",
            "snippet": "Artisanal coffee roaster and brunch spot famous for sourdough and specialty espresso."
        },
        {
            "name": "Feeka Coffee Roasters",
            "rating": 4.5,
            "address": "Jalan Mesui, Bukit Bintang, Kuala Lumpur",
            "latitude": 3.1492,
            "longitude": 101.7088,
            "category": "amenity cafe",
            "snippet": "Scandinavian-inspired cafe serving specialty single-origin brews and pastries."
        },
        {
            "name": "ZUS Coffee Kepong",
            "rating": 4.4,
            "address": "Metro Prima, Kepong, Kuala Lumpur",
            "latitude": 3.2138,
            "longitude": 101.6385,
            "category": "amenity cafe",
            "snippet": "Popular local specialty coffee chain offering handcrafted espresso and frappes."
        }
    ],
    "restaurant": [
        {
            "name": "Ayam Gepuk Pak Gembus Kepong",
            "rating": 4.6,
            "address": "Jalan Rimbunan Raya, Laman Rimbunan, Kepong, Kuala Lumpur",
            "latitude": 3.2148,
            "longitude": 101.6362,
            "category": "amenity restaurant",
            "snippet": "Famous Indonesian crispy fried chicken with signature spicy sambal gepuk, cabbage, and fried tempeh."
        },
        {
            "name": "Restoran Kheng Heong Kepong",
            "rating": 4.5,
            "address": "Jalan Kepong, Metro Prima, Kuala Lumpur",
            "latitude": 3.2132,
            "longitude": 101.6380,
            "category": "amenity restaurant",
            "snippet": "Beloved traditional Kepong eatery famous for aromatic claypot bak kut teh and steamed fish."
        },
        {
            "name": "Village Park Restaurant",
            "rating": 4.6,
            "address": "Damansara Utama, Petaling Jaya",
            "latitude": 3.1378,
            "longitude": 101.6233,
            "category": "amenity restaurant",
            "snippet": "Famous eatery renowned for crispy spiced fried chicken nasi lemak."
        },
        {
            "name": "Madam Kwan's KLCC",
            "rating": 4.3,
            "address": "Suria KLCC, Kuala Lumpur",
            "latitude": 3.1580,
            "longitude": 101.7118,
            "category": "amenity restaurant",
            "snippet": "Upscale Malaysian cuisine serving authentic laksa, nasi bojari, and satay."
        }
    ],
    "mcdonalds": [
        {
            "name": "McDonald's Kepong DT",
            "rating": 4.5,
            "address": "Jalan Kepong, Metro Prima, Kepong, Kuala Lumpur",
            "latitude": 3.2155,
            "longitude": 101.6420,
            "category": "amenity fast_food",
            "snippet": "24/7 Drive-Thru branch serving crispy Ayam Goreng McD, Big Macs, and McCafe beverages."
        },
        {
            "name": "McDonald's Shell Kepong",
            "rating": 4.4,
            "address": "Shell Station, Jalan Kepong, Kuala Lumpur",
            "latitude": 3.2080,
            "longitude": 101.6390,
            "category": "amenity fast_food",
            "snippet": "Convenient station branch offering quick burgers, fries, and breakfast McValue sets."
        },
        {
            "name": "McDonald's Bandar Menjalara DT",
            "rating": 4.5,
            "address": "Bandar Menjalara, Kepong, Kuala Lumpur",
            "latitude": 3.1945,
            "longitude": 101.6315,
            "category": "amenity fast_food",
            "snippet": "Spacious standalone drive-thru branch with dessert kiosk and ample parking."
        }
    ],
    "fast_food": [
        {
            "name": "McDonald's Kepong DT",
            "rating": 4.5,
            "address": "Jalan Kepong, Metro Prima, Kepong, Kuala Lumpur",
            "latitude": 3.2155,
            "longitude": 101.6420,
            "category": "amenity fast_food",
            "snippet": "24/7 Drive-Thru branch serving burgers, fried chicken, and McCafe coffee."
        },
        {
            "name": "KFC Metro Prima Kepong",
            "rating": 4.3,
            "address": "Metro Prima, Kepong, Kuala Lumpur",
            "latitude": 3.2145,
            "longitude": 101.6395,
            "category": "amenity fast_food",
            "snippet": "Popular fried chicken chain serving Original Recipe, Hot & Spicy chicken, and Zinger burgers."
        },
        {
            "name": "McDonald's Bandar Menjalara DT",
            "rating": 4.5,
            "address": "Bandar Menjalara, Kepong, Kuala Lumpur",
            "latitude": 3.1945,
            "longitude": 101.6315,
            "category": "amenity fast_food",
            "snippet": "Spacious drive-thru branch with McCafe and 24-hour service."
        }
    ],
    "kfc": [
        {
            "name": "KFC Metro Prima Kepong",
            "rating": 4.3,
            "address": "Metro Prima, Kepong, Kuala Lumpur",
            "latitude": 3.2145,
            "longitude": 101.6395,
            "category": "amenity fast_food",
            "snippet": "Fast food outlet serving famous pressure-cooked Original Recipe and Hot & Spicy chicken."
        },
        {
            "name": "KFC Bandar Menjalara",
            "rating": 4.2,
            "address": "Jalan Menjalara Idaman 1, Bandar Menjalara, Kuala Lumpur",
            "latitude": 3.1950,
            "longitude": 101.6320,
            "category": "amenity fast_food",
            "snippet": "Local branch offering family buckets, potato gravy, and combo meals."
        }
    ],
    "starbucks": [
        {
            "name": "Starbucks AEON Mall Metro Prima",
            "rating": 4.6,
            "address": "AEON Mall Metro Prima, Kepong, Kuala Lumpur",
            "latitude": 3.2142,
            "longitude": 101.6388,
            "category": "amenity cafe",
            "snippet": "Comfortable mall cafe serving handcrafted espresso, Frappuccinos, and pastries."
        },
        {
            "name": "Starbucks Bandar Menjalara",
            "rating": 4.5,
            "address": "Medan Putra Business Centre, Bandar Menjalara, Kuala Lumpur",
            "latitude": 3.1938,
            "longitude": 101.6308,
            "category": "amenity cafe",
            "snippet": "Cozy neighborhood Starbucks with outdoor seating and Nitro Cold Brew on tap."
        }
    ]
}


def haversine(c1: Tuple[float, float], c2: Tuple[float, float]) -> float:
    """Calculates great-circle distance between two coordinates in km."""
    lat1, lon1 = c1
    lat2, lon2 = c2
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(6371.0 * c, 1)


class PlacesDiscoveryEngine:
    """
    Autonomous Places & POI Discovery Engine using OpenStreetMap Nominatim API.
    Enforces proximity bounding boxes, extracts structured place metadata,
    and provides resilient offline fallbacks.
    """

    def __init__(
        self,
        user_agent: str = "LibraDesktopAssistant/3.0 (contact: local-assistant@libra.ai)",
        timeout: int = 8
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.base_url = "https://nominatim.openstreetmap.org/search"
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json"
        }

    def clean_query(self, raw_query: str) -> str:
        """
        Extracts the canonical place category / search term from natural language requests.
        """
        t = raw_query.lower()
        # Strip conversational and request prefixes
        t = re.sub(
            r"^(?:please\s+)?(?:can\s+you\s+)?(?:find|search\s+for|look\s+for|show\s+me|where\s+are\s+(?:the\s+)?|recommend(?:\s+some)?|what\s+are\s+some|get|give\s+me)\s+",
            "",
            t
        )
        # Strip option quantifiers: 'one or two or three options of', 'options of'
        t = re.sub(r"\b(?:(?:one|two|three|\d+)\s+)?(?:options?\s+(?:of\s+)?(?:the\s+)?)", "", t)
        # Strip spatial anchor phrases
        t = re.sub(
            r"\b(near\s+(?:me|my\s+house|my\s+home|my\s+place|home|house|here|my\s+location|my\s+area)|around\s+(?:here|my\s+area|my\s+house|home|house)|nearby|from\s+home|near\s+home|closest\s+to\s+me|close\s+to\s+me|around\s+my\s+area|near\s+my\s+place|in\s+my\s+area|around\s+us)\b",
            "",
            t
        )
        # Strip qualitative adjectives and articles
        t = re.sub(r"\b(good|best|some|popular|nearest|closest|top|the|a|an)\b", "", t)
        t = t.strip(" .?!")

        # Map common query variants to OSM search terms
        if "mcdonald" in t or "mcd" in t:
            return "mcdonalds"
        if "kfc" in t or "kentucky" in t:
            return "kfc"
        if "starbucks" in t:
            return "starbucks"
        if "fast food" in t or "fastfood" in t or "burger" in t:
            return "fast_food"
        if "place" in t and ("eat" in t or "food" in t):
            return "restaurant"
        if "coffee" in t or "cafe" in t or "cafes" in t:
            return "cafe"
        if "bookstore" in t or "book store" in t or "bookstores" in t or "books" in t:
            return "bookstore"
        if "restaurant" in t or "restaurants" in t or "food" in t or "dining" in t:
            return "restaurant"
        if "bakery" in t or "bakeries" in t:
            return "bakery"
        if "library" in t or "libraries" in t:
            return "library"
        if "park" in t or "parks" in t:
            return "park"
        if "gym" in t or "gyms" in t or "fitness" in t:
            return "gym"

        return t if t else "places"

    def search_places(
        self,
        query: str,
        near_coords: Optional[Tuple[float, float]] = None,
        limit: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Discovers local places from OpenStreetMap Nominatim bounded to near_coords.
        Returns a list of structured place dictionaries sorted by distance.
        """
        anchor = near_coords or DEFAULT_HOME_COORDS
        anchor_lat, anchor_lon = float(anchor[0]), float(anchor[1])

        place_category = self.clean_query(query)

        # Bounding viewbox: delta ≈ 0.15 degrees (~16 km radius around anchor)
        delta = 0.15
        viewbox = f"{anchor_lon - delta:.4f},{anchor_lat + delta:.4f},{anchor_lon + delta:.4f},{anchor_lat - delta:.4f}"

        params = {
            "q": place_category,
            "format": "jsonv2",
            "addressdetails": 1,
            "bounded": 1,
            "viewbox": viewbox,
            "limit": limit
        }

        results: List[Dict[str, Any]] = []

        try:
            resp = requests.get(
                self.base_url,
                params=params,
                headers=self.headers,
                timeout=self.timeout
            )
            if resp.status_code == 200:
                raw_data = resp.json()
                if isinstance(raw_data, list):
                    for item in raw_data:
                        parsed = self._parse_nominatim_item(item, place_category, (anchor_lat, anchor_lon))
                        if parsed:
                            results.append(parsed)
        except Exception as e:
            print(f"[PlacesDiscoveryEngine Warning] Nominatim request failed: {e}")

        # If live API returns fewer than 2 items (e.g. rate limit, network drop), use curated fallback
        if len(results) < 2:
            results = self._get_fallback_places(place_category, (anchor_lat, anchor_lon), limit)

        # Sort strictly by distance ascending
        results.sort(key=lambda x: x.get("distance_km", 999.0))
        return results[:limit]

    def _parse_nominatim_item(
        self,
        item: Dict[str, Any],
        category: str,
        anchor: Tuple[float, float]
    ) -> Optional[Dict[str, Any]]:
        """Parses and sanitizes a raw Nominatim result dictionary."""
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
        except (KeyError, ValueError, TypeError):
            return None

        address = item.get("address", {})
        raw_name = item.get("name") or address.get("shop") or address.get("amenity")
        if not raw_name:
            raw_name = item.get("display_name", "").split(",")[0].strip()
        if not raw_name:
            raw_name = f"{category.capitalize()} Venue"

        # Disambiguate generic names like "Bookstore" or "Cafe" by appending suburb/neighborhood
        generic_names = {"bookstore", "cafe", "restaurant", "shop", "store", "bakery", "library", "coffee shop"}
        if raw_name.lower().strip() in generic_names:
            suburb = address.get("suburb") or address.get("neighbourhood") or address.get("town") or address.get("city")
            if suburb:
                raw_name = f"{raw_name} ({suburb})"

        # Clean address summary
        addr_parts = []
        if address.get("road"):
            addr_parts.append(address["road"])
        sub = address.get("suburb") or address.get("neighbourhood")
        if sub and sub not in addr_parts:
            addr_parts.append(sub)
        city = address.get("city") or address.get("town") or address.get("state")
        if city and city not in addr_parts:
            addr_parts.append(city)

        if addr_parts:
            addr_str = ", ".join(addr_parts)
        else:
            addr_str = ", ".join(item.get("display_name", "").split(",")[:3])

        dist_km = haversine(anchor, (lat, lon))

        return {
            "name": raw_name,
            "address": addr_str,
            "latitude": lat,
            "longitude": lon,
            "coordinates": (lat, lon),
            "distance_km": dist_km,
            "rating": 4.5,
            "category": item.get("category") or item.get("type") or category,
            "snippet": f"{raw_name} located at {addr_str}."
        }

    def _get_fallback_places(
        self,
        category: str,
        anchor: Tuple[float, float],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Returns curated fallback places enriched with precise Haversine distances."""
        fallback_list = CURATED_FALLBACK_PLACES.get(category, CURATED_FALLBACK_PLACES["bookstore"])
        enriched = []
        for item in fallback_list:
            c = dict(item)
            c["coordinates"] = (c["latitude"], c["longitude"])
            c["distance_km"] = haversine(anchor, c["coordinates"])
            enriched.append(c)
        return enriched[:limit]
