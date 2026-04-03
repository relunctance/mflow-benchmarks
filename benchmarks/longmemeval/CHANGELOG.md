# Changelog

All notable changes to the LongMemEval Benchmark project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-27

### Added
- Initial release of LongMemEval Benchmark for MFlow
- Complete benchmark suite with ingestion, evaluation, and analysis scripts
- Support for 50-question evaluation (configurable up to 500)
- Comparison framework for MFlow vs Graphiti
- Comprehensive documentation (README.md, BENCHMARK.md)
- Environment verification script (`verify_setup.py`)
- Results analysis tool (`analyze_results.py`)
- Vector index rebuild utility (`rebuild_vector_index.py`)
- One-click benchmark runner (`run_benchmark.sh`)
- Sample evaluation results with detailed metrics

### Metrics Implemented
- LLM-Judge Accuracy (GPT-4 semantic correctness)
- BLEU-1 (unigram overlap)
- F1 (token-level precision/recall)

### Results Summary (50 Questions)
- **MFlow**: 80.0% LLM-Judge Accuracy
- **Graphiti**: 64.0% LLM-Judge Accuracy
- MFlow achieves +16.0% higher accuracy on 50-question subset

### Known Issues
- Long ingestion time (~10 min/question) due to per-session memorization
- Initial vector index issue fixed with `rebuild_vector_index.py`

### Dependencies
- Python 3.12+
- MFlow v0.5.1+
- OpenAI API access
- NLTK, LanceDB, Kuzu (embedded databases)
