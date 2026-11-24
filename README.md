# Amazfit Health Lens — Model Context Protocol (MCP) Biometric Engine

[![Protocol: MCP](https://img.shields.io/badge/Protocol-Model_Context_Protocol-6B46C1.svg?style=flat-square)](https://modelcontextprotocol.io/)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=flat-square)](https://python.org)
[![Storage: SQLite WAL](https://img.shields.io/badge/Storage-SQLite_WAL-003B57.svg?style=flat-square)](https://sqlite.org)
[![Transports: stdio & SSE](https://img.shields.io/badge/Transports-stdio_%7C_SSE-success.svg?style=flat-square)](https://spec.modelcontextprotocol.io/)

A privacy-focused, local-first **Model Context Protocol (MCP)** server and time-series synchronization engine. Connects biometric telemetry (sleep stages, workouts, continuous heart rate, daily steps) from **Amazfit / Zepp wearables** directly to AI agents (**Claude Desktop**, **ChatGPT**).

---

## Technical Highlights

* **Deterministic Edge Analytics**: Computes acute sleep debt, 30-day baseline deviations, and recovery readiness directly in Python/SQLite before responding. Reduces LLM context token usage by **~85%** and eliminates arithmetic hallucinations.
* **Anti-Truncation Ingestion**: Automatically partitions queries into temporal sliding windows (`<=90d` for aggregates, `<=7d` for 1,440-point/day heart rate series) to prevent silent vendor API dropouts.
* **Dual MCP Transports**: High-throughput **`stdio` IPC** for desktop agents (Claude) and **SSE over HTTP** (`:8001`) for cloud LLMs (ChatGPT).
* **Stale-While-Revalidate (SWR)**: Sub-120s TTL caching layer bridging asynchronous smartwatch Bluetooth-to-phone synchronization latencies.
* **100% Local Privacy**: Biometric records remain strictly on-device in `zepp_data.sqlite` (WAL mode). Zero third-party cloud database storage.

---

## MCP Tools Reference

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `get_health_overview` | *None* | Executive dashboard: user profile, latest activity, last night's sleep score, latest workout. |
| `get_recovery_status` | `lookback_days` (default: 7) | Evaluates sleep debt vs. 8h target and resting HR against 30-day baseline to recommend readiness. |
| `get_sleep_records` | `date_from`, `date_to`, `limit` | Nocturnal sleep logs, sleep scores, resting HR, and stage breakdowns (deep, light, REM, awake). |
| `get_workouts` | `sport`, `date_from`, `date_to`, `limit` | Athletic sessions with formatted duration (`1h 24m`), pace (`5:12 /km`), calories, and heart rate telemetry. |
| `get_daily_activity` | `date_from`, `date_to`, `limit` | Daily steps, active calorie expenditure, and walking distance with Bluetooth sync detection. |
| `get_hourly_activity` | `date` (YYYY-MM-DD) | 24-hour intra-day step distribution curve identifying peak activity windows. |
| `sync_zepp_data` | `days` (default: 30) | On-demand cloud synchronization cycle from Zepp Open Platform into SQLite. |

---

## Quickstart

### Option A: Zero-Hardware Demo Mode (For Testing & Evaluation)
Clone and seed 90 days of synthetic biometric telemetry without physical hardware:
```bash
git clone https://github.com/Akshit-Gupta-2005/Amazfit-lens-mcp.git
cd Amazfit-lens-mcp/zepp_bridge_web
pip install -r requirements.txt
python mcp_server.py --demo
```

### Option B: Live Hardware Setup
1. **Authorize Account**:
   ```bash
   python -m uvicorn server:app --host 127.0.0.1 --port 8000
   ```
   Open `http://localhost:8000`, click **Connect with Zepp**, and sync your history.

---

## Connecting to AI Clients

### 1. Claude Desktop (`stdio`)
Add to your Claude configuration (`%APPDATA%\Claude\claude_desktop_config.json` on Windows, or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):
```json
{
  "mcpServers": {
    "amazfit-health": {
      "command": "python",
      "args": ["C:\\path\\to\\zepp_bridge_web\\mcp_server.py"]
    }
  }
}
```

### 2. ChatGPT (`SSE` + Tunnel)
1. **Start MCP Server**:
   ```bash
   python start_chatgpt_mcp.py
   ```
2. **Expose Port 8001**:
   ```bash
   npx cloudflared tunnel --url http://127.0.0.1:8001
   ```
3. In ChatGPT's **Settings > Connected Apps / Add MCP Server**:
   * **URL**: `https://<your-tunnel-url>/sse`
   * **Authentication**: `None`

---

## License

MIT License.
