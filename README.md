# MFlow Benchmarks

Comparative benchmark suite evaluating episodic memory systems for AI agents.

## Overview

| Benchmark | Questions | Systems Tested | Key Metric |
|-----------|-----------|----------------|------------|
| **LoCoMo-10** | 1,540 | M-flow, Cognee Cloud, Zep Cloud, Supermemory, Mem0 Cloud | LLM-Judge Accuracy |
| **LongMemEval** | 100 | M-flow, Supermemory Cloud, Mem0 Cloud, Zep Cloud, Cognee | LLM-Judge Accuracy |
| **Evolving Events** | 100 | M-flow, Cognee, Graphiti | Human-like Correctness |

## Results Summary

### LoCoMo-10 (Multi-Session Conversational QA)

All systems use gpt-5-mini (answer) + gpt-4o-mini (judge). Cat 5 (adversarial) excluded.

**Aligned (top-k = 10)**

| System | LLM-Judge | Answer LLM | Judge LLM | Top-K |
|--------|:---------:|------------|-----------|:-----:|
| **M-flow** | **81.8%** | gpt-5-mini | gpt-4o-mini | 10 |
| Cognee Cloud | 79.4% | gpt-5-mini | gpt-4o-mini | 10 |
| Zep Cloud (7e+3n) | 73.4% | gpt-5-mini | gpt-4o-mini | 10 |
| Supermemory | 64.4% | gpt-5-mini | gpt-4o-mini | 10 |

**With vendor-default retrieval budgets**

| System | LLM-Judge | Answer LLM | Judge LLM | Top-K |
|--------|:---------:|------------|-----------|:-----:|
| **M-flow** | **81.8%** | gpt-5-mini | gpt-4o-mini | 10 |
| Cognee Cloud | 79.4% | gpt-5-mini | gpt-4o-mini | 10 |
| Zep Cloud (20e+20n) | 78.4% | gpt-5-mini | gpt-4o-mini | 40 |
| Mem0ᵍ Cloud (published) | 68.5% | — | — | — |
| Mem0 Cloud (published) | 67.1% | — | — | — |
| Supermemory | 64.4% | gpt-5-mini | gpt-4o-mini | 10 |
| Mem0 Cloud (tested) | 50.4% | gpt-5-mini | gpt-4o-mini | 30 |

Mem0 published scores from [Mem0 paper](https://arxiv.org/abs/2504.19413); answer/judge LLMs not disclosed. Our tested result (50.4%) uses the same evaluation pipeline as all other systems.

### LongMemEval (Long-term Memory QA)

First 100 questions. All systems use gpt-5-mini (answer) + gpt-4o-mini (judge) + top-k=10.

| System | LLM-Judge | Temporal (60) | Multi-session (40) |
|--------|:---------:|:-------------:|:------------------:|
| **M-flow** | **89%** | **93%** | **82%** |
| Supermemory Cloud | 74% | 78% | 68% |
| Mem0 Cloud | 71% | 77% | 63% |
| Zep Cloud | 61% | 82% | 30% |
| Cognee | 57% | 67% | 43% |

### Evolving Events (Multi-hop Reasoning)

| Config | M-flow HL | Cognee HL | Graphiti HL |
|--------|-----------|-----------|-------------|
| k=5, gpt-5-mini | 95.8% | 88.6% | 66.3% |
| k=5, gpt-5.4 | 96.4% | 89.6% | 63.0% |
| k=10, gpt-5-mini | 96.8% | 91.2% | 69.2% |
| k=10, gpt-5.4 | 97.7% | 93.0% | 68.4% |

*HL = Human-like Correctness (DirectLLM judge)*

## Directory Structure

```
mflow-benchmarks/
├── LICENSE
├── README.md
├── CONTRIBUTING.md
└── benchmarks/
    ├── locomo-mflow/           # M-flow LoCoMo-10 results
    ├── locomo-cognee/          # Cognee Cloud LoCoMo-10 results
    ├── locomo-zep/             # Zep Cloud LoCoMo-10 results
    ├── locomo-supermemory/     # Supermemory LoCoMo-10 results
    ├── locomo-mem0/            # Mem0 Cloud LoCoMo-10 results
    ├── longmemeval-mflow/      # M-flow LongMemEval results
    ├── longmemeval-mem0/       # Mem0 Cloud LongMemEval results
    ├── longmemeval-cognee/     # Cognee LongMemEval results
    ├── longmemeval-zep/        # Zep Cloud LongMemEval results
    ├── longmemeval-supermemory/# Supermemory Cloud LongMemEval results
    └── evolving-events/        # Evolving Events benchmark
```

Each system subdirectory contains a README with full results, reproduction scripts, raw data, and methodology.

## Evaluation Methodology

- **LLM-Judge**: Binary CORRECT/WRONG evaluation using GPT-4 class models
- **Human-like Correctness**: DirectLLM judge for semantic accuracy
- **BLEU-1 / F1**: Token-level precision and recall metrics
- **Category 5** (Adversarial): Excluded from LoCoMo per standard methodology (no gold answers)

All benchmarks use identical prompts, metrics, and judge models across systems to ensure fair comparison.

## Citation

If you use these benchmarks in your research, please cite:

```bibtex
@software{mflow_benchmarks_2026,
  title = {MFlow Benchmarks},
  author = {MFlow Team},
  year = {2026},
  url = {https://github.com/FlowElement-ai/mflow-benchmarks}
}
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
