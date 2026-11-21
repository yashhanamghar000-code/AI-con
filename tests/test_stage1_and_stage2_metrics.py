"""
Unit and Integration Tests for Stage 1 and Stage 2:
Master College Metrics Database, Unified CollegeMetricsService,
and Web Scraper Secondary Enrichment Engine.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from scripts.college_metrics_service import CollegeMetricsService
from scripts.popularity_service import PopularityRankingService
from scripts.roi_service import ROIService
from scripts.web_scraper import CollegeWebScraper, parse_fee_amount, parse_package_amount


class TestStage1And2Metrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics_svc = CollegeMetricsService.get_instance()
        cls.roi_svc = ROIService()
        cls.scraper = CollegeWebScraper(delay_secs=0.0)

    def test_01_master_metrics_database_loaded(self):
        """Master database must contain verified institutional profiles."""
        self.assertGreater(len(self.metrics_svc._metrics_cache), 20)
        viit = self.metrics_svc.get_metrics_for_code("06289")
        self.assertIsNotNone(viit)
        self.assertEqual(viit["short_name"], "VIIT Pune")
        self.assertIn("fee_data", viit)
        self.assertIn("placement_data", viit)

    def test_02_fee_and_placement_data_structure(self):
        """Institutes must provide normalized FeeData and PlacementData objects."""
        test_codes = ["06289", "06272", "06006", "03012", "06146"]
        for code in test_codes:
            fee_obj = self.metrics_svc.get_fee_data_object(code)
            plc_obj = self.metrics_svc.get_placement_data_object(code)

            self.assertGreater(fee_obj.amount, 10000.0)
            self.assertEqual(fee_obj.course_duration_years, 4)
            self.assertGreater(plc_obj.amount, 100000.0)
            self.assertIn(plc_obj.metric_type, ("median", "average"))
            self.assertEqual(plc_obj.verification_status, "verified_official")

    def test_03_roi_is_computable_for_all_metrics(self):
        """ROIService must compute verified proxy ratio without 'not_computable' failure."""
        test_codes = ["06289", "06272", "06006", "03012", "03209", "06139", "06155", "06274"]
        for code in test_codes:
            fee_obj = self.metrics_svc.get_fee_data_object(code)
            plc_obj = self.metrics_svc.get_placement_data_object(code)
            eval_res = self.roi_svc.compute_roi(fee_obj, plc_obj)

            self.assertTrue(eval_res.is_computable, f"ROI failed for {code}")
            self.assertEqual(eval_res.status, "computable")
            self.assertIsNotNone(eval_res.ratio_proxy)
            self.assertGreater(eval_res.ratio_proxy, 0.0)
            self.assertTrue(eval_res.display_summary.endswith("Tuition)"))

    def test_04_web_scraper_numerical_parsing(self):
        """Scraper numerical helpers must parse Indian currency expressions cleanly."""
        self.assertEqual(parse_fee_amount("₹ 1.72 Lakhs per year"), 172000.0)
        self.assertEqual(parse_fee_amount("1.15 L"), 115000.0)
        self.assertEqual(parse_fee_amount("Rs. 95,000/-"), 95000.0)
        self.assertEqual(parse_fee_amount("85000 p.a."), 85000.0)

        self.assertEqual(parse_package_amount("6.75 LPA"), 675000.0)
        self.assertEqual(parse_package_amount("Average Package: ₹ 12.0 Lakhs"), 1200000.0)
        self.assertEqual(parse_package_amount("550000 CTC"), 550000.0)

    def test_05_web_scraper_enrichment_integration(self):
        """Scraper must enrich missing fees and packages using master metrics without altering cutoffs."""
        raw_college = {
            "institute_code": "06272",
            "institute_name": "Dr. D. Y. Patil Pratishthan's D.Y.Patil College of Engineering Akurdi, Pune",
            "cutoff_percentile": 97.6037124,
            "closing_rank": 7164,
        }

        enriched = self.scraper.enrich_missing_fields_safely(
            raw_college, target_fields=["annual_fee", "avg_package", "naac_grade"]
        )

        self.assertEqual(enriched["cutoff_percentile"], 97.6037124)
        self.assertEqual(enriched["closing_rank"], 7164)
        self.assertAlmostEqual(float(enriched["annual_fee"]), 138000.0, places=-2)
        self.assertAlmostEqual(float(enriched["avg_package"]), 620000.0, places=-2)
        self.assertEqual(enriched["naac_grade"], "A")

    def test_06_popularity_signals_populated_cleanly(self):
        """Popularity ranking service evaluates scores when populated from metrics service."""
        pop_svc = PopularityRankingService()
        self.metrics_svc.populate_popularity_signals_to_service(pop_svc)

        ev = pop_svc.evaluate_college(institute_code="06289", institute_name="VIIT Pune")
        self.assertTrue(ev.is_available)
        self.assertIsNotNone(ev.popularity_score)
        self.assertGreater(ev.popularity_score, 50.0)


if __name__ == "__main__":
    unittest.main()
