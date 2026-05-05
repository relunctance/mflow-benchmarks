#!/usr/bin/env python3
"""
LLM-Judge 对比脚本：比较 hawk vs m_flow 回答质量

用法:
  # 只跑 hawk（已有结果）
  python3 eval_compare.py --hawk-results hawk_results_10.json --mflow-results NONE

  # 跑 hawk + m_flow 对比
  python3 eval_compare.py --hawk-results hawk_results_10.json \
                           --mflow-dataset main_dataset \
                           --mflow-url http://127.0.0.1:8000

  # 全流程（提取样本 + 跑 hawk + 跑 m_flow + LLM-Judge）
  python3 eval_compare.py --dataset datasets/locomo/locomo_qa.jsonl \
                           --limit 10 \
                           --output /tmp/compare_results.json

输出格式:
{
  "hawk": { "correct": N, "total": M, "accuracy": X.X },
  "mflow": { "correct": N, "total": M, "accuracy": X.X },
  "per_question": [ { "question": "...", "gold": "...", "hawk_response": "...", "hawk_label": "CORRECT/WRONG", "mflow_response": "...", "mflow_label": "CORRECT/WRONG" }, ... ]
}
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional

# xinference qwen3 client
try:
    from openai import OpenAI
    XINFERENCE_AVAILABLE = True
except ImportError:
    XINFERENCE_AVAILABLE = False

ACCURACY_PROMPT = """Your task is to label an answer to a question as 'CORRECT' or 'WRONG'.
You will be given: question, gold answer, generated answer.

Be generous — if the generated answer touches the same topic/entity as the gold answer, it's CORRECT.
For dates: same date/time = CORRECT even if format differs (e.g. "May 7th" vs "7 May").
For lists: partial overlap = CORRECT.

Question: {question}
Gold answer: {gold_answer}
Generated answer: {generated_answer}

Respond ONLY with JSON: {{"label": "CORRECT"}} or {{"label": "WRONG"}}"""


def get_xinference_client():
    if not XINFERENCE_AVAILABLE:
        return None
    return OpenAI(api_key="unused", base_url="http://localhost:9997/v1")


def judge_with_xinference(question: str, gold: str, response: str, timeout: int = 30) -> str:
    """Use xinference qwen3 as LLM-Judge."""
    client = get_xinference_client()
    if not client:
        return "SKIP (xinference unavailable)"

    prompt = ACCURACY_PROMPT.format(question=question, gold_answer=gold, generated_answer=response)
    try:
        resp = client.chat.completions.create(
            model="qwen3",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0.0,
            timeout=timeout,
        )
        raw = resp.choices[0].message.content.strip()
        # Extract JSON
        import re
        match = re.search(r'\{\s*"label"\s*:\s*"(\w+)"', raw)
        if match:
            return match.group(1)
        # Fallback: look for CORRECT/WRONG
        if "CORRECT" in raw.upper() and "WRONG" not in raw.upper():
            return "CORRECT"
        if "WRONG" in raw.upper():
            return "WRONG"
        return f"PARSE_ERROR: {raw[:100]}"
    except Exception as e:
        return f"ERROR: {str(e)[:50]}"


def load_json(path: str):
    """Load JSON file, return None if not found."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def load_results(path: str) -> list[dict]:
    """Load search results from hawk or mflow output file."""
    data = load_json(path)
    if data is None:
        return []
    # Handle both dict ({"results": [...]}) and list formats
    if isinstance(data, dict):
        if "results" in data:
            return data["results"]
        # Try to find the first list value
        for v in data.values():
            if isinstance(v, list):
                return v
    if isinstance(data, list):
        return data
    return []


async def judge_item_async(semaphore: asyncio.Semaphore, item: dict, judge_fn) -> dict:
    """Judge a single item with rate limiting."""
    async with semaphore:
        q = item.get("question", "")
        gold = item.get("answer", "")

        hawk_resp = item.get("hawk_response", item.get("response", ""))
        hawk_label = judge_fn(q, gold, hawk_resp) if hawk_resp else "NO_RESPONSE"

        mflow_resp = item.get("mflow_response", "")
        mflow_label = judge_fn(q, gold, mflow_resp) if mflow_resp else "NO_RESPONSE"

        await asyncio.sleep(0.05)  # Small delay to avoid overwhelming
        return {
            "question": q,
            "gold": gold,
            "hawk_response": hawk_resp[:500],
            "hawk_label": hawk_label,
            "mflow_response": mflow_resp[:500] if mflow_resp else None,
            "mflow_label": mflow_label,
        }


async def judge_all_async(items: list[dict], judge_fn, max_concurrent: int = 5) -> list[dict]:
    """Judge all items concurrently with semaphore."""
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [judge_item_async(semaphore, item, judge_fn) for item in items]
    return await asyncio.gather(*tasks)


def summarize(results: list[dict]) -> dict:
    """Compute accuracy stats."""
    hawk_correct = sum(1 for r in results if r["hawk_label"] == "CORRECT")
    mflow_correct = sum(1 for r in results if r.get("mflow_label") == "CORRECT")
    hawk_total = sum(1 for r in results if r["hawk_label"] not in ("NO_RESPONSE", "SKIP"))
    mflow_total = sum(1 for r in results if r.get("mflow_label") not in ("NO_RESPONSE", "SKIP", None, ""))

    hawk_accuracy = (hawk_correct / hawk_total * 100) if hawk_total > 0 else 0
    mflow_accuracy = (mflow_correct / mflow_total * 100) if mflow_total > 0 else 0

    return {
        "hawk": {"correct": hawk_correct, "total": hawk_total, "accuracy": round(hawk_accuracy, 1)},
        "mflow": {"correct": mflow_correct, "total": mflow_total, "accuracy": round(mflow_accuracy, 1)},
    }


def main():
    parser = argparse.ArgumentParser(description="LLM-Judge 对比 hawk vs m_flow")
    parser.add_argument("--hawk-results", type=str, help="hawk search results JSON file")
    parser.add_argument("--mflow-results", type=str, default=None, help="mflow search results JSON file (use NONE to skip mflow)")
    parser.add_argument("--output", type=str, default="/tmp/compare_results.json", help="Output JSON path")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of items (0=all)")
    args = parser.parse_args()

    # Load hawk results
    hawk_data = load_results(args.hawk_results) if args.hawk_results else []
    print(f"Loaded {len(hawk_data)} hawk results")

    if not hawk_data:
        print("ERROR: No hawk results loaded", file=sys.stderr)
        sys.exit(1)

    # Limit
    if args.limit > 0:
        hawk_data = hawk_data[:args.limit]

    # Format items for judgment
    items = []
    for item in hawk_data:
        formatted = {
            "question": item.get("question", ""),
            "answer": item.get("answer", ""),
            "hawk_response": item.get("response", ""),
            "mflow_response": item.get("mflow_response", ""),
        }
        items.append(formatted)

    print(f"Judging {len(items)} items with xinference qwen3...")
    start = time.time()

    # Run judgment
    results = asyncio.run(judge_all_async(items, judge_with_xinference, max_concurrent=5))

    elapsed = time.time() - start
    stats = summarize(results)

    print(f"\n=== Results ({elapsed:.1f}s) ===")
    print(f"hawk:  {stats['hawk']['correct']}/{stats['hawk']['total']} = {stats['hawk']['accuracy']}%")
    if stats['mflow']['total'] > 0:
        print(f"mflow: {stats['mflow']['correct']}/{stats['mflow']['total']} = {stats['mflow']['accuracy']}%")

    output = {
        "hawk": stats["hawk"],
        "mflow": stats["mflow"],
        "per_question": results,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {args.output}")

    # Print per-question detail
    print("\n=== Per-question detail ===")
    for i, r in enumerate(results):
        hawk_ok = "✅" if r["hawk_label"] == "CORRECT" else "❌"
        mflow_ok = "✅" if r.get("mflow_label") == "CORRECT" else "❌" if r.get("mflow_label") else "-"
        print(f"{i+1}. {hawk_ok} hawk | {mflow_ok} mflow | Q: {r['question'][:50]} | Gold: {r['gold']}")


if __name__ == "__main__":
    main()
