import os
import json
import requests
from datetime import datetime, date

# Load city settings from config.json
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
config_file = os.path.join(project_root, "config.json")

# Default coordinates for Kuala Lumpur
LATITUDE = 3.1390
LONGITUDE = 101.6869

if os.path.exists(config_file):
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # If city is Kuala Lumpur, coordinates match
            if cfg.get("city", "").lower() == "kuala lumpur":
                LATITUDE = 3.1390
                LONGITUDE = 101.6869
    except Exception:
        pass

WMO_WEATHER_CODES = {
    0: "clear skies", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "rime fog", 51: "light drizzle", 53: "moderate drizzle",
    55: "dense drizzle", 61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    71: "light snow", 73: "moderate snow", 75: "heavy snow", 80: "rain showers",
    81: "moderate showers", 82: "torrential rain", 95: "thunderstorms",
    96: "thunderstorms with hail", 99: "severe thunderstorms"
}

def fetch_weather_api():
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={LATITUDE}&longitude={LONGITUDE}"
        f"&daily=temperature_2m_max,temperature_2m_min,weathercode,precipitation_probability_max"
        f"&forecast_days=16&timezone=auto"
    )
    try:
        response = requests.get(url, timeout=6)
        response.raise_for_status()
        return response.json().get("daily", {})
    except Exception as e:
        print(f"[Weather API Error]: {e}")
        return None

def get_forecast_for_iso_date(target_date_str: str):
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except Exception:
        target_date = date.today()

    today = date.today()
    offset = (target_date - today).days

    if offset < 0:
        return "I can only forecast future atmospheric conditions, not historical dates."

    if offset > 14:
        return (
            f"I cannot provide a reliable forecast for {target_date.strftime('%B %d')}. "
            "Atmospheric numerical models only maintain precision up to 14 days in advance."
        )

    daily = fetch_weather_api()
    if not daily or "time" not in daily:
        return "I am unable to retrieve the live atmospheric telemetry at the moment."

    times = daily.get("time", [])
    if offset >= len(times):
        return f"Telemetry for {target_date.strftime('%B %d')} is currently unavailable."

    max_temp = round(daily["temperature_2m_max"][offset])
    min_temp = round(daily["temperature_2m_min"][offset])
    code = daily["weathercode"][offset]
    rain_prob = daily.get("precipitation_probability_max", [0])[offset]
    condition = WMO_WEATHER_CODES.get(code, "variable conditions")

    day_str = target_date.strftime("%A, %B %d")
    speech = f"On {day_str}, the forecast indicates {condition}, with a high of {max_temp}° and a low of {min_temp}° Celsius."
    if rain_prob and rain_prob > 25:
        speech += f" There is a {rain_prob}% probability of rain."

    return speech

def get_weekly_forecast():
    daily = fetch_weather_api()
    if not daily or "time" not in daily:
        return []

    times = daily.get("time", [])
    max_temps = daily.get("temperature_2m_max", [])
    codes = daily.get("weathercode", [])

    forecast_table = []
    for i in range(min(7, len(times))):
        d_obj = datetime.strptime(times[i], "%Y-%m-%d")
        forecast_table.append({
            "date": d_obj.strftime("%A (%b %d)"),
            "temp": f"{round(max_temps[i])}°C" if i < len(max_temps) else "--",
            "condition": WMO_WEATHER_CODES.get(codes[i], "Variable").title()
        })
    return forecast_table