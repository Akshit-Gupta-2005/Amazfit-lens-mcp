import datetime
from typing import Dict, Any, List, Optional

def parse_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        f = float(val)
        return int(round(f))
    except (ValueError, TypeError):
        return None

def parse_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def normalize_sport_type(raw_type: str) -> str:
    """Map Zepp official sport strings to standardized lowercase identifiers."""
    upper = (raw_type or "").strip().upper()
    mapping = {
        "OUTDOOR_RUN": "run",
        "OUTDOOR_RUNNING": "run",
        "RUNNING": "run",
        "TREADMILL": "treadmill",
        "INDOOR_RUN": "treadmill",
        "INDOOR_RUNNING": "treadmill",
        "WALKING": "walking",
        "OUTDOOR_WALKING": "walking",
        "INDOOR_WALKING": "indoor_walking",
        "OUTDOOR_CYCLING": "ride",
        "CYCLING": "ride",
        "INDOOR_CYCLING": "indoor_cycling",
        "MOUNTAINEER": "hiking",
        "MOUNTAINEERING": "hiking",
        "HIKING": "hiking",
        "TRAIL_RUN": "trail_running",
        "TRAIL_RUNNING": "trail_running",
        "POOL_SWIMMING": "pool_swimming",
        "OPEN_WATER_SWIMMING": "open_water_swimming",
        "CIRCUIT_MODE": "circuit_training",
        "CIRCUIT": "circuit_training",
        "FOOTBALL": "football",
        "SOCCER": "football",
        "OUTDOOR_FOOTBALL": "football",
        "OUTDOOR_SOCCER": "football",
        "INDOOR_FOOTBALL": "indoor_football",
        "INDOOR_SOCCER": "indoor_football",
        "BASKETBALL": "basketball",
        "BADMINTON": "badminton",
        "TENNIS": "tennis",
        "TABLE_TENNIS": "table_tennis",
        "CRICKET": "cricket",
        "VOLLEYBALL": "volleyball",
        "STRENGTH_TRAINING": "strength",
        "STRENGTH": "strength",
        "FREE_TRAINING": "free_training",
        "YOGA": "yoga",
        "ROCK_CLIMBING": "rock_climbing",
        "ACTIVITY": "activity"
    }
    return mapping.get(upper, raw_type.lower() if raw_type else "workout")

def map_sleep_stage_name(mode: int) -> str:
    """Map Zepp raw stage numbers to human-readable sleep stages."""
    # Zepp official mode encoding
    stages = {
        1: "deep",
        2: "light",
        3: "rem",
        4: "awake",
        5: "awake"
    }
    return stages.get(mode, "unknown")

class Normalizer:
    
    @staticmethod
    def extract_items(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("items", "data", "list", "sleeps", "activities", "sports", "records"):
                val = payload.get(key)
                if isinstance(val, list):
                    return val
        return []

    @staticmethod
    def normalize_sleep(raw: Any) -> List[Dict[str, Any]]:
        items = Normalizer.extract_items(raw)
        results = []
        for item in items:
            start = parse_int(item.get("start"))
            stop = parse_int(item.get("stop"))
            if not start or not stop or stop <= start:
                continue
                
            # Date of sleep is typically assigned to wake-up date
            wake_dt = datetime.datetime.fromtimestamp(stop)
            date_str = wake_dt.strftime("%Y-%m-%d")
            
            deep = parse_int(item.get("deepSleepTime"))
            light = parse_int(item.get("shallowSleepTime"))
            awake = parse_int(item.get("wakeTime"))
            rem = parse_int(item.get("rem"))
            score = parse_int(item.get("sleepScore") or item.get("score"))
            resting_hr = parse_int(item.get("restingHeartRate") or item.get("avgHeartRate"))
            
            span_minutes = (stop - start) // 60
            
            # If awake was tracked, net duration = total span - awake
            if awake is not None:
                duration_minutes = max(0, span_minutes - awake)
            elif deep is not None and light is not None:
                duration_minutes = (deep or 0) + (light or 0) + (rem or 0)
            else:
                duration_minutes = span_minutes
                
            # Parse nap stages if present
            naps = item.get("napStage") or []
            nap_minutes = 0
            if isinstance(naps, list):
                for nap in naps:
                    n_start = parse_int(nap.get("start"))
                    n_stop = parse_int(nap.get("stop"))
                    if n_start is not None and n_stop is not None and n_stop >= n_start:
                        nap_minutes += (n_stop - n_start + 1)
                        
            # Parse sleep stage timeline slices
            stage_slices = []
            raw_stages = item.get("stage") or []
            if isinstance(raw_stages, list):
                for st in raw_stages:
                    m = parse_int(st.get("mode"))
                    s_min = parse_int(st.get("start"))
                    e_min = parse_int(st.get("stop"))
                    if m is not None and s_min is not None and e_min is not None:
                        stage_slices.append({
                            "stage": map_sleep_stage_name(m),
                            "start_offset_minutes": s_min,
                            "stop_offset_minutes": e_min,
                            "raw_mode": m
                        })
                        
            results.append({
                "sleep_id": f"official:{start}",
                "date": date_str,
                "start_time": start,
                "end_time": stop,
                "duration_minutes": duration_minutes,
                "deep_minutes": deep,
                "light_minutes": light,
                "rem_minutes": rem,
                "awake_minutes": awake,
                "score": score,
                "resting_hr": resting_hr,
                "naps_count": len(naps) if isinstance(naps, list) else 0,
                "nap_total_minutes": nap_minutes,
                "stages": stage_slices
            })
        return results

    @staticmethod
    def normalize_daily_activity(raw: Any) -> List[Dict[str, Any]]:
        items = Normalizer.extract_items(raw)
        results = []
        for item in items:
            date_str = item.get("date") or item.get("day")
            if not date_str:
                continue
            steps = parse_int(item.get("steps") or item.get("step")) or 0
            cals = parse_float(item.get("calories") or item.get("calorie")) or 0.0
            dist = parse_float(item.get("distance")) or 0.0
            
            results.append({
                "date": str(date_str),
                "steps": steps,
                "active_calories": cals,
                "distance_meters": dist
            })
        return results

    @staticmethod
    def normalize_hourly_activity(raw: Any) -> List[Dict[str, Any]]:
        items = Normalizer.extract_items(raw)
        results = []
        for item in items:
            date_str = item.get("date")
            hour = parse_int(item.get("hour"))
            if not date_str or hour is None or not (0 <= hour <= 23):
                continue
            steps = parse_int(item.get("steps")) or 0
            results.append({
                "date": str(date_str),
                "hour": hour,
                "steps": steps
            })
        return results

    @staticmethod
    def normalize_heart_rate(raw: Any) -> List[Dict[str, Any]]:
        items = Normalizer.extract_items(raw)
        results = []
        for item in items:
            ts = parse_int(item.get("timestamp"))
            bpm = parse_int(item.get("heartRateData") or item.get("heartRate"))
            if not ts or not bpm or not (25 <= bpm <= 250):
                continue
            dt = datetime.datetime.fromtimestamp(ts)
            results.append({
                "timestamp": ts,
                "date": dt.strftime("%Y-%m-%d"),
                "bpm": bpm
            })
        return results

    @staticmethod
    def normalize_workouts(raw: Any) -> List[Dict[str, Any]]:
        items = Normalizer.extract_items(raw)
        results = []
        for item in items:
            track_id = str(item.get("trackId") or item.get("trackid") or item.get("id") or "")
            if not track_id:
                continue
                
            raw_sport = item.get("type") or item.get("sportType") or item.get("sport") or "RUN"
            sport_norm = normalize_sport_type(str(raw_sport))
            
            start = parse_int(item.get("startTime") or item.get("startTrackId")) or 0
            end = parse_int(item.get("endTime") or item.get("stopTrackId")) or start
            
            # Format calendar date string
            date_str = ""
            if start > 0:
                try:
                    date_str = datetime.datetime.fromtimestamp(start).strftime("%Y-%m-%d")
                except Exception:
                    date_str = ""
            
            # Duration in seconds (Zepp uses sportTime)
            dur = parse_int(item.get("sportTime") or item.get("costTime") or item.get("duration"))
            if dur is None and end > start:
                dur = end - start
            dur = dur or 0
            
            dist = parse_float(item.get("distance") or (item.get("distanceInCentimeter", 0) / 100.0 if item.get("distanceInCentimeter") else 0.0)) or 0.0
            cal = parse_float(item.get("calories") or item.get("calorie")) or 0.0
            
            # Heart rate: Zepp uses averageHeartRate
            avg_hr = parse_int(item.get("averageHeartRate") or item.get("avgHeartRate") or item.get("avg_hr"))
            max_hr = parse_int(item.get("maxHeartRate") or item.get("maximumHeartRate") or item.get("max_hr"))
            
            # Pace: Zepp returns raw averagePace in seconds per meter (e.g. 0.896)
            # Standard pace is stored in seconds per kilometer (e.g. 896 s/km)
            raw_pace = parse_float(item.get("averagePace") or item.get("avg_pace"))
            if raw_pace and raw_pace > 0:
                if raw_pace < 50.0:  # seconds per meter -> convert to seconds per km
                    avg_pace_sec = int(round(raw_pace * 1000.0))
                else:
                    avg_pace_sec = int(round(raw_pace))
            elif dist > 0 and dur > 0:
                avg_pace_sec = int(round(dur / (dist / 1000.0)))
            else:
                avg_pace_sec = None
                
            cadence = parse_int(item.get("averageStepFrequency") or item.get("avg_cadence"))
            stride = parse_int(item.get("averageStrideLength") or item.get("avg_stride_length"))
            total_steps = parse_int(item.get("totalStep") or item.get("steps") or item.get("step") or 0)
            
            results.append({
                "workout_id": track_id,
                "sport_type": sport_norm,
                "date": date_str,
                "start_time": start,
                "end_time": end,
                "duration_seconds": dur,
                "distance_meters": dist,
                "calories": cal,
                "avg_hr": avg_hr,
                "max_hr": max_hr,
                "avg_pace_seconds": avg_pace_sec,
                "avg_cadence": cadence,
                "avg_stride_length_cm": stride,
                "total_steps": total_steps,
                "raw": item
            })
        return results
