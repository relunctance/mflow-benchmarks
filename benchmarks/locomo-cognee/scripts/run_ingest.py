#!/usr/bin/env python3
"""
Cognee LOCOMO Ingest Script
Aligned with MFlow's run_ingest_batched.py

Three-step pipeline per session:
  1. POST /api/v1/add        — add formatted text to dataset
  2. POST /api/v1/cognify    — build knowledge graph (blocking)
  3. GET /api/v1/datasets/status — confirm completion

Session serial ingest within each conversation (same as MFlow):
  Episode/entity routing needs to see prior session content.

Conversation parallel ingest across batches (same as MFlow's 3-3-4 strategy).

Time handling (identical to MFlow):
  - Parse LOCOMO timestamps ("1:56 pm on 8 May, 2023") to datetime
  - Add time prefix to each message: "[May 08, 2023, 1:56 PM] Speaker: text"
  - Include blip_caption for image descriptions

Dataset naming (identical to MFlow):
  locomo_benchmark_{speaker_a}_{speaker_b}_{idx}

Usage:
    python run_ingest.py --data dataset/locomo10.json
    python run_ingest.py --data dataset/locomo10.json --max 2  # first 2 conversations
    python run_ingest.py --data dataset/locomo10.json --skip-delete
"""
import json
import re
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from argparse import ArgumentParser
from typing import List, Dict, Any, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

# === Configuration ===
API_BASE = os.getenv("COGNEE_API_BASE", "https://api.cognee.ai")
API_PREFIX = os.getenv("COGNEE_API_PREFIX", "/api/v1")
API_KEY = os.getenv("COGNEE_API_KEY", "")
DATA_PATH = "dataset/locomo10.json"
DEFAULT_BATCHES = [3, 3, 4]
POLL_INTERVAL = 15
COGNIFY_TIMEOUT = 1800  # 30 min max per cognify call


def _update_poll_interval(new_val: int):
    global POLL_INTERVAL
    POLL_INTERVAL = new_val

# LOCOMO time format: "1:56 pm on 8 May, 2023"
LOCOMO_TIME_PATTERN = re.compile(
    r"(\d{1,2}):(\d{2})\s*(am|pm)\s+on\s+(\d{1,2})\s+(\w+),?\s*(\d{4})",
    re.IGNORECASE,
)

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


# ================================================================
# Time parsing — identical to MFlow
# ================================================================

def parse_locomo_datetime(time_str: str) -> Optional[datetime]:
    if not time_str:
        return None
    time_str = time_str.strip()

    iso_patterns = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d",
    ]
    for pattern in iso_patterns:
        try:
            dt = datetime.strptime(time_str, pattern)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    match = LOCOMO_TIME_PATTERN.search(time_str)
    if match:
        hour, minute, meridiem, day, month_name, year = match.groups()
        hour = int(hour)
        minute = int(minute)
        if meridiem.lower() == "pm" and hour != 12:
            hour += 12
        elif meridiem.lower() == "am" and hour == 12:
            hour = 0
        month = MONTH_MAP.get(month_name.lower())
        if month:
            try:
                return datetime(
                    year=int(year), month=month, day=int(day),
                    hour=hour, minute=minute, tzinfo=timezone.utc,
                )
            except ValueError:
                pass
    return None


def format_date_for_message(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.strftime("[%B %d, %Y, %I:%M %p]")


# ================================================================
# Cognee API helpers
# ================================================================

def cognee_headers() -> dict:
    return {
        "X-Api-Key": API_KEY,
    }


def cognee_health_check() -> bool:
    try:
        r = requests.get(f"{API_BASE}/api/health", headers=cognee_headers(), timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"  Health check failed: {e}")
        return False


def cognee_get_datasets() -> List[Dict]:
    r = requests.get(f"{API_BASE}{API_PREFIX}/datasets", headers=cognee_headers(), timeout=30)
    if r.status_code == 200:
        return r.json()
    print(f"  Get datasets failed: {r.status_code} {r.text[:200]}")
    return []


def cognee_delete_dataset(dataset_id: str) -> bool:
    r = requests.delete(
        f"{API_BASE}{API_PREFIX}/datasets/{dataset_id}",
        headers=cognee_headers(), timeout=30,
    )
    return r.status_code == 200


def cognee_add_text(content: str, dataset_name: str, file_label: str = "session") -> Tuple[bool, Any]:
    """
    Add text content to a Cognee dataset.
    Uses multipart/form-data with text as file data.
    Each call MUST use a unique file_label to avoid Cognee's content dedup
    overwriting prior uploads within the same dataset.
    """
    filename = f"{dataset_name}_{file_label}.txt"
    files = [("data", (filename, content.encode("utf-8"), "text/plain"))]
    data = {"datasetName": dataset_name}
    try:
        r = requests.post(
            f"{API_BASE}{API_PREFIX}/add",
            files=files,
            data=data,
            headers=cognee_headers(),
            timeout=120,
        )
        if r.status_code == 200:
            return True, r.json()
        return False, {"status": r.status_code, "detail": r.text[:500]}
    except Exception as e:
        return False, {"detail": str(e)}


def cognee_cognify(dataset_name: str, run_in_background: bool = False) -> Tuple[bool, Any]:
    """
    Cognify a dataset — build knowledge graph.
    Blocking mode by default (waits for completion).
    """
    payload = {
        "datasets": [dataset_name],
        "runInBackground": run_in_background,
    }
    headers = {**cognee_headers(), "Content-Type": "application/json"}
    timeout = 30 if run_in_background else COGNIFY_TIMEOUT
    try:
        r = requests.post(
            f"{API_BASE}{API_PREFIX}/cognify",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        if r.status_code == 200:
            return True, r.json()
        return False, {"status": r.status_code, "detail": r.text[:500]}
    except requests.exceptions.Timeout:
        return False, {"detail": f"Cognify timed out after {timeout}s"}
    except Exception as e:
        return False, {"detail": str(e)}


def cognee_get_dataset_status(dataset_ids: List[str]) -> Dict[str, str]:
    """Poll dataset processing status."""
    params = [("dataset", did) for did in dataset_ids]
    try:
        r = requests.get(
            f"{API_BASE}{API_PREFIX}/datasets/status",
            params=params,
            headers=cognee_headers(),
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def wait_for_cognify(
    dataset_name: str,
    dataset_id: Optional[str] = None,
    poll_interval: int = POLL_INTERVAL,
    max_wait: int = COGNIFY_TIMEOUT,
) -> bool:
    """
    Wait for cognify to complete by polling dataset status.
    Used when cognify is run in background mode.
    """
    if not dataset_id:
        datasets = cognee_get_datasets()
        for ds in datasets:
            if ds.get("name") == dataset_name:
                dataset_id = ds["id"]
                break
        if not dataset_id:
            print(f"    Warning: dataset '{dataset_name}' not found for status check")
            return True

    start = time.time()
    while time.time() - start < max_wait:
        status_map = cognee_get_dataset_status([dataset_id])
        status = status_map.get(dataset_id, "")
        if "COMPLETED" in str(status).upper():
            return True
        if "ERROR" in str(status).upper() or "FAILED" in str(status).upper():
            print(f"    Cognify failed for {dataset_name}: {status}")
            return False
        time.sleep(poll_interval)

    print(f"    Cognify timed out for {dataset_name}")
    return False


# ================================================================
# Session formatting — identical to MFlow
# ================================================================

def format_single_session(
    conv: Dict, session_key: str, include_blip_caption: bool = True,
) -> Tuple[str, Optional[datetime]]:
    """Format one session with time prefix on each message."""
    lines = []
    ts_str = conv.get(f"{session_key}_date_time", "")
    session_dt = parse_locomo_datetime(ts_str)
    time_prefix = format_date_for_message(session_dt)

    for msg in conv.get(session_key, []):
        speaker = msg.get("speaker", "Unknown")
        text = msg.get("text", "")
        if time_prefix:
            msg_line = f"{time_prefix} {speaker}: {text}"
        else:
            msg_line = f"{speaker}: {text}"
        lines.append(msg_line)

        if include_blip_caption:
            blip_caption = msg.get("blip_caption", "")
            if blip_caption:
                lines.append(f"  [Image shared by {speaker}: {blip_caption}]")

    return "\n".join(lines), session_dt


# ================================================================
# Data loading & preparation — identical to MFlow
# ================================================================

def load_conversations(data_path: str, max_count: Optional[int] = None) -> List[Dict]:
    with open(data_path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        sorted_keys = sorted(data.keys(), key=lambda x: int(x))
        data = [data[k] for k in sorted_keys]
    if max_count:
        data = data[:max_count]
    return data


def prepare_datasets(conversations: List[Dict], run_id: str = "r3") -> List[Dict]:
    """
    Build dataset list — one entry per conversation with per-session records.
    Identical naming and formatting to MFlow's prepare_datasets().
    """
    datasets = []
    for idx, item in enumerate(conversations):
        conv = item["conversation"]

        if isinstance(conv, list):
            sessions_info = _prepare_sessions_from_list(conv)
            speakers_set = set()
            for msg in conv[:20]:
                speakers_set.add(msg.get("speaker", "Unknown"))
            speakers_list = sorted(speakers_set)
            speaker_a = speakers_list[0] if len(speakers_list) > 0 else "A"
            speaker_b = speakers_list[1] if len(speakers_list) > 1 else "B"
        else:
            speaker_a = conv.get("speaker_a", "A")
            speaker_b = conv.get("speaker_b", "B")
            sessions_info = _prepare_sessions_from_dict(conv)

        dataset_name = f"locomo_{run_id}_{speaker_a}_{speaker_b}_{idx}"

        if sessions_info:
            datasets.append({
                "name": dataset_name,
                "sessions": sessions_info,
                "speakers": f"{speaker_a} <-> {speaker_b}",
                "total_messages": sum(s["message_count"] for s in sessions_info),
                "index": idx,
            })
    return datasets


def _prepare_sessions_from_list(messages: List[Dict]) -> List[Dict]:
    sessions_info = []
    current_ts = None
    current_session_msgs = []
    session_idx = 1

    for msg in messages:
        ts = msg.get("timestamp", "")
        if ts != current_ts and current_session_msgs:
            session_info = _format_session_from_msgs(
                current_session_msgs, current_ts, f"session_{session_idx}",
            )
            sessions_info.append(session_info)
            session_idx += 1
            current_session_msgs = []
        current_ts = ts
        current_session_msgs.append(msg)

    if current_session_msgs:
        session_info = _format_session_from_msgs(
            current_session_msgs, current_ts, f"session_{session_idx}",
        )
        sessions_info.append(session_info)
    return sessions_info


def _format_session_from_msgs(messages: List[Dict], timestamp_str: str, session_key: str) -> Dict:
    session_dt = parse_locomo_datetime(timestamp_str)
    time_prefix = format_date_for_message(session_dt)
    lines = []
    for msg in messages:
        speaker = msg.get("speaker", "Unknown")
        text = msg.get("text", "")
        if time_prefix:
            msg_line = f"{time_prefix} {speaker}: {text}"
        else:
            msg_line = f"{speaker}: {text}"
        lines.append(msg_line)
    content = "\n".join(lines)
    created_at_iso = session_dt.isoformat() if session_dt else None
    return {
        "content": content,
        "message_count": len(messages),
        "created_at": created_at_iso,
        "created_at_display": timestamp_str,
        "session_key": session_key,
    }


def _prepare_sessions_from_dict(conv: Dict) -> List[Dict]:
    sessions_info = []
    session_keys = sorted(
        [k for k in conv.keys() if k.startswith("session_") and not k.endswith("_date_time")],
        key=lambda x: int(x.replace("session_", "")),
    )
    for session_key in session_keys:
        content, session_dt = format_single_session(conv, session_key)
        if not content.strip():
            continue
        msg_count = len(conv.get(session_key, []))
        created_at_iso = session_dt.isoformat() if session_dt else None
        ts_str = conv.get(f"{session_key}_date_time", "")
        sessions_info.append({
            "content": content,
            "message_count": msg_count,
            "created_at": created_at_iso,
            "created_at_display": ts_str,
            "session_key": session_key,
        })
    return sessions_info


# ================================================================
# Ingest logic
# ================================================================

def ingest_dataset_serial(
    dataset: Dict, verbose: bool = False,
) -> Tuple[str, str, int, int]:
    """
    Ingest all sessions of one dataset into Cognee.

    Strategy: batch add all sessions FIRST, then cognify ONCE.
    Each session uses a globally unique filename ({dataset_name}_{session_key}.txt)
    to avoid Cognee's cross-dataset content dedup.
    This avoids per-session cognify which triggers database creation conflicts
    on Cognee Cloud.
    """
    dataset_name = dataset["name"]
    sessions = dataset.get("sessions", [])
    total = len(sessions)
    add_success = 0
    failed_sessions = []

    # Phase 1: Add all sessions
    for i, sess in enumerate(sessions):
        session_key = sess.get("session_key", f"session_{i}")
        content = sess["content"]

        ok, result = cognee_add_text(content, dataset_name, file_label=session_key)
        if not ok:
            failed_sessions.append(session_key)
            if verbose:
                print(f"      [{dataset_name}] {session_key} add failed: {result}")
            continue

        add_success += 1
        if verbose and ((i + 1) % 5 == 0 or i == 0 or i == total - 1):
            print(f"      [{dataset_name}] add {i + 1}/{total} {session_key} ok")

    if add_success == 0:
        return dataset_name, "failed", 0, total

    print(f"      [{dataset_name}] added {add_success}/{total} sessions, cognifying...")

    # Phase 2: Cognify once
    ok, result = cognee_cognify(dataset_name, run_in_background=False)
    if not ok:
        print(f"      [{dataset_name}] blocking cognify failed, trying background...")
        ok, result = cognee_cognify(dataset_name, run_in_background=True)
        if ok:
            completed = wait_for_cognify(dataset_name)
            if not completed:
                return dataset_name, "partial", add_success, total
        else:
            print(f"      [{dataset_name}] cognify failed: {result}")
            return dataset_name, "partial", add_success, total

    print(f"      [{dataset_name}] cognify done")

    status = "completed" if add_success == total else "partial"
    return dataset_name, status, add_success, total


def create_batches(datasets: List[Dict], batch_sizes: List[int]) -> List[List[Dict]]:
    batches = []
    offset = 0
    for size in batch_sizes:
        batch = datasets[offset:offset + size]
        if batch:
            batches.append(batch)
        offset += size
    remaining = datasets[offset:]
    if remaining:
        batches.append(remaining)
    return batches


# ================================================================
# Main
# ================================================================

def main():
    parser = ArgumentParser(description="Cognee LOCOMO ingest script (aligned with MFlow)")
    parser.add_argument("--data", default=DATA_PATH, help="Path to locomo10.json")
    parser.add_argument("--max", type=int, help="Process at most N conversations")
    parser.add_argument("--batch-size", type=int, help="Parallel count per batch")
    parser.add_argument("--skip-delete", action="store_true", help="Skip deleting existing datasets")
    parser.add_argument("--run-id", type=str, default="r3", help="Run ID suffix for dataset names (avoids DB conflicts)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--poll", type=int, default=POLL_INTERVAL, help="Poll interval (seconds)")
    args = parser.parse_args()

    if args.poll != POLL_INTERVAL:
        _update_poll_interval(args.poll)

    print("=" * 60)
    print("Cognee LOCOMO Benchmark — Ingest")
    print("=" * 60)
    print(f"API Base: {API_BASE}")
    print(f"API Key:  {API_KEY[:8]}...{API_KEY[-4:]}" if len(API_KEY) > 12 else "API Key: (not set)")
    print(f"Data:     {args.data}")

    if not API_KEY:
        print("\nERROR: COGNEE_API_KEY not set. Export it or add to .env")
        return

    # Health check
    print("\n[Step 1] Health check")
    if cognee_health_check():
        print("  OK")
    else:
        print("  WARNING: Health check failed, continuing anyway...")

    # Delete existing locomo datasets (unless skipped)
    if not args.skip_delete:
        print("\n[Step 2] Clean existing locomo datasets")
        existing = cognee_get_datasets()
        locomo_datasets = [ds for ds in existing if ds.get("name", "").startswith(("locomo_benchmark_", "locomo_r"))]
        if locomo_datasets:
            print(f"  Found {len(locomo_datasets)} existing locomo dataset(s), deleting...")
            for ds in locomo_datasets:
                ok = cognee_delete_dataset(ds["id"])
                symbol = "done" if ok else "FAILED"
                print(f"    {ds['name']}: {symbol}")
            time.sleep(3)
        else:
            print("  No existing locomo datasets")
    else:
        print("\n[Step 2] Skip delete (--skip-delete)")

    # Load data
    print(f"\n[Step 3] Load data: {args.data}")
    conversations = load_conversations(args.data, args.max)
    datasets = prepare_datasets(conversations, run_id=args.run_id)
    total_sessions = sum(len(ds.get("sessions", [])) for ds in datasets)
    print(f"  {len(datasets)} conversation(s), {total_sessions} session(s)")

    for ds in datasets:
        print(f"    [{ds['index']}] {ds['speakers']}:")
        for sess in ds.get("sessions", []):
            ts = sess.get("created_at_display", sess.get("created_at", "N/A"))
            print(f"        {sess['session_key']}: {sess['message_count']} msgs @ {ts}")

    # Build batches
    print("\n[Step 4] Batch plan")
    if args.batch_size:
        batch_sizes = []
        remaining = len(datasets)
        while remaining > 0:
            size = min(args.batch_size, remaining)
            batch_sizes.append(size)
            remaining -= size
    else:
        batch_sizes = DEFAULT_BATCHES[:len(datasets)]
        total_in_batches = sum(batch_sizes)
        if total_in_batches < len(datasets):
            batch_sizes.append(len(datasets) - total_in_batches)

    batches = create_batches(datasets, batch_sizes)
    print(f"  Batch sizes: {[len(b) for b in batches]}")
    for i, batch in enumerate(batches):
        conv_info = [f"conv{ds['index']}" for ds in batch]
        print(f"    Batch {i + 1}: {conv_info}")

    # Batched ingest
    print("\n[Step 5] Start batched ingest")
    print("  Strategy: sessions serial per dataset, datasets parallel per batch")
    total_start = time.time()
    all_results = []

    for batch_idx, batch in enumerate(batches):
        batch_num = batch_idx + 1
        print(f"\n{'=' * 40}")
        print(f"Batch {batch_num}/{len(batches)}: {len(batch)} conversation(s)")
        print(f"{'=' * 40}")

        batch_start = time.time()
        for ds in batch:
            sessions = ds.get("sessions", [])
            print(f"  -> Conv {ds['index']}: {ds['name']} ({len(sessions)} sessions)")

        batch_results = []

        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            future_to_ds = {
                executor.submit(
                    ingest_dataset_serial, ds, args.verbose,
                ): ds
                for ds in batch
            }
            for future in as_completed(future_to_ds):
                ds = future_to_ds[future]
                try:
                    ds_name, status, success, total = future.result()
                    batch_results.append({
                        "name": ds_name, "status": status,
                        "success": success, "total": total,
                    })
                    symbol = "done" if status == "completed" else "WARN"
                    print(f"    [{symbol}] {ds_name}: {success}/{total} sessions")
                except Exception as e:
                    batch_results.append({
                        "name": ds["name"], "status": "error", "error": str(e),
                    })
                    print(f"    [ERR] {ds['name']}: {e}")

        batch_duration = time.time() - batch_start
        for r in batch_results:
            all_results.append({"name": r["name"], "status": r["status"]})

        completed = sum(1 for r in batch_results if r["status"] == "completed")
        print(f"\n  Batch {batch_num}: {completed}/{len(batch)} completed, {batch_duration / 60:.1f} min")

    # Summary
    total_duration = time.time() - total_start
    completed = sum(1 for r in all_results if r["status"] == "completed")
    failed = len(all_results) - completed

    hours, remainder = divmod(int(total_duration), 3600)
    minutes, seconds = divmod(remainder, 60)
    time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m {seconds}s"

    print("\n" + "=" * 60)
    print("Ingest Summary")
    print("=" * 60)
    print(f"  Conversations: {len(datasets)}")
    print(f"  Sessions:      {total_sessions}")
    print(f"  Succeeded:     {completed}")
    print(f"  Failed:        {failed}")
    print(f"  Total time:    {time_str}")

    if failed > 0:
        print("\n  Failures:")
        for r in all_results:
            if r["status"] != "completed":
                print(f"    - {r['name']}: {r['status']}")

    # Verify datasets exist
    print("\n  Final dataset check:")
    final_datasets = cognee_get_datasets()
    locomo_datasets = [ds for ds in final_datasets if ds.get("name", "").startswith(("locomo_benchmark_", "locomo_r"))]
    print(f"    {len(locomo_datasets)} locomo dataset(s) in Cognee")
    for ds in locomo_datasets:
        print(f"      - {ds['name']} (id: {ds['id'][:8]}...)")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
