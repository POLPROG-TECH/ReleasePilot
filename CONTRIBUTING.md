# Contributing to ReleasePilot

Thank you for your interest in contributing to ReleasePilot! This guide will help you get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/polprog-tech/ReleasePilot.git
cd ReleasePilot

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Install in development mode with dev dependencies
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run the full test suite
python3 -m pytest tests/ -q

# Run with verbose output
python3 -m pytest tests/ -v

# Run a specific test file
python3 -m pytest tests/test_rendering.py -v
```

## Code Quality

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Lint
python3 -m ruff check src/ tests/

# Auto-fix lint issues
python3 -m ruff check --fix src/ tests/
```

## Playground / Demo Environment

The `playground/` directory provides a full demo environment:

```bash
# Bootstrap sample repos and run all 29 demo workflows
python3 playground/scripts/run_demo.py --setup
```

See [`playground/README.md`](playground/README.md) for details.

## How to Contribute

### Reporting Bugs

- Use the [Bug Report](https://github.com/polprog-tech/ReleasePilot/issues/new?template=bug_report.md) issue template
- Include steps to reproduce, expected behavior, and actual behavior
- Include your Python version and OS

### Suggesting Features

- Use the [Feature Request](https://github.com/polprog-tech/ReleasePilot/issues/new?template=feature_request.md) issue template
- Describe the use case and expected behavior

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Make your changes
4. Ensure tests pass (`python3 -m pytest tests/ -q`)
5. Ensure lint is clean (`python3 -m ruff check src/ tests/`)
6. Commit with a descriptive message using [Conventional Commits](https://www.conventionalcommits.org/)
7. Push and open a Pull Request

### Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add PDF export for executive briefs
fix: correct Polish date formatting
docs: update playground instructions
perf: optimize commit grouping algorithm
refactor: simplify rendering pipeline
test: add translation coverage tests
chore: upgrade reportlab dependency
```

## Project Structure

```
src/releasepilot/
├── cli/           CLI commands (Click-based)
├── core/          Pipeline: collect → classify → group → compose
├── rendering/     Output renderers (Markdown, PDF, DOCX, JSON, plaintext)
├── i18n/          Internationalization labels (10 languages)
└── schema/        JSON schema for config/input validation
```

## Code Style

- Python 3.12+
- Type hints on all public functions
- Docstrings for modules and public classes/functions
- No commented-out code in commits
- Ruff-clean before merging

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
