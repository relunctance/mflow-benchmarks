#!/bin/bash
# Cognee LOCOMO Benchmark — One-click Reproduction
# Aligned with MFlow's run_benchmark.sh
#
# Prerequisites:
#   1. Python 3.10+ with requirements installed
#   2. Environment variables set in .env or exported:
#      - COGNEE_API_KEY    (Cognee Cloud API key)
#      - OPENAI_API_KEY    (OpenAI API key for answer + judge)
#   3. Dataset: dataset/locomo10.json
#
# Usage:
#   cd cognee-locomo-bench
#   bash run_benchmark.sh
#
# Total time: depends on Cognee Cloud processing speed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_PATH="${SCRIPT_DIR}/dataset/locomo10.json"
RESULTS_DIR="${SCRIPT_DIR}/results"

mkdir -p "$RESULTS_DIR"

echo "============================================================"
echo "Cognee LOCOMO Benchmark"
echo "============================================================"
echo "Script dir:  $SCRIPT_DIR"
echo "Data:        $DATA_PATH"
echo "Results:     $RESULTS_DIR"
echo "============================================================"

# Check prerequisites
if [ ! -f "$DATA_PATH" ]; then
    echo ""
    echo "Dataset not found at $DATA_PATH"
    echo "Downloading LoCoMo-10 dataset..."
    mkdir -p "$(dirname "$DATA_PATH")"
    curl -L -o "$DATA_PATH" \
        "https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json"
    if [ ! -f "$DATA_PATH" ]; then
        echo "ERROR: Failed to download dataset"
        exit 1
    fi
    echo "Dataset downloaded."
fi

if [ -z "${COGNEE_API_KEY:-}" ]; then
    if [ -f "$SCRIPT_DIR/.env" ]; then
        export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
    fi
    if [ -z "${COGNEE_API_KEY:-}" ]; then
        echo "ERROR: COGNEE_API_KEY not set"
        exit 1
    fi
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "ERROR: OPENAI_API_KEY not set"
    exit 1
fi

# ============================================================
# Step 1: Ingest
# ============================================================
echo ""
echo "[Step 1/4] Ingesting LoCoMo data into Cognee..."
echo "This step may take a while depending on Cognee Cloud processing."
read -p "Skip ingestion? (y/N): " SKIP_INGEST
if [ "${SKIP_INGEST:-n}" != "y" ]; then
    cd "$SCRIPT_DIR"
    PYTHONUNBUFFERED=1 python -u run_ingest.py \
        --data "$DATA_PATH" \
        2>&1 | tee "$RESULTS_DIR/ingest.log"
    echo "[Step 1] Ingestion complete."
else
    echo "[Step 1] Skipped."
fi

# ============================================================
# Step 2: Search + Answer
# ============================================================
echo ""
echo "[Step 2/4] Running search + answer (all 10 conversations)..."
cd "$SCRIPT_DIR"
PYTHONUNBUFFERED=1 python -u search_aligned.py \
    --data-path "$DATA_PATH" \
    --output-path "$RESULTS_DIR/cognee_search.json" \
    --top-k 10 \
    2>&1 | tee "$RESULTS_DIR/search.log"
echo "[Step 2] Search complete."

# ============================================================
# Step 3: Evaluate
# ============================================================
echo ""
echo "[Step 3/4] Evaluating results..."
cd "$SCRIPT_DIR"
PYTHONUNBUFFERED=1 python -u evaluate_aligned.py \
    --input-file "$RESULTS_DIR/cognee_search.json" \
    --output-file "$RESULTS_DIR/cognee_eval.json" \
    2>&1 | tee "$RESULTS_DIR/eval.log"
echo "[Step 3] Evaluation complete."

# ============================================================
# Step 4: Generate Scores
# ============================================================
echo ""
echo "[Step 4/4] Generating score report..."
cd "$SCRIPT_DIR"
PYTHONUNBUFFERED=1 python -u generate_scores.py \
    --input-file "$RESULTS_DIR/cognee_eval.json" \
    --output-csv "$RESULTS_DIR/cognee_report.csv" \
    2>&1 | tee "$RESULTS_DIR/scores.log"
echo "[Step 4] Report complete."

# ============================================================
# Summary
# ============================================================
echo ""
echo "============================================================"
echo "Benchmark Complete"
echo "============================================================"
echo "Results: $RESULTS_DIR/cognee_eval.json"
echo ""
python -c "
import json
with open('$RESULTS_DIR/cognee_eval.json') as f:
    data = json.load(f)
tp = sum(e.get('llm_score',0) for v in data.values() for e in v)
te = sum(len(v) for v in data.values())
bleu = sum(e.get('bleu_score',0) for v in data.values() for e in v) / te
f1 = sum(e.get('f1_score',0) for v in data.values() for e in v) / te
print(f'LLM-Judge: {tp}/{te} = {tp/te*100:.1f}%')
print(f'BLEU-1:    {bleu:.3f}')
print(f'F1:        {f1:.3f}')
print()
for k in sorted(data.keys(), key=int):
    items = data[k]
    p = sum(e.get('llm_score',0) for e in items)
    print(f'  Conv {k}: {p}/{len(items)} = {p/len(items)*100:.1f}%')
"
