import os
import re
import json
import requests
from datetime import datetime

from core.memory import MemoryCore
from tools.knowledge_agent import get_entity_summary
from tools.search_agent import search_live_web
from tools.system_actions import launch_any_application, close_any_application, find_and_open_file, web_search
from tools.weather import get_forecast_for_iso_date, get_weekly_forecast


def condense_spelling(text: str) -> str:
    """Condenses spaced-out spellings (e.g., 'M E S S I' -> 'MESSI')."""
    return re.sub(r"(?:\b[a-zA-Z]\b\s+){2,}\b[a-zA-Z]\b", lambda m: m.group(0).replace(" ", ""), text)


def extract_valid_json(text: str) -> dict:
    """Extracts and parses JSON object from an LLM response string."""
    if not text:
        return {}
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    try:
        return json.loads(text)
    except Exception:
        return {}


class LocalLLM:
    def __init__(self, host="http://localhost:11434"):
        self.host = host
        self.models = {
            "router": "qwen3:8b",
            "chat": "qwen3:8b",
            "web_research": "qwen3:8b"
        }
        self.city = "Kuala Lumpur"
        self.memory = MemoryCore()
        self.conversation_history = []
        self.session_state = {
            "active_apps": [],
            "last_target": None,
            "last_action": None,
            "current_entity": None
        }

    def call_ollama(
        self,
        model: str,
        prompt: str,
        system_prompt: str = "",
        as_json: bool = False,
        timeout: int = 40,
        include_history: bool = False
    ) -> str:
        url = f"{self.host}/api/chat"
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # ONLY pass conversational history for 'chat', not for structured routing
        if include_history and self.conversation_history:
            messages.extend(self.conversation_history[-6:])

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1}
        }
        if as_json:
            payload["format"] = "json"

        try:
            response = requests.post(url, json=payload, timeout=timeout)
            if response.status_code == 200:
                content = response.json().get("message", {}).get("content", "").strip()
                return content
            else:
                print(f"[Ollama Error Status]: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[Ollama Call Exception]: {e}")
        return ""

    def plan_and_respond(self, user_query: str) -> dict:
        today = datetime.now()
        today_str = today.strftime("%A, %B %d, %Y")

        cleaned_query = condense_spelling(user_query)
        q_lower = cleaned_query.lower().strip()

        # -------------------------------------------------------------
        # 1. DIRECT MEMORY FAST-TRACK ("Remember that...")
        # -------------------------------------------------------------
        mem_match = re.search(r"(?:remember\s+(?:that\s+)?|save\s+(?:that\s+)?|note\s+(?:that\s+)?)(.+)", q_lower)
        if mem_match and any(trigger in q_lower for trigger in ["remember", "note that", "save that"]):
            raw_fact = mem_match.group(1).strip()
            # Clean leading polite prefixes
            raw_fact = re.sub(r"^(?:please\s+|can\s+you\s+)", "", raw_fact)
            # Normalize first-person phrasing (e.g. "my favorite" stays or "I am")
            clean_fact = raw_fact.rstrip(".?!")
            self.memory.add_fact(clean_fact)
            ack_msg = f"Got it. I've committed that to memory: {clean_fact}."
            decision = {"action": "remember_fact", "fact": clean_fact, "voice_response": ack_msg}
            self._record_turn(user_query, ack_msg)
            return decision

        # -------------------------------------------------------------
        # 2. PRONOUN RESOLUTION VIA SESSION STATE (App Termination)
        # -------------------------------------------------------------
        if any(w in q_lower for w in ["close it", "shut it down", "exit it", "kill it"]):
            if self.session_state["last_target"]:
                target = self.session_state["last_target"]
                print(f"[State Engine] Pronoun 'it' -> '{target}'")
                success, msg = close_any_application(target)
                if target in self.session_state["active_apps"]:
                    self.session_state["active_apps"].remove(target)
                decision = {"action": "close_app", "target_app": target, "voice_response": msg}
                self._record_turn(user_query, msg)
                return decision

        # -------------------------------------------------------------
        # 3. COMPOUND ACTION: OPEN BROWSER + READ SUMMARY ALOUD
        # -------------------------------------------------------------
        # Matches: "open google and search for X and read one for me / tell me"
        wants_read_aloud = any(p in q_lower for p in ["read one", "tell me one", "summarize", "read it", "tell me about it", "read for me"])
        explicit_search = re.search(
            r"(?:open\s+(?:google|chrome|browser)\s+and\s+search(?:\s+for)?|search\s+(?:on\s+)?(google|youtube)(?:\s+for)?)\s+(.+)",
            q_lower
        )

        if explicit_search:
            platform = "youtube" if "youtube" in q_lower else "google"
            raw_search_query = explicit_search.group(2).strip()

            # Separate search terms from the conversational read command
            clean_search_query = re.sub(r"(?:and\s+)?(?:read|tell|summarize).*", "", raw_search_query).strip()
            clean_search_query = re.sub(r"[?!.]+$", "", clean_search_query).strip()

            # Launch browser
            web_search(clean_search_query, platform=platform)

            # If user also asked to read/summarize, pull live research and speak it!
            if wants_read_aloud:
                print(f"[Compound Action] Opened browser for '{clean_search_query}', now gathering verbal summary...")
                snippets = search_live_web(f"{clean_search_query} top headlines latest")
                synth_prompt = (
                    f"You are Libra. Today is {today_str}.\n"
                    f"The user opened Google for '{clean_search_query}' and asked you to read one key piece of news or result aloud.\n"
                    f"Based on these live search results:\n{snippets}\n\n"
                    f"State that you opened the browser, then read out ONE prominent story or finding concisely in 2 spoken sentences.\n"
                    f"Do not use markdown formatting or asterisks."
                )
                spoken = self.call_ollama(self.models.get("web_research", "qwen3:8b"), synth_prompt, timeout=40)
                spoken_response = spoken or f"I opened Google for {clean_search_query}."
            else:
                spoken_response = f"Opening {platform.capitalize()} search for {clean_search_query}."

            decision = {
                "action": "compound_web_search",
                "platform": platform,
                "search_query": clean_search_query,
                "voice_response": spoken_response
            }
            self._record_turn(user_query, spoken_response)
            return decision

        # -------------------------------------------------------------
        # 4. FAST-TRACK ENTITY MATCHER (Guarded against pronouns)
        # -------------------------------------------------------------
        pronoun_words = {"he", "his", "him", "she", "her", "hers", "it", "its", "they", "them", "their"}
        entity_match = re.search(r"^(?:who is|tell me about)\s+([a-zA-Z0-9\s]+?)(?:\?|$)", q_lower)

        if entity_match:
            candidate_entity = entity_match.group(1).strip()
            tokens = set(candidate_entity.split())

            if not tokens.intersection(pronoun_words) and not any(w in candidate_entity for w in ["the weather", "running", "today", "tomorrow"]):
                self.session_state["current_entity"] = candidate_entity
                decision = self._execute_entity_lookup(candidate_entity, user_query, today_str)
                self._record_turn(user_query, decision.get("voice_response", ""))
                return decision

        # -------------------------------------------------------------
        # 5. ROUTER PASS WITH QUERY-AWARE CONTEXT & FEW-SHOT EXAMPLES
        # -------------------------------------------------------------
        router_model = self.models.get("router", "qwen3:8b")
        memory_ctx = self.memory.get_context_summary(current_query=cleaned_query)
        active_apps_str = ", ".join(self.session_state["active_apps"]) or "None"
        current_subject = self.session_state.get("current_entity") or "None"

        system_instructions = (
            f"You are Libra, an elite autonomous cybernetic desktop assistant. Date: {today_str}. Location: {self.city}.\n"
            f"Active Apps: [{active_apps_str}] | Active Conversation Subject: {current_subject}\n"
            f"User Profile Memory:\n{memory_ctx}\n"
            "Analyze intent and respond with ONLY a single raw JSON object matching the schemas below."
        )

        prompt = f"""Select the best matching action for the request.

Schemas and Examples:
- Launch app: {{"action": "open_app", "target_app": "name"}}
- Close app: {{"action": "close_app", "target_app": "name"}}
- Open file: {{"action": "open_file", "target_file": "filename"}}
- Weather: {{"action": "get_daily_weather", "target_date": "YYYY-MM-DD"}} or {{"action": "get_weekly_weather"}}
- Entity bio: {{"action": "lookup_entity", "target_entity": "person or topic"}}
- Verbal live research: {{"action": "live_research", "search_query": "specific search terms"}}
- Conversational chat / questions about stored memory / capabilities: {{"action": "chat", "voice_response": "spoken message"}}

Request: "{cleaned_query}"
JSON:"""

        raw_json = self.call_ollama(
            router_model,
            prompt,
            system_prompt=system_instructions,
            as_json=True,
            timeout=40,
            include_history=False,
        )

        decision = extract_valid_json(raw_json)
        if not decision or "action" not in decision or decision.get("action") == "":
            # Fallback to conversational chat using memory context
            chat_reply = self.call_ollama(
                self.models.get("chat", "qwen3:8b"),
                f"Respond conversationally in 1-2 spoken sentences to: '{cleaned_query}'. Use the provided User Profile Memory if relevant. Do not output JSON.",
                system_prompt=system_instructions,
                timeout=30,
                include_history=True
            )
            clean_reply = re.sub(r"\{.*?\}", "", chat_reply, flags=re.DOTALL).strip() or chat_reply
            decision = {"action": "chat", "voice_response": clean_reply or "Understood. How can I assist you?"}

        action = decision.get("action")

        # -------------------------------------------------------------
        # 6. ACTION DISPATCH & EXECUTION
        # -------------------------------------------------------------
        if action == "lookup_entity":
            target = decision.get("target_entity", cleaned_query)
            if any(p in target.lower().split() for p in pronoun_words) and self.session_state.get("current_entity"):
                target = self.session_state["current_entity"]
            self.session_state["current_entity"] = target
            decision = self._execute_entity_lookup(target, user_query, today_str)

        elif action == "live_research":
            query = decision.get("search_query", cleaned_query)
            if self.session_state.get("current_entity") and any(p in query.lower().split() for p in pronoun_words):
                query = f"{self.session_state['current_entity']} {query}"

            snippets = search_live_web(query)
            synth_model = self.models.get("web_research", "qwen3:8b")
            synth_prompt = (
                f"You are Libra. Today is {today_str}.\n"
                f"Answer the user's question: '{cleaned_query}' in 2 spoken sentences based strictly on these search results:\n{snippets}\n"
                f"Do not use markdown formatting or asterisks."
            )
            spoken = self.call_ollama(synth_model, synth_prompt, timeout=45)
            decision["voice_response"] = spoken or "I reviewed the search results, but could not formulate a clear answer."

        elif action == "open_app":
            target = decision.get("target_app", "").strip()
            success, msg = launch_any_application(target)
            if success:
                if target.lower() not in self.session_state["active_apps"]:
                    self.session_state["active_apps"].append(target.lower())
                self.session_state["last_target"] = target.lower()
                self.session_state["last_action"] = "open_app"
            decision["voice_response"] = msg

        elif action == "close_app":
            target = decision.get("target_app", "").strip().lower() or self.session_state["last_target"]
            if target:
                success, msg = close_any_application(target)
                if target in self.session_state["active_apps"]:
                    self.session_state["active_apps"].remove(target)
                decision["voice_response"] = msg
            else:
                decision["voice_response"] = "No active application was targeted for termination."

        elif action == "open_file":
            target = decision.get("target_file", "")
            success, msg = find_and_open_file(target)
            decision["voice_response"] = msg

        elif action == "get_daily_weather":
            target_date = decision.get("target_date", datetime.today().strftime("%Y-%m-%d"))
            decision["voice_response"] = get_forecast_for_iso_date(target_date)

        elif action == "get_weekly_weather":
            table = get_weekly_forecast()
            if table:
                decision["voice_response"] = (
                    f"Here is the upcoming forecast for {self.city}: "
                    f"{table[0]['date']} starts with {table[0]['condition']} at {table[0]['temp']}."
                )
            else:
                decision["voice_response"] = "Atmospheric telemetry is currently unavailable."

        elif action == "chat":
            if not decision.get("voice_response"):
                chat_model = self.models.get("chat", "qwen3:8b")
                reply = self.call_ollama(
                    chat_model,
                    cleaned_query,
                    system_prompt=system_instructions,
                    timeout=30,
                    include_history=True,
                )
                decision["voice_response"] = reply or "Acknowledged."

        self._record_turn(user_query, decision.get("voice_response", ""))
        return decision

    def _execute_entity_lookup(self, entity: str, user_query: str, today_str: str) -> dict:
        print(f"[Knowledge Engine] Querying entity: '{entity}' for query: '{user_query}'")

        # Strip relational tokens to locate base Wikipedia article
        clean_target = entity
        for noise in [" wife", " husband", " net worth", " career", " salary", " age", " kids", " height"]:
            clean_target = clean_target.replace(noise, "")
        clean_target = clean_target.strip()

        summary = get_entity_summary(clean_target) if clean_target else ""

        # Check if query requests relational or fast-moving facts
        search_intel = ""
        needs_search = any(w in user_query.lower() for w in ["wife", "husband", "married", "net worth", "contract", "salary", "team currently", "currently"])

        if not summary or needs_search:
            print(f"[Knowledge Engine] Querying live web search for: '{entity}'")
            search_query = f"{clean_target} {user_query}" if clean_target else entity
            search_intel = search_live_web(search_query)

        combined_facts = f"Wikipedia Context:\n{summary}\n\nLive Search Intel:\n{search_intel}".strip()

        if not combined_facts or combined_facts == "Wikipedia Context:\n\nLive Search Intel:":
            return {"action": "chat", "voice_response": f"I couldn't locate verified records for {entity}."}

        synth_prompt = (
            f"You are Libra. Today is {today_str}.\n"
            f"User Question: '{user_query}'\n"
            f"Available Intel:\n{combined_facts}\n\n"
            f"Provide a direct, conversational 1 to 2 sentence answer addressing the user's specific question.\n"
            f"Do not mention 'according to Wikipedia' or 'search results'. No asterisks or bullet points."
        )
        voice_text = self.call_ollama(self.models.get("chat", "qwen3:8b"), synth_prompt, timeout=35)
        return {"action": "lookup_entity", "voice_response": voice_text or summary[:200]}

    def _record_turn(self, user_text: str, assistant_text: str):
        """Maintains the sliding window conversation history."""
        if user_text:
            self.conversation_history.append({"role": "user", "content": user_text})
        if assistant_text:
            self.conversation_history.append({"role": "assistant", "content": assistant_text})
        if len(self.conversation_history) > 8:
            self.conversation_history = self.conversation_history[-8:]