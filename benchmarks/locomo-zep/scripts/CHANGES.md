# Changes from Original Zep Scripts

Scripts in this directory are adapted from `getzep/zep-papers` (`kg_architecture_agent_memory/locomo_eval/`).

## zep_locomo_ingestion.py

| Change | Original | Adapted | Reason |
|--------|----------|---------|--------|
| Data path | `../data/locomo.json` | `data/locomo.json` | Path consistency |
| Data source | Download from GitHub URL | Read local file | Python 3.9 SSL certificate issue |
| Group creation | `zep.group.add(group_id=)` | `zep.graph.create(graph_id=)` | zep-cloud SDK 3.x API change |
| Graph add | `graph.add(..., group_id=)` | `graph.add(..., graph_id=)` | zep-cloud SDK 3.x parameter rename |

## zep_locomo_search.py

| Change | Original | Adapted | Reason |
|--------|----------|---------|--------|
| Data source | Download from GitHub URL | Read local file | Avoid redundant download |
| Search params | `group_id=` | `graph_id=` | zep-cloud SDK 3.x parameter rename |
| Retry logic | None (crash on timeout) | 3 retries with exponential backoff | Network resilience |
| Progress saving | Save only at end | Save per-user (incremental) | Crash recovery |
| Edge/Node limits | `limit=20` (both) | Configurable: Round 1 used 20+20, Round 2 used 7+3 | Testing different retrieval budgets |

## zep_locomo_responses.py

| Change | Original | Adapted | Reason |
|--------|----------|---------|--------|
| Answer model | `gpt-4o-mini` | `gpt-5-mini` | Stronger answer model per test requirements |
| Temperature | `temperature=0` | Removed | gpt-5-mini does not support temperature parameter |
| `zip(strict=True)` | Present | Removed | Python 3.9 compatibility |

## zep_locomo_eval.py

**No changes.** Identical to original. Uses `gpt-4o-mini` with `temperature=0` for deterministic judging.

## SDK Compatibility Note

- Original scripts require `zep-cloud==2.22.1` (last version with `group_id` parameter)
- Adapted scripts require `zep-cloud>=3.0` (uses `graph_id` parameter)
- zep-cloud 3.x removed `zep.group` client entirely
