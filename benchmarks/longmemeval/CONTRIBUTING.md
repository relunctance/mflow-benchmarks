# Contributing to LongMemEval Benchmark

Thank you for your interest in contributing to the LongMemEval Benchmark project!

## How to Contribute

### Reporting Issues

1. Check existing issues to avoid duplicates
2. Use the issue template if available
3. Include:
   - Clear description of the issue
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (Python version, OS, etc.)

### Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests: `python verify_setup.py`
5. Commit with clear messages
6. Push and create a Pull Request

### Code Style

- Follow PEP 8 for Python code
- Use type hints for function signatures
- Write docstrings for public functions
- Keep functions focused and modular

### Adding New Metrics

To add a new evaluation metric:

1. Create a function in `mflow_qa_eval.py`:
   ```python
   def calculate_your_metric(prediction: str, reference: str) -> float:
       """Calculate your custom metric"""
       # Implementation
       return score
   ```

2. Add the metric to `evaluate_single()` function
3. Update the summary statistics
4. Document the metric in README.md

### Testing

Before submitting:

1. Run syntax check: `python -m py_compile *.py`
2. Run environment verification: `python verify_setup.py`
3. Run a smoke test: `python mflow_ingest.py --max-questions 1`

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

## Questions?

Open an issue or reach out to the maintainers.

Thank you for contributing!
