import json
import ollama
from tools.weather import get_weather
from core.stt import listen
from core.tts import speak
import re
from core.tts import TextToSpeech
from core.stt import SpeechToText
from tools.weather import get_weather

# Map available tools by name
TOOL_MAP = {
    "get_weather": get_weather
}

SYSTEM_PROMPT = """You are Libra, an authentic, highly capable AI assistant like JARVIS.
Default location: Kuala Lumpur, Malaysia. If the user asks about the weather without specifying a location, assume Kuala Lumpur.
Keep your spoken responses natural, concise, and direct."""

def clean_for_speech(text):
    """Strips markdown, redundant time formats, and emojis for TTS."""
    if not text:
        return ""
        
    # Remove Markdown formatting (like ** or *)
    text = re.sub(r'\*+', '', text)
    
    # Remove redundant 24-hour times in parentheses e.g. (20:00)
    text = re.sub(r'\(\d{1,2}:\d{2}\)', '', text)
    
    # Remove emojis by keeping only standard ASCII characters (letters, numbers, basic punctuation)
    text = text.encode('ascii', 'ignore').decode('ascii')
    
    # Clean up any leftover double spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def chat_loop():
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    
    speak("All systems online. I am ready.")
    
    while True:
        try:
            # 1. Listen for voice input
            user_text = listen(duration=5)
            
            if not user_text or len(user_text.strip()) == 0:
                continue
                
            print(f"\n[You]: {user_text}")
            messages.append({"role": "user", "content": user_text})
            
            # 2. First call to Ollama (checking for tool calls)
            response = ollama.chat(
                model='qwen3:8b',
                messages=messages,
                tools=[get_weather],
            )
            
            # Append model's response (tool call or direct message)
            messages.append(response.message)
            
            # 3. Handle Tool Calls if the model triggered one
            if response.message.tool_calls:
                for tool_call in response.message.tool_calls:
                    func_name = tool_call.function.name
                    args = tool_call.function.arguments
                    
                    if func_name in TOOL_MAP:
                        print(f"⚙️ [Tool Calling]: {func_name}({args})")
                        tool_result = TOOL_MAP[func_name](**args)
                        
                        # Feed the tool output back into the conversation history
                        messages.append({
                            "role": "tool",
                            "content": json.dumps(tool_result),
                        })
                
                # Ask Ollama to synthesize the final spoken answer using the tool data
                followup_response = ollama.chat(
                    model='qwen3:8b',
                    messages=messages
                )
                final_reply = followup_response.message.content
                messages.append(followup_response.message)
            else:
                final_reply = response.message.content

            # 4. Speak and display the final reply
            print(f"\n[Libra]: {final_reply}")
            if final_reply:
                spoken_reply = clean_for_speech(final_reply)
                speak(spoken_reply)

        except KeyboardInterrupt:
            print("\nShutting down Libra.")
            break
        except Exception as e:
            print(f"Error encountered: {e}")

if __name__ == "__main__":
    chat_loop()