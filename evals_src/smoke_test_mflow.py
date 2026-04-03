"""
Mflow local smoke test — 10 docs, 1 question, per-doc add+memorize.
Logs ingestion time per document.
"""
import asyncio
import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


async def run_single_test(corpus, question, expected, qa_engine, display_mode="summary"):
    """Run a single test with the given retrieval engine."""
    import m_flow

    print(f"\n{'='*60}", flush=True)
    print(f"Testing: {qa_engine}", flush=True)
    print(f"{'='*60}", flush=True)

    # Step 1: Prune
    print("[1/3] Pruning...", flush=True)
    await m_flow.prune.prune_data()
    await m_flow.prune.prune_system(metadata=True)
    print("      Done", flush=True)

    # Step 2: Per-doc add+memorize with timing
    total = len(corpus)
    print(f"[2/3] Ingesting {total} docs (per-doc add+memorize)...", flush=True)
    ingest_times = []
    ingest_start_total = time.time()

    for idx, doc in enumerate(corpus, 1):
        t0 = time.time()
        await m_flow.add(doc)
        await m_flow.memorize(chunk_size=1024)
        elapsed = time.time() - t0
        ingest_times.append({"doc_index": idx, "time_sec": round(elapsed, 2)})
        preview = doc[:60].replace("\n", " ")
        print(f"      [{idx}/{total}] {elapsed:.1f}s | {preview}...", flush=True)

    ingest_total = time.time() - ingest_start_total
    print(f"      Ingestion complete: {ingest_total:.1f}s total, avg {ingest_total/total:.1f}s/doc", flush=True)

    # Step 3: Search
    print(f"[3/3] Querying ({qa_engine})...", flush=True)

    if qa_engine == "unified_triplet":
        from m_flow.retrieval.unified_triplet_search import UnifiedTripletSearch
        retriever = UnifiedTripletSearch(
            system_prompt_path="answer_simple_question_benchmark2.txt",
            top_k=15,
            wide_search_top_k=100,
        )
    elif qa_engine == "episodic":
        from m_flow.retrieval.episodic_retriever import EpisodicRetriever
        from m_flow.retrieval.episodic import EpisodicConfig
        episodic_config = EpisodicConfig(
            top_k=10,
            wide_search_top_k=100,
            display_mode=display_mode,
        )
        retriever = EpisodicRetriever(
            system_prompt_path="answer_simple_question_benchmark2.txt",
            top_k=10,
            config=episodic_config,
        )
    else:
        raise ValueError(f"Unknown engine: {qa_engine}")

    t0 = time.time()
    results = await retriever.get_completion(question)
    search_time = time.time() - t0
    answer = str(results[0]) if results else "No answer"

    print(flush=True)
    print(f"Question:    {question}", flush=True)
    print(f"Answer:      {answer}", flush=True)
    print(f"Expected:    {expected}", flush=True)
    match = "MATCH" if answer.strip().lower() == expected.strip().lower() else "MISMATCH"
    print(f"Result:      {match}", flush=True)
    print(f"Search time: {search_time:.1f}s", flush=True)

    return {
        "question": question,
        "answer": answer,
        "golden_answer": expected,
        "engine": qa_engine,
        "match": match,
        "ingest_total_sec": round(ingest_total, 2),
        "ingest_per_doc": ingest_times,
        "search_time_sec": round(search_time, 2),
    }


async def main():
    from m_flow.shared.logging_utils import setup_logging, ERROR
    setup_logging(log_level=ERROR)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(script_dir, "benchmark_corpus.json")) as f:
        corpus = json.load(f)
    with open(os.path.join(script_dir, "benchmark_qa_pairs.json")) as f:
        qa_pairs = json.load(f)

    # First question + its 10 context paragraphs
    corpus = corpus[:10]
    question = qa_pairs[0]["question"]
    expected = qa_pairs[0]["answer"]

    print(f"Corpus:   {len(corpus)} docs", flush=True)
    print(f"Question: {question}", flush=True)
    print(f"Expected: {expected}", flush=True)

    all_results = []

    # Test 1: unified_triplet
    r1 = await run_single_test(corpus, question, expected, "unified_triplet")
    all_results.append(r1)

    # Test 2: episodic
    r2 = await run_single_test(corpus, question, expected, "episodic")
    all_results.append(r2)

    # Save
    out_path = os.path.join(script_dir, "smoke_mflow_result.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {out_path}", flush=True)
    print("MFLOW SMOKE TEST COMPLETE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
