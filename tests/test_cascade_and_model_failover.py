import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.scraper.query_builder import LinkedInQueryBuilder
from src.storage.db import DatabaseManager
from src.ai.gateway import AIGateway
from src.api.server import UniversalCareerProfile, analyze_career_profile_with_ai

class TestCascadeAndModelFailover(unittest.TestCase):

    def test_expand_role_synonyms_design(self):
        synonyms = LinkedInQueryBuilder.expand_role_synonyms("Product Designer")
        self.assertIn("Product Designer", synonyms)
        self.assertTrue(any("UX" in s or "UI" in s for s in synonyms))

    def test_expand_role_synonyms_engineering(self):
        synonyms = LinkedInQueryBuilder.expand_role_synonyms("Full Stack Developer")
        self.assertIn("Full Stack Developer", synonyms)
        self.assertTrue(any("Engineer" in s or "Software" in s for s in synonyms))

    def test_expand_role_synonyms_dynamic_custom(self):
        synonyms = LinkedInQueryBuilder.expand_role_synonyms("Senior Cloud Architect")
        self.assertTrue(len(synonyms) >= 1)
        self.assertIn("Senior Cloud Architect", synonyms)

    def test_build_posts_search_cascade(self):
        cascade = LinkedInQueryBuilder.build_posts_search_cascade(
            query_text="Product Designer",
            target_roles=["UI/UX Designer", "UX Designer"]
        )
        self.assertTrue(len(cascade) >= 4)
        labels = [c["label"] for c in cascade]
        self.assertTrue(any("Primary" in l for l in labels))
        self.assertTrue(any("Recent Date Shift" in l for l in labels))
        urls = [c["url"] for c in cascade]
        self.assertTrue(any("date_posted" in u for u in urls))

    def test_get_existing_job_hashes(self):
        test_db_path = str(ROOT_DIR / "data" / "test_cascade_apps.db")
        db = DatabaseManager(db_path=test_db_path)
        mock_job = [{
            "job_id": "test_post_999",
            "link": "https://www.linkedin.com/feed/update/urn:li:activity:999?query=1",
            "title": "Lead Product Designer",
            "company": "Figma",
            "author_name": "Dylan Field",
            "description": "We are looking for an exceptional Product Designer to join our core team."
        }]
        db.upsert_scraped_jobs(mock_job)
        hashes = db.get_existing_job_hashes()
        self.assertIn("test_post_999", hashes)
        self.assertIn("https://www.linkedin.com/feed/update/urn:li:activity:999", hashes)
        self.assertTrue(any("dylan field::we are looking" in h for h in hashes))
        if Path(test_db_path).exists():
            try:
                Path(test_db_path).unlink()
            except Exception:
                pass

    def test_gateway_model_failover_loop(self):
        gw = AIGateway(purpose="scoring")
        gw.base_url = "https://mock-gateway.com/v1"
        gw.api_key = "mock-key"
        gw.model = "fragile-model-primary"

        with patch.object(gw, "fetch_available_models", return_value=["fragile-model-primary", "backup-model-stable"]):
            def mock_post(url, headers=None, data=None, timeout=None):
                import json
                req_data = json.loads(data)
                if req_data.get("model") == "fragile-model-primary":
                    mock_resp = MagicMock()
                    mock_resp.status_code = 429
                    mock_resp.text = "Rate limit exceeded (429: Too many requests)"
                    return mock_resp
                else:
                    mock_resp = MagicMock()
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {
                        "choices": [{
                            "message": {
                                "content": '{"primary_role": "Product Designer", "target_roles": ["UX Designer"], "seniority": "Senior", "max_yoe": 5, "target_locations": ["Remote"], "domain_keywords": ["Figma"], "exclude_keywords": ["intern"]}'
                            }
                        }],
                        "usage": {"total_tokens": 120}
                    }
                    return mock_resp

            with patch("requests.post", side_effect=mock_post):
                result = gw.generate_structured_output("Test prompt", UniversalCareerProfile)
                self.assertIsNotNone(result)
                self.assertEqual(result.primary_role, "Product Designer")
                # Ensure model automatically failed over from fragile model
                self.assertNotEqual(gw.model, "fragile-model-primary")

if __name__ == "__main__":
    unittest.main()
