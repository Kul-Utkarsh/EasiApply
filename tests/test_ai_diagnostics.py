import sys
sys.path.insert(0, ".")
from unittest.mock import patch, MagicMock
from src.api.server import (
    TestAIRequest, TestPromptRequest,
    _run_micro_inference, test_ai, test_ai_prompt
)

# This file is a standalone script (run: python tests/test_ai_diagnostics.py),
# not a pytest module. The imported endpoint functions/models have test-like
# names, so stop pytest from collecting them as tests.
for _n in ("test_ai", "test_ai_prompt", "TestAIRequest", "TestPromptRequest"):
    globals()[_n].__test__ = False
del _n

# 1. Test Model Schema Validation
req1 = TestAIRequest(
    baseUrl="http://localhost:8000/v1",
    apiKey="test-key",
    model="gpt-4o-mini",
    model_scoring="claude-3-5-sonnet",
    model_drafts="deepseek-r1"
)
assert req1.model == "gpt-4o-mini"
assert req1.model_scoring == "claude-3-5-sonnet"
assert req1.model_drafts == "deepseek-r1"

# 2. Test _run_micro_inference with mock success
mock_resp = MagicMock()
mock_resp.status_code = 200
mock_resp.json.return_value = {
    "choices": [{"message": {"content": "Online gpt-4o-mini active."}}],
    "usage": {"total_tokens": 12}
}

with patch("requests.post", return_value=mock_resp):
    rep = _run_micro_inference("http://mock-ai/v1", "key", "gpt-4o-mini", "Main Model")
    assert rep["status"] == "ok"
    assert rep["reply"] == "Online gpt-4o-mini active."
    assert rep["tokens"] == 12
    assert rep["latency_ms"] >= 0

# 3. Test _run_micro_inference with mock error (HTTP 404 Model Not Found)
mock_err_resp = MagicMock()
mock_err_resp.status_code = 404
mock_err_resp.json.return_value = {"error": {"message": "Model 'deepseek-xyz' does not exist"}}
mock_err_resp.text = "Model not found"

with patch("requests.post", return_value=mock_err_resp):
    err_rep = _run_micro_inference("http://mock-ai/v1", "key", "deepseek-xyz", "Drafts Model")
    assert err_rep["status"] == "error"
    assert "does not exist" in err_rep["error"]

# 4. Test multi-model test_ai endpoint
def mock_post_dispatcher(url, headers, json, timeout):
    m_id = json.get("model")
    m = MagicMock()
    if m_id == "claude-3-5-sonnet":
        m.status_code = 200
        m.json.return_value = {"choices": [{"message": {"content": "Claude active."}}], "usage": {"total_tokens": 8}}
    elif m_id == "gpt-4o-mini":
        m.status_code = 200
        m.json.return_value = {"choices": [{"message": {"content": "GPT active."}}], "usage": {"total_tokens": 7}}
    else:
        m.status_code = 404
        m.json.return_value = {"error": {"message": "Unknown model"}}
    return m

mock_get = MagicMock()
mock_get.status_code = 200

with patch("requests.get", return_value=mock_get), patch("requests.post", side_effect=mock_post_dispatcher), patch("src.api.server.save_env_dict"):
    res = test_ai(req1)
    assert res["status"] == "success"
    assert len(res["models"]) == 3
    # Check that each model has an entry
    purposes = [m["purpose"] for m in res["models"]]
    assert "Main Model" in purposes
    assert "Scoring Model" in purposes
    assert "Drafts Model" in purposes

# 5. Test test_ai_prompt endpoint
prompt_req = TestPromptRequest(
    baseUrl="http://mock-ai/v1",
    apiKey="test-key",
    model_id="gpt-4o-mini",
    prompt="Say hi"
)
with patch("requests.post", return_value=mock_resp):
    prompt_res = test_ai_prompt(prompt_req)
    assert prompt_res["status"] == "success"
    assert prompt_res["reply"] == "Online gpt-4o-mini active."

print("SUCCESS: ALL AI DIAGNOSTICS TESTS PASSED!")
