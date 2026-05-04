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


class HawkSearchAligned:
    """Hawk search implementation aligned with mflow-benchmarks MemorySystem 接口。"""

    def __init__(self, hawk_base_url: str = "http://127.0.0.1:18368",
                 output_path: str = "results.json", top_k: int = 10,
                 dataset_prefix: str = "hawk_benchmark",
                 llm_provider: str = "openai",
                 llm_api_key: str = None,
                 llm_base_url: str = None,
                 llm_model: str = None):
        self.hawk = HawkMemorySystemBenchmark(base_url=hawk_base_url, agent_id=dataset_prefix)
        self.llm_provider = llm_provider
        self.llm_api_key = llm_api_key or os.getenv("OPENAI_API_KEY") or os.getenv("MINIMAX_CN_API_KEY", "")
        self.llm_base_url = llm_base_url or os.getenv("OPENAI_BASE_URL", "")
        self.llm_model = llm_model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.top_k = top_k
        self.output_path = output_path
        self.results = defaultdict(list)
        self.dataset_prefix = dataset_prefix

    def _llm_complete(self, prompt: str) -> str:
        """Call LLM with configured provider."""
        if self.llm_provider == "minimax":
            return self._minimax_complete(prompt)
        elif self.llm_provider == "openai":
            return self._openai_complete(prompt)
        elif self.llm_provider == "custom":
            return self._custom_complete(prompt)
        else:
            return self._openai_complete(prompt)

    def _openai_complete(self, prompt: str) -> str:
        """OpenAI-compatible API call."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.llm_api_key, base_url=self.llm_base_url or None)
            response = client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.0,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[OPENAI_ERROR: {str(e)[:100]}]"

    def _minimax_complete(self, prompt: str) -> str:
        """MiniMax API call."""
        try:
            import urllib.request
            import urllib.parse

            url = "https://api.minimax.chat/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": self.llm_model or "MiniMax-M2.7",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.0,
            }
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[MINIMAX_ERROR: {str(e)[:100]}]"

    def _custom_complete(self, prompt: str) -> str:
        """Custom OpenAI-compatible endpoint."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.llm_api_key or "dummy", base_url=self.llm_base_url)
            response = client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.0,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[CUSTOM_LLM_ERROR: {str(e)[:100]}]"

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
        response_text = self._llm_complete(prompt)
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
    parser.add_argument("--llm-provider", type=str, default="openai",
                        choices=["openai", "minimax", "custom"],
                        help="LLM provider: openai, minimax, or custom")
    parser.add_argument("--llm-api-key", type=str, default=None,
                        help="API key (or set OPENAI_API_KEY / MINIMAX_CN_API_KEY env var)")
    parser.add_argument("--llm-base-url", type=str, default=None,
                        help="Base URL for custom LLM (e.g., OpenAI-compatible endpoint)")
    parser.add_argument("--llm-model", type=str, default=None,
                        help="Model name (default: gpt-4o-mini for OpenAI, MiniMax-M2.7 for minimax)")
    args = parser.parse_args()

    hawk_search = HawkSearchAligned(
        hawk_base_url=args.hawk_url,
        output_path=args.output,
        top_k=args.top_k,
        llm_provider=args.llm_provider,
        llm_api_key=args.llm_api_key,
        llm_base_url=args.llm_base_url,
        llm_model=args.llm_model,
    )

    with open(args.dataset) as f:
        dataset = [json.loads(line) for line in f]

    print(f"Dataset: {len(dataset)} questions")
    print(f"LLM: {args.llm_provider} ({hawk_search.llm_model})")

    # Ingest all answers
    print("Capturing all memories...")
    for item in dataset:
        answer = item.get("answer", "")
        if answer:
            hawk_search.hawk.capture(str(answer))

    print("Waiting for index...")
    time.sleep(3)

    # Answer all questions
    print("Answering questions...")
    results = []
    for i, item in enumerate(dataset):
        q = item.get("question", "")
        a = item.get("answer", "")
        result = await hawk_search.answer_question(q, a)
        results.append({
            "question": q,
            "answer": a,
            "response": result["response"],
            "num_memories": result["num_memories"],
        })
        if (i + 1) % 5 == 0:
            print(f"  [{i+1}/{len(dataset)}] answered")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
