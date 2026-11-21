import datetime
import time
from typing import Dict, Any, List, Tuple
import requests

from db import (
    save_daily_activities,
    save_hourly_activities,
    save_sleep_sessions,
    save_heart_rate_records,
    save_workouts,
    update_sync_meta
)
from normalizer import Normalizer

ZEPP_API_BASE = "https://api-open.zepp.com"

def date_chunks(start_date: datetime.date, end_date: datetime.date, chunk_days: int) -> List[Tuple[datetime.date, datetime.date]]:
    """Split a date window [start_date, end_date] into smaller chunks (newest first)."""
    chunks = []
    curr_end = end_date
    while curr_end >= start_date:
        curr_start = max(start_date, curr_end - datetime.timedelta(days=chunk_days - 1))
        chunks.append((curr_start, curr_end))
        curr_end = curr_start - datetime.timedelta(days=1)
    return chunks

class ZeppDataSyncEngine:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "Vitalens-Bridge/1.0"
        }

    def _get(self, path: str, params: Dict[str, Any] = None) -> Any:
        url = f"{ZEPP_API_BASE}{path}"
        resp = requests.get(url, params=params, headers=self.headers, timeout=25)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code in (400, 404):
            # Endpoint may not be active for this account/region
            return {}
        else:
            print(f"Warning: Zepp API {path} returned status {resp.status_code}")
            return {}

    def sync_sleep(self, start_date: datetime.date, end_date: datetime.date) -> int:
        chunks = date_chunks(start_date, end_date, 90)
        total_normalized = 0
        now_ts = int(time.time())
        
        for c_start, c_end in chunks:
            raw = self._get("/users/-/sleep", {
                "interval": "daily",
                "startDate": c_start.strftime("%Y-%m-%d"),
                "endDate": c_end.strftime("%Y-%m-%d")
            })
            records = Normalizer.normalize_sleep(raw)
            if records:
                save_sleep_sessions(records, now_ts)
                total_normalized += len(records)
                
        update_sync_meta("sleep", total_normalized, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), now_ts)
        return total_normalized

    def sync_daily_activity(self, start_date: datetime.date, end_date: datetime.date) -> int:
        chunks = date_chunks(start_date, end_date, 90)
        total_normalized = 0
        now_ts = int(time.time())
        
        for c_start, c_end in chunks:
            raw = self._get("/users/-/activities", {
                "interval": "daily",
                "startDate": c_start.strftime("%Y-%m-%d"),
                "endDate": c_end.strftime("%Y-%m-%d")
            })
            records = Normalizer.normalize_daily_activity(raw)
            if records:
                save_daily_activities(records, now_ts)
                total_normalized += len(records)
                
        update_sync_meta("daily_activity", total_normalized, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), now_ts)
        return total_normalized

    def sync_hourly_activity(self, start_date: datetime.date, end_date: datetime.date) -> int:
        # Hourly activity: keep to recent 14-30 days to avoid overloading
        chunks = date_chunks(start_date, end_date, 30)
        total_normalized = 0
        now_ts = int(time.time())
        
        for c_start, c_end in chunks:
            raw = self._get("/users/-/activities", {
                "interval": "hourly",
                "startDate": c_start.strftime("%Y-%m-%d"),
                "endDate": c_end.strftime("%Y-%m-%d")
            })
            records = Normalizer.normalize_hourly_activity(raw)
            if records:
                save_hourly_activities(records, now_ts)
                total_normalized += len(records)
                
        update_sync_meta("hourly_activity", total_normalized, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), now_ts)
        return total_normalized

    def sync_heart_rate(self, start_date: datetime.date, end_date: datetime.date) -> int:
        # Heart rate is 1440 points/day: query in 7-day chunks (ZeppBridge convention)
        chunks = date_chunks(start_date, end_date, 7)
        total_normalized = 0
        now_ts = int(time.time())
        
        for c_start, c_end in chunks:
            raw = self._get("/users/-/heartrates", {
                "type": "ALL",
                "timezone": "UTC",
                "startDate": c_start.strftime("%Y-%m-%d"),
                "endDate": c_end.strftime("%Y-%m-%d")
            })
            records = Normalizer.normalize_heart_rate(raw)
            if records:
                save_heart_rate_records(records, now_ts)
                total_normalized += len(records)
                
        update_sync_meta("heart_rate", total_normalized, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), now_ts)
        return total_normalized

    def sync_workouts(self, start_date: datetime.date, end_date: datetime.date) -> int:
        chunks = date_chunks(start_date, end_date, 90)
        total_normalized = 0
        now_ts = int(time.time())
        
        for c_start, c_end in chunks:
            raw = self._get("/users/-/sports", {
                "timezone": "UTC",
                "startDate": c_start.strftime("%Y-%m-%d"),
                "endDate": c_end.strftime("%Y-%m-%d")
            })
            records = Normalizer.normalize_workouts(raw)
            if records:
                save_workouts(records, now_ts)
                total_normalized += len(records)
                
        update_sync_meta("workouts", total_normalized, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), now_ts)
        return total_normalized

    def sync_all(self, days: int = 90) -> Dict[str, Any]:
        """Execute full multi-category synchronization and populate SQLite."""
        today = datetime.date.today()
        start_date = today - datetime.timedelta(days=days - 1)
        
        results = {}
        # 1. Sleep
        results["sleep"] = self.sync_sleep(start_date, today)
        # 2. Daily activity
        results["daily_activity"] = self.sync_daily_activity(start_date, today)
        # 3. Hourly activity (past 14 days)
        hourly_start = max(start_date, today - datetime.timedelta(days=14))
        results["hourly_activity"] = self.sync_hourly_activity(hourly_start, today)
        # 4. Heart rate (past 14 days by default for speed, or full window)
        hr_start = max(start_date, today - datetime.timedelta(days=14))
        results["heart_rate"] = self.sync_heart_rate(hr_start, today)
        # 5. Workouts (Sync up to full year window to capture all historical athletic records)
        workout_start = min(start_date, today - datetime.timedelta(days=365))
        results["workouts"] = self.sync_workouts(workout_start, today)
        
        return results
