# LongMemEval Benchmark for MFlow

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

A comprehensive benchmark suite for evaluating episodic memory retrieval and question-answering capabilities using the LongMemEval dataset.

## Highlights

- Evaluates MFlow and Graphiti on 50 LongMemEval questions
- MFlow: 80% accuracy, Graphiti: 64% accuracy
- Complete evaluation pipeline with ingestion, retrieval, and answer generation
- Detailed metrics: LLM-Judge, BLEU-1, F1

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
export OPENAI_API_KEY="your-key-here"
export LLM_API_KEY="your-key-here"

# 3. Obtain the LongMemEval dataset
# Download from: https://github.com/xiaowu0162/LongMemEval
# Place the oracle file at: data/longmemeval_oracle.json

# 4. Verify setup
python scripts/verify_setup.py

# 5. Run benchmark
./scripts/run_benchmark.sh --questions 50
```

## Results Summary

| Metric | MFlow | Graphiti | Difference |
|--------|-------|----------|------------|
| LLM-Judge Accuracy | 80.0% | 64.0% | +16.0% |
| F1 Score | 0.405 | 0.372 | +0.033 |
| BLEU-1 | 0.295 | 0.289 | +0.006 |

## Project Structure

```
longmemeval-benchmark/
├── README.md                 # This file
├── LICENSE                   # MIT License
├── CONTRIBUTING.md           # Contribution guidelines
├── CHANGELOG.md              # Version history
├── requirements.txt          # Python dependencies
├── config.yaml               # Benchmark configuration
├── data/                     # Dataset (see download instructions above)
│
├── scripts/                  # Benchmark scripts
│   ├── run_benchmark.sh      # One-click runner
│   ├── verify_setup.py       # Environment verification
│   ├── mflow_ingest.py       # Data ingestion
│   ├── mflow_qa_eval.py      # QA evaluation
│   ├── analyze_results.py    # Results analysis
│   └── rebuild_vector_index.py  # Vector index repair
│
├── results/                  # Evaluation results
│   ├── mflow_eval_results.json
│   ├── graphiti_eval_results.json
│   └── BENCHMARK_REPORT.md   # Detailed comparison report
│
└── docs/                     # Documentation
    └── BENCHMARK.md          # Full benchmark specification
```

## Requirements

### System Requirements
- Python 3.12+
- 8GB+ RAM
- 10GB+ free disk space

### Dependencies
- MFlow v0.5.1+ (with Kuzu + LanceDB)
- OpenAI API access
- NLTK for text metrics

### Data
- LongMemEval dataset (500 questions)
- Place at: `data/longmemeval_oracle.json`

## Usage

### Step-by-Step Execution

```bash
# Step 1: Ingest data (creates isolated datasets per question)
python scripts/mflow_ingest.py --max-questions 50

# Step 2: Run QA evaluation
python scripts/mflow_qa_eval.py --max-questions 50

# Step 3: Analyze results
python scripts/analyze_results.py results/mflow_eval_results.json

# Compare with Graphiti
python scripts/analyze_results.py --compare results/mflow_eval_results.json results/graphiti_eval_results.json
```

### Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--max-questions` | 50 | Number of questions to evaluate |
| `--answer-model` | gpt-4.1-mini | Model for answer generation |
| `--judge-model` | gpt-4.1-mini | Model for answer evaluation |
| `--output-dir` | results | Output directory |

## Metrics

| Metric | Description |
|--------|-------------|
| **LLM-Judge Accuracy** | GPT-4 judges if answer is semantically correct |
| **BLEU-1** | Unigram word overlap with reference |
| **F1** | Token-level precision/recall harmonic mean |

## Documentation

- [Full Benchmark Specification](docs/BENCHMARK.md)
- [Detailed Results Report](results/BENCHMARK_REPORT.md)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Troubleshooting

### Vector Index Empty After Ingestion

```bash
python scripts/rebuild_vector_index.py --max-datasets 50
```

### API Rate Limiting

Increase delay in `scripts/mflow_qa_eval.py`:
```python
await asyncio.sleep(1.0)  # Increase from 0.5
```

## Citation

```bibtex
@misc{mflow_longmemeval_2026,
  title={LongMemEval Benchmark for MFlow},
  author={MFlow Team},
  year={2026},
  url={https://github.com/mflow-ai/mflow-benchmarks}
}
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
