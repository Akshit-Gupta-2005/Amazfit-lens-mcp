# Zepp Health Data Bridge & Probe Web Service

A lightweight, local-first web service implementing the **ZeppBridge official OAuth flow**, real-time token claim polling, and automatic health data retrieval checks.

---

## What It Does

1. **Local Host Web Server**: Runs locally at `http://localhost:8000`.
2. **Browser-based Login**: Click **Connect with Zepp**, and the official Zepp login page opens in your web browser (supports Google, Apple, Xiaomi, or email/phone).
3. **Automatic Return & Verification**:
   - The server communicates with the ZeppBridge Cloudflare relay (`zeppbridge.com`), completes the code exchange, securely receives the tokens, and persists them locally in `session.json`.
   - The web dashboard automatically detects login completion, greets the user with their profile name and user ID, and immediately triggers data checks.
4. **Data Retrieval Checks & Metrics**:
   - **Range Covered**: Displays the exact start and end date probed (e.g. past 90 days).
   - **Activity Coverage**: Shows how many days have step/activity records, the total step count, and coverage percentage.
   - **Sleep Coverage**: Shows how many nights have recorded sleep, average duration, and average sleep score.
   - **Workouts**: Shows recorded sport sessions.
   - **Data Tables**: Recent day-by-day activity and sleep breakdown.
   - **Raw JSON Viewer**: Displays the exact payload returned by `api-open.zepp.com`, ready for designing your custom MCP tools.

---

## How to Run

1. Open a terminal in this directory:
   ```bash
   cd C:\Users\akshi\Documents\Coding\VSCode\python\projects\Vitalens\zepp_bridge_web
   ```

2. (Optional) Install dependencies if not already installed:
   ```bash
   pip install -r requirements.txt
   ```

3. Start the server:
   ```bash
   python run.py
   ```
   Or via uvicorn directly:
   ```bash
   uvicorn server:app --host 127.0.0.1 --port 8000
   ```

4. The browser will open automatically at `http://localhost:8000`. Click **Connect with Zepp** and sign in!

---

## How It Works (ZeppBridge Architecture Reference)

- **Zero-Secret Client Flow**: Because Zepp Open Platform OAuth requires a `client_secret` but does not support PKCE, requests are initiated via the public zero-knowledge relay:
  - Generates 43-character URL-safe random `state` and `claim_secret`.
  - Sends `claim_hash = sha256(claim_secret)` to `https://zeppbridge.com/api/zepp/oauth/start`.
  - When the browser finishes authorization, the local server polls `/api/zepp/oauth/claim` delivering the secret to securely claim the tokens.
- **Direct Cloud Sync**: All health records are retrieved directly from `https://api-open.zepp.com` using the issued Bearer access token.

---

## Building an MCP Server Next

This codebase gives you everything you need to expose your Zepp data to an AI client (Claude, Codex, ChatGPT) via Model Context Protocol:
- Authenticated session handling: [`get_valid_access_token()`](file:///C:/Users/akshi/Documents/Coding/VSCode/python/projects/Vitalens/zepp_bridge_web/server.py)
- Token auto-refresh: [`refresh_official_token()`](file:///C:/Users/akshi/Documents/Coding/VSCode/python/projects/Vitalens/zepp_bridge_web/server.py)
- API endpoints for activities, sleep, and sports: [`make_zepp_api_request()`](file:///C:/Users/akshi/Documents/Coding/VSCode/python/projects/Vitalens/zepp_bridge_web/server.py)
