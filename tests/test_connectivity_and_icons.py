import json
import re
import os
import pytest
from fastapi.testclient import TestClient
from src.api.server import app

client = TestClient(app)

def test_api_state_send_quota():
    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "today_sent_count" in data
    assert "daily_send_cap" in data
    assert isinstance(data["today_sent_count"], int)
    assert isinstance(data["daily_send_cap"], int)

def test_api_analytics_adaptive_trend():
    for p in ["30d", "90d", "ytd", "all"]:
        resp = client.get(f"/api/analytics?period={p}")
        assert resp.status_code == 200
        data = resp.json()
        assert "trend_label" in data
        assert "daily_trend" in data
        assert isinstance(data["recent"], list)

def test_api_analytics_export_csv():
    resp = client.get("/api/analytics/export?period=30d")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    content = resp.text
    assert "ID,Job ID,Position,Company,Location,Recruiter,Contact Email,Match Score,ATS Score,Status,Created At,Updated At,Post URL" in content

def test_api_application_status_patch():
    # Attempt patching a test id
    resp = client.patch("/api/applications/999999/status", json={"status": "Interviewing"})
    assert resp.status_code in [200, 404]

def test_api_settings_prompts_reset():
    resp = client.post("/api/settings/prompts/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "success"
    assert "prompts" in data
    prompts = data["prompts"]
    assert "SYSTEM_PROMPT_EXTRACTION" in prompts
    assert "SYSTEM_PROMPT_SCORING" in prompts
    assert "SYSTEM_PROMPT_EMAIL" in prompts

def test_template_icons_validity():
    """Verify that updated template icons resolve in xicons.js without orphan icons."""
    xicons_path = os.path.join("tool", "frontend", "static", "xicons.js")
    with open(xicons_path, "r", encoding="utf-8") as f:
        xicons_code = f.read()

    # Required icons added/verified in Phase 2
    for icon in ["database", "calculate-1", "check_circle_3", "share_2", "files", "chat_dots", "chat_check", "file_edit"]:
        assert f'"{icon}":' in xicons_code, f"Icon {icon} must be mapped in xicons.js"
