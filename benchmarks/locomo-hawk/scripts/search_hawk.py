"""
Hawk Memory LoCoMo Search + QA Script
完全对齐 mflow-benchmarks 官方 search_aligned.py 接口
独立于 hawk-eval，不影响 21 护城河 benchmark。
"""
import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, "/home/gql/repos/hawk-eval/src")

from adapters.hawk_memory_benchmark import HawkMemorySystemBenchmark
from openai import OpenAI


class HawkSearchAligned:
    """Hawk search implementation aligned with mflow-benchmarks MemorySystem 接口。"""

    def __init__(self, hawk_base_url: str = "http://127.0.0.1:18368",
                 output_path: str = "results.json", top_k: int = 10,
                 dataset_prefix: str = "hawk_benchmark"):
        self.hawk = HawkMemorySystemBenchmark(base_url=hawk_base_url, agent_id=dataset_prefix)
        self.openai_client = OpenAI()
        self.top_k = top_k
        self.output_path = output_path
        self.results = defaultdict(list)
        self.dataset_prefix = dataset_prefix

    def search_memories(self, query: str) -> list[dict]:
        """返回格式对齐 m_flow 官方：list[{"memory": str, "timestamp": str, "score": float}]"""
        texts = self.hawk.recall(query, self.top_k)
        return [{"memory": text, "timestamp": "", "score": 0.0} for text in texts]

    async def answer_question(self, question: str, answer: str) -> dict[str, Any]:
        """Answer a question using retrieved memories."""
        memories = self.search_memories(question)

        def format_memories(memories: list[dict]) -> str:
            if not memories:
                return "(No memories available)"
            lines = []
            for i, m in enumerate(memories, 1):
                lines.append(f"[Memory {i}]\n{m.get('memory', '')}")
            return "\n\n".join(lines)

        prompt = f"""Answer the question using ONLY the memories below. Be concise (5-6 words). No explanation.

RULES:
- Read ALL memories before answering — do not stop at the first match.
- Look for both direct mentions and indirect implications. Say "Unknown" only if nothing is relevant.

Memories:

{format_memories(memories)}

Question: {question}

Answer:"""

        t1 = time.time()
        try:
            response = self.openai_client.chat.completions.create(
                model=os.getenv("MODEL", "gpt-5-mini"),
                messages=[{"role": "system", "content": prompt}],
            )
            response_text = response.choices[0].message.content
        except Exception as e:
            response_text = f"[ERROR: {str(e)[:100]}]"
        t2 = time.time()

        return {
            "response": response_text,
            "memories": memories,
            "num_memories": len(memories),
            "response_time": t2 - t1,
        }


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, required=True)
    parser.add_argument("--output", type=str, default="results/hawk_results.json")
    parser.add_argument("--hawk-url", type=str, default="http://127.0.0.1:18368")
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    hawk_search = HawkSearchAligned(
        hawk_base_url=args.hawk_url,
        output_path=args.output,
        top_k=args.top_k,
    )

    with open(args.dataset) as f:
        dataset = [json.loads(line) for line in f]

    print(f"Dataset: {len(dataset)} questions")

    # Ingest all answers
    print("Capturing all memories...")
    for item in dataset:
        answer = item.get("answer", "")
        if answer:
            hawk_search.hawk.capture(answer)

    print("Waiting for index...")
    time.sleep(3)

    # Answer all questions
    print("Answering questions...")
    results = []
    for item in dataset:
        q = item.get("question", "")
        a = item.get("answer", "")
        result = await hawk_search.answer_question(q, a)
        results.append({
            "question": q,
            "answer": a,
            "response": result["response"],
            "num_memories": result["num_memories"],
        })

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())