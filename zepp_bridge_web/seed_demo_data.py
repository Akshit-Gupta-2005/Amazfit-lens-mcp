"""
Seed Demo Biometric Data Generator for Amazfit Health Lens MCP
Enables instant reproduction, evaluation, and testing without requiring physical Zepp/Amazfit hardware.
Generates 90 days of physiologically realistic circadian activity, sleep stages, and workout telemetry.
"""

import datetime
import random
import time
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from db import (
    init_db,
    save_daily_activities,
    save_hourly_activities,
    save_sleep_sessions,
    save_heart_rate_records,
    save_workouts,
    update_sync_meta
)
from server import save_session

def _log(msg: str):
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()

def seed_demo_data(days: int = 90, clear_existing: bool = False):
    _log(f"[DemoSeed] Initializing SQLite database schema...")
    init_db()

    # Save mock profile session so session getters return a valid demo profile
    session_file = os.path.join(CURRENT_DIR, "session.json")
    if not os.path.exists(session_file):
        with open(session_file, "w", encoding="utf-8") as f:
            import json
            json.dump({
                "access_token": "DEMO_SYNTHETIC_BEARER_TOKEN",
                "refresh_token": "DEMO_SYNTHETIC_REFRESH_TOKEN",
                "user_id": "DEMO_USER_998811",
                "nickname": "Demo Athlete",
                "connected_at": int(time.time()),
                "expires_at": int(time.time()) + 86400 * 365,
                "is_demo": True
            }, f, indent=2)

    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=days - 1)
    now_ts = int(time.time())

    _log(f"[DemoSeed] Generating {days} days of synthetic biometric telemetry ({start_date} to {today})...")

    daily_records = []
    hourly_records = []
    sleep_records = []
    hr_records = []
    workout_records = []

    workout_counter = 1000

    for i in range(days):
        cur_date = start_date + datetime.timedelta(days=i)
        cur_date_str = cur_date.strftime("%Y-%m-%d")
        day_of_week = cur_date.weekday() # 5, 6 = weekend

        # 1. Daily Activities (steps, calories, distance)
        # Normal baseline ~6,000 - 12,000 steps with occasional high activity days
        is_active_day = (day_of_week in [2, 5, 6]) or (random.random() < 0.25)
        base_steps = random.randint(8500, 14000) if is_active_day else random.randint(4500, 8500)
        
        # Calculate realistic calories and distance from step count
        distance_meters = round(base_steps * 0.74, 1) # ~0.74m stride
        active_calories = round(base_steps * 0.042 + random.uniform(10, 50), 1)

        daily_records.append({
            "date": cur_date_str,
            "steps": base_steps,
            "active_calories": active_calories,
            "distance_meters": distance_meters
        })

        # 2. Hourly Activity (circadian distribution)
        # Low at night (0-6), morning peak (8-10), afternoon dip, evening peak (17-20)
        remaining_steps = base_steps
        weights = [
            0, 0, 0, 0, 0, 1, 2, 5, 9, 8, 5, 6, 7, 5, 4, 6, 8, 11, 10, 6, 4, 2, 1, 0
        ]
        total_weight = sum(weights)

        for hour in range(24):
            hour_steps = int((weights[hour] / total_weight) * base_steps + random.randint(-40, 40))
            hour_steps = max(0, hour_steps)
            dt_str = f"{cur_date_str} {hour:02d}:00:00"
            hourly_records.append({
                "datetime_str": dt_str,
                "date": cur_date_str,
                "hour": hour,
                "steps": hour_steps
            })

        # 3. Sleep Sessions
        # Sleep bedtime ~22:30 - 00:30, duration ~6.5h - 8.5h
        bedtime_hour = random.choice([22, 23, 0])
        bedtime_min = random.randint(0, 59)
        base_sleep_dt = datetime.datetime.combine(cur_date - datetime.timedelta(days=1), datetime.time(bedtime_hour, bedtime_min))
        sleep_dur_mins = random.randint(390, 520) # 6.5h to 8.6h
        wake_dt = base_sleep_dt + datetime.timedelta(minutes=sleep_dur_mins)

        deep_mins = int(sleep_dur_mins * random.uniform(0.18, 0.26))
        rem_mins = int(sleep_dur_mins * random.uniform(0.20, 0.28))
        awake_mins = random.randint(15, 35)
        light_mins = sleep_dur_mins - deep_mins - rem_mins - awake_mins

        score = min(98, max(55, int(70 + (deep_mins + rem_mins) / 6 - awake_mins / 2 + random.randint(-5, 8))))
        resting_hr = random.randint(52, 64)

        sleep_records.append({
            "sleep_id": f"demo_sleep_{cur_date_str}",
            "date": cur_date_str,
            "start_time": int(base_sleep_dt.timestamp()),
            "end_time": int(wake_dt.timestamp()),
            "duration_minutes": sleep_dur_mins,
            "deep_minutes": deep_mins,
            "light_minutes": light_mins,
            "rem_minutes": rem_mins,
            "awake_minutes": awake_mins,
            "score": score,
            "resting_hr": resting_hr,
            "naps_count": 0,
            "nap_total_minutes": 0,
            "stages_json": "[]"
        })

        # 4. Continuous Heart Rate Samples (Seed recent 14 days to preserve speed)
        if i >= (days - 14):
            day_start_ts = int(datetime.datetime.combine(cur_date, datetime.time(0, 0)).timestamp())
            for m in range(0, 1440, 10): # 10-minute intervals
                sample_ts = day_start_ts + (m * 60)
                hour_val = m // 60
                if 0 <= hour_val < 6:
                    bpm = random.randint(52, 62)
                elif hour_val in [17, 18, 19]:
                    bpm = random.randint(85, 135)
                else:
                    bpm = random.randint(65, 88)

                hr_records.append({
                    "timestamp": sample_ts,
                    "date": cur_date_str,
                    "bpm": bpm
                })

        # 5. Athletic Workouts (2-4 workouts per week)
        if is_active_day and random.random() < 0.65:
            workout_counter += 1
            sport = random.choice(["outdoor_running", "walking", "cycling", "gym_workout"])
            dur_secs = random.randint(1200, 3600) # 20m - 60m
            w_start_ts = int(datetime.datetime.combine(cur_date, datetime.time(random.choice([7, 18]), random.randint(0, 45))).timestamp())
            w_end_ts = w_start_ts + dur_secs

            if sport == "outdoor_running":
                dist_m = round(dur_secs * random.uniform(2.8, 3.5), 1)
                pace_sec = int(dur_secs / (dist_m / 1000.0))
                cals = round(dur_secs * 0.18, 1)
                avg_hr = random.randint(142, 168)
                max_hr = avg_hr + random.randint(15, 25)
                steps = int(dur_secs * 2.7)
            elif sport == "cycling":
                dist_m = round(dur_secs * random.uniform(5.5, 7.5), 1)
                pace_sec = int(dur_secs / (dist_m / 1000.0))
                cals = round(dur_secs * 0.15, 1)
                avg_hr = random.randint(128, 150)
                max_hr = avg_hr + 20
                steps = 0
            else: # walking / gym
                dist_m = round(dur_secs * 1.3, 1)
                pace_sec = int(dur_secs / (dist_m / 1000.0)) if dist_m > 0 else 0
                cals = round(dur_secs * 0.08, 1)
                avg_hr = random.randint(105, 128)
                max_hr = avg_hr + 18
                steps = int(dur_secs * 1.8)

            workout_records.append({
                "workout_id": f"demo_wk_{workout_counter}",
                "sport_type": sport,
                "date": cur_date_str,
                "start_time": w_start_ts,
                "end_time": w_end_ts,
                "duration_seconds": dur_secs,
                "distance_meters": dist_m,
                "calories": cals,
                "avg_hr": avg_hr,
                "max_hr": max_hr,
                "avg_pace_seconds": pace_sec,
                "avg_cadence": random.randint(160, 175) if sport == "outdoor_running" else None,
                "avg_stride_length_cm": 95 if sport == "outdoor_running" else None,
                "total_steps": steps,
                "raw_json": "{}"
            })

    # Commit records to SQLite
    save_daily_activities(daily_records, now_ts)
    save_hourly_activities(hourly_records, now_ts)
    save_sleep_sessions(sleep_records, now_ts)
    save_heart_rate_records(hr_records, now_ts)
    save_workouts(workout_records, now_ts)

    update_sync_meta("daily_activity", len(daily_records), start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), now_ts)
    update_sync_meta("sleep", len(sleep_records), start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), now_ts)
    update_sync_meta("workouts", len(workout_records), start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), now_ts)

    _log(f"[DemoSeed] Successfully seeded:")
    _log(f"  • {len(daily_records)} Daily Activity Summaries")
    _log(f"  • {len(hourly_records)} Hourly Activity Samples")
    _log(f"  • {len(sleep_records)} Sleep Records (Scores & Stages)")
    _log(f"  • {len(workout_records)} Athletic Workouts")
    _log(f"  • {len(hr_records)} Heart Rate Samples")
    _log(f"[DemoSeed] Database ready at: zepp_data.sqlite")

if __name__ == "__main__":
    seed_demo_data(days=90)
