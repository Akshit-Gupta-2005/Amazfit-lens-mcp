import os
import sys
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

# Initialize MCP Server
app = MCPServer("ZeppHealthMCP")

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

# --- MCP Tools ---

@app.tool()
def get_health_overview() -> Dict[str, Any]:
    """
    Get a high-level summary of all indexed health records, user account profile,
    today's activity summary, last night's sleep score, and latest workout.
    Use this first when the user asks broad questions about their health status.
    """
    session = get_session() or {}
    nickname = session.get("nickname", "User")
    user_id = session.get("user_id", "Unknown")

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
        "latest_workout": latest_workout
    }

@app.tool()
def get_workouts(
    sport: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 15
) -> List[Dict[str, Any]]:
    """
    Retrieve athletic workout logs (e.g. football/soccer, outdoor run, walking, circuit training).
    Includes net active duration, distance, calories burned, heart rate telemetry, pace, cadence, and steps.
    
    Parameters:
    - sport: Optional filter by sport type (e.g. 'football', 'soccer', 'run', 'walking', 'circuit_training').
    - date_from: Optional filter for start date (YYYY-MM-DD).
    - date_to: Optional filter for end date (YYYY-MM-DD).
    - limit: Maximum number of workout records to return (default 15, max 100).
    """
    limit = max(1, min(limit, 100))
    query = "SELECT workout_id, sport_type, date, start_time, duration_seconds, distance_meters, calories, avg_hr, max_hr, avg_pace_seconds, avg_cadence, total_steps FROM workouts WHERE 1=1"
    params = []

    if sport:
        sport_clean = sport.strip().lower()
        if sport_clean in ("soccer", "football"):
            query += " AND (sport_type LIKE '%football%' OR sport_type LIKE '%soccer%')"
        else:
            query += " AND sport_type LIKE ?"
            params.append(f"%{sport_clean}%")

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
    Retrieve nocturnal sleep logs, quality scores, resting heart rate, and sleep stage breakdowns.
    
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
def get_daily_activity(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 30
) -> List[Dict[str, Any]]:
    """
    Retrieve daily total physical activity summaries (total steps, active calories burned, distance).
    
    Parameters:
    - date_from: Optional start date (YYYY-MM-DD).
    - date_to: Optional end date (YYYY-MM-DD).
    - limit: Maximum days to retrieve (default 30, max 180).
    """
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
    for r in rows:
        d = dict(r)
        d["distance_km"] = round(d["distance_meters"] / 1000.0, 2) if d.get("distance_meters") else 0.0
        results.append(d)

    return results

@app.tool()
def get_hourly_activity(date: str) -> Dict[str, Any]:
    """
    Retrieve hour-by-hour step distribution across 24 hours for a specific calendar date.
    Use this to identify sedentary hours, peak movement times, or intra-day walking patterns.
    
    Parameters:
    - date: Calendar date in YYYY-MM-DD format (e.g. '2026-11-12').
    """
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
    Call this when the user mentions they recently completed a workout, or asks to refresh/fetch latest records.
    
    Parameters:
    - days: Number of historical days to probe and sync (default 30, range 1 to 365).
    """
    days = max(1, min(days, 365))
    try:
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
    # Run standard MCP server over Stdio transport
    app.run(transport="stdio")
