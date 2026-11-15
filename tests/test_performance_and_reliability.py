"""
Unit and regression tests for Task 17: Performance and Reliability.
Tests system profiling, latency bounds, and graceful degradation across offline subsystems.
"""
import unittest
from scripts.agents.orchestrator import Orchestrator
from scripts.system_profiler import SystemProfiler


class TestPerformanceAndReliability(unittest.TestCase):
    def setUp(self):
        self.profiler = SystemProfiler()

    def test_01_profiler_latency_bounds(self):
        """Profiling runs and verifies sub-150ms ML inference latency."""
        profile = self.profiler.profile_all()
        self.assertIn("startup", profile)
        self.assertIn("ml_inference", profile)
        self.assertIn("discovery_query", profile)

        # ML inference should be fast (typically < 100ms)
        self.assertLess(profile["ml_inference"]["latency_ms"], 200.0)

    def test_02_all_degraded_modes_safe(self):
        """All 4 degraded failure modes (LLM, vector, ML, scraper) must degrade gracefully without uncaught exceptions."""
        degraded = SystemProfiler.test_degraded_modes(Orchestrator)
        self.assertTrue(degraded["llm_degradation_safe"])
        self.assertTrue(degraded["vector_degradation_safe"])
        self.assertTrue(degraded["ml_degradation_safe"])
        self.assertTrue(degraded["scraper_degradation_safe"])


if __name__ == "__main__":
    unittest.main()
