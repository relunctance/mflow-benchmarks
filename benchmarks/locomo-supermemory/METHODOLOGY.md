# Supermemory LoCoMo Benchmark — Methodology

## 1. Framework

This benchmark was run using **MemoryBench**, an open-source TypeScript framework for evaluating AI memory systems. The framework handles the full pipeline: ingest → index → search → answer → evaluate → report.

## 2. Pipeline

```
Phase 1: Ingest     Phase 2: Index      Phase 3: Search     Phase 4: Answer     Phase 5: Evaluate
locomo10.json →     Wait for indexing    Search top-10       gpt-5-mini          gpt-4o-mini
Supermemory API     to complete          memories per        generates answer    judges
add memories                             question            from context        CORRECT/WRONG
```

## 3. Configuration

- **Run ID**: locomo-sm-test-002
- **Dataset**: LoCoMo-10 (1986 questions, all categories including adversarial)
- **Answer model**: gpt-5-mini
- **Judge model**: gpt-4o-mini
- **Top-K**: 10
- **Concurrency**: 5

## 4. Differences from Other Systems

### Adversarial Questions Included

Supermemory evaluates **all 1986 questions** including Category 5 (adversarial, 446 questions with no gold answers). M-flow and Zep exclude these. For comparison:
- Including adversarial: 1291/1986 = 65.0%
- **Excluding adversarial: 991/1540 = 64.4%**

### Category Labels

MemoryBench uses text labels that correctly align with snap-research/locomo Issue #27:

| MemoryBench Label | Official Label | Cat # in Data | Count |
|-------------------|---------------|:---:|:---:|
| multi-hop | Multi-hop | 1 | 321 |
| temporal | Temporal | 2 | 96 |
| world-knowledge | Open-domain | 3 | 841 |
| single-hop | Single-hop | 4 | 282 |
| adversarial | Adversarial | 5 | 446 |

### Rich Retrieval Metrics

Unlike M-flow/Zep which only report LLM-Judge accuracy, MemoryBench also computes:
- Hit@K, Precision@K, Recall@K, F1@K
- MRR (Mean Reciprocal Rank)
- NDCG (Normalized Discounted Cumulative Gain)

### Per-Question Result Files

Each of the 1986 questions has an individual JSON file in `results/per_question/` containing:
- Full search results (memories with text, similarity scores, metadata, document chunks)
- Generated answer (hypothesis)
- Judge verdict (score, label, explanation)
- Retrieval metrics per question
- Latency breakdown

## 5. Data Fields

### report.json (Full — 359MB)

Contains everything including `evaluations` array with all searchResults. Key top-level fields:
- `summary`: overall scores
- `latency`: per-phase timing statistics
- `tokens`: token usage statistics
- `retrieval`: aggregate retrieval metrics
- `byQuestionType`: per-category breakdown
- `evaluations`: 1986 items with full details

### report_slim.json (2MB)

Same as above but `evaluations` have truncated hypothesis and no searchResults.

### Per-question files

Each file in `per_question/` contains:
- `questionId`: e.g., "conv-26-q0"
- `question`: question text
- `questionType`: category label
- `groundTruth`: gold answer
- `results`: array of search results (memories with full metadata)
- `durationMs`: total processing time

## 6. Known Limitations

1. **gpt-5-mini non-deterministic**: Temperature not explicitly controlled
2. **1/1986 questions has no searchResults**: One question returned empty search
3. **perConversation array is empty**: report.json lacks per-conversation breakdown
4. **Adversarial scoring**: 67.3% on adversarial questions may inflate overall score compared to systems that exclude these
