#!/usr/bin/env python3
"""
Cognee LOCOMO Search + QA Script
Aligned with MFlow's search_aligned.py

Pipeline:
  1. For each question, search the corresponding Cognee dataset
  2. Format retrieved chunks as memories
  3. Generate answer using LLM with aligned prompt
  4. Save results in MFlow-compatible format

Search modes:
  - CHUNKS: Raw text segments (default — purest retrieval, closest to MFlow)
  - GRAPH_COMPLETION + only_context: Graph-enhanced context
  - SUMMARIES: Pre-generated summaries

Dataset naming matches MFlow:
  locomo_benchmark_{speaker_a}_{speaker_b}_{idx}
"""

import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

from prompts import COGNEE_CHUNKS_PROMPT, COGNEE_GRAPH_PROMPT, COGNEE_COMPLETION_PROMPT

load_dotenv()

# === Configuration ===
API_BASE = os.getenv("COGNEE_API_BASE", "https://api.cognee.ai")
API_PREFIX = os.getenv("COGNEE_API_PREFIX", "/api/v1")
API_KEY = os.getenv("COGNEE_API_KEY", "")
DEFAULT_SEARCH_TYPE = "CHUNKS"
DEFAULT_TOP_K = 10

# Prompt selection by search type
PROMPT_BY_SEARCH_TYPE = {
    "CHUNKS": COGNEE_CHUNKS_PROMPT,
    "SUMMARIES": COGNEE_CHUNKS_PROMPT,
    "GRAPH_COMPLETION": COGNEE_GRAPH_PROMPT,
    "TRIPLET_COMPLETION": COGNEE_GRAPH_PROMPT,
    "RAG_COMPLETION": COGNEE_CHUNKS_PROMPT,
}


def cognee_headers() -> dict:
    return {"X-Api-Key": API_KEY}


def cognee_search(
    query: str,
    dataset_name: str,
    search_type: str = DEFAULT_SEARCH_TYPE,
    top_k: int = DEFAULT_TOP_K,
    only_context: bool = False,
    system_prompt: str = None,
) -> tuple[list, float]:
    """
    Search Cognee for relevant content.

    Args:
        system_prompt: Custom system prompt for completion-type searches.
            Cognee's API passes this to the LLM that generates the final answer.
            Only effective for GRAPH_COMPLETION, RAG_COMPLETION, TRIPLET_COMPLETION
            (i.e., search types that invoke an LLM completion step).

    Returns:
        (results_list, search_time_seconds)
    """
    payload = {
        "searchType": search_type,
        "query": query,
        "datasets": [dataset_name],
        "topK": top_k,
        "onlyContext": only_context,
    }
    if system_prompt:
        payload["systemPrompt"] = system_prompt
    headers = {**cognee_headers(), "Content-Type": "application/json"}

    start = time.time()
    try:
        r = requests.post(
            f"{API_BASE}{API_PREFIX}/search",
            json=payload,
            headers=headers,
            timeout=120,
        )
        elapsed = time.time() - start

        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return data, elapsed
            return [], elapsed
        else:
            print(f"  Search error {r.status_code}: {r.text[:200]}")
            return [], elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"  Search exception: {e}")
        return [], elapsed


def format_search_results_as_memories(results: list, dataset_name: str) -> list[dict]:
    """
    Convert Cognee search results to memory format (aligned with MFlow).

    MFlow format: [{"memory": str, "timestamp": str, "score": float}, ...]

    Cognee Cloud API returns (access_control enabled):
      [{"search_result": <value>, "dataset_id": ..., "dataset_name": ...}]

    Where <value> depends on search type:
      CHUNKS:                  list of dicts  [{"text": "...", ...}, ...]
      GRAPH_COMPLETION ctx:    string         "Nodes:\n...\nConnections:\n..."
      GRAPH_COMPLETION full:   list of str    ["answer text"]

    Local Cognee (no access control) may return unwrapped results:
      [{"text": "chunk1"}, {"text": "chunk2"}]   or   ["answer text"]
    """
    memories = []

    for item in results:
        _extract_memories_from_item(item, memories)

    return memories


def _extract_memories_from_item(item: any, memories: list):
    """Recursively extract memory entries from a single search result item."""

    if isinstance(item, dict):
        search_result = item.get("search_result")

        if search_result is not None:
            # Cognee Cloud format: {"search_result": <value>, "dataset_id": ...}
            # Recurse into the search_result value
            _extract_memories_from_item(search_result, memories)
            return

        # Direct chunk dict: {"text": "...", "chunk_size": ...}
        text = item.get("text", "") or item.get("content", "") or item.get("name", "")
        if text:
            memories.append({
                "memory": str(text).strip(),
                "timestamp": item.get("timestamp", "Unknown date"),
                "score": round(item["score"], 2) if isinstance(item.get("score"), (int, float)) else 0.9,
            })
            return

        # Dict without known text fields — serialize it
        serialized = str(item)
        if serialized and serialized != "{}":
            memories.append({"memory": serialized, "timestamp": "Unknown date", "score": 0.5})

    elif isinstance(item, list):
        # List of results — flatten by recursing into each element
        for sub_item in item:
            _extract_memories_from_item(sub_item, memories)

    elif isinstance(item, str) and item.strip():
        # Plain string (graph context or completion text)
        memories.append({"memory": item.strip(), "timestamp": "Unknown date", "score": 0.9})


class CogneeSearchAligned:
    """
    Cognee search implementation aligned with MFlow's MflowSearchAligned.

    Architecture: Same as MFlow — single search per question (not per-speaker),
    because Cognee datasets are shared across speakers.
    """

    def __init__(
        self,
        output_path: str = "results.json",
        top_k: int = DEFAULT_TOP_K,
        dataset_prefix: str = "locomo_benchmark",
        search_type: str = DEFAULT_SEARCH_TYPE,
        cognee_native: bool = False,
    ):
        self.openai_client = OpenAI()
        self.top_k = top_k
        self.output_path = output_path
        self.results = defaultdict(list)
        self.dataset_prefix = dataset_prefix
        self.search_type = search_type
        self.cognee_native = cognee_native

    def search_memory(
        self, query: str, dataset_name: str,
    ) -> tuple[list[dict], float]:
        """
        Search memories using Cognee's search API.

        Three modes:
        1. CHUNKS/SUMMARIES:  pure vector retrieval → our LLM answers
        2. GRAPH + not native: only_context=True → graph context → our LLM answers
        3. GRAPH + native:     Cognee's LLM answers via custom systemPrompt

        Returns:
            (memories_list, search_time)
        """
        is_graph = self.search_type in ("GRAPH_COMPLETION", "TRIPLET_COMPLETION")

        if self.cognee_native and is_graph:
            # Mode 3: let Cognee's own LLM generate the answer
            results, search_time = cognee_search(
                query=query,
                dataset_name=dataset_name,
                search_type=self.search_type,
                top_k=self.top_k,
                only_context=False,
                system_prompt=COGNEE_COMPLETION_PROMPT,
            )
        elif is_graph:
            # Mode 2: get graph context, we generate the answer
            results, search_time = cognee_search(
                query=query,
                dataset_name=dataset_name,
                search_type=self.search_type,
                top_k=self.top_k,
                only_context=True,
            )
        else:
            # Mode 1: pure vector retrieval
            results, search_time = cognee_search(
                query=query,
                dataset_name=dataset_name,
                search_type=self.search_type,
                top_k=self.top_k,
            )

        memories = format_search_results_as_memories(results, dataset_name)
        return memories[:self.top_k], search_time

    def _format_chunks_context(self, memories: list[dict]) -> str:
        """
        Format CHUNKS results as numbered conversation fragments.

        CHUNKS returns raw text from DocumentChunk payloads — these are
        conversation fragments with embedded timestamps like:
          [May 08, 2023, 1:56 PM] Caroline: text

        We number them for the LLM to reference, but preserve the raw text
        because the timestamps inside ARE the temporal evidence.
        """
        if not memories:
            return "(No conversation fragments available)"
        parts = []
        for i, m in enumerate(memories, 1):
            text = m.get("memory", "")
            parts.append(f"--- Fragment {i} ---\n{text}")
        return "\n\n".join(parts)

    def _format_graph_context(self, memories: list[dict]) -> str:
        """
        Format GRAPH_COMPLETION context (only_context=True).

        Graph context from resolve_edges_to_text() is already structured:
          Nodes:\n  Node: title\n  __node_content_start__\n  content\n  ...
          Connections:\n  A --[rel]--> B

        We pass it through mostly as-is since the COGNEE_GRAPH_PROMPT
        explains the format to the LLM.
        """
        if not memories:
            return "(No knowledge graph context available)"
        parts = [m.get("memory", "") for m in memories if m.get("memory")]
        return "\n\n".join(parts) if parts else "(No knowledge graph context available)"

    def answer_question(
        self,
        speaker_a_user_id: str,
        speaker_b_user_id: str,
        dataset: str,
        question: str,
        answer: str,
        category: int,
    ) -> dict[str, Any]:
        """
        Answer a question using retrieved context.

        Prompt selection adapts to Cognee's search type:
        - CHUNKS: raw conversation fragments → COGNEE_CHUNKS_PROMPT
        - GRAPH_COMPLETION: graph nodes+connections → COGNEE_GRAPH_PROMPT
        - Others: fallback to CHUNKS prompt

        Single search (not per-speaker) — same as MFlow:
        Cognee datasets hold objective conversation data, not per-user views.
        """
        memories, search_time = self.search_memory(question, dataset)

        speaker_1_name = speaker_a_user_id.split("_")[0]
        speaker_2_name = speaker_b_user_id.split("_")[0]

        is_graph = self.search_type in ("GRAPH_COMPLETION", "TRIPLET_COMPLETION")

        # Mode 3 (cognee_native): Cognee's LLM already generated the answer
        # during search — the "memory" text IS the answer
        if self.cognee_native and is_graph and memories:
            response_text = memories[0].get("memory", "Unknown")
            t1 = t2 = time.time()
        else:
            # Mode 1 & 2: we generate the answer ourselves
            if is_graph:
                context = self._format_graph_context(memories)
            else:
                context = self._format_chunks_context(memories)

            prompt_template = PROMPT_BY_SEARCH_TYPE.get(
                self.search_type, COGNEE_CHUNKS_PROMPT
            )

            prompt = prompt_template.format(
                speaker_1=speaker_1_name,
                speaker_2=speaker_2_name,
                context=context,
                question=question,
            )

            model = os.getenv("MODEL", "gpt-5-mini")
            supports_temperature = not any(
                model.startswith(p) for p in ("o1", "o3", "o4", "gpt-5")
            )

            t1 = time.time()
            try:
                kwargs = {
                    "model": model,
                    "messages": [{"role": "system", "content": prompt}],
                }
                if supports_temperature:
                    kwargs["temperature"] = 0.0
                response = self.openai_client.chat.completions.create(**kwargs)
                response_text = response.choices[0].message.content
            except Exception as e:
                print(f"  LLM error: {e}")
                response_text = f"[ERROR: {str(e)[:100]}]"
            t2 = time.time()

        return {
            "response": response_text,
            "memories": memories,
            "num_memories": len(memories),
            "search_time": search_time,
            "response_time": t2 - t1,
            "search_type": self.search_type,
            "speaker_1_memories": memories,
            "speaker_2_memories": [],
            "num_speaker_1_memories": len(memories),
            "num_speaker_2_memories": 0,
            "speaker_1_memory_time": search_time,
            "speaker_2_memory_time": 0,
        }

    def process_question(
        self, val: dict, speaker_a_user_id: str, speaker_b_user_id: str, dataset: str,
    ) -> dict[str, Any]:
        question = val.get("question", "")
        answer = val.get("answer", "")
        category = val.get("category", -1)
        evidence = val.get("evidence", [])
        adversarial_answer = val.get("adversarial_answer", "")

        result = self.answer_question(
            speaker_a_user_id, speaker_b_user_id, dataset,
            question, str(answer), category,
        )

        result.update({
            "question": question,
            "answer": str(answer),
            "category": category,
            "evidence": evidence,
            "adversarial_answer": adversarial_answer,
        })
        return result

    def process_data_file(self, file_path: str, max_conversations: int = None):
        """
        Process all questions from LOCOMO data file.
        Aligned with MFlow's process_data_file().
        """
        with open(file_path, "r") as f:
            data = json.load(f)

        if max_conversations is not None:
            data = data[:max_conversations]
            print(f"Processing {len(data)} conversations (limited)...")
        else:
            print(f"Processing {len(data)} conversations...")

        for idx, item in enumerate(tqdm(data, desc="Conversations")):
            qa = item["qa"]
            conversation = item["conversation"]
            speaker_a = conversation["speaker_a"]
            speaker_b = conversation["speaker_b"]

            speaker_a_user_id = f"{speaker_a}_{idx}"
            speaker_b_user_id = f"{speaker_b}_{idx}"
            shared_dataset = f"{self.dataset_prefix}_{speaker_a}_{speaker_b}_{idx}"

            print(f"\n[Conv {idx}] {speaker_a} <-> {speaker_b}, {len(qa)} questions")
            print(f"  Dataset: {shared_dataset}")

            for question_item in tqdm(qa, total=len(qa), desc="  Questions", leave=False):
                try:
                    result = self.process_question(
                        question_item, speaker_a_user_id, speaker_b_user_id, shared_dataset,
                    )
                except Exception as e:
                    print(f"  Question error: {e}")
                    result = {
                        "question": question_item.get("question", ""),
                        "answer": str(question_item.get("answer", "")),
                        "category": question_item.get("category", -1),
                        "response": f"[ERROR: {str(e)[:100]}]",
                        "error": str(e),
                    }
                self.results[idx].append(result)

                with open(self.output_path, "w") as f:
                    json.dump(dict(self.results), f, indent=2)

        with open(self.output_path, "w") as f:
            json.dump(dict(self.results), f, indent=2)

        total_questions = sum(len(v) for v in self.results.values())
        print(f"\nComplete! {len(self.results)} conversations, {total_questions} questions")
        print(f"Results saved to: {self.output_path}")
        return dict(self.results)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Cognee LOCOMO Search (aligned with MFlow)"
    )
    parser.add_argument(
        "--data-path", type=str,
        default="dataset/locomo10.json",
        help="Path to LOCOMO JSON file",
    )
    parser.add_argument(
        "--output-path", type=str,
        default="./results/cognee_search.json",
        help="Output path for results",
    )
    parser.add_argument(
        "--top-k", type=int, default=DEFAULT_TOP_K,
        help="Number of memories to retrieve",
    )
    parser.add_argument(
        "--dataset-prefix", type=str,
        default="locomo_r3",
        help="Dataset name prefix (must match run_ingest.py --run-id)",
    )
    parser.add_argument(
        "--search-type", type=str,
        default=DEFAULT_SEARCH_TYPE,
        choices=["CHUNKS", "GRAPH_COMPLETION", "SUMMARIES", "RAG_COMPLETION", "TRIPLET_COMPLETION"],
        help="Cognee search type",
    )
    parser.add_argument(
        "--cognee-native", action="store_true",
        help="Let Cognee's own LLM answer (via systemPrompt). Only for GRAPH_COMPLETION/TRIPLET_COMPLETION.",
    )
    parser.add_argument(
        "--max-conversations", type=int, default=None,
        help="Max conversations to process (for testing)",
    )

    args = parser.parse_args()

    Path(args.output_path).parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Cognee LOCOMO Benchmark — Search Phase")
    print("=" * 60)
    print(f"API Base:     {API_BASE}")
    print(f"Data:         {args.data_path}")
    print(f"Output:       {args.output_path}")
    print(f"Top-K:        {args.top_k}")
    print(f"Search Type:  {args.search_type}")
    if args.cognee_native:
        print(f"Native Mode:  ON (Cognee's LLM answers via custom systemPrompt)")
    if args.max_conversations:
        print(f"Max Convos:   {args.max_conversations}")
    print("=" * 60)

    searcher = CogneeSearchAligned(
        output_path=args.output_path,
        top_k=args.top_k,
        dataset_prefix=args.dataset_prefix,
        search_type=args.search_type,
        cognee_native=args.cognee_native,
    )

    searcher.process_data_file(args.data_path, max_conversations=args.max_conversations)


if __name__ == "__main__":
    main()
