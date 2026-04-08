#!/usr/bin/env python3
"""
Cognee LOCOMO Evaluation Script
Fully aligned with MFlow's evaluate_aligned.py

Calculates:
  - BLEU-1 (unigram precision with smoothing)
  - F1 (token-level precision/recall)
  - LLM-Judge (binary CORRECT/WRONG using ACCURACY_PROMPT)
"""

import argparse
import concurrent.futures
import json
import os
import threading
from collections import defaultdict

from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

from metrics import calculate_bleu1, calculate_f1, evaluate_llm_judge

load_dotenv()


def process_item(item_data: tuple, client: OpenAI, model: str) -> dict:
    """
    Process a single conversation's questions.
    Aligned with MFlow's process_item().
    """
    conv_idx, questions = item_data
    local_results = defaultdict(list)

    for item in questions:
        gt_answer = str(item.get("answer", ""))
        pred_answer = str(item.get("response", ""))
        category = str(item.get("category", -1))
        question = str(item.get("question", ""))

        # Skip category 5 (aligned with MFlow/Mem0)
        if category == "5":
            continue

        bleu_score = calculate_bleu1(pred_answer, gt_answer)
        f1_score = calculate_f1(pred_answer, gt_answer)
        llm_score = evaluate_llm_judge(question, gt_answer, pred_answer, client, model)

        local_results[conv_idx].append({
            "question": question,
            "answer": gt_answer,
            "response": pred_answer,
            "category": category,
            "bleu_score": round(bleu_score, 4),
            "f1_score": round(f1_score, 4),
            "llm_score": llm_score,
        })

    return local_results


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate Cognee LOCOMO results (aligned with MFlow)"
    )
    parser.add_argument(
        "--input-file", type=str,
        default="./results/cognee_search.json",
        help="Path to search results file",
    )
    parser.add_argument(
        "--output-file", type=str,
        default="./results/cognee_eval.json",
        help="Path to save evaluation metrics",
    )
    parser.add_argument(
        "--max-workers", type=int, default=10,
        help="Maximum number of worker threads",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Model for LLM-Judge (default: from JUDGE_MODEL env var or gpt-4o-mini)",
    )

    args = parser.parse_args()

    model = args.model or os.getenv("JUDGE_MODEL", "gpt-4o-mini")

    print("=" * 60)
    print("Cognee LOCOMO Benchmark — Evaluation Phase")
    print("=" * 60)
    print(f"Input:   {args.input_file}")
    print(f"Output:  {args.output_file}")
    print(f"Model:   {model}")
    print(f"Workers: {args.max_workers}")
    print("=" * 60)

    with open(args.input_file, "r") as f:
        data = json.load(f)

    client = OpenAI()

    results = defaultdict(list)
    results_lock = threading.Lock()

    total_questions = sum(
        len([q for q in v if str(q.get("category", -1)) != "5"])
        for v in data.values()
    )
    print(f"Total questions to evaluate: {total_questions}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [
            executor.submit(process_item, (k, v), client, model)
            for k, v in data.items()
        ]

        for future in tqdm(
            concurrent.futures.as_completed(futures),
            total=len(futures),
            desc="Evaluating",
        ):
            local_results = future.result()
            with results_lock:
                for k, items in local_results.items():
                    results[k].extend(items)

    with open(args.output_file, "w") as f:
        json.dump(dict(results), f, indent=2)

    all_items = []
    for items in results.values():
        all_items.extend(items)

    if all_items:
        avg_bleu = sum(i["bleu_score"] for i in all_items) / len(all_items)
        avg_f1 = sum(i["f1_score"] for i in all_items) / len(all_items)
        avg_llm = sum(i["llm_score"] for i in all_items) / len(all_items) * 100

        print("\n" + "=" * 60)
        print("Evaluation Summary")
        print("=" * 60)
        print(f"Questions evaluated: {len(all_items)}")
        print(f"BLEU-1 (avg): {avg_bleu:.4f}")
        print(f"F1 (avg):     {avg_f1:.4f}")
        print(f"LLM-J (avg):  {avg_llm:.2f}%")
        print("=" * 60)

    print(f"\nResults saved to: {args.output_file}")


if __name__ == "__main__":
    main()
