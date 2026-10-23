# Agent Guide

## Development

- Python 3.14.3, uv 0.5.13; dependencies are locked in `uv.lock`.
- `src/`: future application code; `tests/`: automated tests; `scripts/`: development entrypoints.
- Setup: `./scripts/setup`. Verification (same as CI): `./scripts/verify`.
- Format: `make format`; format check: `make format-check`; lint: `make lint`.
- Tests: `make test`; single test: `uv run --frozen pytest tests/test_toolchain.py -k coverage_policy`.
- Coverage: `make coverage`. Application code must meet the configured 80% threshold; no baseline exists while `src/` is empty.
- Use standard-library logging with the development defaults in `logging.ini`: WARNING to stderr, no log files. Never log secrets or full transcripts.
- Keep credentials and private run artifacts out of version control; `artifacts/` is ignored.
- Bootstrap contains no application implementation or build step yet.

## Domain Vocabulary

- Read `CONTEXT.md` before naming domain concepts.
- Use its canonical terms consistently in code, tests, documentation, and user-facing output.
- Resolve terminology conflicts before adding or renaming terms.
- Treat the accepted specification as authoritative for behavior and `CONTEXT.md` as authoritative for naming.
- Preserve public-interface compatibility; do not silently rename established CLI, JSON, or API fields.
