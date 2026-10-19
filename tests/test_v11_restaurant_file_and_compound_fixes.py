import unittest
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.llm import LocalLLM
from core.orchestrator import SupervisorHub
from tools.file_manager import FileManager
from tools.places_engine import PlacesDiscoveryEngine


class TestV11RestaurantFileAndCompoundFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = LocalLLM()
        cls.supervisor = SupervisorHub(llm=cls.llm)

    def setUp(self):
        self.llm.session_state = {
            "active_apps": [],
            "last_action": None,
            "last_target": None,
            "pending_action": None,
            "pending_args": None,
        }
        self.llm.last_context = {
            "city": None,
            "app": None,
            "folder": None,
            "file": None
        }
        self.llm.session_mgr.clear_candidates()

    # -------------------------------------------------------------------------
    # 1. TIMEZONE OBJECTION REGEX & NO FALSE POSITIVES ("house", "just")
    # -------------------------------------------------------------------------
    def test_timezone_no_false_positive_on_house_or_just(self):
        """Verify queries containing 'house' or 'just' never trigger timezone objections."""
        # Query A: "Hey Libra, no I mean like can you find me like one or two or three options of the nearest restaurant near my house?"
        q_restaurant = "Hey Libra, no I mean like can you find me like one or two or three options of the nearest restaurant near my house?"
        plan_res = self.llm.plan(q_restaurant, dry_run=True)
        self.assertEqual(plan_res.get("action"), "places_search", f"Expected places_search but got {plan_res.get('action')}")
        self.assertNotIn("united states is not in the same time zone", plan_res.get("voice_response", "").lower())

        # Query B: "Hey Libra, no I mean the test.py file that you just created not long ago."
        self.llm.last_context["file"] = "C:\\Users\\chenx\\Desktop\\test.py"
        self.llm.session_state["last_action"] = "create_file"
        q_file = "Hey Libra, no I mean the test.py file that you just created not long ago."
        plan_file = self.llm.plan(q_file, dry_run=True)
        self.assertEqual(plan_file.get("action"), "open_file", f"Expected open_file but got {plan_file.get('action')}")
        self.assertNotIn("united states is not in the same time zone", plan_file.get("voice_response", "").lower())

    def test_timezone_legitimate_objection(self):
        """Verify legitimate US/Malaysia timezone objections correctly trigger timezone clarification."""
        q_tz = "Hey Libra, no I mean I'm in Malaysia and the time in the US is same as mine, are you sure?"
        plan_tz = self.llm.plan(q_tz, dry_run=True)
        self.assertEqual(plan_tz.get("action"), "world_time")
        self.assertIn("united states is not in the same time zone", plan_tz.get("voice_response", "").lower())
        self.assertIn("utc+8", plan_tz.get("voice_response", "").lower())

    def test_world_time_queries(self):
        """Verify time queries for specific cities like Arizona and Qatar."""
        plan_arizona = self.llm.plan("what's the time now in the US, Arizona?", dry_run=True)
        self.assertEqual(plan_arizona.get("action"), "world_time")
        self.assertIn("Arizona", plan_arizona.get("voice_response", ""))

        plan_qatar = self.llm.plan("what's the time now in Qatar?", dry_run=True)
        self.assertEqual(plan_qatar.get("action"), "world_time")
        self.assertIn("Qatar", plan_qatar.get("voice_response", ""))

    # -------------------------------------------------------------------------
    # 2. LOCAL RESTAURANT POI SEARCH & REVIEW INQUIRY
    # -------------------------------------------------------------------------
    def test_restaurant_discovery_near_house(self):
        """Verify 'nearest restaurant near my house' triggers places_search and populates candidates."""
        q = "Okay now can you find me the nearest restaurant near my house?"
        plan = self.llm.plan(q, dry_run=True)
        self.assertEqual(plan.get("action"), "places_search")
        candidates = plan.get("candidates", [])
        self.assertGreaterEqual(len(candidates), 2)
        # Check that local eateries (e.g. Ayam Gepuk or Kepong restaurants) are present
        names = [c.get("name") for c in candidates]
        self.assertTrue(any("Ayam Gepuk" in n or "Kepong" in n for n in names))

    def test_restaurant_review_follow_up(self):
        """Verify follow-up inquiries like 'tell me about the first one' return details and reviews."""
        # First trigger places search
        self.llm.plan("find restaurants near my house", dry_run=True)
        self.assertGreaterEqual(len(self.llm.session_mgr.candidates), 1)

        # Follow-up: "tell me about the first one"
        detail_plan = self.llm.plan("can you tell me about the first one?", dry_run=True)
        self.assertEqual(detail_plan.get("action"), "place_detail")
        self.assertIn("stars", detail_plan.get("voice_response", "").lower())

    # -------------------------------------------------------------------------
    # 3. FILE CREATION, EDITING & OPENING
    # -------------------------------------------------------------------------
    def test_file_create_edit_open_lifecycle(self):
        """Verify complete file creation, variable update, and file opening pipeline."""
        # 1. Create file: "create a Python file called test and I want you to write a simple declare variable inside the test.python"
        q_create = "Hey Libra, so I want you to create a Python file called test and I want you to write a simple declare variable inside the test.python."
        plan_create = self.llm.plan(q_create, dry_run=True)
        self.assertEqual(plan_create.get("action"), "create_file")
        self.assertEqual(plan_create.get("args", {}).get("file_name"), "test.py")
        self.assertEqual(self.llm.session_state.get("last_action"), "create_file")
        self.assertIn("test.py", self.llm.last_context.get("file", ""))

        # 2. Edit file: "We can put an integer variable called x and x is equal to 10."
        q_edit = "We can put an integer variable called x and x is equal to 10."
        plan_edit = self.llm.plan(q_edit, dry_run=True)
        self.assertEqual(plan_edit.get("action"), "write_file")
        self.assertIn("x", plan_edit.get("voice_response", ""))
        self.assertEqual(self.llm.session_state.get("last_action"), "write_file")

        # 3. Open file: "since you created that file, can you open it for me to see?"
        q_open = "since you created that file, can you open it for me to see?"
        plan_open = self.llm.plan(q_open, dry_run=True)
        self.assertEqual(plan_open.get("action"), "open_file")
        self.assertIn("test.py", plan_open.get("voice_response", ""))

    def test_file_manager_direct_methods(self):
        """Verify FileManager sanitize, create, write, and open directly."""
        fm = FileManager()
        clean_name = fm.sanitize_file_name("test.python")
        self.assertEqual(clean_name, "test.py")

        # Test dry-run creation
        create_res = fm.create_file("unit_test_demo.py", content="print('hello')", dry_run=True)
        self.assertEqual(create_res.get("status"), "created")
        self.assertEqual(fm.last_file_name, "unit_test_demo.py")

        # Test dry-run open
        open_res = fm.open_file("unit_test_demo.py", dry_run=True)
        self.assertEqual(open_res.get("status"), "opened")

    # -------------------------------------------------------------------------
    # 4. COMPOUND REQUESTS & CONCURRENT QUERIES
    # -------------------------------------------------------------------------
    def test_compound_time_and_weather(self):
        """Verify 'what about the time here and also can you tell me about the weather for today?' executes both."""
        q = "what about the time here and also can you tell me about the weather for today?"
        sub_steps = self.supervisor.split_compound_intent(q)
        self.assertEqual(len(sub_steps), 2, f"Expected 2 steps but got {sub_steps}")

        plan = self.supervisor.plan(q)
        self.assertTrue(plan.get("compound"))
        self.assertEqual(len(plan.get("actions", [])), 2)
        self.assertIn("world_time", plan.get("actions", []))
        self.assertIn("weather", plan.get("actions", []))

    def test_compound_web_search_preserved(self):
        """Verify 'open my Google and search YouTube' is preserved as web_search."""
        q = "open my Google and search YouTube"
        sub_steps = self.supervisor.split_compound_intent(q)
        self.assertEqual(len(sub_steps), 1)

        plan = self.llm.plan(q, dry_run=True)
        self.assertEqual(plan.get("action"), "web_search")


if __name__ == "__main__":
    unittest.main()
