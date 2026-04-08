# Zep Cloud LoCoMo Benchmark — Methodology

## 1. Pipeline Overview

Based on `getzep/zep-papers` official 4-step pipeline:

```
Step 1: Ingestion       Step 2: Search          Step 3: Response        Step 4: Evaluation
zep_locomo_ingestion.py zep_locomo_search.py    zep_locomo_responses.py zep_locomo_eval.py

locomo10.json →         For each question:      gpt-5-mini generates    gpt-4o-mini judges
Zep Cloud API           2 parallel searches:    answer from context     CORRECT/WRONG
graph.add()             - edges (cross_encoder)
                        - nodes (rrf)
                        Compose context template
```

## 2. Ingestion

- **API**: `zep.graph.create()` + `zep.graph.add(type='message', created_at=...)`
- **Data**: 10 users × 19-32 sessions = 5882 messages
- **Time**: ~27 minutes
- **Known bug preserved**: `blip_captions` typo drops all 1226 image descriptions (see `known_issues/`)
- **Session timestamps**: Parsed from LOCOMO format `"1:56 pm on 8 May, 2023"` → ISO 8601

## 3. Search

Two configurations were tested:

### Round 1: 20 edges + 20 nodes (= 40 items/query)
```python
await asyncio.gather(
    zep.graph.search(scope='nodes', reranker='rrf', limit=20),
    zep.graph.search(scope='edges', reranker='cross_encoder', limit=20),
)
```

### Round 2: 7 edges + 3 nodes (= 10 items/query)
Reduced to match M-flow's `top_k=10` retrieval budget. Selection rationale:
- Token budget alignment: Zep 2079 chars ≈ M-flow ~1800 chars (estimated at design time)
- Preserves Zep's dual-channel architecture (edges + nodes)
- Ratio 7:3 close to Zep's default 3:1 (15:5)

### Context Template
```
<FACTS>
  - {edge.fact} (event_time: {edge.valid_at})
  ...
</FACTS>
<ENTITIES>
  - {node.name}: {node.summary}
  ...
</ENTITIES>
```

## 4. Response Generation

- **Model**: `gpt-5-mini` (original scripts use `gpt-4o-mini`)
- **Temperature**: Default (1) — gpt-5-mini does not support temperature=0
- **Prompt**: System prompt with 7-step reasoning chain + timestamp interpretation guidance
- **Processing**: All questions per user via `asyncio.gather` (parallel)

## 5. Evaluation

- **Model**: `gpt-4o-mini` (temperature=0, deterministic)
- **Prompt**: Zep's ACCURACY_PROMPT (contains `williolw23` typo, preserved for consistency)
- **Format**: Pydantic structured output: `Grade(is_correct: str, reasoning: str)`
- **Score**: `is_correct.strip().lower() == 'correct'`
- **Denominator**: Hardcoded `/1540` in original script

## 6. Differences from Official Zep Benchmark

| Aspect | Official (75.13%) | Our Test |
|--------|-------------------|----------|
| Answer model | gpt-4o-mini | gpt-5-mini |
| Answer temperature | 0 | 1 (not configurable) |
| Judge model | gpt-4o-mini | gpt-4o-mini (same) |
| Edge limit | 20 | Round 1: 20, Round 2: 7 |
| Node limit | 20 | Round 1: 20, Round 2: 3 |
| SDK version | ~2.x | Adapted for 3.x |
| blip_captions bug | Present | Present (preserved) |
| eval prompt typo | Present | Present (preserved) |

## 7. Data Fields

Each item in `FULL_REPORT.json`:

| Field | Description |
|-------|-------------|
| `user_id` | LOCOMO user identifier |
| `question_index` | Sequential index within user's non-cat5 questions |
| `question` | Question text |
| `category` | Category number (1-5) |
| `category_label` | Correct label (Multi-hop/Temporal/Open-domain/Single-hop) |
| `gold_answer` | Ground truth answer |
| `zep_answer` | Zep's generated answer |
| `grade` | Judge verdict: true/false |
| `search_context` | Full retrieved context (FACTS + ENTITIES template) |
| `retrieval_config` | `{"edges": N, "nodes": M}` |

## 8. Known Limitations

1. **gpt-5-mini temperature=1**: Non-deterministic; results may vary between runs
2. **Zep Cloud is a SaaS**: Internal models/algorithms may change; results reflect 2026-04-02/03
3. **Embedding model unknown**: Zep Cloud handles embedding internally (Graphiti default: text-embedding-3-small)
4. **blip_captions bug**: 1226 image descriptions not ingested
5. **11 duplicate questions**: 11 question texts appear twice across different users (1540 total, 1529 unique)
