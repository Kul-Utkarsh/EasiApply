import streamlit as st
from pathlib import Path


def load_env_vars():
    """Load all environment variables from .env file."""
    env_path = Path(".env")
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip().strip("\"'")
    return env_vars, env_path


def save_env_vars(env_vars, env_path):
    """Save environment variables back to .env file."""
    lines = []
    for key, value in env_vars.items():
        if value and isinstance(value, str):
            if " " in value or "@" in value:
                lines.append(f'{key}="{value}"')
            else:
                lines.append(f"{key}={value}")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def settings_page():
    """Settings page for AI Gateway, Email, and Browser configuration."""
    st.markdown('<div class="vercel-title">Settings</div>', unsafe_allow_html=True)
    st.markdown('<div class="vercel-subtitle">Configure your AI gateway, email, and browser automation preferences.</div>', unsafe_allow_html=True)

    env_vars, env_path = load_env_vars()
    tab1, tab2, tab3, tab4 = st.tabs(["AI Gateway", "Email (SMTP)", "Browser", "Raw .env"])

    # =========================================================================
    # TAB 1: AI GATEWAY
    # =========================================================================
    with tab1:
        st.markdown("#### AI Gateway Configuration")
        st.caption("Connect any OpenAI-compatible provider (OmniRoute, OpenAI, OpenRouter, Ollama local, custom)")

        from src.ai.providers import PROVIDER_PRESETS, resolve_ai_config
        _saved = resolve_ai_config(env_vars)
        _names = list(PROVIDER_PRESETS.keys())
        provider = st.selectbox(
            "Provider",
            options=_names,
            index=_names.index(_saved["provider"]) if _saved["provider"] in _names else 0,
            format_func=lambda k: PROVIDER_PRESETS[k]["label"],
        )
        _preset = PROVIDER_PRESETS[provider]

        col1, col2 = st.columns(2)
        with col1:
            omniroute_base_url = st.text_input(
                "API Base URL",
                value=env_vars.get("AI_BASE_URL") or env_vars.get("OMNIROUTE_BASE_URL", "") or _preset["base_url"],
                placeholder=_preset["base_url"] or "https://your-gateway.example.com/v1"
            )
        with col2:
            omniroute_api_key = st.text_input(
                "API Key" + ("" if _preset["requires_key"] else " (not needed for this provider)"),
                value=env_vars.get("AI_API_KEY") or env_vars.get("OMNIROUTE_API_KEY", ""),
                type="password",
                placeholder="your-api-key-here" if _preset["requires_key"] else "leave empty for local providers"
            )

        colm1, colm2 = st.columns(2)
        with colm1:
            scoring_model = st.text_input(
                "Scoring model override (optional)",
                value=env_vars.get("AI_MODEL_SCORING", ""),
                placeholder="Defaults to main model"
            )
        with colm2:
            drafts_model = st.text_input(
                "Drafts model override (optional)",
                value=env_vars.get("AI_MODEL_DRAFTS", ""),
                placeholder="Defaults to main model"
            )
        _main_default = env_vars.get("AI_MODEL") or env_vars.get("CLAUDE_MODEL", "") or _preset["default_model"]

        available_models = []
        if st.button("Fetch Available Models", key="fetch_models"):
            try:
                import requests
                headers = {
                    "Authorization": f"Bearer {omniroute_api_key}",
                    "Content-Type": "application/json"
                }
                response = requests.get(
                    f"{omniroute_base_url.rstrip('/')}/models",
                    headers=headers,
                    timeout=30
                )
                if response.status_code == 200:
                    models_data = response.json()
                    if "data" in models_data:
                        available_models = [m.get("id", m.get("name", "")) for m in models_data["data"]]
                    elif isinstance(models_data, list):
                        available_models = [
                            m.get("id", m.get("name", "")) if isinstance(m, dict) else str(m)
                            for m in models_data
                        ]
                    st.session_state["fetched_models"] = available_models
                    st.success(f"Found {len(available_models)} models!")
                else:
                    st.error(f"Could not fetch models. Status: {response.status_code}")
            except Exception as e:
                st.error(f"Error fetching models: {e}")

        if "fetched_models" in st.session_state and st.session_state["fetched_models"]:
            available_models = st.session_state["fetched_models"]

        if available_models:
            saved_model = _main_default
            default_index = 0
            if saved_model and saved_model in available_models:
                default_index = available_models.index(saved_model)
            elif saved_model:
                available_models.insert(0, saved_model)
            claude_model = st.selectbox("Select Model", options=available_models, index=default_index)
        else:
            claude_model = st.text_input(
                "Model Name",
                value=_main_default,
                placeholder="e.g., claude-sonnet-5, gpt-4"
            )

        st.divider()
        col_test, col_save = st.columns(2)

        with col_test:
            if st.button("Test Connection", key="test_ai", use_container_width=True):
                try:
                    import requests
                    headers = {
                        "Authorization": f"Bearer {omniroute_api_key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "messages": [{"role": "user", "content": "Say 'Connection successful!' in exactly 3 words."}],
                        "temperature": 0.0
                    }
                    if claude_model:
                        payload["model"] = claude_model
                    response = requests.post(
                        f"{omniroute_base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=30
                    )
                    if response.status_code == 200:
                        st.success("Connection successful!")
                    else:
                        st.error(f"Connection failed. Status: {response.status_code}\n\n{response.text}")
                except Exception as e:
                    st.error(f"Error testing connection: {e}")

        with col_save:
            if st.button("Save AI Settings", key="save_ai", use_container_width=True):
                env_vars["AI_PROVIDER"] = provider
                env_vars["AI_BASE_URL"] = omniroute_base_url
                if omniroute_api_key:
                    env_vars["AI_API_KEY"] = omniroute_api_key
                elif "AI_API_KEY" in env_vars:
                    del env_vars["AI_API_KEY"]
                if claude_model:
                    env_vars["AI_MODEL"] = claude_model
                elif "AI_MODEL" in env_vars:
                    del env_vars["AI_MODEL"]
                if scoring_model:
                    env_vars["AI_MODEL_SCORING"] = scoring_model
                elif "AI_MODEL_SCORING" in env_vars:
                    del env_vars["AI_MODEL_SCORING"]
                if drafts_model:
                    env_vars["AI_MODEL_DRAFTS"] = drafts_model
                elif "AI_MODEL_DRAFTS" in env_vars:
                    del env_vars["AI_MODEL_DRAFTS"]
                save_env_vars(env_vars, env_path)
                st.success("AI settings saved!")

    # =========================================================================
    # TAB 2: EMAIL (SMTP)
    # =========================================================================
    with tab2:
        st.markdown("#### Email Configuration (SMTP)")
        st.caption("Set up your email credentials for automated outreach.")

        col1, col2 = st.columns(2)
        with col1:
            smtp_host = st.text_input("SMTP Host", value=env_vars.get("SMTP_HOST", "smtp.gmail.com"))
            smtp_port = st.number_input("SMTP Port", value=int(env_vars.get("SMTP_PORT", 587)), min_value=1, max_value=65535)
        with col2:
            smtp_user = st.text_input("Email Address", value=env_vars.get("SMTP_USER", ""))
            sender_name = st.text_input("Your Name (Sender)", value=env_vars.get("SENDER_NAME", ""))

        smtp_password = st.text_input(
            "Email Password or App Password",
            value=env_vars.get("SMTP_PASSWORD", ""),
            type="password"
        )

        st.info(
            "Gmail setup: Enable 2FA → go to myaccount.google.com/apppasswords → "
            "generate an app password for Mail → paste it here."
        )

        col_test, col_save = st.columns(2)
        with col_test:
            if st.button("Test Email Connection", key="test_email", use_container_width=True):
                try:
                    import smtplib
                    server = smtplib.SMTP(smtp_host, smtp_port)
                    server.starttls()
                    server.login(smtp_user, smtp_password)
                    server.quit()
                    st.success("Email connection successful!")
                except Exception as e:
                    st.error(f"Email connection failed: {e}")

        with col_save:
            if st.button("Save Email Settings", key="save_email", use_container_width=True):
                env_vars["SMTP_HOST"] = smtp_host
                env_vars["SMTP_PORT"] = str(smtp_port)
                env_vars["SMTP_USER"] = smtp_user
                env_vars["SMTP_PASSWORD"] = smtp_password
                env_vars["SENDER_NAME"] = sender_name
                save_env_vars(env_vars, env_path)
                st.success("Email settings saved!")

    # =========================================================================
    # TAB 3: BROWSER
    # =========================================================================
    with tab3:
        st.markdown("#### Browser Automation Settings")
        st.caption("Configure Playwright browser automation and scrolling parameters.")

        col1, col2 = st.columns(2)
        with col1:
            headless_val = env_vars.get("HEADLESS", "False").lower() == "true"
            headless = st.checkbox("Run in Headless Mode", value=headless_val)
            slow_mo_ms = st.number_input(
                "Slow Motion (ms)",
                value=int(env_vars.get("SLOW_MO_MS", 100)),
                min_value=0, max_value=2000, step=50
            )
            max_scroll = st.number_input(
                "Max Scroll Attempts",
                value=int(env_vars.get("MAX_SCROLL_ATTEMPTS", 60)),
                min_value=1, max_value=200
            )
            scroll_delay = st.number_input(
                "Scroll Delay (ms)",
                value=int(env_vars.get("SCROLL_DELAY_MS", 3000)),
                min_value=500, max_value=10000, step=500
            )
            search_url_override = st.text_input(
                "Search URL Override (Optional)",
                value=env_vars.get("EASYAPPLY_SELENIUM_SEARCH_URL", ""),
                placeholder="https://www.linkedin.com/search/results/..."
            )
        with col2:
            max_jobs = st.number_input(
                "Max Jobs per Session",
                value=int(env_vars.get("MAX_JOBS_PER_SESSION", 25)),
                min_value=5, max_value=200
            )
            page_load_wait = st.number_input(
                "Page Load Wait (ms)",
                value=int(env_vars.get("PAGE_LOAD_WAIT_MS", 5000)),
                min_value=1000, max_value=30000, step=1000
            )

        st.warning(
            "LinkedIn detection tip: If blocked, increase scroll delays. "
            "Keep headless OFF for the first run so you can log in manually."
        )

        if st.button("Save Browser Settings", key="save_browser", use_container_width=True):
            env_vars["HEADLESS"] = "True" if headless else "False"
            env_vars["SLOW_MO_MS"] = str(slow_mo_ms)
            env_vars["MAX_JOBS_PER_SESSION"] = str(max_jobs)
            env_vars["MAX_SCROLL_ATTEMPTS"] = str(max_scroll)
            env_vars["SCROLL_DELAY_MS"] = str(scroll_delay)
            env_vars["PAGE_LOAD_WAIT_MS"] = str(page_load_wait)
            env_vars["EASYAPPLY_SELENIUM_SEARCH_URL"] = search_url_override
            env_vars.pop("MIN_PAGE_DELAY", None)
            env_vars.pop("MAX_PAGE_DELAY", None)
            save_env_vars(env_vars, env_path)
            st.success("Browser settings saved!")

    # =========================================================================
    # TAB 4: RAW .ENV
    # =========================================================================
    with tab4:
        st.markdown("#### Raw .env File Editor")
        st.caption("Edit all configuration as plain text. Be careful with formatting.")

        env_content = env_path.read_text(encoding="utf-8") if env_path.exists() else "# .env\n"
        new_env = st.text_area("Full .env Content", value=env_content, height=350)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Save Raw .env", key="save_raw_env", use_container_width=True):
                env_path.write_text(new_env, encoding="utf-8")
                st.success("Saved .env successfully!")
        with c2:
            if st.button("Reload", key="reload_env", use_container_width=True):
                st.rerun()

        st.divider()
        st.warning(
            "Keep your .env safe — it contains API keys and email passwords. "
            "Never commit it to GitHub or share it publicly."
        )


if __name__ == "__main__":
    settings_page()
