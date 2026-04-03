# M-Flow Benchmark Results

Comparative evaluation of M-Flow's Episodic Retriever against Cognee's Graph Completion and Graphiti's Temporal Context Graph.

## Benchmarks

| Benchmark | Questions | Source | Task Type |
|-----------|-----------|--------|-----------|
| [Evolving Events](evolving-events/) | 100 | Custom enterprise knowledge corpus (159 chunks) | Long-term cross-chunk fuzzy & multi-hop reasoning |

## Systems Under Test

| System | Retrieval Method | Graph DB | Vector DB |
|--------|-----------------|----------|-----------|
| **M-Flow** | Episodic Bundle Search (path-cost scoring, adaptive weights) | KuzuDB | LanceDB |
| **Cognee** | Graph Completion (triplet search) | KuzuDB | LanceDB |
| **Graphiti** | Temporal Context Graph (BM25 + Vector + RRF hybrid) | Neo4j | Neo4j built-in |

## Configuration

- **Ingestion LLM**: M-Flow uses `gpt-5-nano`, Cognee and Graphiti use `gpt-5-mini` (respective defaults)
- **Answer LLM**: `gpt-5.4` and `gpt-5-mini` (tested both)
- **Judge LLM**: `gpt-5.4` (for both DeepEval and DirectLLM evaluation)
- **top_k**: 5, 10
- **Evaluation**: Human-like Correctness (DirectLLM judge) + DeepEval Correctness (GEval)

## Results

### Evolving Events (100 cross-chunk fuzzy & multi-hop questions)

|  k  | LLM       | M-Flow HL | Cognee HL | Graphiti HL | M-Flow DE | Cognee DE | Graphiti DE |
|-----|-----------|-----------|-----------|-------------|-----------|-----------|-------------|
|  5  | gpt-5-mini | 0.958     | 0.886     | 0.663       | 0.636     | 0.604     | 0.469       |
|  5  | gpt-5.4    | 0.964     | 0.896     | 0.630       | 0.655     | 0.625     | 0.468       |
| 10  | gpt-5-mini | 0.968     | 0.912     | 0.692       | 0.639     | 0.635     | 0.504       |
| 10  | gpt-5.4    | 0.977     | 0.930     | 0.684       | 0.654     | 0.628     | 0.496       |

HL = Human-like Correctness (DirectLLM judge) · DE = DeepEval Correctness (GEval)  
Bootstrap 95% confidence intervals available in each `summary.json` file.

## Metrics

- **Human-like Correctness**: LLM-as-judge evaluation where gpt-5.4 scores answer correctness on a 0-1 scale, comparing generated answers against golden answers.
- **DeepEval Correctness**: GEval-based evaluation using gpt-5.4, measuring semantic correctness with structured rubric scoring.

## Reproducibility

Results were generated using the scripts in the project's benchmark workspace. To reproduce:

1. Install M-Flow, Cognee, and Graphiti from source with their respective dependencies
2. Set `LLM_API_KEY` environment variable with an OpenAI API key
3. Ingest the corpus data into each system's database
4. Run answer generation with the specified `top_k` and LLM model
5. Run evaluation using DeepEval and DirectLLM frameworks with `gpt-5.4` as judge

Each `results/{system}/topk{k}_{llm}/` directory contains the raw outputs for full transparency. The `unified_evaluated.json` file contains per-question scores for detailed analysis.

## Directory Structure

```
benchmarks/
├── README.md                    # This file
├── all_results.json             # Machine-readable summary of all results
└── evolving-events/
    ├── README.md                # Evolving Events benchmark details
    ├── data/                    # Questions and corpus (159 chunks, 100 questions)
    └── results/
        ├── mflow/               # M-Flow results per config
        ├── cognee/              # Cognee results per config
        └── graphiti/            # Graphiti results per config
```

Each result directory contains:
- `answers.json` — Generated answers with questions and golden answers
- `summary.json` — Aggregated metrics with bootstrap confidence intervals
- `unified_evaluated.json` — Per-question evaluation scores

## License

Benchmark data and results are released under the same license as the M-Flow project.
