"""
weather.py: Fetches weather for a city using the free Open-Meteo API (no API key needed).
"""

import requests

# WMO weather interpretation codes used by Open-Meteo.
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def get_coordinates(city_name: str):
    """Turn a city name into latitude/longitude using Open-Meteo's geocoding API."""
    try:
        response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city_name, "count": 1, "language": "en", "format": "json"},
            timeout=10,
        )
        data = response.json()
        results = data.get("results")
        if results:
            r = results[0]
            return r["latitude"], r["longitude"], r["name"], r.get("country", "")
    except Exception as e:
        print(f"Error fetching coordinates: {e}")
    return None, None, None, None


def get_weather(city_name: str) -> str:
    """Return current weather, today's summary, and an hourly forecast for the rest of today."""
    lat, lon, name, country = get_coordinates(city_name)
    if lat is None or lon is None:
        return f"Could not find coordinates for city: {city_name}"

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                   "precipitation,weather_code,wind_speed_10m",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "forecast_days": 1,
        "timezone": "auto",  # all times come back in the city's local time
    }

    try:
        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        current = data.get("current", {})
        daily = data.get("daily", {})
        hourly = data.get("hourly", {})

        condition = WEATHER_CODES.get(current.get("weather_code"), "Unknown")
        local_time = current.get("time", "")  # e.g. "2026-10-07T14:15"

        summary = (
            f"Weather in {name}, {country} (local time {local_time.replace('T', ' ')}):\n"
            f"- Condition now: {condition}\n"
            f"- Temperature: {current.get('temperature_2m')}°C "
            f"(feels like {current.get('apparent_temperature')}°C)\n"
            f"- Today's high/low: {daily.get('temperature_2m_max', [None])[0]}°C / "
            f"{daily.get('temperature_2m_min', [None])[0]}°C\n"
            f"- Humidity: {current.get('relative_humidity_2m')}%\n"
            f"- Current precipitation: {current.get('precipitation')} mm\n"
            f"- Highest rain chance today: {daily.get('precipitation_probability_max', [None])[0]}%\n"
            f"- Wind: {current.get('wind_speed_10m')} km/h"
        )

        # Hourly forecast from the current hour until the end of today.
        current_hour = local_time[:13]  # "2026-10-07T14"
        lines = []
        for t, temp, prob, code in zip(
            hourly.get("time", []),
            hourly.get("temperature_2m", []),
            hourly.get("precipitation_probability", []),
            hourly.get("weather_code", []),
        ):
            if t[:13] < current_hour:
                continue
            lines.append(
                f"  {t[11:16]}: {temp}°C, {WEATHER_CODES.get(code, 'Unknown')}, rain chance {prob}%"
            )

        if lines:
            summary += "\n\nHourly forecast for the rest of today (local time):\n" + "\n".join(lines)

        return summary
    except Exception as e:
        return f"Error fetching weather data: {e}"