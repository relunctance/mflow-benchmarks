# Cognee Cloud LoCoMo Benchmark — Methodology

## 1. Pipeline Overview

```
Step 1: Ingest        Step 2: Search         Step 3: Answer         Step 4: Evaluate
(~1 hour)             (~30 min/conv)         (parallel w/ search)   (~15 min/conv)

locomo10.json →       For each question:     gpt-5-mini             gpt-4o-mini
Per-session upload    CHUNKS vector search   generates answer       judges CORRECT/WRONG
to Cognee Cloud →     top-10 chunks          from retrieved chunks  + BLEU-1, F1
cognify (KG build)
```

## 2. Dataset

- **Name**: LoCoMo-10 (Long Conversation Memory)
- **Source**: [snap-research/locomo](https://github.com/snap-research/locomo)
- **Contents**: 10 multi-session conversations between two speakers
- **Total questions**: 1986
- **Evaluated questions**: 1540 (Category 5 / Adversarial excluded — no gold answers)
- **Category mapping**: See `config/category_mapping.json` for the correct mapping (confirmed by official Issue #27)

### Question Distribution

| Cat | Type | Count | % |
|:---:|------|:-----:|:---:|
| 4 | Single-hop | 841 | 54.6% |
| 2 | Temporal | 321 | 20.8% |
| 1 | Multi-hop | 282 | 18.3% |
| 3 | Open-domain | 96 | 6.2% |

## 3. Ingestion

- **Script**: `scripts/run_ingest.py`
- **Strategy**: Each conversation session is uploaded as a separate text file to a Cognee dataset, then `cognify` is called once per conversation to build the knowledge graph.
- **Session formatting**: Each message is prefixed with its timestamp:
  ```
  [May 08, 2023, 01:56 PM] Caroline: I went to a LGBTQ support group yesterday...
  [May 08, 2023, 01:56 PM] Melanie: Wow, that's cool, Caroline!...
  ```
- **Image descriptions** from `blip_caption` are included as `[Image shared by Speaker: description]`.
- **Dataset naming**: `locomo_r4_{speaker_a}_{speaker_b}_{idx}` (e.g., `locomo_r4_Caroline_Melanie_0`)
- **Batching**: 3-3-4 pattern (3 conversations parallel in batch 1, 3 in batch 2, 4 in batch 3)

### Cognee Processing (Server-Side)

When `cognify` is called, Cognee Cloud processes each uploaded text file through:

1. **Document classification** → TextDocument
2. **Chunking** → `TextChunker` with `chunk_by_paragraph` (max_chunk_size = `get_max_chunk_tokens()`, approximately 8191 tokens for `text-embedding-3-small`)
3. **Graph extraction** → Entity and relationship extraction from chunks
4. **Summarization** → Text summaries
5. **Embedding** → Vector embeddings stored in `DocumentChunk_text` collection

Since each session file is smaller than the max chunk size (~700-2700 tokens), each session becomes **one DocumentChunk**. This means the chunk granularity equals the session granularity.

## 4. Search + Answer

- **Script**: `scripts/search_aligned.py`
- **Search type**: `CHUNKS` — pure vector similarity search on `DocumentChunk_text` collection
- **Top-k**: 10 (retrieves 10 most similar conversation session chunks)
- **Answer LLM**: `gpt-5-mini` (OpenAI reasoning model)
- **Answer constraint**: "Be concise (5-6 words). No explanation." — aligned with M-flow and Mem0

### Search Modes Available (Only CHUNKS Used)

| Mode | Description | Used in This Benchmark |
|------|-------------|:---------------------:|
| CHUNKS | Pure vector search on text chunks | **Yes** |
| GRAPH_COMPLETION | Graph-enhanced context (Cognee's LLM answers) | No |
| SUMMARIES | Pre-generated summaries | No |
| RAG_COMPLETION | RAG-based completion | No |

### Answer Prompt

The CHUNKS prompt is designed for raw conversation fragments (see `scripts/prompts.py`):

- Instructs the LLM to extract facts from dialogue
- Provides timestamp resolution guidance (e.g., "last year" in May 2023 → 2022)
- Handles conflicting information by preferring more recent conversations
- Falls back to "Unknown" only when no fragment contains relevant information

## 5. Evaluation

- **Script**: `scripts/evaluate_aligned.py`
- **Judge LLM**: `gpt-4o-mini` (temperature=0, deterministic)
- **Judge prompt**: Mem0's published `ACCURACY_PROMPT` — generous grading that counts answers as CORRECT if they "touch on the same topic" as the gold answer
- **Response format**: `json_object` with `{"label": "CORRECT"}` or `{"label": "WRONG"}`

### Metrics

| Metric | Implementation | Notes |
|--------|---------------|-------|
| **LLM-Judge** | Binary CORRECT/WRONG via `gpt-4o-mini` | Primary metric; generous grading |
| **BLEU-1** | Unigram precision with Method1 smoothing | `nltk.translate.bleu_score.sentence_bleu` |
| **F1** | Token-level precision/recall | Tokenization by whitespace after lowercasing and punctuation removal |

All metric implementations are in `scripts/metrics.py` and are aligned with the Mem0 published implementation.

## 6. Run History

### Run r3 (Failed)

- **Date**: April 3-4, 2026
- **Dataset prefix**: `locomo_r3`
- **Result**: Overall 1.49% — catastrophic failure
- **Root cause**: Cognee Cloud dataset isolation failure. Search queries for one conversation returned chunks from different conversations. Additionally, Conv 9 suffered from "connection pool exhaustion" causing sessions 16-30 to fail cognify.
- **Status**: Data preserved in original `cognee-locomo-bench/results/` but **not included** in this package.

### Run r4 (Successful)

- **Date**: April 5, 2026 (00:13 - 07:35 UTC)
- **Dataset prefix**: `locomo_r4`
- **Result**: Overall 79.42% (1223/1540)
- **Fix applied**: New `run_id` prefix (`r4`) to ensure clean dataset isolation on Cognee Cloud.
- **Status**: All 10 conversations complete. **This is the data in this package.**

## 7. Differences from M-flow Evaluation

| Aspect | Cognee | M-flow |
|--------|--------|--------|
| Search type | CHUNKS (vector) | EpisodicRetriever (vector + graph + bundle scoring) |
| Context format | Raw conversation text with embedded timestamps | Episode summaries with structured metadata |
| Context size per question | ~7000-27000 tokens (10 full session chunks) | ~500-1500 tokens (10 episode summaries) |
| Chunk granularity | Session-level (~15-30 messages) | Episode-level (LLM-summarized) |
| Evaluated questions | 1540 (all cat5 excluded) | 1541 (1 cat5 included in conv1) |
| Answer model | gpt-5-mini | gpt-5-mini |
| Judge model | gpt-4o-mini | gpt-4o-mini |
| Overlap/redundancy | No chunk overlap | N/A (episodes are deduplicated) |

## 8. Known Limitations

1. **No chunk overlap**: Cognee's default `TextChunker` does not implement overlap between chunks. Information at chunk boundaries could be lost if sessions were large enough to be split.

2. **Session-level granularity**: Since each session is uploaded as a separate file and each is smaller than `max_chunk_size`, every session becomes exactly one chunk. Finer-grained chunking was not tested.

3. **CHUNKS bypasses the knowledge graph**: The CHUNKS search type performs pure vector search and does not leverage the graph structures built during `cognify`. Graph-based search types (GRAPH_COMPLETION) were not used for this benchmark.

4. **Cognee Cloud as black box**: The exact embedding model, vector database, and graph database used by Cognee Cloud are not directly configurable or inspectable. Configuration is inferred from the open-source Cognee codebase.

5. **Non-deterministic answers**: `gpt-5-mini` is a reasoning model where temperature is not user-configurable. Results may vary slightly between runs.

6. **No variance measurement**: Unlike M-flow's 5-run variance test on Conv 8, Cognee was only run once. Natural LLM variance is expected to be ±1-2%.

## 9. Data Integrity

All data in this package has been verified:

- **10/10 conversations** have complete search, eval, and full_report data
- **detail reports match eval data**: Accuracy figures in `full_report.json` exactly match scores computed from `eval.json` for all 10 conversations
- **search-eval alignment**: All non-cat5 questions in search results appear in eval results (verified per conversation)
- **aggregate consistency**: Per-category sums equal overall totals (1223 correct, 1540 evaluated)
