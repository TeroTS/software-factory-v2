# Autonomous Coding Factory

Development environment only. Product decisions: [DECISIONS.md](DECISIONS.md).
Domain terminology: [CONTEXT.md](CONTEXT.md). No factory implementation exists yet.

## Requirements

- Python 3.14.3 (`.python-version`)
- uv 0.5.13 (the verified version, also pinned in CI)
- Make and a POSIX shell

## Development commands

```sh
./scripts/setup       # Install the exact uv.lock dependencies
make format           # Format Python
make format-check     # Check formatting without changing files
make lint             # Lint Python
make test             # Run tests
make coverage         # Run tests under coverage
./scripts/verify      # Format check, lint, tests with coverage; also used by CI
```

Run one test:

```sh
uv run --frozen pytest tests/test_toolchain.py -k coverage_policy
```

`Makefile` owns task definitions. The setup/verify scripts work from outside the
repository as well. Development commands use the project virtual environment;
no global Python packages are installed.

## Structure

- `src/`: reserved for application code; currently empty.
- `tests/`: development-toolchain checks, not application behavior tests.
- `scripts/`: setup, verify, and coverage entrypoints.
- `.github/workflows/verify.yml`: runs the same setup/verify commands as local development.
- `logging.ini`: standard-library logging configuration, not automatically loaded.

## Coverage

Application coverage includes `src/`, with branch measurement and an 80% minimum.
Tests are not counted as application coverage. There is no application code yet,
so the coverage command runs but reports no data; there is no meaningful baseline
or XML report until source exists. It explicitly relaxes the threshold only while
`src/` contains no Python files. Adding the first Python file automatically enables
the configured threshold and `coverage.xml` reporting. Do not add dummy application
code or measure tests just to manufacture coverage.

Generated code and framework boilerplate must be excluded when introduced; do not
exclude business logic. Coverage policy and empty-source handling have automated
checks. The GitHub workflow is configured, but has not been executed on GitHub yet.

## Development logging and private artifacts

`logging.ini` provides WARNING-level output to stderr, with no file handler.
Future startup code can load it using `logging.config.fileConfig`; there is no
application entrypoint yet. Never emit credentials, full transcripts, or sensitive
command output into shared logs or GitHub comments. Warnings can still contain
sensitive data if callers include it: the format is not a redaction mechanism.

Store local run artifacts under ignored `artifacts/`; do not commit workspaces,
credentials, or logs. `.env` files and tool-generated caches/reports are also ignored.

## Not bootstrapped

No issue processing, Pi integration, sandbox containers, credentials, or repository
Compose configuration is created here. Copilot authentication and the first target
repository's sandbox remain end-to-end feasibility checks from `DECISIONS.md`.
