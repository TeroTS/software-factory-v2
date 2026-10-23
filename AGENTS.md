# Agent Guide

## Development

- Python 3.14.3, uv 0.5.13; dependencies are locked in `uv.lock`.
- `src/software_factory/`: application code; `tests/`: automated tests; `scripts/`: development entrypoints.
- Setup: `./scripts/setup`. Verification (same as CI): `./scripts/verify`.
- Format: `make format`; format check: `make format-check`; lint: `make lint`.
- Tests: `make test`; single test: `uv run --frozen pytest tests/test_toolchain.py -k coverage_policy`.
- Coverage: `make coverage`. Python and the Node Pi bridge must meet their 80% thresholds; Node.js 22.19+ is required (CI: 22.19.0).
- Real Docker integration: `FACTORY_DOCKER_TESTS=1 ./scripts/verify` (enabled in CI). Live Copilot/GitHub tests require explicit opt-in; see `README.md`.
- Use standard-library logging with the development defaults in `logging.ini`: WARNING to stderr, no log files. Never log secrets or full transcripts.
- Keep credentials and private run artifacts out of version control; `artifacts/` is ignored.
- US-01 is active; read `docs/slices/current-slice.md` before continuing. Do not mark it done without the live issue-to-PR test.
- Application packaging uses the pinned Hatchling backend in `pyproject.toml`; `./scripts/setup` installs it editable.

## Domain Vocabulary

- Read `CONTEXT.md` before naming domain concepts.
- Use its canonical terms consistently in code, tests, documentation, and user-facing output.
- Resolve terminology conflicts before adding or renaming terms.
- Treat the accepted specification as authoritative for behavior and `CONTEXT.md` as authoritative for naming.
- Preserve public-interface compatibility; do not silently rename established CLI, JSON, or API fields.

## Commenting Convention

- Every production module and function must have a comment directly above it.
- The comment must state its purpose, key inputs/output, and externally visible effects or
  failure handling where applicable.
- Docstrings do not satisfy this rule.

Exemptions:

- generated files
