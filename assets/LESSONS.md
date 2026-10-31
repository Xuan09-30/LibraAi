# Project Libra — Counterfactual Correction & Operational Lesson Memory

This file stores explicit user corrections and operational rules learned across sessions.
Whenever a similar ambiguous query or command arises, Libra consults these lessons to prevent repeating past operational mistakes.

## 1. File Paths & Directory Resolution
- Prefer the active Windows 11 Desktop (`OneDrive\Desktop` if synced, otherwise `~/Desktop`) when resolving desktop folders.

## 2. Tool & Application Selection
- Launch Steam games via `steam://rungameid/<AppID>` or clean detached environment to avoid Easy Anti-Cheat (EAC) DLL conflicts.

## 3. Naming & Parameter Preferences
<!-- Dynamic counterfactual corrections appended below -->
- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-17 17:58)
- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-17 21:06)
- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-17 21:06)
- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-17 22:07)
- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-17 22:34)
- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-17 22:45)
- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-17 22:47)
- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-18 09:05)
- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-19 09:48)
- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-19 16:25)
- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-19 16:36)

## 4. Screen Vision & In-Game Grounding
- **Trigger**: `what is my screen showing` / `can you see my screen` / `can you see my in-game name` | **Avoid**: Text-only fallback hallucinations (`LibraTest`, `LibraTestUser`) | **Corrected Action**: Attach thread to input desktop, retrieve active window metadata (`League of Legends`, etc.) via `ActiveWindowEngine`, capture real display pixels with `ImageGrab`, and run `qwen2.5vl:7b`. If text is occluded or blurry, truthfully state that the fine text is not legible. Never invent player names or active windows.

## 5. Timezones & Location Clarifications
- **Trigger**: `what's the time in the US, Arizona` | **Avoid**: Defaulting to user's local timezone (`Asia/Kuala_Lumpur`) | **Corrected Action**: Resolve US state to Mountain Standard Time (`America/Phoenix`, UTC-7).
- **Trigger**: `time in the US is same as mine, are you sure?` | **Avoid**: Capturing conversational objection phrases as location names | **Corrected Action**: Disambiguate factually (explain the 15-hour difference between Malaysia UTC+8 and US Mountain Time UTC-7).

## 6. Chrome Multi-Profile & UI Automation
- **Trigger**: `open Google for me` / `open first account in Chrome` | **Avoid**: Launching generic apps named `first account in google chrome` | **Corrected Action**: Resolve ordinal account profiles (0 -> `Default`/`Chuah`), launch Chrome with `--profile-directory`, and use `GUIControlAgent` to focus and activate profile selector tiles.

## 7. Follow-Up Listening & Conversational Standby
- **Trigger**: `thank you` / `thanks` / `bye` / `that's all` | **Avoid**: Keeping microphone open in follow-up mode | **Corrected Action**: Immediately reset `in_followup_mode = False` and return to standby. Only maintain follow-up when the assistant asked an open-ended question or clarification.

## 8. Timezone Objection Substring Guard
- **Trigger**: `no I mean...` with words like `house`, `just`, `focus` | **Avoid**: Unbounded substring checks (`"us" in q_lower`) falsely triggering US/Malaysia timezone objections | **Corrected Action**: Enforce strict word boundaries (`\b(?:same\s+time|timezone|time\s*zone|time\s+in\s+the\s+us)\b`).

## 9. Real File System Creation & Opening
- **Trigger**: `create a python file called test...` / `open it for me to see` / `no I mean the test.py file...` | **Avoid**: LLM conversational hallucination stating a file was created without touching disk, and routing pronoun file openings to folder searches | **Corrected Action**: Invoke `FileManager.create_file()` to write real code to Desktop/workspace, update `last_file_path`, allow code updates (`write_to_file()`), and resolve pronoun references to open the file in the default editor / VS Code.

## 10. Local Restaurant POI Discovery & Compound Intents
- **Trigger**: `nearest restaurant near my house` / `options of the nearest restaurant` / `what about the time here and also can you tell me about the weather for today?` | **Avoid**: Falling through to web search summaries or ignoring the time component of compound requests | **Corrected Action**: Route to `PlacesDiscoveryEngine` with Kepong fallbacks (including favorite food *Ayam Gepuk*), support candidate detail/review follow-ups, and split compound multi-intent commands on `and also` to answer both time and weather in a single cohesive turn.

## 11. Microphone Dynamic Reconnection & Physical Disconnect Recovery
- **Trigger**: Microphone unplugged, Bluetooth headset disconnected, or device re-inserted while app is running | **Avoid**: Crashing PyAudio worker threads, falling silent indefinitely, or requiring a manual application restart | **Corrected Action**: Implement non-blocking polling retry loop (every 2.0s) in `VoiceAssistantWorker`. When a microphone is lost, cleanly close the stream, drop to Text Mode, and emit notification balloon and chatbox alert. The instant a microphone endpoint is plugged back into Windows, auto-open the audio stream, display a "Microphone Connected" desktop balloon, and restore full voice wake word listening.

## 12. Live Source Code Auto-Reloader & Hot Refresh Watchdog
- **Trigger**: Developer or AI assistant updates code files (`.py`, `.html`) | **Avoid**: Running stale versions in memory without detecting updates, or restarting into broken syntax crash loops | **Corrected Action**: Run background `CodeReloader` via `watchdog` monitoring `PROJECT_ROOT` (excluding logs, venv, caches, and vendor scripts). Debounce file events (1.5s), validate Python syntax with `ast.parse()` prior to reload, display desktop and terminal notifications, cleanly release IPC socket (`libra_instance_ipc`), and relaunch `pythonw.exe` preserving window visibility state.


- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-21 17:37)
- **Windows Startup & Process Singleton**: Never register in both `HKCU\...\Run` and `shell:startup` simultaneously (Windows will execute both at logon). Always use an atomic Windows Named Mutex (`CreateMutexW`) before importing heavy modules (Torch/Whisper) to guarantee zero-latency single-instance protection and avoid GPU/PyAudio port collisions. To guarantee UI window focus on Windows 11 boot, use VK_MENU Alt pulse + `AttachThreadInput` + `SetWindowPos(HWND_TOPMOST -> HWND_NOTOPMOST)` with staggered timer pulses.
- **Trigger**: `open my project folder` | **Avoid**: `OldDrafts` | **Corrected Action**: `LibraAi` (2026-10-26 01:01)
- **Trigger**: `navigate cinejoy.pk` | **Avoid**: `Foreign ad overlays and DOM layout delays on cinejoy.pk` | **Corrected Action**: `Executed loop recovery: dismissed ad pop-ups with Ctrl+W, grounded DOM elements via CDP/OCR, and verified resume state.` (2026-10-31 12:26)
- **Trigger**: `navigate cinejoy.pk` | **Avoid**: `Foreign ad overlays and DOM layout delays on cinejoy.pk` | **Corrected Action**: `Executed loop recovery: dismissed ad pop-ups with Ctrl+W, grounded DOM elements via CDP/OCR, and verified hannibal on my pc state.` (2026-10-31 13:58)
