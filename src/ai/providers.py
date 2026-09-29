"""Provider-agnostic AI configuration for EasiApply.

Any OpenAI-compatible endpoint works (Omniroute, OpenAI, OpenRouter,
Ollama, LocalAI, custom gateways) — the provider is just a named preset
for base URL + key requirements. Legacy OMNIROUTE_*/CLAUDE_MODEL env vars
keep working as fallbacks so existing installs don't break.

Also hosts the process-wide AI usage meter (tokens, latency, errors).
"""
import os
import time
from typing import Any, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

PROVIDER_PRESETS: Dict[str, Dict[str, Any]] = {
    "omniroute": {
        "label": "OmniRoute Gateway",
        "base_url": "http://localhost:8080/v1",
        "default_model": "claude-sonnet-5",
        "requires_key": True,
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "requires_key": True,
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-3.5-sonnet",
        "requires_key": True,
    },
    "ollama": {
        "label": "Ollama (local)",
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.1",
        "requires_key": False,
    },
    "custom": {
        "label": "Custom / Self-hosted",
        "base_url": "",
        "default_model": "",
        "requires_key": False,
    },
}

DEFAULT_PROVIDER = "custom"

# Rough per-1M-token prices (USD in/out) for the meter's cost *estimate*.
# Missing entries report tokens only.
PRICE_MAP = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
}


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def resolve_ai_config(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Merge canonical AI_* keys with legacy fallbacks into one config dict."""
    e = env or {}
    def get(canonical: str, *legacy: str, default: str = "") -> str:
        for key in (canonical, *legacy):
            val = e.get(key, "") if e else ""
            if not val:
                val = _env(key)
            if val:
                return val.strip()
        return default

    provider = get("AI_PROVIDER", default=DEFAULT_PROVIDER).lower() or DEFAULT_PROVIDER
    if provider not in PROVIDER_PRESETS:
        provider = "custom"
    preset = PROVIDER_PRESETS[provider]

    legacy_base = _env("OMNIROUTE_BASE_URL")
    base_url = get("AI_BASE_URL") or legacy_base or preset["base_url"]
    api_key = get("AI_API_KEY") or _env("OMNIROUTE_API_KEY")
    model = get("AI_MODEL") or _env("CLAUDE_MODEL") or preset["default_model"]

    return {
        "provider": provider,
        "provider_label": preset["label"],
        "base_url": base_url.rstrip("/"),
        "api_key": api_key,
        "model": model,
        # Per-feature overrides fall back to the main model.
        "model_scoring": get("AI_MODEL_SCORING") or model,
        "model_drafts": get("AI_MODEL_DRAFTS") or model,
        "requires_key": preset["requires_key"],
        "configured": bool(base_url and (api_key or not preset["requires_key"])),
    }


def model_for_purpose(cfg: Dict[str, Any], purpose: Optional[str] = None,
                      explicit: Optional[str] = None) -> str:
    """explicit arg > purpose override (scoring/drafts) > main model."""
    if explicit:
        return explicit
    if purpose == "scoring":
        return cfg.get("model_scoring") or cfg.get("model", "")
    if purpose == "drafts":
        return cfg.get("model_drafts") or cfg.get("model", "")
    return cfg.get("model", "")


# -----------------------------------------------------------------------------
# Usage meter (process-wide, no backend dependency so src/ai stays import-clean)
# -----------------------------------------------------------------------------
_METER: Dict[str, Any] = {
    "calls": 0,
    "errors": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "total_seconds": 0.0,
    "estimated_cost_usd": 0.0,
    "last": None,
}


def record_ai_usage(purpose: Optional[str], model: str, prompt_chars: int,
                    seconds: float, usage: Optional[Dict[str, Any]] = None,
                    ok: bool = True) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "purpose": purpose or "general",
        "model": model or "",
        "prompt_chars": prompt_chars,
        "seconds": round(seconds, 2),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "ok": ok,
        "at": time.strftime("%H:%M:%S"),
    }
    if usage:
        try:
            pt = int(usage.get("prompt_tokens", 0) or 0)
            ct = int(usage.get("completion_tokens", 0) or 0)
        except (TypeError, ValueError):
            pt, ct = 0, 0
        entry.update(prompt_tokens=pt, completion_tokens=ct, total_tokens=pt + ct)
        for key, (pin, pout) in PRICE_MAP.items():
            if key in (model or "").lower():
                entry["estimated_cost_usd"] = round(pt * pin / 1e6 + ct * pout / 1e6, 6)
                break
    _METER["calls"] += 1
    if not ok:
        _METER["errors"] += 1
    _METER["prompt_tokens"] += entry["prompt_tokens"]
    _METER["completion_tokens"] += entry["completion_tokens"]
    _METER["total_tokens"] += entry["total_tokens"]
    _METER["total_seconds"] = round(_METER["total_seconds"] + seconds, 2)
    _METER["estimated_cost_usd"] = round(
        _METER["estimated_cost_usd"] + entry["estimated_cost_usd"], 6)
    _METER["last"] = entry
    return entry


def get_ai_meter() -> Dict[str, Any]:
    return dict(_METER)
