import sqlite3
import os
import json
from typing import Dict, Any, List, Optional, Tuple

DB_PATH = os.path.join(os.path.dirname(__file__), "zepp_data.sqlite")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize structured SQLite tables matching ZeppBridge's data contract."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Daily Activities (steps, calories, distance)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_activities (
                date TEXT PRIMARY KEY,
                steps INTEGER NOT NULL DEFAULT 0,
                active_calories REAL NOT NULL DEFAULT 0.0,
                distance_meters REAL NOT NULL DEFAULT 0.0,
                synced_at INTEGER NOT NULL
            )
        """)
        
        # 2. Hourly Activity Samples (hourly steps curve)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hourly_activities (
                datetime_str TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                hour INTEGER NOT NULL,
                steps INTEGER NOT NULL DEFAULT 0,
                synced_at INTEGER NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hourly_date ON hourly_activities (date)")

        # 3. Sleep Sessions (sleep duration, score, stages, resting HR)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sleep_sessions (
                sleep_id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                start_time INTEGER NOT NULL,
                end_time INTEGER NOT NULL,
                duration_minutes INTEGER NOT NULL,
                deep_minutes INTEGER,
                light_minutes INTEGER,
                rem_minutes INTEGER,
                awake_minutes INTEGER,
                score INTEGER,
                resting_hr INTEGER,
                naps_count INTEGER DEFAULT 0,
                nap_total_minutes INTEGER DEFAULT 0,
                stages_json TEXT,
                synced_at INTEGER NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sleep_date ON sleep_sessions (date)")

        # 4. Continuous Heart Rate Samples
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS heart_rate_records (
                timestamp INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                bpm INTEGER NOT NULL,
                synced_at INTEGER NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hr_date ON heart_rate_records (date)")

        # 5. Workouts & Sports Sessions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                workout_id TEXT PRIMARY KEY,
                sport_type TEXT NOT NULL,
                date TEXT NOT NULL DEFAULT '',
                start_time INTEGER NOT NULL,
                end_time INTEGER NOT NULL,
                duration_seconds INTEGER NOT NULL,
                distance_meters REAL NOT NULL DEFAULT 0.0,
                calories REAL NOT NULL DEFAULT 0.0,
                avg_hr INTEGER,
                max_hr INTEGER,
                avg_pace_seconds INTEGER,
                avg_cadence INTEGER,
                avg_stride_length_cm INTEGER,
                total_steps INTEGER NOT NULL DEFAULT 0,
                raw_json TEXT,
                synced_at INTEGER NOT NULL
            )
        """)
        # Migrate workouts schema if previously created without date or total_steps
        cursor.execute("PRAGMA table_info(workouts)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        if "date" not in existing_cols:
            cursor.execute("ALTER TABLE workouts ADD COLUMN date TEXT NOT NULL DEFAULT ''")
        if "total_steps" not in existing_cols:
            cursor.execute("ALTER TABLE workouts ADD COLUMN total_steps INTEGER NOT NULL DEFAULT 0")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workout_sport ON workouts (sport_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workout_time ON workouts (start_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workout_date ON workouts (date)")

        # Backfill date for any existing rows
        cursor.execute("UPDATE workouts SET date = strftime('%Y-%m-%d', datetime(start_time, 'unixepoch', 'localtime')) WHERE date = '' AND start_time > 0")

        # Cleanup obsolete PAI and Body Composition tables
        cursor.execute("DROP TABLE IF EXISTS body_records")
        cursor.execute("DROP TABLE IF EXISTS pai_records")

        # Sync metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_meta (
                category TEXT PRIMARY KEY,
                last_synced_at INTEGER NOT NULL,
                records_count INTEGER NOT NULL DEFAULT 0,
                date_from TEXT,
                date_to TEXT
            )
        """)
        cursor.execute("DELETE FROM sync_meta WHERE category IN ('body', 'pai')")
        
        conn.commit()

# --- Upsert Operations ---

def save_daily_activities(records: List[Dict[str, Any]], synced_at: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        for r in records:
            cursor.execute("""
                INSERT INTO daily_activities (date, steps, active_calories, distance_meters, synced_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    steps = excluded.steps,
                    active_calories = excluded.active_calories,
                    distance_meters = excluded.distance_meters,
                    synced_at = excluded.synced_at
            """, (r["date"], r.get("steps", 0), r.get("active_calories", 0.0), r.get("distance_meters", 0.0), synced_at))
        conn.commit()

def save_hourly_activities(records: List[Dict[str, Any]], synced_at: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        for r in records:
            dt_str = f"{r['date']} {r['hour']:02d}:00"
            cursor.execute("""
                INSERT INTO hourly_activities (datetime_str, date, hour, steps, synced_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(datetime_str) DO UPDATE SET
                    steps = excluded.steps,
                    synced_at = excluded.synced_at
            """, (dt_str, r["date"], r["hour"], r.get("steps", 0), synced_at))
        conn.commit()

def save_sleep_sessions(records: List[Dict[str, Any]], synced_at: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        for r in records:
            cursor.execute("""
                INSERT INTO sleep_sessions (
                    sleep_id, date, start_time, end_time, duration_minutes,
                    deep_minutes, light_minutes, rem_minutes, awake_minutes,
                    score, resting_hr, naps_count, nap_total_minutes, stages_json, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sleep_id) DO UPDATE SET
                    duration_minutes = excluded.duration_minutes,
                    deep_minutes = excluded.deep_minutes,
                    light_minutes = excluded.light_minutes,
                    rem_minutes = excluded.rem_minutes,
                    awake_minutes = excluded.awake_minutes,
                    score = excluded.score,
                    resting_hr = excluded.resting_hr,
                    naps_count = excluded.naps_count,
                    nap_total_minutes = excluded.nap_total_minutes,
                    stages_json = excluded.stages_json,
                    synced_at = excluded.synced_at
            """, (
                r["sleep_id"], r["date"], r["start_time"], r["end_time"], r["duration_minutes"],
                r.get("deep_minutes"), r.get("light_minutes"), r.get("rem_minutes"), r.get("awake_minutes"),
                r.get("score"), r.get("resting_hr"), r.get("naps_count", 0), r.get("nap_total_minutes", 0),
                json.dumps(r.get("stages", [])), synced_at
            ))
        conn.commit()

def save_heart_rate_records(records: List[Dict[str, Any]], synced_at: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        for r in records:
            cursor.execute("""
                INSERT INTO heart_rate_records (timestamp, date, bpm, synced_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(timestamp) DO UPDATE SET
                    bpm = excluded.bpm,
                    synced_at = excluded.synced_at
            """, (r["timestamp"], r["date"], r["bpm"], synced_at))
        conn.commit()

def save_workouts(records: List[Dict[str, Any]], synced_at: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        for r in records:
            cursor.execute("""
                INSERT INTO workouts (
                    workout_id, sport_type, date, start_time, end_time, duration_seconds,
                    distance_meters, calories, avg_hr, max_hr, avg_pace_seconds,
                    avg_cadence, avg_stride_length_cm, total_steps, raw_json, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workout_id) DO UPDATE SET
                    sport_type = excluded.sport_type,
                    date = excluded.date,
                    duration_seconds = excluded.duration_seconds,
                    distance_meters = excluded.distance_meters,
                    calories = excluded.calories,
                    avg_hr = excluded.avg_hr,
                    max_hr = excluded.max_hr,
                    avg_pace_seconds = excluded.avg_pace_seconds,
                    avg_cadence = excluded.avg_cadence,
                    avg_stride_length_cm = excluded.avg_stride_length_cm,
                    total_steps = excluded.total_steps,
                    raw_json = excluded.raw_json,
                    synced_at = excluded.synced_at
            """, (
                r["workout_id"], r["sport_type"], r.get("date", ""), r["start_time"], r["end_time"], r["duration_seconds"],
                r.get("distance_meters", 0.0), r.get("calories", 0.0), r.get("avg_hr"), r.get("max_hr"),
                r.get("avg_pace_seconds"), r.get("avg_cadence"), r.get("avg_stride_length_cm"),
                r.get("total_steps", 0), json.dumps(r.get("raw", {})), synced_at
            ))
        conn.commit()

def update_sync_meta(category: str, count: int, date_from: Optional[str], date_to: Optional[str], synced_at: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sync_meta (category, last_synced_at, records_count, date_from, date_to)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(category) DO UPDATE SET
                last_synced_at = excluded.last_synced_at,
                records_count = excluded.records_count,
                date_from = excluded.date_from,
                date_to = excluded.date_to
        """, (category, synced_at, count, date_from, date_to))
        conn.commit()

# --- Category Stats & Schema Inspection for MCP ---

def get_categories_overview() -> List[Dict[str, Any]]:
    """Returns structured summary of each data domain for the MCP server catalog."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        categories = [
            {
                "id": "sleep",
                "name": "Sleep & Recovery",
                "icon": "😴",
                "description": "Daily nocturnal sleep sessions, stages (Deep, Light, REM, Awake), sleep score, resting HR, and naps.",
                "mcp_intent": "Use to analyze user recovery, circadian rhythms, sleep quality trends, and resting heart rate.",
                "table": "sleep_sessions",
                "date_col": "date",
                "schema": [
                    {"field": "date", "type": "string (YYYY-MM-DD)", "desc": "Date of morning awakening"},
                    {"field": "duration_minutes", "type": "integer", "desc": "Total time asleep in minutes"},
                    {"field": "deep_minutes", "type": "integer", "desc": "Slow-wave deep sleep minutes"},
                    {"field": "light_minutes", "type": "integer", "desc": "Light sleep minutes"},
                    {"field": "rem_minutes", "type": "integer", "desc": "Rapid Eye Movement (REM) dream sleep minutes"},
                    {"field": "awake_minutes", "type": "integer", "desc": "Awake time during the night in minutes"},
                    {"field": "score", "type": "integer (1-100)", "desc": "Algorithmic sleep quality score"},
                    {"field": "resting_hr", "type": "integer (bpm)", "desc": "Resting heart rate during sleep"},
                    {"field": "naps_count", "type": "integer", "desc": "Number of afternoon/day naps"},
                    {"field": "stages", "type": "array of stage slices", "desc": "Full chronological timeline of sleep stages"}
                ]
            },
            {
                "id": "daily_activity",
                "name": "Daily Activity Summaries",
                "icon": "🚶",
                "description": "Daily total step count, active calorie burn, and cumulative walking/running distance.",
                "mcp_intent": "Use to monitor daily physical movement volume, active energy expenditure, and distance progress.",
                "table": "daily_activities",
                "date_col": "date",
                "schema": [
                    {"field": "date", "type": "string (YYYY-MM-DD)", "desc": "Calendar date"},
                    {"field": "steps", "type": "integer", "desc": "Total daily step count"},
                    {"field": "active_calories", "type": "float (kcal)", "desc": "Active calorie burn from movement"},
                    {"field": "distance_meters", "type": "float (meters)", "desc": "Total distance traveled on foot"}
                ]
            },
            {
                "id": "hourly_activity",
                "name": "Hourly Activity Distribution",
                "icon": "⏱️",
                "description": "Hourly step breakdown across 24 hours per day.",
                "mcp_intent": "Use to detect sedentary periods, peak active hours, and intra-day movement habits.",
                "table": "hourly_activities",
                "date_col": "date",
                "schema": [
                    {"field": "datetime_str", "type": "string (YYYY-MM-DD HH:00)", "desc": "Hour identifier"},
                    {"field": "date", "type": "string (YYYY-MM-DD)", "desc": "Calendar date"},
                    {"field": "hour", "type": "integer (0-23)", "desc": "Hour of the day"},
                    {"field": "steps", "type": "integer", "desc": "Steps walked within that specific hour"}
                ]
            },
            {
                "id": "heart_rate",
                "name": "Continuous Heart Rate Series",
                "icon": "❤️",
                "description": "Minute-by-minute continuous heart rate measurements recorded throughout the day and night.",
                "mcp_intent": "Use for high-resolution cardiovascular tracking, detecting spikes, and resting baseline analysis.",
                "table": "heart_rate_records",
                "date_col": "date",
                "schema": [
                    {"field": "timestamp", "type": "integer (unix epoch)", "desc": "UTC epoch timestamp of measurement"},
                    {"field": "date", "type": "string (YYYY-MM-DD)", "desc": "Calendar date"},
                    {"field": "bpm", "type": "integer (25-250)", "desc": "Heart rate reading in beats per minute"}
                ]
            },
            {
                "id": "workouts",
                "name": "Workouts & Sports Sessions",
                "icon": "🏃",
                "description": "Structured workout logs across all sports (running, cycling, walking, treadmill, hiking, etc.).",
                "mcp_intent": "Use to analyze athletic training sessions, cadence, splits, intensity, and cardio workload.",
                "table": "workouts",
                "date_col": "date",
                "schema": [
                    {"field": "workout_id", "type": "string", "desc": "Unique workout track ID"},
                    {"field": "sport_type", "type": "string", "desc": "Normalized sport name (run, walking, circuit_training, etc.)"},
                    {"field": "date", "type": "string (YYYY-MM-DD)", "desc": "Calendar date of workout"},
                    {"field": "start_time", "type": "integer (unix epoch)", "desc": "Session start timestamp"},
                    {"field": "end_time", "type": "integer (unix epoch)", "desc": "Session completion timestamp"},
                    {"field": "duration_seconds", "type": "integer", "desc": "Net active duration in seconds"},
                    {"field": "distance_meters", "type": "float", "desc": "Total distance traveled in meters"},
                    {"field": "calories", "type": "float (kcal)", "desc": "Calories burned during workout"},
                    {"field": "avg_hr", "type": "integer (bpm)", "desc": "Average heart rate"},
                    {"field": "max_hr", "type": "integer (bpm)", "desc": "Peak heart rate"},
                    {"field": "avg_pace_seconds", "type": "integer (sec/km)", "desc": "Average pace in seconds per kilometer"},
                    {"field": "avg_cadence", "type": "integer (spm/rpm)", "desc": "Average cadence (steps/reps per minute)"},
                    {"field": "avg_stride_length_cm", "type": "integer (cm)", "desc": "Average stride length in centimeters"},
                    {"field": "total_steps", "type": "integer", "desc": "Total steps completed in session"}
                ]
            }
        ]
        
        result = []
        for cat in categories:
            table = cat["table"]
            # Total count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            
            date_from = None
            date_to = None
            if count > 0:
                dcol = cat["date_col"]
                cursor.execute(f"SELECT MIN({dcol}), MAX({dcol}) FROM {table} WHERE {dcol} IS NOT NULL AND {dcol} != ''")
                row = cursor.fetchone()
                if row and row[0] and row[1]:
                    date_from = str(row[0])
                    date_to = str(row[1])
                elif cat["id"] == "workouts":
                    cursor.execute("SELECT MIN(start_time), MAX(start_time) FROM workouts")
                    wrow = cursor.fetchone()
                    if wrow and wrow[0] and wrow[1]:
                        import datetime
                        date_from = datetime.datetime.fromtimestamp(wrow[0]).strftime("%Y-%m-%d")
                        date_to = datetime.datetime.fromtimestamp(wrow[1]).strftime("%Y-%m-%d")
                    
            cat_entry = {
                "id": cat["id"],
                "name": cat["name"],
                "icon": cat["icon"],
                "description": cat["description"],
                "mcp_intent": cat["mcp_intent"],
                "total_entries": count,
                "date_range": {
                    "from": date_from,
                    "to": date_to
                },
                "status": "ready" if count > 0 else "empty",
                "schema": cat["schema"]
            }
            result.append(cat_entry)
            
        return result

def get_category_sample(category_id: str) -> Optional[Dict[str, Any]]:
    """Returns the most recent single sample record for a category."""
    records = get_category_records(category_id, limit=1)
    return records[0] if records else None

def get_category_records(category_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Returns up to `limit` most recent records for a category."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        queries = {
            "sleep": "SELECT * FROM sleep_sessions ORDER BY start_time DESC LIMIT ?",
            "daily_activity": "SELECT * FROM daily_activities ORDER BY date DESC LIMIT ?",
            "hourly_activity": "SELECT * FROM hourly_activities ORDER BY datetime_str DESC LIMIT ?",
            "heart_rate": "SELECT * FROM heart_rate_records ORDER BY timestamp DESC LIMIT ?",
            "workouts": "SELECT * FROM workouts ORDER BY start_time DESC LIMIT ?",
        }
        
        query = queries.get(category_id)
        if not query:
            return []
            
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            if "stages_json" in d and d["stages_json"]:
                try:
                    d["stages"] = json.loads(d["stages_json"])
                    del d["stages_json"]
                except Exception:
                    pass
            if "raw_json" in d and d["raw_json"]:
                try:
                    d["raw"] = json.loads(d["raw_json"])
                    del d["raw_json"]
                except Exception:
                    pass
            results.append(d)
        return results
