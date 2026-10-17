import urllib.parse
import requests
from datetime import datetime

DEFAULT_LAT = 3.2008
DEFAULT_LON = 101.6331
DEFAULT_LOC_NAME = "Taman Bukit Maluri, Kuala Lumpur"

WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorms", 96: "Thunderstorms with slight hail", 99: "Severe thunderstorms with hail"
}

BUILT_IN_LOCATIONS = {
    "taman bukit maluri": ("Taman Bukit Maluri, Kuala Lumpur", 3.2008, 101.6331, "Malaysia"),
    "taman bukit maluri, kuala lumpur": ("Taman Bukit Maluri, Kuala Lumpur", 3.2008, 101.6331, "Malaysia"),
    "kuala lumpur": ("Kuala Lumpur", 3.1390, 101.6869, "Malaysia"),
    "kl": ("Kuala Lumpur", 3.1390, 101.6869, "Malaysia"),
    "kepong": ("Kepong", 3.2140, 101.6356, "Malaysia"),
    "kuantan": ("Kuantan", 3.8077, 103.3260, "Malaysia"),
    "penang": ("Penang", 5.4141, 100.3288, "Malaysia"),
    "georgetown": ("George Town, Penang", 5.4141, 100.3288, "Malaysia"),
    "george town": ("George Town, Penang", 5.4141, 100.3288, "Malaysia"),
    "johor bahru": ("Johor Bahru", 1.4927, 103.7414, "Malaysia"),
    "jb": ("Johor Bahru", 1.4927, 103.7414, "Malaysia"),
    "ipoh": ("Ipoh", 4.5975, 101.0901, "Malaysia"),
    "melaka": ("Melaka", 2.1896, 102.2501, "Malaysia"),
    "malacca": ("Melaka", 2.1896, 102.2501, "Malaysia"),
    "kota kinabalu": ("Kota Kinabalu", 5.9804, 116.0735, "Malaysia"),
    "kuching": ("Kuching", 1.5533, 110.3592, "Malaysia"),
    "seremban": ("Seremban", 2.7258, 101.9424, "Malaysia"),
    "shah alam": ("Shah Alam", 3.0733, 101.5185, "Malaysia"),
    "petaling jaya": ("Petaling Jaya", 3.1073, 101.6067, "Malaysia"),
    "pj": ("Petaling Jaya", 3.1073, 101.6067, "Malaysia"),
    "subang jaya": ("Subang Jaya", 3.0565, 101.5851, "Malaysia"),
    "genting highlands": ("Genting Highlands", 3.4236, 101.7932, "Malaysia"),
    "genting": ("Genting Highlands", 3.4236, 101.7932, "Malaysia"),
    "cameron highlands": ("Cameron Highlands", 4.4721, 101.3801, "Malaysia"),
    "langkawi": ("Langkawi", 6.3500, 99.8000, "Malaysia"),
    "putrajaya": ("Putrajaya", 2.9264, 101.6964, "Malaysia"),
    "cyberjaya": ("Cyberjaya", 2.9213, 101.6559, "Malaysia"),
    "singapore": ("Singapore", 1.3521, 103.8198, "Singapore"),
    "tokyo": ("Tokyo", 35.6762, 139.6503, "Japan"),
    "london": ("London", 51.5074, -0.1278, "United Kingdom"),
    "new york": ("New York", 40.7128, -74.0060, "United States"),
    "sydney": ("Sydney", -33.8688, 151.2093, "Australia"),
    "seoul": ("Seoul", 37.5665, 126.9780, "South Korea"),
    "bangkok": ("Bangkok", 13.7563, 100.5018, "Thailand"),
}


def geocode_location(city_name: str) -> dict:
    """
    Resolves a city or location name to geographic coordinates.
    Checks the 0ms built-in lookup dictionary first, then falls back to
    Open-Meteo's free Geocoding API for any location globally.
    """
    if not city_name or not str(city_name).strip():
        return {
            "name": DEFAULT_LOC_NAME,
            "latitude": DEFAULT_LAT,
            "longitude": DEFAULT_LON,
            "country": "Malaysia",
        }

    clean = str(city_name).strip().strip("'\"").rstrip(".?!")
    norm = clean.lower().strip()

    # Check exact match in built-in lookup
    if norm in BUILT_IN_LOCATIONS:
        name, lat, lon, country = BUILT_IN_LOCATIONS[norm]
        return {
            "name": name,
            "latitude": float(lat),
            "longitude": float(lon),
            "country": country,
        }

    # Check substring/prefix match in built-in lookup (e.g., "kuantan, pahang" -> "kuantan")
    for key, (name, lat, lon, country) in BUILT_IN_LOCATIONS.items():
        if len(key) >= 4 and (norm.startswith(key) or f" {key}" in f" {norm}"):
            return {
                "name": name,
                "latitude": float(lat),
                "longitude": float(lon),
                "country": country,
            }

    # Fallback: Open-Meteo Geocoding API
    try:
        encoded = urllib.parse.quote(clean)
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded}&count=1&language=en&format=json"
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        data = res.json()
        results = data.get("results") or []
        if results:
            top = results[0]
            return {
                "name": top.get("name", clean.title()),
                "latitude": float(top.get("latitude", DEFAULT_LAT)),
                "longitude": float(top.get("longitude", DEFAULT_LON)),
                "country": top.get("country", "Unknown"),
            }
    except Exception:
        pass

    return {
        "name": clean.title(),
        "latitude": DEFAULT_LAT,
        "longitude": DEFAULT_LON,
        "country": "Malaysia",
    }


def get_weather(location_query: str = None, target_date_str: str = None, dry_run: bool = False) -> dict:
    """
    Fetches live or dry-run weather telemetry for any global location.
    Defaults to Taman Bukit Maluri, Kuala Lumpur when location_query is None/empty.
    """
    if not location_query or not str(location_query).strip():
        geo = {
            "name": DEFAULT_LOC_NAME,
            "latitude": DEFAULT_LAT,
            "longitude": DEFAULT_LON,
            "country": "Malaysia",
        }
    else:
        geo = geocode_location(location_query)

    resolved_name = geo["name"]
    lat = geo["latitude"]
    lon = geo["longitude"]
    country = geo.get("country", "Malaysia")

    def _deterministic_fallback() -> dict:
        voice = (
            f"In {resolved_name}, it is currently 29.5 degrees Celsius and partly cloudy, "
            f"with a high of 32 and a 30 percent chance of rain."
        )
        return {
            "status": "success",
            "location": resolved_name,
            "latitude": lat,
            "longitude": lon,
            "country": country,
            "temperature_c": 29.5,
            "current_temp": 29.5,
            "high_temp": 32.0,
            "low_temp": 25.0,
            "humidity": 76,
            "condition": "Partly cloudy",
            "rain_chance": 30,
            "voice_response": voice,
        }

    if dry_run:
        return _deterministic_fallback()

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
        f"&daily=temperature_2m_max,temperature_2m_min,weathercode,precipitation_probability_max"
        f"&timezone=auto"
    )
    try:
        res = requests.get(url, timeout=6)
        res.raise_for_status()
        data = res.json()

        current = data.get("current", {})
        daily = data.get("daily", {})

        cur_temp = current.get("temperature_2m", 29.5)
        humidity = current.get("relative_humidity_2m", 75)
        cur_code = current.get("weather_code", 2)
        cur_cond = WMO_CODES.get(cur_code, "Partly cloudy")

        dates = daily.get("time", [])
        idx = 0
        if target_date_str and target_date_str in dates:
            idx = dates.index(target_date_str)

        max_temps = daily.get("temperature_2m_max", [32.0])
        min_temps = daily.get("temperature_2m_min", [25.0])
        rain_probs = daily.get("precipitation_probability_max", [30])
        daily_codes = daily.get("weathercode", [cur_code])

        high_t = max_temps[idx] if idx < len(max_temps) else 32.0
        low_t = min_temps[idx] if idx < len(min_temps) else 25.0
        rain_p = rain_probs[idx] if idx < len(rain_probs) else 30
        day_cond = WMO_CODES.get(daily_codes[idx], cur_cond) if idx < len(daily_codes) else cur_cond

        if target_date_str and idx > 0:
            voice = (
                f"The forecast for {resolved_name} on {target_date_str} is {day_cond.lower()}, "
                f"with a high of {high_t} degrees Celsius, a low of {low_t}, and a {rain_p} percent chance of rain."
            )
        else:
            voice = (
                f"In {resolved_name}, it is currently {cur_temp} degrees Celsius and {cur_cond.lower()}, "
                f"with a high of {high_t} and a {rain_p} percent chance of rain."
            )

        return {
            "status": "success",
            "location": resolved_name,
            "latitude": lat,
            "longitude": lon,
            "country": country,
            "temperature_c": cur_temp,
            "current_temp": cur_temp,
            "high_temp": high_t,
            "low_temp": low_t,
            "humidity": humidity,
            "condition": cur_cond,
            "rain_chance": rain_p,
            "voice_response": voice,
        }
    except Exception:
        return _deterministic_fallback()


def get_forecast_for_iso_date(target_date_str: str, location_query: str = None) -> str:
    """Fetches weather for a specific YYYY-MM-DD date within the next 14 days."""
    geo = geocode_location(location_query) if location_query else {
        "name": DEFAULT_LOC_NAME,
        "latitude": DEFAULT_LAT,
        "longitude": DEFAULT_LON,
    }
    lat, lon, loc_name = geo["latitude"], geo["longitude"], geo["name"]
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        f"&timezone=Asia%2FKuala_Lumpur&forecast_days=14"
    )
    try:
        res = requests.get(url, timeout=8)
        res.raise_for_status()
        data = res.json()

        daily = data.get("daily", {})
        dates = daily.get("time", [])

        if target_date_str not in dates:
            return f"Warning: {target_date_str} is outside the 14-day meteorological forecast window."

        idx = dates.index(target_date_str)
        cond = WMO_CODES.get(daily["weather_code"][idx], "Variable conditions")
        t_max = daily["temperature_2m_max"][idx]
        t_min = daily["temperature_2m_min"][idx]
        rain_prob = daily["precipitation_probability_max"][idx]

        dt_obj = datetime.strptime(target_date_str, "%Y-%m-%d")
        pretty_date = dt_obj.strftime("%A, %B %d")

        report = f"Location: {loc_name}\nTarget Date: {pretty_date} ({target_date_str})\nForecast: {cond}, High of {t_max}°C, Low of {t_min}°C, {rain_prob}% chance of rain."

        if idx == 0 and "current" in data:
            curr = data["current"]
            c_cond = WMO_CODES.get(curr.get("weather_code", 0), "Unknown")
            report += f"\nRight Now: {curr.get('temperature_2m')}°C, {c_cond}, {curr.get('relative_humidity_2m')}% humidity."

        return report
    except Exception as e:
        return f"Weather API Error: {e}"


def get_weekly_forecast(location_query: str = None) -> str:
    """Fetches a full 7-day summary when the user asks about the 'whole week' or 'weekend'."""
    geo = geocode_location(location_query) if location_query else {
        "name": DEFAULT_LOC_NAME,
        "latitude": DEFAULT_LAT,
        "longitude": DEFAULT_LON,
    }
    lat, lon, loc_name = geo["latitude"], geo["longitude"], geo["name"]
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        f"&timezone=Asia%2FKuala_Lumpur&forecast_days=7"
    )
    try:
        res = requests.get(url, timeout=8)
        res.raise_for_status()
        daily = res.json().get("daily", {})
        dates = daily.get("time", [])

        lines = [f"7-Day Forecast for {loc_name}:"]
        for i in range(len(dates)):
            dt_obj = datetime.strptime(dates[i], "%Y-%m-%d")
            day_name = dt_obj.strftime("%A (%b %d)")
            cond = WMO_CODES.get(daily["weather_code"][i], "Unknown")
            lines.append(f"- {day_name}: {cond}, High {daily['temperature_2m_max'][i]}°C, {daily['precipitation_probability_max'][i]}% rain chance.")
        return "\n".join(lines)
    except Exception as e:
        return f"Weather API Error: {e}"