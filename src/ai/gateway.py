import os
import sys
import json
import re
import time
import requests
from typing import Dict, Any, Type, Optional
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.ai.providers import resolve_ai_config, model_for_purpose, record_ai_usage

load_dotenv()

class AIGateway:
    """
    Provider-agnostic gateway: any OpenAI-compatible endpoint
    (Omniroute, OpenAI, OpenRouter, Ollama, custom) with strict
    structured output validation.

    Config resolution (src.ai.providers.resolve_ai_config):
      canonical AI_* keys first, legacy OMNIROUTE_*/CLAUDE_MODEL as fallback.
    """

    def __init__(self, purpose: Optional[str] = None, model: Optional[str] = None):
        cfg = resolve_ai_config()
        self._cfg = cfg
        self.provider = cfg["provider"]
        self.provider_label = cfg["provider_label"]
        self.base_url = cfg["base_url"] or "http://localhost:8000/v1"
        self.api_key = cfg["api_key"]
        self.purpose = purpose
        # explicit arg > purpose override (scoring/drafts) > main model
        self.model = model or model_for_purpose(cfg, purpose)

        if not self.api_key and cfg["requires_key"]:
            raise ValueError(
                "❌ AI API key is missing. Set AI_API_KEY in Settings "
                "(or pick a keyless provider like Ollama).")

        self.headers = {"Content-Type": "application/json"}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    def fetch_available_models(self) -> List[str]:
        """
        Queries the connected AI gateway for available text/chat models.
        Supports OpenRouter, Ollama, OpenAI, OmniRoute, and custom OpenAI-compatible endpoints.
        """
        urls_to_try = [
            f"{self.base_url.rstrip('/')}/models",
            f"{self.base_url.rstrip('/v1').rstrip('/')}/v1/models" if "/v1" in self.base_url else f"{self.base_url.rstrip('/')}/v1/models"
        ]
        discovered = []
        for u in urls_to_try:
            try:
                resp = requests.get(u, headers=self.headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_list = data.get("data") or data.get("models") or []
                    for item in raw_list:
                        m_id = item.get("id") or item.get("name") or (item if isinstance(item, str) else "")
                        if m_id and isinstance(m_id, str):
                            low = m_id.lower()
                            if any(k in low for k in ["whisper", "tts", "dall-e", "embedding", "embed", "moderation", "rerank"]):
                                continue
                            discovered.append(m_id)
                    if discovered:
                        break
            except Exception:
                continue
        return discovered

    def generate_structured_output(self, prompt: str, schema: Type[BaseModel],
                                   model: Optional[str] = None,
                                   purpose: Optional[str] = None) -> Optional[BaseModel]:
        """
        Calls the configured provider, enforcing structured JSON output that
        matches the given Pydantic schema. Includes automatic schema injection
        into the prompt, auto-model selection if none specified, and real-time
        failover across available gateway models on error or rate-limit.
        """
        primary_model = model or (model_for_purpose(self._cfg, purpose)
                                  if purpose else self.model) or self.model
        candidate_models = []
        if primary_model:
            candidate_models.append(primary_model)
        base_m = self._cfg.get("model")
        if base_m and base_m not in candidate_models:
            candidate_models.append(base_m)

        # Auto-discover other models available in gateway for dynamic failover
        try:
            gw_models = self.fetch_available_models()
            for gm in gw_models:
                if gm not in candidate_models:
                    candidate_models.append(gm)
        except Exception:
            pass

        # Fallback default if completely empty
        if not candidate_models:
            if "openrouter" in self.base_url.lower() or self.provider == "openrouter":
                candidate_models.append("inclusionai/ling-3.0-flash-vl:free")
            elif "ollama" in self.base_url.lower():
                candidate_models.append("llama3")
            else:
                candidate_models.append("default")

        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        final_prompt = f"""
{prompt}

# Output Requirements
You MUST return your final response strictly as valid, parsable JSON.
The JSON must adhere to the following JSON Schema:

{schema_json}
"""

        payload = {
            "messages": [{"role": "user", "content": final_prompt}],
            "temperature": 0.0,
        }

        self.last_error = None
        started = time.time()

        for cand_idx, cand_model in enumerate(candidate_models):
            payload["model"] = cand_model
            use_model = cand_model

            if "openrouter" not in self.base_url.lower() and self.provider != "openrouter":
                payload["response_format"] = {"type": "json_object"}
            elif "response_format" in payload:
                del payload["response_format"]

            response = None
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    data=json.dumps(payload),
                    timeout=90
                )

                # Retry without response_format if provider doesn't support it
                if response.status_code == 400 and "response_format" in payload:
                    del payload["response_format"]
                    response = requests.post(
                        f"{self.base_url}/chat/completions",
                        headers=self.headers,
                        data=json.dumps(payload),
                        timeout=90
                    )

                # If status code indicates model invalid, rate limit (429), payment (402), or overload (503)
                if response.status_code in (400, 402, 404, 422, 429, 503):
                    err_snippet = response.text[:180]
                    if cand_idx + 1 < len(candidate_models):
                        next_cand = candidate_models[cand_idx + 1]
                        print(f"⚠️ Model '{cand_model}' returned {response.status_code} ({err_snippet}). Auto-failing over to next available gateway model '{next_cand}'...")
                        continue
                    else:
                        print(f"❌ Model '{cand_model}' failed ({response.status_code}: {err_snippet}) and no alternative models in gateway.")
                        self.last_error = f"Model '{cand_model}' failed ({response.status_code}): {err_snippet}"
                        response.raise_for_status()

                response.raise_for_status()
                response_data = response.json()
                content = response_data['choices'][0]['message']['content']

                if "```" in content:
                    content = re.sub(r'```(?:json)?\s*(.*?)\s*```', r'\1', content, flags=re.DOTALL).strip()

                parsed = schema.model_validate_json(content)
                # Success! Keep working model active
                self.model = cand_model
                record_ai_usage(self.purpose or purpose, cand_model, len(final_prompt),
                                time.time() - started, response_data.get("usage"), ok=True)
                return parsed

            except (requests.exceptions.RequestException, ValidationError) as e:
                err_str = str(e)
                if cand_idx + 1 < len(candidate_models):
                    next_cand = candidate_models[cand_idx + 1]
                    print(f"⚠️ Request with '{cand_model}' failed ({err_str[:120]}). Auto-failing over to '{next_cand}'...")
                    continue
                else:
                    self.last_error = f"All available models in gateway failed. Last error ({cand_model}): {err_str}"
                    print(f"❌ {self.last_error}")
                    record_ai_usage(self.purpose or purpose, cand_model, len(final_prompt),
                                    time.time() - started, None, ok=False)
                    return None
