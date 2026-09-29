import json
import pytest
from fastapi.testclient import TestClient
from src.api.server import app

client = TestClient(app)

def test_settings_get():
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)

def test_settings_post_partial():
    resp = client.post("/api/settings", json={"AI_PROVIDER": "custom"})
    assert resp.status_code in [200, 400]

def test_settings_prompts_reset():
    resp = client.post("/api/settings/prompts/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "success"
    assert "prompts" in data
    assert "SYSTEM_PROMPT_EXTRACTION" in data["prompts"]
    assert "SYSTEM_PROMPT_SCORING" in data["prompts"]
    assert "SYSTEM_PROMPT_EMAIL" in data["prompts"]

def test_linkedin_status_endpoint():
    resp = client.get("/api/linkedin-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data or "logged_in" in data

def test_export_data_endpoint():
    resp = client.get("/api/export-data")
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")

def test_state_endpoint_has_budget():
    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "today_sent_count" in data
    assert "daily_send_cap" in data
