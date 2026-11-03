# Contributing

Thanks for helping. Bug reports with a redacted sample file are the most useful
contribution, especially for export formats that do not parse.

## Setup

```bash
git clone https://github.com/gautamggg53/trade-journal-stats
cd trade-journal-stats
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest --cov
ruff check . && ruff format --check .
```

## Ground rules

- **Never commit real account statements.** Fixtures in `tests/fixtures/` are
  synthetic; keep it that way. Replace account numbers, names and amounts.
- **Every statistic needs a hand-computed test.** Write the expected value and
  how you got it in a comment, as in `tests/test_stats.py`. Do not generate
  expected values by running the code under test.
- **Document formulas** in `docs/METRICS.md` when adding or changing one.
- **Formats:** if you add or fix a parser, say in the PR whether you checked it
  against a real export (redacted) or only against documentation, and update the
  format table in the README accordingly.
- No runtime dependencies beyond the standard library (plus `tzdata` on Windows)
  unless there is a strong reason.
- Add a line under "Unreleased" in `CHANGELOG.md`.

## Releasing (maintainers)

1. Move "Unreleased" entries under a new version in `CHANGELOG.md` and bump
   `version` in `pyproject.toml` and `src/trade_journal_stats/__init__.py`.
2. `python -m build` and smoke-test the wheel in a fresh venv.
3. `git tag -a vX.Y.Z -m "vX.Y.Z"` and push the tag.
