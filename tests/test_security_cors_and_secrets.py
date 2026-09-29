import os
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api.server import (
    app,
    is_masked_secret,
    get_masked_settings,
    save_env_dict,
    load_env_dict,
    ENV_PATH,
    MASKED_SECRET_PLACEHOLDER,
    SENSITIVE_ENV_KEYS,
)


class TestSecurityCorsAndSecrets(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.orig_env_content = ""
        if ENV_PATH.exists():
            self.orig_env_content = ENV_PATH.read_text(encoding="utf-8")

    def tearDown(self):
        if self.orig_env_content:
            ENV_PATH.write_text(self.orig_env_content, encoding="utf-8")

    def test_is_masked_secret_detection(self):
        self.assertTrue(is_masked_secret(MASKED_SECRET_PLACEHOLDER))
        self.assertTrue(is_masked_secret("••••••••••••"))
        self.assertTrue(is_masked_secret("********"))
        self.assertTrue(is_masked_secret("__MASKED__"))
        self.assertTrue(is_masked_secret("••••••••"))

        self.assertFalse(is_masked_secret(""))
        self.assertFalse(is_masked_secret(None))
        self.assertFalse(is_masked_secret("my-super-secret-password-123"))
        self.assertFalse(is_masked_secret("my-test-api-token-placeholder-string"))

    def test_get_masked_settings_masks_sensitive_keys(self):
        with patch("src.api.server.load_env_dict", return_value={
            "SMTP_PASSWORD": "actual_smtp_password",
            "AI_API_KEY": "actual_ai_api_key",
            "OPENAI_API_KEY": "actual_openai_key",
            "LINKEDIN_LI_AT": "actual_linkedin_cookie",
            "CUSTOM_API_KEY": "custom_secret_key",
            "SENDER_NAME": "Public User",
            "AI_PROVIDER": "custom",
            "AI_MODEL": "gemini-2.0-flash",
        }):
            masked = get_masked_settings()
            self.assertEqual(masked["SMTP_PASSWORD"], MASKED_SECRET_PLACEHOLDER)
            self.assertEqual(masked["AI_API_KEY"], MASKED_SECRET_PLACEHOLDER)
            self.assertEqual(masked["OPENAI_API_KEY"], MASKED_SECRET_PLACEHOLDER)
            self.assertEqual(masked["LINKEDIN_LI_AT"], MASKED_SECRET_PLACEHOLDER)
            self.assertEqual(masked["CUSTOM_API_KEY"], MASKED_SECRET_PLACEHOLDER)
            self.assertEqual(masked["SENDER_NAME"], "Public User")
            self.assertEqual(masked["AI_PROVIDER"], "custom")
            self.assertEqual(masked["AI_MODEL"], "gemini-2.0-flash")

    def test_get_settings_endpoint_returns_masked_data(self):
        with patch("src.api.server.load_env_dict", return_value={
            "SMTP_PASSWORD": "super_secret_smtp",
            "AI_API_KEY": "super_secret_ai_key",
            "SENDER_NAME": "Test Sender",
        }):
            resp = self.client.get("/api/settings")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["SMTP_PASSWORD"], MASKED_SECRET_PLACEHOLDER)
            self.assertEqual(data["AI_API_KEY"], MASKED_SECRET_PLACEHOLDER)
            self.assertEqual(data["SENDER_NAME"], "Test Sender")

    def test_post_settings_preserves_masked_secrets(self):
        test_env_data = {
            "SMTP_PASSWORD": "original_smtp_secret",
            "AI_API_KEY": "original_ai_secret",
            "SENDER_NAME": "Old Name",
        }
        with patch("src.api.server.load_env_dict", return_value=test_env_data.copy()), \
             patch("builtins.open", unittest.mock.mock_open()) as mock_file:
            # User submits masked placeholders back with an updated SENDER_NAME
            payload = {
                "SMTP_PASSWORD": MASKED_SECRET_PLACEHOLDER,
                "AI_API_KEY": MASKED_SECRET_PLACEHOLDER,
                "SENDER_NAME": "New Name",
            }
            resp = self.client.post("/api/settings", json=payload)
            self.assertEqual(resp.status_code, 200)

            # Check what was written: original secrets must remain intact!
            written_content = "".join(call.args[0] for call in mock_file().write.call_args_list)
            self.assertIn("original_smtp_secret", written_content)
            self.assertIn("original_ai_secret", written_content)
            self.assertIn("New Name", written_content)
            self.assertNotIn(MASKED_SECRET_PLACEHOLDER, written_content)

    def test_post_settings_updates_when_real_secret_provided(self):
        test_env_data = {
            "SMTP_PASSWORD": "old_password",
            "AI_API_KEY": "old_ai_key",
        }
        with patch("src.api.server.load_env_dict", return_value=test_env_data.copy()), \
             patch("builtins.open", unittest.mock.mock_open()) as mock_file:
            payload = {
                "SMTP_PASSWORD": "new_password_1234",
            }
            resp = self.client.post("/api/settings", json=payload)
            self.assertEqual(resp.status_code, 200)
            written_content = "".join(call.args[0] for call in mock_file().write.call_args_list)
            self.assertIn("new_password_1234", written_content)

    def test_cors_origin_whitelist(self):
        # Localhost / 127.0.0.1 should have Access-Control-Allow-Origin header
        resp_local = self.client.get("/api/state", headers={"Origin": "http://127.0.0.1:8000"})
        self.assertEqual(resp_local.headers.get("access-control-allow-origin"), "http://127.0.0.1:8000")

        resp_local_name = self.client.get("/api/state", headers={"Origin": "http://localhost:8000"})
        self.assertEqual(resp_local_name.headers.get("access-control-allow-origin"), "http://localhost:8000")

        # Untrusted origin should NOT be allowed
        resp_malicious = self.client.get("/api/state", headers={"Origin": "https://malicious-attacker.com"})
        self.assertNotIn("access-control-allow-origin", resp_malicious.headers)
        self.assertNotEqual(resp_malicious.headers.get("access-control-allow-origin"), "*")


if __name__ == "__main__":
    unittest.main()
