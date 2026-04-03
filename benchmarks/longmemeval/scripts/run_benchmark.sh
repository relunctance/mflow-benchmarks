#!/bin/bash
#
# LongMemEval Benchmark Runner
# One-click script to run the complete benchmark
#
# Usage:
#   ./run_benchmark.sh                    # Run with defaults (50 questions)
#   ./run_benchmark.sh --questions 100    # Run with 100 questions
#   ./run_benchmark.sh --skip-ingest      # Skip ingestion, only evaluate
#   ./run_benchmark.sh --help             # Show help
#

set -e  # Exit on error

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RESULTS_DIR="${PROJECT_ROOT}/results"
LOG_DIR="${SCRIPT_DIR}/logs"

# Default parameters
MAX_QUESTIONS=50
SKIP_INGEST=false
SKIP_EVAL=false
ANSWER_MODEL="gpt-4.1-mini"
JUDGE_MODEL="gpt-4.1-mini"

# ============================================================================
# Parse arguments
# ============================================================================

print_help() {
    cat << EOF
LongMemEval Benchmark Runner

Usage: $0 [OPTIONS]

Options:
  --questions N       Number of questions to evaluate (default: 50)
  --skip-ingest       Skip data ingestion step
  --skip-eval         Skip evaluation step (only ingest)
  --answer-model M    Model for answer generation (default: gpt-4.1-mini)
  --judge-model M     Model for answer judging (default: gpt-4.1-mini)
  --help              Show this help message

Examples:
  $0                          # Run full benchmark with 50 questions
  $0 --questions 100          # Run with 100 questions
  $0 --skip-ingest            # Only run evaluation (assumes data already ingested)
  $0 --questions 5 --skip-eval  # Only ingest 5 questions (smoke test)

EOF
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --questions)
            MAX_QUESTIONS="$2"
            shift 2
            ;;
        --skip-ingest)
            SKIP_INGEST=true
            shift
            ;;
        --skip-eval)
            SKIP_EVAL=true
            shift
            ;;
        --answer-model)
            ANSWER_MODEL="$2"
            shift 2
            ;;
        --judge-model)
            JUDGE_MODEL="$2"
            shift 2
            ;;
        --help|-h)
            print_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            print_help
            exit 1
            ;;
    esac
done

# ============================================================================
# Setup
# ============================================================================

mkdir -p "$RESULTS_DIR"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
INGEST_LOG="${LOG_DIR}/ingest_${TIMESTAMP}.log"
EVAL_LOG="${LOG_DIR}/eval_${TIMESTAMP}.log"

# ============================================================================
# Banner
# ============================================================================

echo "============================================================"
echo "LongMemEval Benchmark"
echo "============================================================"
echo "Timestamp:      ${TIMESTAMP}"
echo "Questions:      ${MAX_QUESTIONS}"
echo "Skip Ingest:    ${SKIP_INGEST}"
echo "Skip Eval:      ${SKIP_EVAL}"
echo "Answer Model:   ${ANSWER_MODEL}"
echo "Judge Model:    ${JUDGE_MODEL}"
echo "Results Dir:    ${RESULTS_DIR}"
echo "============================================================"
echo ""

# ============================================================================
# Check prerequisites
# ============================================================================

echo "[1/5] Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "  Python version: ${PYTHON_VERSION}"

# Check .env file
if [[ ! -f "${PROJECT_ROOT}/.env" ]]; then
    echo "ERROR: .env file not found at ${PROJECT_ROOT}/.env"
    echo "Please copy .env.example to .env and add your OpenAI API key"
    exit 1
fi
echo "  .env file: Found"

# Check OpenAI API key
if ! grep -q "OPENAI_API_KEY" "${PROJECT_ROOT}/.env"; then
    echo "WARNING: OPENAI_API_KEY not found in .env"
fi

echo "  Prerequisites OK"
echo ""

# ============================================================================
# Step 2: Data Ingestion
# ============================================================================

if [[ "$SKIP_INGEST" == "false" ]]; then
    echo "[2/5] Running data ingestion..."
    echo "  Log: ${INGEST_LOG}"
    
    START_TIME=$(date +%s)
    
    python3 "${SCRIPT_DIR}/mflow_ingest.py" \
        --max-questions "$MAX_QUESTIONS" \
        2>&1 | tee "$INGEST_LOG"
    
    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))
    
    echo ""
    echo "  Ingestion completed in ${ELAPSED} seconds"
    echo ""
else
    echo "[2/5] Skipping data ingestion (--skip-ingest)"
    echo ""
fi

# ============================================================================
# Step 3: QA Evaluation
# ============================================================================

if [[ "$SKIP_EVAL" == "false" ]]; then
    echo "[3/5] Running QA evaluation..."
    echo "  Log: ${EVAL_LOG}"
    
    START_TIME=$(date +%s)
    
    python3 "${SCRIPT_DIR}/mflow_qa_eval.py" \
        --max-questions "$MAX_QUESTIONS" \
        --answer-model "$ANSWER_MODEL" \
        --judge-model "$JUDGE_MODEL" \
        --output-dir "$RESULTS_DIR" \
        2>&1 | tee "$EVAL_LOG"
    
    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))
    
    echo ""
    echo "  Evaluation completed in ${ELAPSED} seconds"
    echo ""
else
    echo "[3/5] Skipping evaluation (--skip-eval)"
    echo ""
fi

# ============================================================================
# Step 4: Generate Report
# ============================================================================

echo "[4/5] Checking results..."

RESULTS_FILE="${RESULTS_DIR}/mflow_eval_results.json"

if [[ -f "$RESULTS_FILE" ]]; then
    echo "  Results file: ${RESULTS_FILE}"
    
    # Extract summary metrics using Python
    python3 -c "
import json
with open('${RESULTS_FILE}') as f:
    data = json.load(f)
    s = data['summary']
    print(f\"  Total Questions: {s['total_questions']}\")
    print(f\"  LLM-Judge Accuracy: {s['llm_accuracy']*100:.1f}%\")
    print(f\"  BLEU-1: {s['avg_bleu']:.4f}\")
    print(f\"  F1: {s['avg_f1']:.4f}\")
    print(f\"  Avg Retrieval Latency: {s['avg_retrieval_ms']:.2f}ms\")
    print(f\"  Total Time: {s['total_time_seconds']:.2f}s\")
"
else
    echo "  WARNING: Results file not found"
fi

echo ""

# ============================================================================
# Step 5: Summary
# ============================================================================

echo "[5/5] Benchmark Complete"
echo "============================================================"
echo "Results saved to: ${RESULTS_DIR}"
echo "Logs saved to: ${LOG_DIR}"
echo ""
echo "Files:"
ls -la "${RESULTS_DIR}"/mflow_*.json 2>/dev/null || echo "  No result files found"
echo ""
echo "To analyze results:"
echo "  python ${SCRIPT_DIR}/analyze_results.py ${RESULTS_FILE}"
echo ""
echo "============================================================"
