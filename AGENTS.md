# Agent Guide

## Start of work

- Read [README.md](README.md) for setup and operator guidance.
- Read [SPEC.md](SPEC.md) and [docs/contracts.md](docs/contracts.md) for affected
  behavior/interfaces, and [CONTEXT.md](CONTEXT.md) before naming domain concepts.
- For execution-model changes, read [DECISIONS.md](DECISIONS.md). Its accepted
  Docker-enabled shared-image direction is not implemented; this guide and README
  describe the current prepared-Compose runtime. Update SPEC/contracts before
  changing execution behavior; do not mix old isolation claims with Docker access.
- Inspect affected callers, tests, configuration, and working-tree changes. Keep
  changes minimal and preserve unrelated work. Follow the Domain Vocabulary,
  Safety and Contract Invariants, and Commenting Convention sections below.

## Architecture and paths

Local autonomous coding factory: a Python standard-library runner polls GitHub
for `agent:implement`, invokes Pi/Copilot in a prepared Docker Compose sandbox,
then publishes validated nonempty changes as draft PRs for human review. GitHub
holds durable coordination; no database, HTTP API, or hosted deployment exists.

- `src/software_factory/__main__.py`, `config.py`: terminal CLI, signals, four-field TOML.
- `runner.py`: preflight, serial polling, issue runs, bounded repairs, outcomes.
- `github.py`, `repository.py`: host GitHub CLI and trusted Git publication.
- `process.py`: command deadlines, safe errors, private/redacted diagnostics.
- `sandbox.py`, `sandbox_agent.mjs`: Compose isolation/lifecycle and Node/Pi bridge.
- `tests/`: pytest unit, real local Git/process, Docker, and opt-in live tests;
  `tests/wrapper-coverage.test.mjs` drives bridge coverage through pytest.
- `scripts/`, `Makefile`, `.github/workflows/verify.yml`: development entrypoints and CI.
- `docs/architecture/service-architecture.md`: component diagram and boundary evidence.

## Development workflow

From the repository root, use Python **3.14.3**, uv **0.5.13**, Make, a POSIX shell,
Git, and Node.js **22.19+** (CI: **22.19.0**). Dependencies are locked in `uv.lock`;
Hatchling is pinned in `pyproject.toml`. Setup installs the package editable.

```sh
./scripts/setup
./scripts/verify
uv run --frozen python -m software_factory --help
uv run --frozen pytest tests/test_toolchain.py -q
```

- `make format` mutates formatting; `make format-check` and `make lint` do not.
- `make test` runs pytest; `make coverage` runs Python plus Node bridge coverage.
- Verification order: Ruff format check → Ruff lint → tests/coverage.
- Python overall line/branch coverage and Node line/branch/function coverage must
  meet their **80%** gates. Never lower thresholds or exclude business logic.
- No standalone type checker or Markdown linter is configured. Packaging uses the
  pinned backend; there is no release workflow.

CI-equivalent checks require running Docker with Compose; disposable integration
fixtures use `alpine:3.21.3`, pulled if missing:

```sh
FACTORY_DOCKER_TESTS=1 FACTORY_E2E_APPROVED=0 FACTORY_COPILOT_TESTS=0 \
  FACTORY_SMOKE_SANDBOX_TESTS=0 ./scripts/verify
```

Add meaningful tests for behavior changes, including relevant failure cases.
Keep real Git/process and Docker boundary checks where applicable. Pure logic
uses pytest and existing fixtures/patterns. Distinguish scripted external boundaries
from tests against real services. Do not run live checks implicitly:
Copilot probes consume authenticated service access; `tests/test_e2e.py` writes
GitHub labels, comments, a branch, and a PR and requires explicit approval and a
fresh dedicated issue. See [README live checks](README.md#verification-beyond-unit-tests).

## Configuration and local requirements

- Runtime invocation: `uv run --frozen python -m software_factory --config /absolute/path/to/factory.toml`.
  This starts polling and can publish already-labeled issues; it is not a safe smoke check.
- Operator TOML requires exactly `repository`, `compose_file`, `compose_service`,
  and `model`; no credentials/defaults. Compose paths resolve relative to the TOML;
  model IDs must exactly match an accessible `github-copilot` model.
- Host execution needs Git, authenticated `gh`, authenticated Pi/Copilot (tested
  Pi **1.3.0**), and Docker Compose. Authentication/access approval is manual.
- Target-specific agent Docker/Compose assets belong in the target repository
  (smoke target: `../factory-smoke-test/sandbox/agent/`). Keep operator TOML outside
  that checkout and run workspace; a suggested ignored path is
  `artifacts/operator/factory-smoke-test.toml`. These local assets are not in a fresh clone;
  recreate missing operator configuration from the README before opt-in checks.
- Run artifacts default to `artifacts/` beside the configured Compose file, not
  necessarily this checkout. `FACTORY_WORKSPACE` is supplied by the runner.
- Use standard-library logging: WARNING to stderr, no application log files.
  `logging.ini` provides optional equivalent development defaults. Never log
  secrets or full transcripts; command diagnostics belong only in private run logs.
- Keep credentials/private artifacts out of version control; `artifacts/`, `.venv`,
  coverage reports, and caches are ignored. Do not hand-edit generated reports.

## Domain Vocabulary

- Read [CONTEXT.md](CONTEXT.md) before naming domain concepts.
- Use its canonical terms consistently in code, tests,
  documentation, and user-facing output. Resolve conflicts before adding/renaming terms.
- The accepted specification is authoritative for behavior; `CONTEXT.md` for naming.
- An issue run is one fresh attempt under a shared 900-second deadline, including
  at most three repair attempts after initial implementation. Manual requeue is
  explicit label reapplication for a new run, never resumed work/session state.
- Preserve public interfaces; never silently rename established CLI, TOML, JSON,
  or API fields.

## Safety and Contract Invariants

- One repository, one runner instance, serial issue runs, 30-second polling;
  no automatic retries/requeue, session recovery, merging, or review-feedback revisions.
- Task inputs are the immutable title/body snapshot and repository contents, not
  comments, attachments, or linked pages. Treat inputs/output as untrusted data.
- Setup → Pi → verification run inside the sandbox; host publication follows only
  successful verification, sandbox shutdown, and a nonempty diff. Preserve the
  original deadline across all phases/repairs and attempt cleanup after failure.
- Preserve fail-closed Compose isolation, workspace-only mounts, Copilot-only stdin
  credentials, and trusted host Git metadata. Never weaken validation for a fixture.
- Preserve exact `factory/issue-<number>` PR/branch checks and create-only publication;
  the runner must not overwrite or delete remote branches. Uncertain writes require
  inspection, not blind retries. Human review/independent target CI remain required.
- Failed workspaces/logs are private retained diagnostics until operator deletion,
  never recovery state. Manual requeue must not erase them.
- Use existing `FactoryError`, `Commands`, and boundary classes/patterns. Maintain
  explicit return annotations and safe, actionable diagnostics without credential leaks.
- Update accepted specs/contracts before interface or policy changes; keep README,
  and architecture/workflow docs consistent.

## Commenting Convention

- Every production module and function must have a comment directly above it.
- The comment must state its purpose, key inputs/outputs, and externally visible
  effects or failure handling where applicable.
- Docstrings do not satisfy this rule.

Exemptions:

- Generated files.
