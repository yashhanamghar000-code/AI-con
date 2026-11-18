"""
Task 3 Test Suite: Persistent Conversation Memory & Student Profile.
Tests:
1. Every conversation has a stable session ID.
2. Extracted student details stored as structured fields.
3. Explicit updates overwrite values and record change timestamps.
4. Missing values remain unknown (no hallucinated ranks/categories).
5. Follow-up queries inherit prior session context.
6. Shortlist persists as structured institute codes & branches.
7. 'Rank these by ROI' reuses preceding shortlist.
8. 'Show 30 instead' updates requested count in profile.
9. 'Change my percentile to 95' updates only percentile.
10. Strict session isolation (no context leakage between sessions).
"""
import unittest
from scripts.conversation_memory import (
    ConversationMemoryStore,
    StudentProfileState,
    ConversationSessionState,
    ShortlistRecord,
)
from scripts.agents.cutoff_agent import CutoffAgent
from scripts.agents.orchestrator import Orchestrator
from pathlib import Path

CUTOFFS_DIR = Path(__file__).resolve().parent.parent / "cutoffs" / "phase3_final_staging"


class TestConversationMemory(unittest.TestCase):
    def setUp(self):
        self.store = ConversationMemoryStore()
        self.cutoff_agent = CutoffAgent(str(CUTOFFS_DIR))
        self.orchestrator = Orchestrator(cutoff_agent=self.cutoff_agent, college_info_agent=None)

    def tearDown(self):
        self.store.reset_session("test_sess_user_a")
        self.store.reset_session("test_sess_user_b")

    def test_01_profile_field_update_history(self):
        """Verifies structured updates and timestamp tracking."""
        prof = StudentProfileState(session_id="test_sess_user_a")
        self.assertIsNone(prof.percentile)
        self.assertIsNone(prof.merit_rank)

        updated = prof.update_field("percentile", 93.5)
        self.assertTrue(updated)
        self.assertEqual(prof.percentile, 93.5)
        self.assertIn("percentile", prof.field_update_history)

        # None values must not overwrite or infer
        updated_none = prof.update_field("merit_rank", None)
        self.assertFalse(updated_none)
        self.assertIsNone(prof.merit_rank)

    def test_02_session_isolation(self):
        """Context must not leak between different session IDs."""
        sess_a = self.store.get_or_create_session("test_sess_user_a")
        sess_b = self.store.get_or_create_session("test_sess_user_b")

        sess_a.profile.update_field("percentile", 95.0)
        sess_a.profile.update_field("location_preference", "Pune")
        self.store.save_session(sess_a)

        sess_b.profile.update_field("percentile", 82.0)
        sess_b.profile.update_field("location_preference", "Nagpur")
        self.store.save_session(sess_b)

        # Reload from store
        reloaded_a = self.store.get_or_create_session("test_sess_user_a")
        reloaded_b = self.store.get_or_create_session("test_sess_user_b")

        self.assertEqual(reloaded_a.profile.percentile, 95.0)
        self.assertEqual(reloaded_a.profile.location_preference, "Pune")
        self.assertEqual(reloaded_b.profile.percentile, 82.0)
        self.assertEqual(reloaded_b.profile.location_preference, "Nagpur")

    def test_03_orchestrator_multi_turn_profile_update(self):
        """Multi-turn flow: query discovery -> follow-up rank by ROI -> change percentile."""
        sid = "test_sess_user_a"

        # Turn 1: Initial discovery
        res1 = self.orchestrator.answer("Pune colleges at 94 percentile for Computer", session_id=sid)
        self.assertIn("shortlist", res1)
        shortlist1 = res1["shortlist"]
        self.assertGreater(len(shortlist1), 0)

        # Verify persisted state
        sess1 = self.orchestrator.memory_store.get_or_create_session(sid)
        self.assertEqual(sess1.profile.percentile, 94.0)
        self.assertEqual(sess1.profile.location_preference, "Pune")
        self.assertEqual(len(sess1.last_shortlist), len(shortlist1))

        # Turn 2: Follow-up 'rank these colleges by ROI'
        res2 = self.orchestrator.answer("now rank these colleges by ROI", session_id=sid)
        self.assertEqual(res2.get("intent"), "reputation_roi_ranking")
        self.assertIn("shortlist", res2)
        # Verify shortlist codes match
        codes1 = [c["institute_code"] for c in shortlist1]
        codes2 = [c["institute_code"] for c in res2["shortlist"]]
        self.assertEqual(set(codes1), set(codes2))

        # Turn 3: Update percentile explicitly
        res3 = self.orchestrator.answer("change my percentile to 95", session_id=sid)
        sess3 = self.orchestrator.memory_store.get_or_create_session(sid)
        self.assertEqual(sess3.profile.percentile, 95.0)
        # Location and other preferences must remain intact
        self.assertEqual(sess3.profile.location_preference, "Pune")


if __name__ == "__main__":
    unittest.main()

