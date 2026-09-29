# EasiApply — Kinetic Neo-Tech Job Automation Dashboard

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)
![Playwright](https://img.shields.io/badge/Playwright-Chromium-green.svg)

> **EasiApply** is an open-source, local-first job automation copilot designed for product designers, engineers, and digital professionals. It scrapes hiring posts, scores match quality via multi-model AI gateways, generates tailored cold pitches, and tracks application status directly in a cockpit dashboard.

---

## Key Features

- **Local-First & Private**: Your resumes, application database, and browser sessions remain 100% on your machine.
- **Smart Resume Router**: Upload multiple specialized resumes (e.g. UX Designer, Product Designer, Frontend). EasiApply auto-attaches the best-matching resume variant for each opportunity.
- **In-App Document Preview**: Preview your resumes and attachments directly inside the dashboard with zero external download popups.
- **Multi-Model AI Gateway Support**: Connect OmniRoute, OpenAI, OpenRouter, Ollama (local), or any custom OpenAI-compatible API with automatic rate-limit failover.
- **Stealth Scraper Guardrails**: Humanized delays, bezier-curve mouse movements, and anti-bot mitigation protect your LinkedIn session.
- **One-Click Launch**: Self-healing launchers for Windows (`launch.bat`) and macOS/Linux (`launch.sh`) that automatically configure dependencies, `.env`, and browser binaries.

---

## Quickstart

### Prerequisites
- Python 3.10 or higher
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/Kul-Utkarsh/EasiApply.git
cd EasiApply
```

### 2. Start the Application
* **Windows**: Double-click `launch.bat` (or run `launch.bat` in Command Prompt / PowerShell).
* **macOS / Linux**: Run `./launch.sh` (or `bash launch.sh`).

The launcher will automatically:
1. Initialize your `.env` configuration file from `.env.example`.
2. Install required Python packages from `requirements.txt`.
3. Download the Playwright Chromium browser binaries (one-time setup).
4. Launch the FastAPI server on `http://127.0.0.1:8000` and open your dashboard.

---

## Manual Setup (Alternative)

If you prefer manual control:
```bash
# 1. Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Copy environment configuration
cp .env.example .env

# 4. Start the server
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload
```
Open [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard) in your browser.

---

## Configuration & AI Setup

Navigate to **Settings** in the dashboard to connect your AI provider:
- **Ollama (100% Free & Local)**: Base URL `http://localhost:11434/v1` (no API key needed).
- **OpenAI**: Base URL `https://api.openai.com/v1`, enter your OpenAI API key.
- **OpenRouter**: Base URL `https://openrouter.ai/api/v1`, enter your OpenRouter key.
- **OmniRoute / Custom Gateway**: Enter your gateway endpoint and API key.

Click **Test Connection** to verify your provider and auto-populate available models.

---

## License
Distributed under the MIT License. See `LICENSE` for more information.
