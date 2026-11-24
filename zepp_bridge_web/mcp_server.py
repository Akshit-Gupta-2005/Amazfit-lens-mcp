import os
import sys
import time
import json
import sqlite3
import datetime
from typing import Optional, List, Dict, Any

from mcp.server.mcpserver import MCPServer

# Add local directory to path for imports
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from db import get_connection, DB_PATH
from server import get_valid_access_token, get_session
from fetcher import ZeppDataSyncEngine
from auto_sync import start_auto_sync, trigger_sync

# Comprehensive System Instructions for AI Clients (ChatGPT, Claude)
SERVER_INSTRUCTIONS = """You are connected to Amazfit Health Lens, an MCP server providing real-time physiological and wearable health data for the user from their Amazfit / Zepp smartwatch.

Available capabilities:
- Sleep & Recovery: nocturnal sleep sessions, sleep duration, sleep stages (deep, light, REM, awake), sleep quality scores (1-100), and sleeping resting heart rate.
- Workouts & Athletic Training: structured workout logs across all sports (outdoor running, walking, cycling, football/soccer, treadmill, gym), net active duration, distance, calories burned, heart rate telemetry, pace, cadence, and total steps.
- Daily & Hourly Physical Activity: cumulative daily steps, active calorie expenditure, distance, and 24-hour intra-day hourly step distributions.
- Recovery & Readiness Analysis: multi-day sleep debt, recovery grading, and comparison against the user's historical baselines.
- Cloud Synchronization: trigger on-demand sync from Zepp Cloud when the user mentions they finished a workout or want fresh data.

Guidelines for AI:
1. Always use verified metrics returned by these tools rather than estimating or hallucinating health numbers.
2. For broad or open-ended inquiries (e.g. "How am I doing?", "Summarize my health", "How was my week?"), start by calling `get_health_overview`.
3. For questions about tiredness, insomnia, recovery, or sleep quality, call `get_sleep_records` or `get_recovery_status`.
4. For questions about workouts, exercise, running, or training load, call `get_workouts`.
5. For intra-day walking patterns, sedentary time, or step timing, call `get_hourly_activity`.
6. When comparing dates, remember calendar dates are formatted as YYYY-MM-DD.
7. If today's step count is missing or marked 'pending_bluetooth_sync', clearly explain to the user that their Amazfit watch transmits data to the Zepp app on their phone via Bluetooth. Prompt them to simply open the Zepp app on their phone and pull down on the screen to sync their watch to the cloud, then ask again.
"""

# Initialize MCP Server with explicit instructions
app = MCPServer(
    "AmazfitHealthLens",
    instructions=SERVER_INSTRUCTIONS,
    website_url="https://github.com/Akshit-Gupta-2005/Amazfit-lens-mcp"
)

# Start background auto-sync worker (immediate sync on start + every 15 min)
start_auto_sync(interval_seconds=900, startup_sync=True, startup_days=30, periodic_days=7)

def format_duration(seconds: Optional[int]) -> str:
    """Format seconds into readable human string (e.g. 1h 24m or 14m 20s)."""
    if not seconds or seconds <= 0:
        return "0s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"

def format_pace(sec_per_km: Optional[int]) -> str:
    """Format pace in seconds per km to standard min:sec /km format."""
    if not sec_per_km or sec_per_km <= 0 or sec_per_km > 3600:
        return "N/A"
    m = sec_per_km // 60
    s = sec_per_km % 60
    return f"{m}:{s:02d} /km"

def refresh_today_if_stale(max_age_seconds: int = 120):
    """
    Ensure today's live steps/calories/distance are fresh from Zepp Cloud.
    If today's record in SQLite is missing or older than max_age_seconds (default 2 min),
    queries Zepp Cloud in real-time and updates SQLite.
    """
    session = get_session() or {}
    if session.get("is_demo"):
        return

    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    now_ts = int(time.time())

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT synced_at FROM daily_activities WHERE date = ?", (today_str,))
        row = cursor.fetchone()
        if row and (now_ts - row["synced_at"]) < max_age_seconds:
            return  # Already fresh

    try:
        token = get_valid_access_token()
        engine = ZeppDataSyncEngine(token)
        engine.sync_daily_activity(today, today)
    except Exception as e:
        sys.stderr.write(f"[LiveSync] Failed to refresh today's daily activity: {e}\n")

def refresh_today_hourly_if_stale(max_age_seconds: int = 120):
    """Ensure today's hourly step samples are fresh from Zepp Cloud."""
    session = get_session() or {}
    if session.get("is_demo"):
        return

    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    now_ts = int(time.time())

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(synced_at) FROM hourly_activities WHERE date = ?", (today_str,))
        row = cursor.fetchone()
        if row and row[0] and (now_ts - row[0]) < max_age_seconds:
            return  # Already fresh

    try:
        token = get_valid_access_token()
        engine = ZeppDataSyncEngine(token)
        engine.sync_hourly_activity(today, today)
    except Exception as e:
        sys.stderr.write(f"[LiveSync] Failed to refresh today's hourly activity: {e}\n")

# --- MCP Tools ---

@app.tool()
def get_health_overview() -> Dict[str, Any]:
    """
    Get a high-level executive dashboard summary of all indexed health records, user account profile,
    today's activity summary, last night's sleep score, and latest workout.
    
    When to call this tool:
    - Call this tool FIRST whenever the user asks broad, open-ended questions like:
      "How am I doing?", "Summarize my health", "What did I do this week?", or "Give me a health checkup".
    """
    # 1. Ensure today's live activity is fresh from Zepp Cloud (if older than 2 minutes)
    refresh_today_if_stale(max_age_seconds=120)

    session = get_session() or {}
    nickname = session.get("nickname", "User")
    user_id = session.get("user_id", "Unknown")
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    with get_connection() as conn:
        cursor = conn.cursor()

        # Stream counts
        counts = {}
        for tbl in ["sleep_sessions", "daily_activities", "hourly_activities", "heart_rate_records", "workouts"]:
            cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
            counts[tbl] = cursor.fetchone()[0]

        # Latest activity
        cursor.execute("SELECT date, steps, active_calories, distance_meters FROM daily_activities ORDER BY date DESC LIMIT 1")
        latest_act_row = cursor.fetchone()
        latest_activity = dict(latest_act_row) if latest_act_row else None

        # Latest sleep
        cursor.execute("SELECT date, duration_minutes, score, resting_hr, deep_minutes, rem_minutes FROM sleep_sessions ORDER BY start_time DESC LIMIT 1")
        latest_sleep_row = cursor.fetchone()
        latest_sleep = dict(latest_sleep_row) if latest_sleep_row else None

        # Latest workout
        cursor.execute("SELECT date, sport_type, duration_seconds, distance_meters, calories, avg_hr, avg_pace_seconds, total_steps FROM workouts ORDER BY start_time DESC LIMIT 1")
        latest_w_row = cursor.fetchone()
        latest_workout = None
        if latest_w_row:
            lw = dict(latest_w_row)
            lw["duration_formatted"] = format_duration(lw["duration_seconds"])
            lw["pace_formatted"] = format_pace(lw["avg_pace_seconds"])
            latest_workout = lw

        # Workout sports distribution
        cursor.execute("SELECT sport_type, COUNT(*) as cnt FROM workouts GROUP BY sport_type ORDER BY cnt DESC")
        sports_dist = {r["sport_type"]: r["cnt"] for r in cursor.fetchall()}

    today_is_latest = (latest_activity and latest_activity.get("date") == today_str)
    today_sync_status = "live_up_to_date" if today_is_latest else f"Latest recorded date in Zepp Cloud is {latest_activity.get('date') if latest_activity else 'none'}."

    return {
        "user_profile": {
            "nickname": nickname,
            "user_id": user_id,
        },
        "records_indexed": {
            "sleep_nights": counts.get("sleep_sessions", 0),
            "daily_summaries": counts.get("daily_activities", 0),
            "hourly_buckets": counts.get("hourly_activities", 0),
            "heart_rate_points": counts.get("heart_rate_records", 0),
            "workouts_count": counts.get("workouts", 0)
        },
        "sports_distribution": sports_dist,
        "latest_daily_activity": latest_activity,
        "latest_sleep": latest_sleep,
        "latest_workout": latest_workout,
        "today_sync_status": today_sync_status
    }

@app.tool()
def get_workouts(
    sport: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 15
) -> List[Dict[str, Any]]:
    """
    Retrieve athletic workout logs (e.g. outdoor run, walking, football/soccer, cycling, treadmill, circuit training).
    Includes net active duration, distance, calories burned, heart rate telemetry, pace, cadence, and steps.
    
    When to call this tool:
    - Call this tool whenever the user asks about workouts, running, walks, gym sessions, training progress, or exercise intensity.
    
    Parameters:
    - sport: Optional filter by sport type (e.g. 'run', 'walking', 'football', 'soccer', 'ride', 'treadmill').
    - date_from: Optional filter for start date (YYYY-MM-DD).
    - date_to: Optional filter for end date (YYYY-MM-DD).
    - limit: Maximum number of workout records to return (default 15, max 100).
    """
    limit = max(1, min(limit, 100))
    query = """
        SELECT workout_id, sport_type, date, start_time, end_time, duration_seconds,
               distance_meters, calories, avg_hr, max_hr, avg_pace_seconds, avg_cadence,
               avg_stride_length_cm, total_steps
        FROM workouts
        WHERE 1=1
    """
    params = []

    if sport:
        sport_clean = sport.strip().lower()
        query += " AND (sport_type = ? OR sport_type LIKE ?)"
        params.extend([sport_clean, f"%{sport_clean}%"])
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)

    query += " ORDER BY start_time DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["duration_formatted"] = format_duration(d["duration_seconds"])
        d["pace_formatted"] = format_pace(d["avg_pace_seconds"])
        d["distance_km"] = round(d["distance_meters"] / 1000.0, 2) if d.get("distance_meters") else 0.0
        results.append(d)

    return results

@app.tool()
def get_sleep_records(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 14
) -> List[Dict[str, Any]]:
    """
    Retrieve nocturnal sleep logs, quality scores (1-100), resting heart rate during sleep, and sleep stage breakdowns (deep, light, REM, awake).
    
    When to call this tool:
    - Call this tool when the user asks about sleep quality, how well they slept, REM sleep, deep sleep percentages, sleep consistency, or bedtime habits.
    
    Parameters:
    - date_from: Optional start date (YYYY-MM-DD).
    - date_to: Optional end date (YYYY-MM-DD).
    - limit: Maximum number of nights to return (default 14, max 90).
    """
    limit = max(1, min(limit, 90))
    query = "SELECT sleep_id, date, start_time, end_time, duration_minutes, deep_minutes, light_minutes, rem_minutes, awake_minutes, score, resting_hr, naps_count FROM sleep_sessions WHERE 1=1"
    params = []

    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)

    query += " ORDER BY start_time DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

    results = []
    for r in rows:
        d = dict(r)
        dur = d.get("duration_minutes") or 0
        d["duration_formatted"] = f"{dur // 60}h {dur % 60}m" if dur > 0 else "0m"
        if dur > 0:
            d["deep_pct"] = round(((d.get("deep_minutes") or 0) / dur) * 100, 1)
            d["rem_pct"] = round(((d.get("rem_minutes") or 0) / dur) * 100, 1)
            d["light_pct"] = round(((d.get("light_minutes") or 0) / dur) * 100, 1)
        results.append(d)

    return results

@app.tool()
def get_recovery_status(lookback_days: int = 7) -> Dict[str, Any]:
    """
    Evaluate the user's recovery readiness by comparing recent sleep metrics, sleep debt, and resting heart rate against their historical baseline.
    
    When to call this tool:
    - Call this tool when the user asks:
      "Am I well recovered today?", "Should I train hard or rest?", "How is my fatigue level?", or "Analyze my recovery readiness".
      
    Parameters:
    - lookback_days: Number of days to assess recovery over (default: 7, max: 30).
    """
    lookback_days = max(3, min(lookback_days, 30))
    with get_connection() as conn:
        cursor = conn.cursor()
        # Fetch recent sleep records
        cursor.execute("""
            SELECT date, duration_minutes, score, resting_hr, deep_minutes, rem_minutes, awake_minutes
            FROM sleep_sessions
            ORDER BY start_time DESC
            LIMIT ?
        """, (lookback_days,))
        rows = cursor.fetchall()

        # Fetch 30-day baseline for resting HR and sleep duration
        cursor.execute("""
            SELECT AVG(duration_minutes) as avg_dur, AVG(score) as avg_score, AVG(resting_hr) as avg_rhr
            FROM sleep_sessions
            WHERE start_time >= strftime('%s', 'now', '-30 days') AND duration_minutes > 0
        """)
        baseline_row = cursor.fetchone()
        baseline = {
            "avg_sleep_minutes": round(baseline_row["avg_dur"] or 450),
            "avg_sleep_score": round(baseline_row["avg_score"] or 75, 1),
            "avg_resting_hr": round(baseline_row["avg_rhr"] or 65, 1) if baseline_row["avg_rhr"] else None
        }

    if not rows:
        return {"status": "insufficient_data", "message": "No recent sleep records found to compute recovery."}

    nights = [dict(r) for r in rows]
    latest = nights[0]

    # Calculate sleep debt vs 8-hour target (480 mins) over the lookback window
    sleep_debt_minutes = sum(max(0, 480 - (n["duration_minutes"] or 0)) for n in nights)
    sleep_debt_hours = round(sleep_debt_minutes / 60.0, 1)

    # Determine recovery score / grade
    latest_score = latest.get("score") or 70
    latest_dur = latest.get("duration_minutes") or 0
    deep_pct = round(((latest.get("deep_minutes") or 0) / latest_dur) * 100, 1) if latest_dur > 0 else 0

    if latest_score >= 80 and sleep_debt_hours <= 2.5:
        readiness = "High (Optimal for high-intensity training)"
    elif latest_score >= 65 and sleep_debt_hours <= 5.0:
        readiness = "Moderate (Good for baseline training or active recovery)"
    else:
        readiness = "Low (Fatigue risk; prioritize sleep and low-stress activity)"

    return {
        "assessment_date": latest["date"],
        "recovery_readiness": readiness,
        "latest_night": {
            "date": latest["date"],
            "score": latest_score,
            "duration_formatted": f"{latest_dur // 60}h {latest_dur % 60}m",
            "deep_sleep_pct": f"{deep_pct}%",
            "resting_hr": latest.get("resting_hr")
        },
        "sleep_debt_hours": sleep_debt_hours,
        "historical_30d_baseline": {
            "baseline_sleep": f"{baseline['avg_sleep_minutes'] // 60}h {baseline['avg_sleep_minutes'] % 60}m",
            "baseline_score": baseline["avg_sleep_score"],
            "baseline_resting_hr": baseline["avg_resting_hr"]
        },
        "recommendation": "Well rested and recovered" if latest_score >= 75 else "Accumulated fatigue detected; recommend an earlier bedtime or light recovery."
    }

@app.tool()
def get_daily_activity(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 30
) -> List[Dict[str, Any]]:
    """
    Retrieve daily total physical activity summaries (total steps, active calories burned, distance).
    
    When to call this tool:
    - Call this tool when analyzing step goals, daily walking distance, or active energy expenditure.
    
    Parameters:
    - date_from: Optional start date (YYYY-MM-DD).
    - date_to: Optional end date (YYYY-MM-DD).
    - limit: Maximum days to retrieve (default 30, max 180).
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    # If the query requests today (or is open/unconstrained), refresh today's data from Zepp Cloud if older than 2 minutes
    if (not date_to or date_to >= today_str) and (not date_from or date_from <= today_str):
        refresh_today_if_stale(max_age_seconds=120)

    limit = max(1, min(limit, 180))
    query = "SELECT date, steps, active_calories, distance_meters FROM daily_activities WHERE 1=1"
    params = []

    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)

    query += " ORDER BY date DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

    results = []
    has_today_in_results = False
    for r in rows:
        d = dict(r)
        d["distance_km"] = round(d["distance_meters"] / 1000.0, 2) if d.get("distance_meters") else 0.0
        if d.get("date") == today_str:
            has_today_in_results = True
        results.append(d)

    # If user specifically asked for today (date_from >= today) and today isn't in Zepp Cloud yet:
    if date_from and date_from >= today_str and not has_today_in_results:
        results.append({
            "date": today_str,
            "steps": 0,
            "active_calories": 0.0,
            "distance_km": 0.0,
            "sync_status": "pending_bluetooth_sync",
            "message": f"No step records found in Zepp Cloud for today ({today_str}) yet. Amazfit smartwatches upload steps via Bluetooth to the Zepp mobile app on the user's phone, which then syncs to the cloud. Please instruct the user to open their Zepp app on their phone and pull down on the Home screen to sync their watch with the cloud, then ask again."
        })

    return results

@app.tool()
def get_hourly_activity(date: str) -> Dict[str, Any]:
    """
    Retrieve hour-by-hour step distribution across 24 hours for a specific calendar date.
    
    When to call this tool:
    - Call this tool when the user asks about their movement pattern throughout the day, sedentary hours, peak walking times, or what time they exercised.
    
    Parameters:
    - date: Calendar date in YYYY-MM-DD format (e.g. '2026-11-12').
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    if date == today_str:
        refresh_today_hourly_if_stale(max_age_seconds=120)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT hour, steps, datetime_str FROM hourly_activities WHERE date = ? ORDER BY hour ASC", (date,))
        rows = cursor.fetchall()

    if not rows:
        return {"date": date, "message": "No hourly activity data found for this date.", "hours": []}

    hours = [dict(r) for r in rows]
    total_steps = sum(h["steps"] for h in hours)
    peak_hour = max(hours, key=lambda x: x["steps"]) if hours else None

    return {
        "date": date,
        "total_day_steps": total_steps,
        "peak_active_hour": peak_hour["hour"] if peak_hour else None,
        "peak_hour_steps": peak_hour["steps"] if peak_hour else 0,
        "hourly_breakdown": hours
    }

@app.tool()
def sync_zepp_data(days: int = 30) -> Dict[str, Any]:
    """
    Trigger live cloud synchronization from Zepp Open Platform to local SQLite.
    
    When to call this tool:
    - Call this tool ONLY when the user explicitly mentions they completed a workout, or asks to refresh/fetch latest records.
    
    Parameters:
    - days: Number of historical days to probe and sync (default 30, range 1 to 365).
    """
    days = max(1, min(days, 365))
    try:
        session = get_session() or {}
        if session.get("is_demo"):
            return {
                "status": "success",
                "message": f"Demo mode active: synthetic biometric telemetry for the past {days} days is already present in SQLite.",
                "synced_counts": {"sleep": days, "daily_activity": days, "workouts": max(1, days // 3)}
            }
        token = get_valid_access_token()
        engine = ZeppDataSyncEngine(token)
        counts = engine.sync_all(days=days)
        return {
            "status": "success",
            "message": f"Successfully synchronized past {days} days of data from Zepp Cloud into SQLite.",
            "synced_counts": counts
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to sync with Zepp Cloud: {str(e)}"
        }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Amazfit Health Lens MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="Transport mode (stdio for Claude Desktop, sse for ChatGPT)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind for SSE transport (default: 0.0.0.0)")
    parser.add_argument("--demo", action="store_true", help="Populate SQLite with 90 days of synthetic biometric telemetry for zero-hardware evaluation")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind for SSE transport (default: 8001)")
    args = parser.parse_args()

    if args.demo:
        from seed_demo_data import seed_demo_data
        seed_demo_data(days=90)

    if args.transport == "sse":
        print("=" * 60)
        print(f" Amazfit Health Lens MCP Server (SSE Transport)")
        print("=" * 60)
        print(f"Listening on: http://{args.host}:{args.port}")
        print(f"SSE Endpoint: http://127.0.0.1:{args.port}/sse")
        print(f"Ready for ChatGPT / MCP Clients via tunnel or local URL.")
        print("=" * 60)
        app.run(transport="sse", host=args.host, port=args.port, sse_path="/sse", message_path="/messages/")
    else:
        # Default: stdio transport for Claude Desktop
        app.run(transport="stdio")
