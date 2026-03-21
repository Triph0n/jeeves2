"""
Cost Tracker — Sledování nákladů na Gemini Live API.
Odhaduje tokeny z objemu přenesených audio dat (32 tokenů / sec).
Data se ukládají lokálně do JSON, s měsíčním resetem.
"""
import json
import os
import time
import datetime
import threading
from src.logger import logger

# Gemini 2.5 Flash pricing per token
PRICE_INPUT_PER_TOKEN = 0.30 / 1_000_000    # $0.30 per 1M input tokens
PRICE_OUTPUT_PER_TOKEN = 2.50 / 1_000_000   # $2.50 per 1M output tokens

# Audio tokenization: 32 tokens per second
TOKENS_PER_SECOND = 32

# Audio byte rates (16-bit mono PCM)
INPUT_BYTES_PER_SEC = 16000 * 2    # 16kHz * 2 bytes = 32,000 B/sec
OUTPUT_BYTES_PER_SEC = 24000 * 2   # 24kHz * 2 bytes = 48,000 B/sec

# Data file path
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DATA_FILE = os.path.join(DATA_DIR, "cost_history.json")

# Lock for thread safety
_lock = threading.Lock()

# Current session state
_current_session = None


def _empty_data():
    """Returns an empty data structure."""
    return {
        "current_month": datetime.datetime.now().strftime("%Y-%m"),
        "monthly_totals": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0
        },
        "sessions": [],
        "past_months": []
    }


def _load_data() -> dict:
    """Load data from JSON file."""
    if not os.path.exists(DATA_FILE):
        return _empty_data()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load cost data: {e}")
        return _empty_data()


def _save_data(data: dict):
    """Save data to JSON file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save cost data: {e}")


def _check_month_reset(data: dict) -> dict:
    """Check if we need to reset for a new month."""
    current_month = datetime.datetime.now().strftime("%Y-%m")
    
    if data.get("current_month") != current_month:
        logger.info(f"New month detected ({data.get('current_month')} → {current_month}). Archiving and resetting.")
        
        # Archive current month
        if data.get("monthly_totals", {}).get("cost_usd", 0) > 0 or data.get("sessions"):
            data.setdefault("past_months", []).append({
                "month": data.get("current_month", "unknown"),
                "input_tokens": data["monthly_totals"].get("input_tokens", 0),
                "output_tokens": data["monthly_totals"].get("output_tokens", 0),
                "cost_usd": data["monthly_totals"].get("cost_usd", 0),
                "session_count": len(data.get("sessions", []))
            })
        
        # Reset
        data["current_month"] = current_month
        data["monthly_totals"] = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        data["sessions"] = []
        _save_data(data)
    
    return data


def _bytes_to_tokens(byte_count: int, bytes_per_sec: int) -> int:
    """Convert audio bytes to estimated token count."""
    seconds = byte_count / bytes_per_sec
    return int(seconds * TOKENS_PER_SECOND)


def start_session():
    """Start tracking a new session."""
    global _current_session
    with _lock:
        _current_session = {
            "id": datetime.datetime.now().isoformat(),
            "start": datetime.datetime.now().isoformat(),
            "input_bytes": 0,
            "output_bytes": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0
        }
        logger.info("Cost tracker: new session started.")


def track_input(byte_count: int):
    """Track input audio bytes sent to Gemini."""
    global _current_session
    if _current_session is None:
        return
    with _lock:
        _current_session["input_bytes"] += byte_count
        _current_session["input_tokens"] = _bytes_to_tokens(
            _current_session["input_bytes"], INPUT_BYTES_PER_SEC
        )
        _current_session["cost_usd"] = (
            _current_session["input_tokens"] * PRICE_INPUT_PER_TOKEN +
            _current_session["output_tokens"] * PRICE_OUTPUT_PER_TOKEN
        )


def track_output(byte_count: int):
    """Track output audio bytes received from Gemini."""
    global _current_session
    if _current_session is None:
        return
    with _lock:
        _current_session["output_bytes"] += byte_count
        _current_session["output_tokens"] = _bytes_to_tokens(
            _current_session["output_bytes"], OUTPUT_BYTES_PER_SEC
        )
        _current_session["cost_usd"] = (
            _current_session["input_tokens"] * PRICE_INPUT_PER_TOKEN +
            _current_session["output_tokens"] * PRICE_OUTPUT_PER_TOKEN
        )


def end_session():
    """End the current session and save data."""
    global _current_session
    with _lock:
        if _current_session is None:
            return

        _current_session["end"] = datetime.datetime.now().isoformat()
        
        start = datetime.datetime.fromisoformat(_current_session["start"])
        end = datetime.datetime.fromisoformat(_current_session["end"])
        _current_session["duration_sec"] = int((end - start).total_seconds())

        data = _load_data()
        data = _check_month_reset(data)

        # Add session to history
        session_record = {
            "id": _current_session["id"],
            "start": _current_session["start"],
            "end": _current_session["end"],
            "duration_sec": _current_session["duration_sec"],
            "input_tokens": _current_session["input_tokens"],
            "output_tokens": _current_session["output_tokens"],
            "cost_usd": round(_current_session["cost_usd"], 6)
        }
        data["sessions"].append(session_record)

        # Update monthly totals
        data["monthly_totals"]["input_tokens"] += _current_session["input_tokens"]
        data["monthly_totals"]["output_tokens"] += _current_session["output_tokens"]
        data["monthly_totals"]["cost_usd"] = round(
            data["monthly_totals"]["cost_usd"] + _current_session["cost_usd"], 6
        )

        _save_data(data)
        logger.info(
            f"Cost tracker: session ended. "
            f"Input: {_current_session['input_tokens']} tok, "
            f"Output: {_current_session['output_tokens']} tok, "
            f"Cost: ${_current_session['cost_usd']:.6f}"
        )
        _current_session = None


def get_current_session() -> dict | None:
    """Get live data about the current session."""
    with _lock:
        if _current_session is None:
            return None
        
        start = datetime.datetime.fromisoformat(_current_session["start"])
        elapsed = int((datetime.datetime.now() - start).total_seconds())
        
        return {
            "start": _current_session["start"],
            "duration_sec": elapsed,
            "input_tokens": _current_session["input_tokens"],
            "output_tokens": _current_session["output_tokens"],
            "cost_usd": round(_current_session["cost_usd"], 6)
        }


def get_summary() -> dict:
    """Get full cost summary for the API endpoint."""
    with _lock:
        data = _load_data()
        data = _check_month_reset(data)
        
        current_session = None
        if _current_session is not None:
            start = datetime.datetime.fromisoformat(_current_session["start"])
            elapsed = int((datetime.datetime.now() - start).total_seconds())
            current_session = {
                "start": _current_session["start"],
                "duration_sec": elapsed,
                "input_tokens": _current_session["input_tokens"],
                "output_tokens": _current_session["output_tokens"],
                "cost_usd": round(_current_session["cost_usd"], 6)
            }
        
        # Calculate live monthly total (historical + current session)
        monthly = dict(data["monthly_totals"])
        if _current_session:
            monthly["input_tokens"] += _current_session["input_tokens"]
            monthly["output_tokens"] += _current_session["output_tokens"]
            monthly["cost_usd"] = round(
                monthly["cost_usd"] + _current_session["cost_usd"], 6
            )
        
        return {
            "current_month": data.get("current_month"),
            "monthly_totals": monthly,
            "session_count": len(data.get("sessions", [])) + (1 if _current_session else 0),
            "current_session": current_session,
            "recent_sessions": data.get("sessions", [])[-10:],  # Last 10 sessions
            "past_months": data.get("past_months", [])
        }
