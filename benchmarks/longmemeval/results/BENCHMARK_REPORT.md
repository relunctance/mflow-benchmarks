# LongMemEval Benchmark Evaluation Report

**Evaluation Date**: 2026-03-26  
**Questions Evaluated**: 50  
**Dataset**: LongMemEval Oracle

---

## 1. Evaluation Overview

This evaluation compares the retrieval and question-answering capabilities of **Graphiti** and **MFlow** memory engines using the first 50 questions from the LongMemEval dataset.

### Evaluation Pipeline

1. **Ingestion**: 50 questions with context sessions (113 sessions, ~1319 messages)
2. **Retrieval**: Retrieve relevant memories for each question (top-k=10)
3. **Answer Generation**: Generate answers using GPT-4.1-mini based on retrieved context
4. **Scoring**: Calculate BLEU-1, F1, and LLM-Judge metrics

### Unified Configuration

| Configuration | Value |
|---------------|-------|
| Embedding Model | `text-embedding-3-small` |
| Embedding Dimensions | 1024 |
| Answer/Judge Model | `gpt-4.1-mini` |
| Questions Evaluated | 50 |

---

## 2. Overall Comparison Results

### 2.1 Core Metrics Comparison

| Metric | MFlow | Graphiti | Difference |
|--------|-------|----------|------------|
| **LLM-Judge Accuracy** | **80.00%** | 64.00% | **+16.00%** |
| **F1** | **0.4047** | 0.3722 | +0.0325 |
| **BLEU-1** | **0.2953** | 0.2885 | +0.0068 |
| Total Evaluation Time | 137.79 s | 129.64 s | +8.15 s |

### 2.2 Conclusion

**MFlow achieves higher question-answering accuracy than Graphiti on this 50-question subset**:
- LLM-Judge accuracy is **16 percentage points higher** (80% vs 64%)
- MFlow correctly answered 40 out of 50 questions; Graphiti answered 32

---

## 3. MFlow Evaluation Details

### 3.1 Overall Metrics

| Metric | Value |
|--------|-------|
| **BLEU-1** | 0.2953 |
| **F1** | 0.4047 |
| **LLM-Judge Accuracy** | **80.00%** |
| Total Evaluation Time | 137.79 s |

### 3.2 Correct/Incorrect Statistics

- Correct: 40/50 (80%)
- Incorrect: 10/50 (20%)

### 3.3 Examples

**Correct Examples**:

| Question | Gold Answer | Generated Answer | BLEU-1 |
|----------|-------------|------------------|--------|
| What time did my alarm go off this morning? | 6:45 AM | 6:45 AM | 1.00 |
| What airline did I book for my recent trip? | United Airlines | United Airlines | 1.00 |
| What book club am I a member of? | Page Turners | Page Turners | 1.00 |

**Incorrect Examples**:

| Question | Gold Answer | Generated Answer | Cause |
|----------|-------------|------------------|-------|
| Which event did I attend first...? | 'Data Analysis using Python' webinar | Time Management workshop | Temporal reasoning error |
| What streaming service did I subscribe to? | Netflix | Apple TV+ | Memory confusion |

---

## 4. Graphiti Evaluation Details

### 4.1 Overall Metrics

| Metric | Value |
|--------|-------|
| **BLEU-1** | 0.2885 |
| **F1** | 0.3722 |
| **LLM-Judge Accuracy** | **64.00%** |
| Total Evaluation Time | 129.64 s |

### 4.2 Correct/Incorrect Statistics

- Correct: 32/50 (64%)
- Incorrect: 18/50 (36%)

### 4.3 Primary Error Types

1. **Temporal Reasoning Errors**: Difficulty determining correct event ordering
2. **Insufficient Retrieval Recall**: Relevant information not found for some questions
3. **Information Integration Errors**: Confusion between similar memories

---

## 5. Ingestion Statistics

### 5.1 Graphiti Ingestion

| Metric | Value |
|--------|-------|
| Successful Questions | 50/50 |
| Total Messages | 1319 |
| Total Duration | ~9.1 hours |
| Avg Time per Question | ~10.9 minutes |
| Neo4j Nodes | 8288 |
| Neo4j Relationships | ~19000 |

### 5.2 MFlow Ingestion

| Metric | Value |
|--------|-------|
| Successful Questions | 50/50 |
| Total Messages | 1319 |
| Total Duration | ~9.2 hours |
| Avg Time per Question | ~11.1 minutes |
| Kuzu Graph Nodes | ~15000 |
| LanceDB Vectors | 6955 |

---

## 6. Technical Issue Resolution Log

### 6.1 MFlow Vector Index Issue

**Problem**: Vector index was empty after ingestion, causing retrieval to return 0 results.

**Root Cause Analysis**:
```
Ingestion log: ValidationError: vector - List should have at most 1024 items
```
- `LiteLLMEmbeddingEngine.py` did not pass the `dimensions` parameter when calling `litellm.aembedding()`
- OpenAI `text-embedding-3-small` returns 1536 dimensions by default
- LanceDB table schema was limited to 1024 dimensions
- Dimension mismatch caused all vector validations to fail

**Resolution**:
1. Code fix: Added `dimensions=self.dimensions` in `LiteLLMEmbeddingEngine.py`
2. Data fix: Created `rebuild_vector_index.py` script to rebuild vector index from Kuzu nodes

**Result**: Successfully rebuilt 6,955 vector rows without re-ingestion

---

## 7. Conclusions and Recommendations

### 7.1 Performance Comparison Summary

| Dimension | Winner | Notes |
|-----------|--------|-------|
| **QA Accuracy** | MFlow | 80% vs 64%, leading by 16 percentage points |
| **Token Coverage** | MFlow | F1 0.40 vs 0.37 |

### 7.2 Recommendations

1. **Scale Up Testing**: Increase to 100-500 questions for more comprehensive validation
2. **Category Analysis**: Analyze performance differences by question type (temporal, entity, attribute)
3. **Retrieval Recall**: Add Recall@K metric to evaluate retrieval quality

---

## Appendix

### File Locations

- Graphiti evaluation results: `results/graphiti_eval_results.json`
- MFlow evaluation results: `results/mflow_eval_results.json`
- MFlow ingestion script: `scripts/mflow_ingest.py`
- MFlow evaluation script: `scripts/mflow_qa_eval.py`
- Results analysis: `scripts/analyze_results.py`
- Vector rebuild script: `scripts/rebuild_vector_index.py`
