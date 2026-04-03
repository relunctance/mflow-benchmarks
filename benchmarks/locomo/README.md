# LoCoMo-10 Benchmark

## Results

Dataset: LoCoMo-10 (10 conversations, 1540 evaluated questions)
Judge LLM: gpt-4o-mini

| System | LLM-Judge | BLEU-1 | F1 |
|--------|-----------|--------|-----|
| **M-flow** | **76.5%** | **0.422** | **0.503** |
| Mem0 Cloud (tested) | 40.4% | 0.186 | 0.196 |
| Mem0 (published) | 66.9% | — | — |

Testing methodology aligns with Mem0's approach while accommodating architectural differences between systems. Both M-flow and Mem0 Cloud were tested using the same evaluation framework.

### Per-Category

| Category | Description | M-flow | Mem0 Cloud (tested) | Mem0 (published) |
|----------|------------|--------|---------------------|------------------|
| 1 | Single-hop (factual) | 68.5% | 44.7% | 67.1% |
| 2 | Temporal | 78.8% | 7.5% | 55.5% |
| 3 | Multi-hop (reasoning) | 48.0% | 39.6% | 51.1% |
| 4 | Open-domain (event detail) | 81.5% | 44.4% | 72.9% |

### Per-Conversation

| Conv | Speakers | Questions | M-flow | Mem0 Cloud |
|------|----------|-----------|--------|------------|
| 0 | Caroline ↔ Melanie | 152 | 74.2% | 36.8% |
| 1 | Jon ↔ Gina | 81 | 75.0% | 38.3% |
| 2 | John ↔ Maria | 152 | 74.8% | 26.3% |
| 3 | Joanna ↔ Nate | 199 | 76.9% | 36.2% |
| 4 | Tim ↔ John | 178 | 75.5% | 44.9% |
| 5 | Audrey ↔ Andrew | 123 | 72.5% | 45.5% |
| 6 | James ↔ John | 150 | 82.5% | 42.7% |
| 7 | Deborah ↔ Jolene | 191 | 78.1% | 46.1% |
| 8 | Evan ↔ Sam | 156 | 76.7% | 45.5% |
| 9 | Calvin ↔ Dave | 158 | 77.0% | — |

Conv 9 for Mem0 Cloud was not completed due to an API error during testing.

### Reference

Mem0 published data from [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://huggingface.co/papers/2504.19413).

## Reproduce

### Prerequisites

- M-Flow installed (`pip install -e .` from the M-Flow repo root)
- `LLM_API_KEY` and `OPENAI_API_KEY` environment variables set
- For Mem0 testing: `MEM0_API_KEY` environment variable set
- Dataset: `locomo10.json` — the LoCoMo-10 conversation dataset

### Obtaining the Dataset

The LoCoMo-10 dataset (`locomo10.json`) is from the [LoCoMo benchmark](https://github.com/snap-stanford/locomo). To obtain it:

1. Visit the [LoCoMo GitHub repository](https://github.com/snap-stanford/locomo)
2. Download the dataset following their instructions
3. Place it at `dataset/locomo10.json` relative to the benchmark directory

### M-flow: One-click

```bash
cd benchmarks/locomo
bash run_benchmark.sh
```

Total time: ~4 hours (ingest ~2.5h, search ~1h, eval ~30min).

### M-flow: Step by step

```bash
cd benchmarks/locomo

# 1. Ingest (all 10 conversations, ~2.5 hours)
python run_ingest_batched.py --data dataset/locomo10.json

# 2. Stop API server if running (Kuzu file lock)
# 3. Search + Answer (~1 hour)
python search_aligned.py \
  --data-path dataset/locomo10.json \
  --output-path ./results/mflow_search.json \
  --top-k 10

# 4. Evaluate (~30 minutes)
python evaluate_aligned.py \
  --input-file ./results/mflow_search.json \
  --output-file ./results/mflow_eval.json
```

## Methodology

### Dataset

LoCoMo-10: 10 multi-session conversations between two speakers, totaling 1986 questions. Category 5 (adversarial) is excluded per standard methodology, leaving 1540 evaluated questions across 4 categories.

### Evaluation

- **LLM-Judge**: Binary CORRECT/WRONG using Mem0's published ACCURACY_PROMPT
- **BLEU-1**: Unigram precision with smoothing (aligned with Mem0 implementation)
- **F1**: Token-level precision/recall (aligned with Mem0 implementation)

### M-flow Configuration

- Ingestion: per-session serial ingest with Episode Routing enabled
- Retrieval: EpisodicRetriever (vector search + graph projection + bundle scoring)
- top-k: 10

### Mem0 Cloud Configuration

Mem0 was tested using their published evaluation code from [mem0ai/mem0 `/evaluation`](https://github.com/mem0ai/mem0/tree/main/evaluation), with the following configuration aligned for fair comparison:

| Parameter | Value | Notes |
|-----------|-------|-------|
| SDK | mem0ai 1.0.7 | Latest at time of testing |
| Ingestion API | `MemoryClient.add()` | `version="v2"`, `infer=True` |
| Ingestion mode | Per-speaker, dual-thread | As per Mem0's `evaluation/src/memzero/add.py` |
| Custom instructions | Enabled | Set via `client.project.update(custom_instructions=...)` |
| Batch size | 2 messages per API call | As per Mem0's default |
| Retrieval API | `MemoryClient.search()` | `filters={"user_id": ...}` |
| Retrieval mode | Per-speaker (2 searches per question) | Speaker A + Speaker B searched separately |
| top-k | 10 per speaker | Up to 20 memories total per question |
| Embedding | Mem0 Cloud default | Not configurable via API |
| Answer prompt | Mem0's published `ANSWER_PROMPT` | Dual-speaker memories format |
| Judge prompt | Mem0's published `ACCURACY_PROMPT` | Same as M-flow evaluation |
| Judge LLM | gpt-4o-mini | Same as M-flow evaluation |
| Temperature | 0.0 | Deterministic output |
