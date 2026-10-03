# EasiApply — Kinetic Neo-Tech Job Automation Dashboard

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)
![Playwright](https://img.shields.io/badge/Playwright-Chromium-green.svg)

> **EasiApply** is an open-source, local-first job automation copilot designed for product designers, engineers, and digital professionals. It scrapes hiring posts, scores match quality via multi-model AI gateways, generates tailored cold pitches, and tracks application status directly in a cockpit dashboard.

> [!CAUTION]
> **Account Safety & Secondary Account Recommendation**:
> LinkedIn strictly monitors automated account activity. For your own safety, **strongly recommend using a secondary or alternate LinkedIn account** rather than your primary personal account for job scraping.
> 
> **Important Disclaimer**: This tool is provided for personal automation and educational purposes only. If excessive usage or aggressive scraping leads to your LinkedIn account being flagged, temporarily restricted, or permanently banned, the creator and contributors **will not be held responsible**. Automate responsibly and keep scraping session limits low.

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

EasiApply supports any OpenAI-compatible API gateway. You can configure your provider either via the dashboard UI (**Settings** page) or directly in your `.env` file.

### Step-by-Step: Connecting OpenRouter (Recommended — Easiest Setup)

[OpenRouter](https://openrouter.ai/) gives you access to models from Anthropic (Claude), OpenAI (GPT-4o), Google (Gemini), Meta (Llama), and dozens of free or low-cost models with a single API key.

#### 1. Get Your OpenRouter API Key
1. Go to [https://openrouter.ai/](https://openrouter.ai/) and create a free account (or sign in with Google/GitHub).
2. Go to [https://openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) (or click your profile icon → **Keys**).
3. Click **Create Key**.
4. Give it a name (e.g., `EasiApply`), optionally set a credit limit, and click **Create**.
5. **Copy the key immediately** (it begins with `sk-or-v1-...`). You won't be able to view it again.
6. *(Optional)* If you plan to use paid models (like Claude 3.5 Sonnet or GPT-4o), add a small credit balance ($5) under [openrouter.ai/credits](https://openrouter.ai/credits). Many models (like `meta-llama/llama-3.1-8b-instruct:free`) are completely free to use.

#### 2. Connect in EasiApply (Two Easy Ways)

**Option A: Through the Web Dashboard (Recommended)**
1. Launch EasiApply (`launch.bat` on Windows or `./launch.sh` on macOS/Linux).
2. Open [http://127.0.0.1:8000/settings](http://127.0.0.1:8000/settings) in your browser.
3. In the **AI Provider** dropdown, select **OpenRouter**.
4. Paste your API key (`sk-or-v1-...`) into the **API Key** field.
5. Base URL will automatically default to `https://openrouter.ai/api/v1`.
6. Click **Test Connection**. Once connected, choose your preferred model from the dropdown (e.g., `anthropic/claude-3.5-sonnet`, `meta-llama/llama-3.1-70b-instruct`, or any free model).
7. Click **Save Settings**.

**Option B: Directly in your `.env` File**
Open your `.env` file in a text editor and set:
```ini
AI_PROVIDER="openrouter"
AI_BASE_URL="https://openrouter.ai/api/v1"
AI_API_KEY="sk-or-v1-your-actual-openrouter-key-here"

# Set any model ID of your choice available on OpenRouter:
# Free options (zero cost):
#   AI_MODEL="meta-llama/llama-3.1-8b-instruct:free"
#   AI_MODEL="mistralai/mistral-7b-instruct:free"
#   AI_MODEL="google/gemma-2-9b-it:free"
# Paid / High-intelligence options (requires credits):
#   AI_MODEL="anthropic/claude-3.5-sonnet"
#   AI_MODEL="openai/gpt-4o-mini"
AI_MODEL="meta-llama/llama-3.1-8b-instruct:free"
```

---

### Other AI Providers Supported
- **Ollama (100% Free & Local)**: Base URL `http://localhost:11434/v1` (no API key needed, runs offline).
- **OpenAI**: Base URL `https://api.openai.com/v1`, enter your OpenAI API key (`sk-...`).
- **OmniRoute / Custom Gateway**: Enter your custom gateway endpoint and token.

---

## How LinkedIn Login Works (No Credentials in Code)

You **never** need to store your LinkedIn password or email in your `.env` file or codebase:
1. When you trigger scraping for the first time, EasiApply automatically launches a real Playwright Chromium browser window.
2. You log in to LinkedIn manually inside this browser window just like you normally do (including solving any CAPTCHA or 2FA prompts).
3. EasiApply safely saves your session state and authentication cookies locally inside the `user_data/` folder on your own machine.
4. On future runs, EasiApply uses your saved local session automatically without asking you to log in again.
5. The `user_data/` directory is strictly ignored by `.gitignore` and is never tracked by Git.

---

## Email Outreach Setup (Optional)

If you wish to send outreach emails directly from the dashboard, you can configure your email provider under **Settings** or in `.env`:

> [!TIP]
> **For Gmail Users:**
> Do **not** use your normal Gmail account password. Google requires an **App Password**:
> 1. Go to your [Google Account Security Settings](https://myaccount.google.com/security).
> 2. Ensure **2-Step Verification** is turned ON.
> 3. Search for or navigate to **App Passwords** ([direct link](https://myaccount.google.com/apppasswords)).
> 4. Create a new App Password named `EasiApply` (it generates a 16-character code like `abcd efgh ijkl mnop`).
> 5. Use that 16-character code as your `SMTP_PASSWORD`.

---

## Legal & Platform Disclaimer

> [!WARNING]
> Please read this section carefully before using or contributing to this project.

1. **Independent Project & Non-Affiliation**:
   - EasiApply is an independent open-source software project designed strictly for personal productivity, educational exploration, and job application tracking.
   - It is **not** endorsed by, certified by, partnered with, or affiliated with LinkedIn® Corporation, Microsoft Corporation, or any of their affiliates or subsidiaries. "LinkedIn" is a registered trademark of LinkedIn Corporation.

2. **Compliance with Third-Party Terms of Service**:
   - Automated interaction or scraping on LinkedIn may be against LinkedIn's [User Agreement](https://www.linkedin.com/legal/user-agreement).
   - Users are exclusively responsible for their own actions, usage frequency, and compliance with all applicable third-party Terms of Service.
   - The authors and maintainers accept **no liability** for any account suspension, restriction, IP throttling, or loss of data resulting from the use of this software.

3. **Anti-Spam & Responsible Communication**:
   - The cold email drafting and SMTP outreach functionality must be used ethically and in accordance with international communication regulations, including the **CAN-SPAM Act**, **GDPR**, **CASL**, and other local laws.
   - **Do not** use this tool for bulk spamming, unsolicited mass marketing, or harvesting unauthorized personal data.

4. **Privacy & Data Security**:
   - EasiApply operates locally on your machine. No user resumes, login session cookies, or scraped data are sent to external servers other than the AI provider endpoints you explicitly configure.
   - The software is provided "as is", without warranty of any kind, express or implied.

---

## Contributing & Code of Conduct

Contributions, bug reports, and suggestions are welcome! Feel free to open an Issue or submit a Pull Request.

---

## License
Distributed under the MIT License. See `LICENSE` for more information.



