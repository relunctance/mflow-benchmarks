# Known Issues

## 1. Category Label: "world-knowledge" vs "Open-domain"

Supermemory/MemoryBench uses `world-knowledge` for what snap-research/locomo Issue #27 calls `Open-domain` (Category 3 in the dataset). The labels are functionally equivalent but named differently.

## 2. Adversarial Questions Included in Score

Supermemory's overall score (65.0%) includes Category 5 (adversarial) questions. These 446 questions have no gold answers in the dataset. MemoryBench scores them based on whether the system appropriately indicates inability to answer.

For comparison with M-flow/Zep (which exclude adversarial), use the excluding-adversarial score: **64.4% (991/1540)**.

## 3. perConversation Data Missing

The `report.json` file's `perConversation` array is empty. Per-conversation breakdowns need to be computed from the `evaluations` array or individual result files.

## 4. One Question Missing Search Results

1985 out of 1986 questions have `searchResults`. One question returned empty search results.

## 5. Test-001 vs Test-002

Two runs exist in the data:
- **locomo-sm-test-001**: 200 questions, 67.0% — initial small-scale test
- **locomo-sm-test-002**: 1986 questions, 65.0% — full benchmark (authoritative)

The test-001 results are included in `results/test_001/` for reference only.
