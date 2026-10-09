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
    """Safely extracts and parses JSON even if wrapped in markdown blocks or chat fluff."""
    if not text:
        return {}
    try:
        return json.loads(text.strip())
    except Exception:
        pass

    # Match ```json { ... } ```
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # Match outermost { ... }
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
        
        # Real conversation history tracking across turns
        # Structure: [{"role": "user"|"assistant", "content": str}, ...]
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

    def call_ollama(
        self, 
        model: str, 
        prompt: str, 
        system_prompt: str = "", 
        as_json: bool = False, 
        timeout: int = 60, 
        include_history: bool = False
    ) -> str:
        """Invokes Ollama's chat API with thinking disabled and options configured."""
        url = f"{self.base_url.rstrip('/')}/api/chat"
        messages = []

        # /no_think informs Qwen3 to skip internal reasoning tokens
        base_system = (system_prompt + " /no_think").strip() if system_prompt else "/no_think"
        messages.append({"role": "system", "content": base_system})

        # Inject real conversation history so pronouns and follow-ups resolve
        if include_history and self.conversation_history:
            messages.extend(self.conversation_history[-6:])

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,  # API-level reasoning disable
            "options": {
                "num_ctx": 4096,  # Lean context for fast latency
                "temperature": 0.3
            }
        }
        if as_json:
            payload["format"] = "json"

        try:
            res = requests.post(url, json=payload, timeout=timeout)
            if res.status_code == 200:
                data = res.json()
                return data.get("message", {}).get("content", "").strip()
            else:
                print(f"[Ollama Error {res.status_code}]: {res.text}")
        except Exception as e:
            print(f"[Ollama Call Failed for {model}]: {e}")
        return ""

    def plan_and_respond(self, user_query: str) -> dict:
        today = datetime.now()
        today_str = today.strftime("%A, %B %d, %Y")
        q_lower = user_query.lower().strip()

        # -------------------------------------------------------------
        # TIGHTENED ENTITY MATCHER (No broad "what is" trap)
        # -------------------------------------------------------------
        entity_match = re.search(r'^(?:who is|tell me about)\s+([a-zA-Z0-9\s]+?)(?:\?|$)', q_lower)
        if entity_match:
            target_entity = entity_match.group(1).strip()
            if not any(w in target_entity for w in ["the weather", "running", "today", "tomorrow"]):
                print(f"[FastTrack] Targeted Entity: '{target_entity}'")
                decision = self._execute_entity_lookup(target_entity, user_query, today_str)
                self._record_turn(user_query, decision.get("voice_response", ""))
                return decision

        # -------------------------------------------------------------
        # ROUTER CLASSIFICATION PASS (With History Awareness)
        # -------------------------------------------------------------
        router_model = self.models.get("router", "qwen3:8b")
        memory_ctx = self.memory.get_context_summary()

        system_instructions = (
            f"You are Libra, an elite autonomous cybernetic assistant. Current Date: {today_str}. Location: {self.city}.\n"
            f"Context Memory: {memory_ctx}\n"
            "Analyze intent and reply ONLY with a valid JSON object matching the requested schema."
        )

        prompt = f"""User request: "{user_query}"

Allowed actions:
- "lookup_entity": Biographical or factual questions about a specific person, place, or concept. ("target_entity": name)
- "live_research": Current news, recent tournament scores, sports results. ("search_query": keyword string)
- "open_app": Launching desktop software/games. ("target_app": app name)
- "web_search": Explicitly asking to search Google or YouTube. ("platform": "google"|"youtube", "search_query": query)
- "get_daily_weather": Specific day weather. ("target_date": "YYYY-MM-DD")
- "get_weekly_weather": 7-day weather overview.
- "chat": Greetings, jokes, opinions, or conversational follow-ups. ("voice_response": concise spoken text)

Output JSON:"""

        raw_json = self.call_ollama(
            router_model, 
            prompt, 
            system_prompt=system_instructions, 
            as_json=True, 
            timeout=45, 
            include_history=True
        )
        decision = extract_valid_json(raw_json)

        if not decision or "action" not in decision:
            decision = {"action": "chat", "voice_response": "I'm online. How can I assist you?"}

        action = decision.get("action")

        # -------------------------------------------------------------
        # DISPATCH EXECUTION
        # -------------------------------------------------------------
        if action == "lookup_entity":
            target = decision.get("target_entity") or user_query
            decision = self._execute_entity_lookup(target, user_query, today_str)

        elif action == "live_research":
            query = decision.get("search_query", user_query)
            snippets = search_live_web(query)
            
            synth_model = self.models.get("web_research", "qwen3:8b")
            synth_prompt = (
                f"You are Libra. Today is {today_str}.\n"
                f"Summarize these search results to answer '{user_query}' in 2 spoken sentences.\n"
                f"Do not read out URLs or snippet headers. No markdown asterisks.\n\n"
                f"Search Intel:\n{snippets}"
            )
            spoken = self.call_ollama(synth_model, synth_prompt, timeout=60)
            decision["voice_response"] = spoken or "I reviewed the search results, but could not formulate a clear answer."

        elif action == "chat":
            # If router didn't generate a conversational line, generate it using full history
            if not decision.get("voice_response") or decision.get("voice_response") in ["{}", "{\n\n}"]:
                chat_model = self.models.get("chat", "qwen3:8b")
                reply = self.call_ollama(
                    chat_model, 
                    user_query, 
                    system_prompt=system_instructions, 
                    timeout=30, 
                    include_history=True
                )
                decision["voice_response"] = reply or "Understood. Standing by."

        # Commit this interaction to persistent rolling session history
        self._record_turn(user_query, decision.get("voice_response", ""))
        return decision

    def _execute_entity_lookup(self, entity: str, original_query: str, today_str: str) -> dict:
        print(f"[Knowledge Engine] Entity Lookup: '{entity}'")
        summary = get_entity_summary(entity)
        if not summary:
            raw_web = search_live_web(f"{entity} biography overview")
            snippets = re.findall(r'Snippet:\s*(.+)', raw_web)
            summary = " ".join(snippets[:2]) if snippets else ""

        if not summary:
            return {
                "action": "chat",
                "voice_response": f"I couldn't verify records for {entity}."
            }

        synth_prompt = (
            f"You are Libra. State who {entity} is in 2 spoken sentences based on these facts:\n"
            f"Focus on who they are, their role/identity, and where they are from (avoid rattling off raw stats).\n"
            f"No markdown asterisks.\n\n"
            f"Facts:\n{summary}"
        )
        voice_text = self.call_ollama(self.models.get("chat", "qwen3:8b"), synth_prompt, timeout=35)
        
        # Guard: clean out any raw snippet debris if the synthesis failed
        if not voice_text:
            clean = re.sub(r'Title:.*?\n|Snippet:\s*', '', summary)
            voice_text = clean[:220].strip()

        return {
            "action": "lookup_entity",
            "voice_response": voice_text
        }

    def _record_turn(self, user_text: str, assistant_text: str):
        if user_text:
            self.conversation_history.append({"role": "user", "content": user_text})
        if assistant_text:
            self.conversation_history.append({"role": "assistant", "content": assistant_text})
        # Keep recent 8 conversational turns (4 exchanges) in memory window
        if len(self.conversation_history) > 8:
            self.conversation_history = self.conversation_history[-8:]