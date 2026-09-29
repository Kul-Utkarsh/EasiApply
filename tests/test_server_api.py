import unittest
from fastapi.testclient import TestClient
from src.api.server import app, SCRAPE_STATE

class TestServerEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_state_endpoint_fields(self):
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("server_instance_id", data)
        self.assertIn("session_scraped_count", data)

    def test_scrape_request_default_empty_keywords(self):
        # Verify ScrapeRequest model defaults to empty keywords
        from src.api.server import ScrapeRequest
        req = ScrapeRequest()
        self.assertEqual(req.keywords, "")

    def test_shutdown_endpoint(self):
        response = self.client.post("/api/shutdown")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "shutting_down")

    def test_clear_logs_endpoint(self):
        from src.api.server import ACTIVITY_LOGS, add_log
        add_log("TEST", "Test log entry")
        self.assertGreater(len(ACTIVITY_LOGS), 0)
        response = self.client.post("/api/logs/clear")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")
        self.assertEqual(len(ACTIVITY_LOGS), 0)

if __name__ == "__main__":
    unittest.main()
