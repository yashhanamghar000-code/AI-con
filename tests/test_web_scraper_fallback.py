"""
Unit and regression tests for Task 15: Web Scraper Fallback and Source Verification.
Tests field provenance tracking, cache TTL expiry, protection of authoritative cutoffs,
and strict fallback-only behavior.
"""
import time
import unittest
from scripts.web_scraper import CollegeWebScraper, ScrapedField, ScraperCache


class TestWebScraperFallback(unittest.TestCase):
    def setUp(self):
        self.scraper = CollegeWebScraper(delay_secs=0.0)

    def test_01_scraped_field_provenance(self):
        """ScrapedField must record source URL, timestamp, publisher, year, scope, and verification status."""
        field = ScrapedField(
            field_name="naac_grade",
            value="A++",
            source_url="https://shiksha.com/example",
            publisher="Shiksha",
            academic_or_placement_year="2024-25",
            verification_status="secondary_unverified",
            field_scope="college_level",
        )
        d = field.to_dict()
        self.assertEqual(d["field_name"], "naac_grade")
        self.assertEqual(d["value"], "A++")
        self.assertEqual(d["source_url"], "https://shiksha.com/example")
        self.assertEqual(d["verification_status"], "secondary_unverified")
        self.assertIn("retrieval_timestamp", d)

    def test_02_scraper_cache_ttl(self):
        """ScraperCache must return cached values before expiry and evict after TTL."""
        cache = ScraperCache(ttl_seconds=1)  # 1 second TTL
        cache.set("06006_COEP", {"naac_grade_scraped": "A+"})

        self.assertIsNotNone(cache.get("06006_COEP"))
        time.sleep(1.2)  # Wait past TTL
        self.assertIsNone(cache.get("06006_COEP"))

    def test_03_no_overwriting_authoritative_cutoffs(self):
        """Scraper fallback must NEVER overwrite official closing cutoffs or institute codes."""
        authoritative = {
            "institute_code": "06006",
            "institute_name": "COEP Technological University",
            "cutoff_percentile": 99.85,
            "closing_rank": 120,
        }

        # Mock cache with synthetic scraped data attempting to overwrite cutoffs
        self.scraper.cache.set("06006_COEP Technological University", {
            "cutoff_percentile": 80.0,
            "closing_rank": 9999,
            "naac_grade_scraped": "A++",
        })

        enriched = self.scraper.enrich_missing_fields_safely(
            authoritative,
            target_fields=["cutoff_percentile", "closing_rank", "naac_grade"]
        )

        # Official cutoffs must remain 100% intact!
        self.assertEqual(enriched["cutoff_percentile"], 99.85)
        self.assertEqual(enriched["closing_rank"], 120)
        self.assertEqual(enriched["institute_code"], "06006")
        # Missing non-cutoff field was enriched with provenance
        self.assertEqual(enriched["naac_grade"], "A++")
        self.assertIn("naac_grade", enriched["scraped_provenance"])
        self.assertEqual(enriched["scraped_provenance"]["naac_grade"]["verification_status"], "secondary_unverified")

    def test_04_fallback_only_for_missing_fields(self):
        """Fields already present in the college record are not overwritten."""
        record = {
            "institute_code": "01002",
            "institute_name": "Government College of Engineering, Amravati",
            "affiliation": "Sant Gadge Baba Amravati University (Official Master Record)",
        }
        self.scraper.cache.set("01002_Government College of Engineering, Amravati", {
            "affiliation_scraped": "Different Unverified University",
            "naac_grade_scraped": "A",
        })

        enriched = self.scraper.enrich_missing_fields_safely(record, target_fields=["affiliation", "naac_grade"])
        # Existing authoritative affiliation preserved!
        self.assertEqual(enriched["affiliation"], "Sant Gadge Baba Amravati University (Official Master Record)")
        # Missing NAAC enriched
        self.assertEqual(enriched["naac_grade"], "A")


if __name__ == "__main__":
    unittest.main()
