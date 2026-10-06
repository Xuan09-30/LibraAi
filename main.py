"""
main.py: Libra, step 1 (terminal version).
Chat with a local Ollama model that can call a weather tool by itself.
"""

import json
from datetime import datetime
from pathlib import Path

from ollama import Client

from weather import get_weather

CONFIG_PATH = Path(__file__).parent / "config.json"

# Describes the tool to the model in plain English so it knows when to use it.
WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Get the current weather and the hourly forecast for the rest of today "
            "in a city. Use it for questions about weather, rain, temperature, "
            "outdoor activities, or what to wear."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city_name": {
                    "type": "string",
                    "description": "The city to check, e.g. Kuala Lumpur.",
                }
            },
            "required": ["city_name"],
        },
    },
}


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def build_system_prompt(default_city: str) -> str:
    """Rebuilt every turn so the date and time are always current."""
    now = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    return (
        "You are Libra, a helpful local voice assistant running on the user's Windows PC.\n"
        f"The current local date and time is {now}.\n"
        f"The user's home city is {default_city}. Assume it unless they name another city.\n"
        "For questions about weather, rain, temperature, outdoor plans or clothing, "
        "you MUST call the get_weather tool before answering, and base your answer "
        "on its numbers, including the hourly forecast for time-specific questions."
    )


def run_turn(client: Client, model: str, messages: list, default_city: str) -> str:
    """Send the conversation to the model, run any tools it asks for, return the final reply."""
    messages[0] = {"role": "system", "content": build_system_prompt(default_city)}

    # Allow a few rounds so the model can call a tool, read the result, and answer.
    for _ in range(4):
        response = client.chat(
            model=model,
            messages=messages,
            tools=[WEATHER_TOOL],
            think=False,  # turn off Qwen3's slow "thinking" mode
        )
        message = response.message
        messages.append(message)

        if not message.tool_calls:
            return message.content or ""

        for call in message.tool_calls:
            name = call.function.name
            args = call.function.arguments or {}
            if name == "get_weather":
                city = args.get("city_name", default_city)
                print(f"\n[Libra is checking weather for {city}...]")
                result = get_weather(city)
            else:
                result = f"Unknown tool: {name}"
            messages.append({"role": "tool", "content": result})

    return "Sorry, I got stuck trying to answer that. Could you ask again?"


def main():
    config = load_config()
    model = config.get("ollama_model", "qwen3:8b")
    default_city = config.get("city", "Kuala Lumpur")
    client = Client(host=config.get("ollama_base_url", "http://localhost:11434"))

    print("=" * 60)
    print("Libra AI Assistant (Step 1 - Terminal)")
    print(f"Model: {model} | Home city: {default_city}")
    print("Type your question (type 'exit' or 'quit' to stop).")
    print("=" * 60)

    messages = [{"role": "system", "content": build_system_prompt(default_city)}]

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                print("Goodbye!")
                break

            messages.append({"role": "user", "content": user_input})
            reply = run_turn(client, model, messages, default_city)
            print(f"\nLibra: {reply}")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError communicating with Ollama: {e}")
            print("Make sure the Ollama app is running and the model is pulled (ollama pull qwen3:8b).")


if __name__ == "__main__":
    main()