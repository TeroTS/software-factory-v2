# Agent Guide

## Start of work

- Read [README.md](README.md) for setup and operator guidance.
- Read [SPEC.md](SPEC.md) and [docs/contracts.md](docs/contracts.md) for affected
  behavior/interfaces, and [CONTEXT.md](CONTEXT.md) before naming domain concepts.
- For execution-model changes, read [DECISIONS.md](DECISIONS.md). US-04 replaces
  startup with the shared-image configuration. An operator-approved temporary
  pre-claim guard disables issue execution until US-05; do not enable the old
  Compose backend. SPEC/contracts record this interim constraint. Docker engine
  access grants effective engine/host control, not sandbox isolation.
- Inspect affected callers, tests, configuration, and working-tree changes. Keep
  changes minimal and preserve unrelated work. Follow the Domain Vocabulary,
  Safety and Contract Invariants, and Commenting Convention sections below.

## Architecture and paths

Local autonomous coding factory: the Python standard-library runner currently
validates shared-image startup and polls GitHub read-only. Issue execution and
publication are guarded until US-05. GitHub holds durable coordination; no
database, HTTP API, or hosted deployment exists.

- `src/software_factory/__main__.py`, `config.py`: terminal CLI, signals, four-field TOML.
- `runner.py`: native local image/engine preflight, serial polling, temporary pre-claim guard.
- `agent/`: factory-maintained pinned shared-image build definition and instructions.
- `github.py`, `repository.py`: host GitHub CLI and trusted Git publication.
- `process.py`: command deadlines, safe errors, private/redacted diagnostics.
- `sandbox.py`, `sandbox_agent.mjs`: reusable credential/verification/Pi boundaries;
  historical Compose helpers are not an active backend and must be replaced in US-05.
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

CI-equivalent checks run on native ARM64 with local Docker/Compose and an
explicitly built shared image. Historical helper fixtures use `alpine:3.21.3`,
pulled if missing; these do not prove Docker-enabled issue execution.

```sh
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 \
  FACTORY_E2E_APPROVED=0 FACTORY_COPILOT_TESTS=0 \
  FACTORY_SMOKE_SANDBOX_TESTS=0 ./scripts/verify
```

Add meaningful tests for behavior changes, including relevant failure cases.
Keep real Git/process and Docker boundary checks where applicable. Pure logic
uses pytest and existing fixtures/patterns. Distinguish scripted external boundaries
from tests against real services. Do not run live checks implicitly:
Copilot probes consume authenticated service access; historical GitHub-writing
and target-specific live harnesses are disabled during US-04. Port them only with
the corresponding execution stories; never bypass the guard to run them. New live
checks require explicit approval. See [README live checks](README.md#verification-beyond-unit-tests).

## Configuration and local requirements

- Runtime invocation: `uv run --frozen python -m software_factory --config /absolute/path/to/factory.toml`.
  US-04 starts read-only polling with the approved pre-claim guard. After US-05,
  already-labeled issues will become eligible; inspect labels before that upgrade.
- Operator TOML requires exactly `repository`, `model`, `agent_image`, and
  `artifacts_dir`; no credentials/defaults. Relative artifact paths resolve against
  the TOML; model IDs exactly match an accessible `github-copilot` model. Reject
  legacy Compose fields with migration guidance; never automatically migrate.
- Host execution needs Git, authenticated `gh`, authenticated Pi/Copilot (tested
  Pi **1.3.0**), and Docker Compose. Authentication/access approval is manual.
- The operator builds the shared `agent/Dockerfile` image before startup. Require
  a local native linux/arm64 engine/image and retain the resolved immutable image
  ID for the session. No remote engine, automatic build/pull, or emulation fallback.
- Keep operator TOML outside the target checkout and future run workspace, e.g.
  ignored `artifacts/operator/factory.toml`. Artifacts use configured `artifacts_dir`
  with no default; never move/delete previous diagnostics implicitly. US-04 creates
  no issue-run workspace. Targets will supply ordinary application services, not
  target-specific factory agent images or Compose profiles.
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
- When US-05 replaces the guard, setup → Pi → verification run inside the agent
  environment. Host publication requires successful verification, completed scoped
  cleanup, remaining time, and a nonempty diff. Preserve the original 900-second
  deadline across all phases/repairs and attempt bounded cleanup after failure.
- Preserve fail-closed startup validation and the temporary pre-claim guard.
  Future Docker-enabled execution is not a host-security boundary. Keep normal
  mounts/credentials limited, Copilot-only stdin delivery, and trusted host Git
  metadata without claiming protection against deliberate Docker-mediated access.
  Historical Compose isolation helpers/tests are not the active execution backend.
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
