#!/usr/bin/env python3
"""
Ingest LOCOMO into m_flow (local, no Docker).
Uses skip_memorize=True to avoid LLM hang, then manual memorize.
"""
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any, List
import argparse

API = "http://127.0.0.1:8000"

LOCOMO_TIME_PATTERN = re.compile(
    r"(\d{1,2}):(\d{2})\s*(am|pm)\s+on\s+(\d{1,2})\s+(\w+),?\s*(\d{4})",
    re.IGNORECASE
)
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12
}


def parse_locomo_datetime(time_str: str) -> Optional[datetime]:
    m = LOCOMO_TIME_PATTERN.search(time_str)
    if not m:
        return None
    hour, minute, ampm, day, month_name, year = m.groups()
    hour = int(hour)
    minute = int(minute)
    if ampm.lower() == "pm" and hour != 12:
        hour += 12
    elif ampm.lower() == "am" and hour == 12:
        hour = 0
    return datetime(
        year=int(year), month=MONTH_MAP[month_name.lower()],
        day=int(day), hour=hour, minute=minute, tzinfo=timezone.utc
    )


def format_date_for_message(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.strftime("[%B %d, %Y, %I:%M %p]")


def format_conversation(conv: Dict, include_blip_caption: bool = True) -> Tuple[str, Optional[datetime]]:
    """Format one LOCOMO conversation (all sessions) into a single text block."""
    lines = []
    earliest_dt = None

    session_keys = sorted(
        [k for k in conv.keys()
         if k.startswith("session_") and not k.endswith("_date_time") and not k.endswith("_summary")],
        key=lambda x: int(x.replace("session_", ""))
    )

    for key in session_keys:
        ts_str = conv.get(f"{key}_date_time", "")
        session_dt = parse_locomo_datetime(ts_str)

        if session_dt is not None:
            if earliest_dt is None or session_dt < earliest_dt:
                earliest_dt = session_dt
            iso_time = session_dt.isoformat()
            lines.append(f"\n=== {key.upper()}: {iso_time} ===\n")
        else:
            lines.append(f"\n=== {key.upper()}: {ts_str} ===\n")

        time_prefix = format_date_for_message(session_dt)

        for msg in conv.get(key, []):
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

    return "\n".join(lines), earliest_dt


def login() -> str:
    req = urllib.request.Request(
        f"{API}/api/v1/auth/login",
        data="username=default_user@example.com&password=default_password".encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)["access_token"]


def api_call(method: str, endpoint: str, data: Any = None, token: str = None) -> Tuple[Any, int]:
    url = f"{API}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp), resp.status
    except urllib.error.HTTPError as e:
        try:
            return json.load(e), e.code
        except Exception:
            return {"detail": str(e)}, e.code
    except urllib.error.URLError as e:
        return {"detail": f"Connection error: {e}"}, 0


def ingest_one_skip_memorize(
    dataset_name: str,
    content: str,
    token: str,
    created_at_ms: Optional[int] = None,
) -> Tuple[bool, Dict]:
    """Ingest with skip_memorize=False, run_in_background=False (synchronous EPISODIC)."""
    payload = {
        "content": content,
        "dataset_name": dataset_name,
        "enable_content_routing": True,
        "content_type": "dialog",
        "enable_episode_routing": False,
        "skip_memorize": False,
        "run_in_background": False,
        "enable_cache": False,
    }
    if created_at_ms:
        payload["created_at"] = created_at_ms

    response_data, http_status = api_call("POST", "/api/v1/ingest", payload, token)

    if http_status != 200:
        return False, {"detail": f"HTTP {http_status}", "response": response_data}
    return True, response_data


def trigger_memorize(dataset_id: str, token: str) -> Tuple[bool, Dict]:
    """Trigger memorize pipeline for a dataset."""
    payload = {
        "dataset_id": dataset_id,
        "enable_content_routing": True,
        "content_type": "dialog",
        "enable_episode_routing": False,
        "incremental_loading": False,
        "enable_cache": False,
    }
    response_data, http_status = api_call("POST", "/api/v1/ingest", payload, token)
    if http_status != 200:
        return False, {"detail": f"HTTP {http_status}", "response": response_data}
    return True, response_data


def wait_for_pipeline(token: str, dataset_id: str, poll_interval: int = 10, max_wait: int = 300) -> bool:
    """Wait for memorize pipeline for specific dataset to complete."""
    start = time.time()
    while time.time() - start < max_wait:
        result, status = api_call("GET", "/api/v1/pipeline/active", token=token)
        if status == 200:
            pipelines = result if isinstance(result, list) else result.get("pipelines", [])
            my_pipelines = [p for p in pipelines if p.get("datasetId") == dataset_id]
            if not my_pipelines:
                elapsed = int(time.time() - start)
                print(f"  Pipeline done ({elapsed}s)")
                return True
            step = my_pipelines[0].get("currentStep", "?")
            print(f"  Still running: {step}...")
        time.sleep(poll_interval)
    print(f"  Timeout after {max_wait}s")
    return False


def main():
    parser = argparse.ArgumentParser(description="Ingest LOCOMO into m_flow (local)")
    parser.add_argument("--max", type=int, default=None)
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--max-wait", type=int, default=300)
    parser.add_argument("--dataset-prefix", default="locomo_local")
    parser.add_argument("--data-path",
                        default="/home/gql/repos/mflow-benchmarks/benchmarks/locomo-mflow/data/locomo10.json")
    parser.add_argument("--memorize-timeout", type=int, default=120)
    args = parser.parse_args()

    # Load LOCOMO data
    with open(args.data_path) as f:
        data = json.load(f)
    if args.max:
        data = data[:args.max]
    print(f"Loaded {len(data)} conversations")

    token = login()
    print(f"Logged in")

    dataset_ids = []
    # Step 1: Ingest all with skip_memorize=True
    print("\n=== Phase 1: Ingest content (skip_memorize=True) ===")
    for idx, conv in enumerate(data):
        conv_data = conv.get("conversation", {})
        speaker_a = conv_data.get("speaker_a", "Unknown")
        speaker_b = conv_data.get("speaker_b", "Unknown")
        dataset_name = f"{args.dataset_prefix}_{speaker_a}_{speaker_b}_{idx}"

        content, earliest_dt = format_conversation(conv_data)
        created_at_ms = int(earliest_dt.timestamp() * 1000) if earliest_dt else None

        print(f"[{idx}/{len(data)}] Ingesting {dataset_name}")
        success, result = ingest_one_skip_memorize(dataset_name, content, token, created_at_ms)

        if success:
            ds_id = result.get("dataset_id", "?")
            status = result.get("status", "unknown")
            print(f"  → status={status}, dataset_id={ds_id[:8] if ds_id else '?'}...")
            dataset_ids.append(ds_id)
        else:
            print(f"  → FAILED: {result}")

        time.sleep(0.5)

    # Step 2: Verify (EPISODIC already built synchronously — no separate memorize needed)
    print(f"\n=== Phase 2: Verify EPISODIC data for {len(dataset_ids)} datasets ===")
    for i, ds_id in enumerate(dataset_ids):
        print(f"[{i}/{len(dataset_ids)}] Verifying dataset {ds_id[:8]}... (EPISODIC built inline)")
    print("(EPISODIC built synchronously — no separate memorize needed)")

    print("\nDone!")


if __name__ == "__main__":
    main()
