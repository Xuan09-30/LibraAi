import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.media_controller import MediaController
from tools.spotify_agent import SpotifyAgent
from tools.places_engine import PlacesDiscoveryEngine
from core.orchestrator import SupervisorHub
from core.llm import LocalLLM
from core.audio_capture import AudioDucker


class TestLiveTranscriptFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = LocalLLM()
        cls.hub = SupervisorHub(cls.llm)
        cls.places = PlacesDiscoveryEngine()

    def test_01_media_controller_methods(self):
        """Test 1: Verify MediaController and SpotifyAgent have pause, resume, play, stop."""
        mc = MediaController()
        res_pause = mc.pause(dry_run=True)
        self.assertEqual(res_pause["status"], "success")
        self.assertEqual(res_pause["action"], "pause")

        res_resume = mc.resume(dry_run=True)
        self.assertEqual(res_resume["status"], "success")
        self.assertEqual(res_resume["action"], "resume")

        res_stop = mc.stop(dry_run=True)
        self.assertEqual(res_stop["status"], "success")
        self.assertEqual(res_stop["action"], "stop")

        res_play = mc.play(dry_run=True)
        self.assertEqual(res_play["status"], "success")

        sp = SpotifyAgent()
        self.assertEqual(sp.pause(dry_run=True)["status"], "success")
        self.assertEqual(sp.resume(dry_run=True)["status"], "success")
        self.assertEqual(sp.stop(dry_run=True)["status"], "success")

    def test_02_orchestrator_media_pause(self):
        """Test 2: Orchestrator executing media_action pause does not raise AttributeError."""
        res = self.hub._execute_cached_tool("media_action", {"sub_action": "pause"}, dry_run=True)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("action"), "pause")

        # Also test via plan_or_execute
        res2 = self.hub.plan_or_execute("can you pause the music for me?", dry_run=True)
        self.assertIn(res2.get("action"), ["pause", "media_action"])

    def test_03_screen_button_click_routing(self):
        """Test 3: Screen button click query must NOT be routed as app launch."""
        query = "do you see there's a green launch button on my screen? Can you help me to click it?"
        plan = self.llm.plan(query, dry_run=True)
        self.assertNotEqual(plan.get("action"), "open_app", "Click button on screen misrouted as app launch!")
        self.assertEqual(plan.get("action"), "gui_action", f"Expected gui_action, got {plan.get('action')}")
        self.assertEqual(plan.get("args", {}).get("sub_action"), "click_mark")
        target = plan.get("args", {}).get("target", "").lower()
        self.assertIn("green launch button", target)

    def test_04_explicit_browser_searches(self):
        """Test 4: Google and YouTube search queries must open browser without Wikipedia override."""
        # Query 1: "I want you to search YouTube for me."
        q1 = "I want you to search YouTube for me."
        p1 = self.llm.plan(q1, dry_run=True)
        self.assertEqual(p1.get("action"), "web_search")

        # Query 2: "can you google search YouTube for me?"
        q2 = "can you google search YouTube for me?"
        p2 = self.llm.plan(q2, dry_run=True)
        self.assertEqual(p2.get("action"), "web_search")
        self.assertEqual(p2.get("args", {}).get("platform"), "google")
        self.assertIn("Google", p2.get("voice_response", ""))

    def test_05_nearby_places_and_mcdonalds(self):
        """Test 5: Nearby places and fast-food queries route to places_search with local results."""
        # Simulate last_entity as Tokyo
        self.llm.session_state["last_entity"] = "Tokyo"

        # Query 1: "Can you search out the nearest restaurant near my house like a few of them?"
        q1 = "Can you search out the nearest restaurant near my house like a few of them?"
        p1 = self.llm.plan(q1, dry_run=True)
        self.assertEqual(p1.get("action"), "places_search", f"Expected places_search, got {p1.get('action')}")
        self.assertNotIn("Tokyo", p1.get("place_type", ""))

        # Query 2: "Can you find me some McDonald's near my house"
        q2 = "Can you find me some McDonald's near my house"
        p2 = self.llm.plan(q2, dry_run=True)
        self.assertEqual(p2.get("action"), "places_search")
        self.assertEqual(p2.get("place_type"), "mcdonalds")
        places = p2.get("places", [])
        self.assertTrue(len(places) > 0, "No McDonald's places found!")
        self.assertTrue(any("Kepong" in p["name"] or "Menjalara" in p["name"] for p in places))

    def test_06_contextual_folder_pronoun_resolution(self):
        """Test 6: Pronoun resolution for folders opens the cached folder, not 'that folder'."""
        # Step 1: User asks to find / open a folder
        self.llm.last_context["folder"] = r"C:\Users\chenx\Desktop\LibraTest"
        self.llm.file_mgr.last_folder_path = r"C:\Users\chenx\Desktop\LibraTest"
        self.llm.file_mgr.last_folder_name = "LibraTest"

        # Step 2: User says "Yeah, open it, please"
        q = "Yeah, open it, please"
        plan = self.llm.plan(q, dry_run=True)
        self.assertEqual(plan.get("action"), "open_folder")
        folder_arg = plan.get("args", {}).get("folder")
        self.assertNotEqual(folder_arg, "that folder", "Folder target was literally 'that folder'!")
        self.assertIn("LibraTest", str(folder_arg))

    def test_07_clipboard_inspection(self):
        """Test 7: 'can you see my clipboard' reads clipboard without triggering code debug explanation."""
        self.llm.clipboard_agent.set_clipboard("https://github.com/project-libra/core")
        q = "can you see my clipboard and what is I'm copying right now?"
        plan = self.llm.plan(q, dry_run=True)
        self.assertEqual(plan.get("action"), "clipboard_assist")
        self.assertEqual(plan.get("sub_action"), "clipboard_read")
        voice = plan.get("voice_response", "")
        self.assertIn("clipboard contains", voice.lower())
        self.assertIn("https://github.com/project-libra/core", voice)

    def test_08_audio_ducker_sanity(self):
        """Test 8: AudioDucker methods execute safely without COM thread errors."""
        ducker = AudioDucker()
        ducked = ducker.duck_background_audio(target_level=0.15)
        self.assertIsInstance(ducked, int)
        restored = ducker.restore_background_audio()
        self.assertIsInstance(restored, int)


if __name__ == "__main__":
    unittest.main()
