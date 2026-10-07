import os
import re
import json
import requests
from datetime import datetime

from core.memory import MemoryCore
from tools.search_agent import search_live_web
from tools.spotify_agent import SpotifyAgent
from tools.knowledge_agent import get_entity_summary


def extract_valid_json(text: str) -> dict:
    if not text:
        return {}
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    match = re.search(r'(\{.*\})', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    return {}


class LocalLLM:
    def __init__(self, config_path="config.json"):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.config_path = os.path.join(project_root, config_path)

        self.base_url = "http://localhost:11434"
        self.city = "Kuala Lumpur"
        self.models = {
            "router": "qwen3:8b",
            "web_research": "qwen3:8b",
            "chat": "qwen3:8b"
        }

        self.load_config()
        self.memory = MemoryCore()
        self.spotify = SpotifyAgent()
        self.conversation_history = []

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.base_url = cfg.get("ollama_base_url", self.base_url)
                    self.city = cfg.get("city", self.city)
                    default_m = cfg.get("ollama_model") or cfg.get("default_model", "qwen3:8b")
                    for k in self.models:
                        self.models[k] = default_m
                    model_pool = cfg.get("models", {})
                    for role, name in model_pool.items():
                        self.models[role] = name
            except Exception as e:
                print(f"[LLM Config Error]: {e}")

    def call_ollama(self, model: str, prompt: str, system_prompt: str = "", as_json: bool = False) -> str:
        """Invokes Ollama using the chat endpoint for reliable instruction following."""
        url = f"{self.base_url.rstrip('/')}/api/chat"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False
        }
        if as_json:
            payload["format"] = "json"

        try:
            res = requests.post(url, json=payload, timeout=18)
            if res.status_code == 200:
                return res.json().get("message", {}).get("content", "").strip()
        except Exception as e:
            print(f"[Ollama Call Failed for {model}]: {e}")
        return ""

    def plan_and_respond(self, user_query: str) -> dict:
        today = datetime.now()
        today_str = today.strftime("%A, %B %d, %Y")
        q_lower = user_query.lower().strip()

        # -------------------------------------------------------------
        # FAST TRACK: Direct Entity Detection
        # -------------------------------------------------------------
        # If user explicitly asks "who is X" or "tell me about X", bypass JSON parsing risks
        entity_match = re.search(r'\b(?:who is|tell me about|what is|search up who is)\s+([a-zA-Z0-9\s]+?)(?:\s+using|\?|$)', q_lower)
        if entity_match:
            target_entity = entity_match.group(1).strip()
            # Clean extraneous trailing phrases
            for stopword in ["using", "with", "the tools", "can you", "please"]:
                if stopword in target_entity:
                    target_entity = target_entity.split(stopword)[0].strip()

            if len(target_entity) > 2:
                print(f"[FastTrack] Detected entity query: '{target_entity}'")
                return self._execute_entity_lookup(target_entity, user_query, today_str)

        # -------------------------------------------------------------
        # LLM ROUTING PASS
        # -------------------------------------------------------------
        router_model = self.models.get("router", "qwen3:8b")
        system_instructions = (
            f"You are Libra, an autonomous desktop assistant. Current Date: {today_str}. Location: {self.city}.\n"
            "Classify the user intent and reply with ONLY a JSON object.\n"
            "Actions: 'lookup_entity', 'live_research', 'open_app', 'web_search', 'get_daily_weather', 'get_weekly_weather', 'chat'."
        )

        prompt = f"""User request: "{user_query}"

Respond with ONLY this JSON format:
{{
  "action": "lookup_entity" | "live_research" | "open_app" | "web_search" | "get_daily_weather" | "get_weekly_weather" | "chat",
  "target_entity": "person or concept name if lookup_entity",
  "search_query": "keywords if live_research or web_search",
  "target_app": "app name if open_app",
  "target_date": "YYYY-MM-DD if get_daily_weather",
  "voice_response": "vocal response if chat"
}}"""

        raw_json = self.call_ollama(router_model, prompt, system_prompt=system_instructions, as_json=True)
        decision = extract_valid_json(raw_json)

        # If JSON choked, try a fallback entity search
        if not decision or "action" not in decision:
            print(f"[LLM] Parsing failed on: '{raw_json}'. Checking for entity fallback...")
            return self._execute_entity_lookup(user_query, user_query, today_str)

        action = decision.get("action")

        # -------------------------------------------------------------
        # EXECUTION DISPATCH
        # -------------------------------------------------------------
        if action == "lookup_entity":
            target = decision.get("target_entity") or user_query
            return self._execute_entity_lookup(target, user_query, today_str)

        elif action == "live_research":
            query = decision.get("search_query", user_query)
            snippets = search_live_web(query)
            synth_prompt = f"Summarize these search results to answer '{user_query}' in 2 spoken sentences. Avoid markdown:\n{snippets}"
            decision["voice_response"] = self.call_ollama(self.models.get("web_research", "qwen3:8b"), synth_prompt)

        return decision

    def _execute_entity_lookup(self, entity: str, original_query: str, today_str: str) -> dict:
        print(f"[Knowledge Engine] Looking up: {entity}")
        summary = get_entity_summary(entity)
        if not summary:
            raw_web = search_live_web(f"{entity} biography overview")
            # Extract plain text from snippet if Ollama is unreachable
            import re
            snippets = re.findall(r'Snippet:\s*(.+)', raw_web)
            summary = " ".join(snippets[:2]) if snippets else ""

        if not summary:
            return {
                "action": "chat",
                "voice_response": f"I couldn't locate reliable records for {entity}."
            }

        synth_prompt = f"""You are Libra. State who {entity} is in 2 spoken sentences based strictly on the facts below.
Focus on: Where they are from, who they are, their role/identity, and their background (NOT just a list of career stats or numbers).

Facts:
{summary}

Spoken reply (natural, no markdown asterisks):"""
        voice_text = self.call_ollama(self.models.get("chat", "qwen3:8b"), synth_prompt)
        
        # If Ollama timed out, sanitize summary so it doesn't read 'Title:' or 'Snippet:'
        if not voice_text:
            clean_speech = re.sub(r'Title:.*?\n|Snippet:\s*', '', summary)
            voice_text = clean_speech[:250].strip()

        return {
            "action": "lookup_entity",
            "voice_response": voice_text
        }