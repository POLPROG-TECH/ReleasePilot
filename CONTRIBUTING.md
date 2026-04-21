# Contributing to ReleasePilot

Thank you for your interest in contributing to ReleasePilot! This guide covers everything you need to get started.

## Development Setup

```bash
git clone https://github.com/polprog-tech/ReleasePilot.git
cd ReleasePilot

python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

pip3 install -e ".[all]"
```

Verify the installation:

```bash
releasepilot --version
```

### Pre-commit hook

```bash
cp scripts/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

The hook runs ruff lint (with auto-fix), ruff format check, and the full test suite before each commit.

## Running Tests

```bash
pytest                                    # all tests
pytest -v                                 # verbose
pytest tests/test_dedup.py                # specific file
pytest tests/test_dedup.py::TestExactDedup # specific class
```

Tests follow the **GIVEN/WHEN/THEN** docstring pattern (see existing tests for examples).

## Code Quality

```bash
ruff check src/ tests/
ruff format --check src/ tests/
```

## Playground / Demo Environment

The `playground/` directory provides a full demo environment:

```bash
python3 playground/scripts/run_demo.py --setup
```

See [`playground/README.md`](playground/README.md) for details.

## How to Contribute

### Reporting Bugs

Include: expected vs actual behavior, `.releasepilot.json` (redacted), Python/OS version, steps to reproduce.

### Pull Requests

1. Branch from `main`
2. Make changes + add tests
3. Run `pytest` and `ruff check src/ tests/`
4. Open PR with clear description

## Commit Convention

[Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`

## License

See [LICENSE](LICENSE).
