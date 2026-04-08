#!/usr/bin/env python3
"""
Cognee LOCOMO Score Generation Script
Aligned with MFlow's generate_scores.py

Generates:
  - Per-category scores
  - Overall scores
  - Comparison-ready table
"""

import argparse
import json
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser(
        description="Generate Cognee LOCOMO benchmark scores"
    )
    parser.add_argument(
        "--input-file", type=str,
        default="./results/cognee_eval.json",
        help="Path to evaluation metrics file",
    )
    parser.add_argument(
        "--output-csv", type=str,
        default="./results/cognee_report.csv",
        help="Path to save CSV report",
    )

    args = parser.parse_args()

    with open(args.input_file, "r") as f:
        data = json.load(f)

    all_items = []
    for key in data:
        all_items.extend(data[key])

    if not all_items:
        print("No evaluation data found.")
        return

    df = pd.DataFrame(all_items)
    df["category"] = pd.to_numeric(df["category"])

    print("=" * 70)
    print("Cognee LOCOMO Benchmark Results")
    print("(Aligned with MFlow Evaluation Methodology)")
    print("=" * 70)

    # Per-category
    category_stats = df.groupby("category").agg({
        "bleu_score": "mean",
        "f1_score": "mean",
        "llm_score": "mean",
    }).round(4)
    category_stats["count"] = df.groupby("category").size()
    category_stats.columns = ["BLEU-1", "F1", "LLM-J", "Count"]

    print("\nPer-Category Scores:")
    print("-" * 70)
    print(category_stats.to_string())

    # Overall
    overall = {
        "BLEU-1": round(df["bleu_score"].mean(), 4),
        "F1": round(df["f1_score"].mean(), 4),
        "LLM-J (%)": round(df["llm_score"].mean() * 100, 2),
        "Total Questions": len(df),
    }

    print("\n" + "-" * 70)
    print("Overall Scores:")
    for k, v in overall.items():
        print(f"  {k}: {v}")
    print("=" * 70)

    # Per-conversation
    print("\nPer-Conversation Scores:")
    print("-" * 70)
    for conv_key in sorted(data.keys(), key=lambda x: int(x)):
        items = data[conv_key]
        if not items:
            continue
        tp = sum(i.get("llm_score", 0) for i in items)
        total = len(items)
        pct = tp / total * 100 if total > 0 else 0
        print(f"  Conv {conv_key}: {tp}/{total} = {pct:.1f}%")

    # Save CSV
    category_stats.to_csv(args.output_csv)
    print(f"\nReport saved to: {args.output_csv}")

    # Save JSON summary
    summary = {
        "per_category": category_stats.to_dict(),
        "overall": overall,
    }
    summary_path = Path(args.output_csv).with_suffix(".json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary saved to: {summary_path}")

    # Comparison table
    print("\n" + "=" * 70)
    print("Comparison Format:")
    print("-" * 70)
    print("| System | LLM-Judge | BLEU-1 | F1 |")
    print("|--------|-----------|--------|-----|")
    print(f"| Cognee | {overall['LLM-J (%)']:.1f}% | {overall['BLEU-1']:.3f} | {overall['F1']:.3f} |")
    print(f"| M-flow (ref) | 76.5% | 0.422 | 0.503 |")
    print(f"| Mem0 (ref) | 66.9% | — | — |")
    print("=" * 70)


if __name__ == "__main__":
    main()
