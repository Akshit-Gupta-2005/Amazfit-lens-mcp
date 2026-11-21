import os
import sys
import time
import threading
import datetime
from typing import Optional, Dict, Any

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from db import get_connection

_sync_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_sync_lock = threading.Lock()

def get_session():
    from server import get_session as _gs
    return _gs()

def get_valid_access_token():
    from server import get_valid_access_token as _gt
    return _gt()

def log(msg: str):
    """Log to stderr so stdio JSON-RPC transport for Claude Desktop is never contaminated."""
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()

def is_sync_due(min_interval_seconds: int = 3600) -> bool:
    """Return True if the last recorded sync was more than min_interval_seconds ago."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(last_synced_at) FROM sync_meta")
            row = cursor.fetchone()
            if not row or not row[0]:
                return True
            last_sync = row[0]
            elapsed = time.time() - last_sync
            return elapsed >= min_interval_seconds
    except Exception as e:
        log(f"[AutoSync] is_sync_due check error: {e}")
        return True

def trigger_sync(days: int = 14, force: bool = False, reason: str = "auto") -> Optional[Dict[str, Any]]:
    """
    Attempt to run synchronization from Zepp Cloud into SQLite.
    Skips if another sync is currently running or if sync is not yet due (unless force=True).
    """
    if not _sync_lock.acquire(blocking=False):
        log(f"[AutoSync] Sync already running in another thread ({reason}), skipping duplicate trigger.")
        return None

    try:
        session = get_session()
        if not session or not session.get("access_token"):
            log(f"[AutoSync] [{reason}] No authenticated Zepp session found. Waiting for user login.")
            return None

        # Check if due (unless forced)
        if not force:
            min_gap = 600 if reason == "startup" else 3500
            if not is_sync_due(min_interval_seconds=min_gap):
                log(f"[AutoSync] [{reason}] Recent sync already up to date (< {min_gap}s ago). Skipping.")
                return None

        from fetcher import ZeppDataSyncEngine

        token = get_valid_access_token()
        engine = ZeppDataSyncEngine(token)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log(f"[AutoSync] [{now_str}] Executing sync ({reason}, days={days})...")
        counts = engine.sync_all(days=days)
        log(f"[AutoSync] [{now_str}] Sync complete: {counts}")
        return counts
    except Exception as e:
        log(f"[AutoSync] Sync error during {reason}: {e}")
        return None
    finally:
        _sync_lock.release()

def _worker_loop(interval_seconds: int, startup_sync: bool, startup_days: int, periodic_days: int):
    # 1. Startup sync: run shortly after process boot
    if startup_sync:
        time.sleep(2)  # Short pause to let server bind sockets
        trigger_sync(days=startup_days, force=False, reason="startup")

    # 2. Hourly periodic sync loop
    while not _stop_event.is_set():
        # Sleep in 5s increments to be responsive to termination
        for _ in range(int(interval_seconds // 5)):
            if _stop_event.is_set():
                return
            time.sleep(5)

        trigger_sync(days=periodic_days, force=False, reason="hourly-cron")

def start_auto_sync(
    interval_seconds: int = 3600,
    startup_sync: bool = True,
    startup_days: int = 30,
    periodic_days: int = 14
):
    """
    Start the background auto-sync worker thread if not already running.
    """
    global _sync_thread
    if _sync_thread and _sync_thread.is_alive():
        return

    _stop_event.clear()
    _sync_thread = threading.Thread(
        target=_worker_loop,
        args=(interval_seconds, startup_sync, startup_days, periodic_days),
        daemon=True,
        name="ZeppAutoSyncWorker"
    )
    _sync_thread.start()
    log(f"[AutoSync] Background auto-sync worker initialized (interval={interval_seconds}s, startup={startup_sync}).")

def stop_auto_sync():
    """Stop the background worker."""
    global _sync_thread
    _stop_event.set()
    if _sync_thread:
        _sync_thread = None
