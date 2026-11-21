# Amazfit Health Lens — Local-First Biometric MCP Server

A privacy-focused, local-first **Model Context Protocol (MCP)** server and synchronization engine that connects personal health, fitness, and sleep telemetry from **Amazfit / Zepp wearables** directly to AI agents (**Claude Desktop** and **ChatGPT**).

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│                   WEARABLE TELEMETRY                   │
│         Amazfit Smartwatch / Smart Ring / Scale        │
│                           │                            │
│                           ▼                            │
│                  Zepp Cloud Platform                   │
└───────────────────────────┬────────────────────────────┘
                            │ OAuth 2.0 / Bearer Auth
                            ▼
┌────────────────────────────────────────────────────────┐
│            VITALENS DATA ENGINE (zepp_bridge_web)       │
│                                                        │
│  • Web OAuth Login & Zero-Secret Relay                 │
│  • Anti-Truncation Multi-Chunk Synchronizer            │
│  • Physiological Normalizer & Sleep Stage Parser       │
│  • Local Persistent Store (zepp_data.sqlite)           │
│  • Interactive Category Catalog Web UI (:8000)         │
└───────────────────────────┬────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              │ stdio (Local)             │ SSE (HTTP/Tunnel)
              ▼                           ▼
┌───────────────────────────┐   ┌────────────────────────┐
│      CLAUDE DESKTOP       │   │    CHATGPT (Cloud)     │
│  claude_desktop_config    │   │  Custom MCP Connector  │
└───────────────────────────┘   └────────────────────────┘
```

---

## Key Features

1. **Deterministic AI Tool Calling (No Hallucinations)**:
   - Exposes high-level analytical tools instead of raw data dumps.
   - Computes recovery readiness, sleep debt, and pace z-scores directly in Python/SQL before returning structured findings to the LLM.
2. **Dual MCP Transport Support**:
   - **`stdio`**: Direct process communication for **Claude Desktop** and CLI agents.
   - **`sse`**: Server-Sent Events over HTTP for **ChatGPT Custom MCP integration**, Cursor, and web clients.
3. **100% Local Privacy**:
   - Biometric records remain strictly on your local machine in `zepp_data.sqlite`.
   - The LLM only receives anonymized, filtered context needed to answer the immediate prompt.
4. **Anti-Truncation Sync Engine**:
   - Automatically segments queries into safe chunk sizes (≤90 days for activities/sleep, ≤7 days for minute-level heart rate) to prevent Zepp's undocumented server-side data truncation.

---

## Indexed Biometric Domains

| Category | Indexed Metrics | Primary MCP Purpose |
| :--- | :--- | :--- |
| **😴 Sleep & Recovery** | Duration, Sleep Score, Deep Sleep, Light Sleep, REM, Wake Time, Resting HR, Naps | Recovery grading, sleep debt tracking, circadian consistency. |
| **🏃 Athletic Workouts** | Sport type (runs, walks, football, rides, gym), duration, distance, calories, avg/max HR, pace, cadence | Training workload analysis, pace efficiency, cardio effort. |
| **🚶 Daily Activity** | Total steps, active calorie expenditure, walking distance | Daily physical activity volume and goal progression. |
| **⏱️ Hourly Distribution**| 24-hour intra-day step breakdown | Sedentary window detection and active hour identification. |
| **❤️ Heart Rate Series** | Minute-by-minute continuous BPM telemetry | Cardiovascular baseline tracking and heart rate spikes. |

---

## MCP Tools Reference

The server exposes 7 distinct tools:

- `get_health_overview()`: Executive dashboard of user profile, recent daily steps, last night's sleep score, and latest workout.
- `get_recovery_status(lookback_days)`: Evaluates fatigue, sleep debt against an 8-hour target, and compares against 30-day baseline to provide a recovery recommendation.
- `get_sleep_records(date_from, date_to, limit)`: Detailed nocturnal sleep logs, quality scores, resting HR, and deep/REM percentages.
- `get_workouts(sport, date_from, date_to, limit)`: Filterable sports sessions with formatted durations (`1h 24m`), paces (`5:30 /km`), and heart rate stats.
- `get_daily_activity(date_from, date_to, limit)`: Daily steps, distance in km, and active energy burn.
- `get_hourly_activity(date)`: 24-hour step curve identifying peak activity hours.
- `sync_zepp_data(days)`: On-demand live cloud sync from Zepp Open Platform to local SQLite.

---

## Getting Started

### 1. Installation

```bash
cd zepp_bridge_web
pip install -r requirements.txt
```

### 2. Connect Your Account & Sync Data

Start the verification web dashboard:
```bash
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```
- Open [http://localhost:8000](http://localhost:8000).
- Click **Connect with Zepp** and authorize your account.
- Select your historical range (e.g. **Past 90 Days**) and click **Sync & Populate Data Layer**.

---

## Connecting to AI Clients

### A. Claude Desktop (stdio)

Add the following to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "amazfit-health": {
      "command": "python",
      "args": [
        "C:\\Users\\akshi\\Documents\\Coding\\VSCode\\python\\projects\\Vitalens\\zepp_bridge_web\\mcp_server.py"
      ]
    }
  }
}
```
Restart Claude Desktop. The **Hammer icon 🔨** will display all 7 Amazfit health tools.

### B. ChatGPT (SSE + Tunnel)

1. **Start the MCP server in SSE mode:**
   ```bash
   python start_chatgpt_mcp.py
   ```
   *(Listens on port `8001` at `/sse`)*

2. **Expose port 8001 via a secure tunnel:**
   ```bash
   npx localtunnel --port 8001
   ```
   *(Or using ngrok: `ngrok http 8001`)*

3. **In ChatGPT's "Add custom MCP server" dialog:**
   - **Name**: `Amazfit Health Lens`
   - **Connection**: `Server URL`
   - **URL**: `https://<your-tunnel-url>/sse`
   - **Authentication**: `None`

---

## Example Prompts to Ask

- *"Give me an overview of my health, sleep, and workouts."*
- *"Am I well recovered today? Should I push a hard training session or rest?"*
- *"Look at my recent runs and walks. What was my average pace and heart rate?"*
- *"Analyze my sleep quality over the last 14 days. Did I get enough deep and REM sleep?"*
- *"What was my peak walking hour on my most active day last week?"*
