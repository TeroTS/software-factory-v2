# Agent Guide

## Start of work

- Read [README.md](README.md) for setup and operator guidance.
- Read [SPEC.md](SPEC.md) and [docs/contracts.md](docs/contracts.md) for affected
  behavior/interfaces, and [CONTEXT.md](CONTEXT.md) before naming domain concepts.
- For execution-model changes, read [DECISIONS.md](DECISIONS.md) and
  [docs/slices/current-slice.md](docs/slices/current-slice.md). Keep one execution
  backend. Docker engine access grants effective engine/host control, not isolation.
- Keep story scope/status, implementation notes, verification evidence, and next
  steps only in `docs/slices/current-slice.md`. README is operator/developer guidance;
  AGENTS contains standing agent rules; architecture docs describe boundaries;
  workflow docs contain procedures. Update those only when their durable content
  changes, not to mirror slice progress.
- Inspect affected callers, tests, configuration, and working-tree changes. Keep
  changes minimal and preserve unrelated work. Follow the Domain Vocabulary,
  Safety and Contract Invariants, and Commenting Convention sections below.

## Architecture and paths

Local autonomous coding factory: the Python standard-library runner validates
shared-image startup, polls GitHub, and executes issue runs.
GitHub holds durable coordination; no database, HTTP API, or hosted deployment exists.

- `src/software_factory/__main__.py`, `config.py`: terminal CLI, signals, four-field TOML.
- `runner.py`: native image/engine preflight, serial issue coordination, cleanup/publication gates.
- `agent/`: factory-maintained pinned shared-image build definition and instructions.
- `github.py`, `repository.py`: host GitHub CLI and trusted Git publication.
- `process.py`: command deadlines, safe errors, private/redacted diagnostics.
- `sandbox.py`, `sandbox_agent.py`: shared-image agent lifecycle, scoped cleanup, credentials/Pi/verification.
- `tests/`: pytest unit, real local Git/process/Docker, scripted external-boundary CLI E2E;
  `tests/test_agent_wrapper.py` exercises the standalone Python bridge and measures its coverage.
- `scripts/`, `Makefile`, `.github/workflows/verify.yml`: development entrypoints and CI.
- `scripts/provision-host`, `infra/lima/`: explicit Ubuntu host preparation;
  privileged provisioning checks require operator authorization.

## Development workflow

From the repository root, use Python **3.14.3**, uv **0.5.13**, Make, a POSIX shell,
and Git. Node.js remains in the shared image for Pi/target tooling, not host
verification. Dependencies are locked in `uv.lock`; Hatchling is pinned in
`pyproject.toml`. Setup installs the package editable.

```sh
./scripts/setup
./scripts/verify
uv run --frozen python -m software_factory --help
uv run --frozen pytest tests/test_toolchain.py -q
```

- `make format` mutates formatting; `make format-check` and `make lint` do not.
- `make test` runs pytest; `make coverage` runs Python coverage, including the Pi bridge.
- Verification order: Ruff format check → Ruff lint → tests/coverage.
- Python overall line/branch coverage, including the Pi bridge, must meet its
  **80%** gate. Never lower thresholds or exclude business logic.
- No standalone type checker or Markdown linter is configured. Packaging uses the
  pinned backend; there is no release workflow.

CI-equivalent checks run on native ARM64 with local Docker/Compose and an
explicitly built shared image. Target fixtures build ordinary application images,
install a local npm tool inside the agent, and verify against real Compose services.

```sh
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 ./scripts/verify
```

Add meaningful tests for behavior changes, including relevant failure cases.
Keep real Git/process and Docker boundary checks where applicable. Pure logic
uses pytest and existing fixtures/patterns. Distinguish scripted external boundaries
from tests against real services. Do not run live checks implicitly:
Copilot probes consume authenticated service access. Live checks require explicit
approval. See [README live checks](README.md#verification-beyond-unit-tests).

## Configuration and local requirements

- Runtime invocation: `uv run --frozen python -m software_factory --config /absolute/path/to/factory.toml`.
  Inspect trigger labels before starting/upgrading: already-labeled issues are
  eligible for execution. Verification failures end the run without automatic repair.
- Operator TOML requires exactly `repository`, `model`, `agent_image`, and
  `artifacts_dir`; no credentials/defaults. Relative artifact paths resolve against
  the TOML; model IDs exactly match an accessible `github-copilot` model. Reject
  legacy Compose fields with migration guidance; never automatically migrate.
- Host execution needs Git, authenticated `gh`, authenticated Pi/Copilot (tested
  Pi **1.3.0**), and Docker Compose. Authentication/access approval is manual.
- The operator builds the shared `agent/Dockerfile` image before startup. Require
  a local native linux/arm64 engine/image and retain the resolved immutable image
  ID for the session. Factory-owned containers request `--platform linux/arm64`
  and `--pull=never`; target commands inherit `DOCKER_DEFAULT_PLATFORM=linux/arm64`
  and use the image's unmodified Docker executable. Target scripts must use native
  images/tools; explicit platform overrides are not intercepted and may invoke
  engine-supported emulation. No remote engine, automatic shared-image build/pull,
  or factory-selected emulation fallback.
- Keep operator TOML outside the target checkout and future run workspace, e.g.
  ignored `artifacts/operator/factory.toml`. Artifacts use configured `artifacts_dir`
  with no default; never move/delete previous diagnostics implicitly. Use fresh
  private run directories and host-usable files. Targets supply ordinary services, not
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
- Setup → Pi → verification run inside the agent as the host UID/GID, with writable
  container-local home/caches and explicit `sudo -n` for system installs. No automatic
  root fallback or recursive workspace permission repair. Trusted root initialization
  configures only container account/home/socket groups; never run workspace code in it.
  Host publication requires successful verification, completed scoped cleanup,
  required host file access, remaining time, and a nonempty diff. Preserve the original 900-second
  deadline across all phases/repairs and attempt bounded cleanup after failure.
- Preserve fail-closed startup validation. Docker-enabled execution is not a
  host-security boundary. Keep normal mounts/credentials limited, Copilot-only stdin delivery, and trusted host Git
  metadata without claiming protection against deliberate Docker-mediated access.
  Never restore historical Compose isolation helpers or a parallel backend.
- Preserve matching unique `FACTORY_RUN_ID`/`COMPOSE_PROJECT_NAME` and exact ownership
  labels. Cleanup uses host-owned identities, not mutable target teardown, and
  stops owned containers before networks/disposable volumes. Preserve unrelated
  resources/images/cache; cleanup/access errors block publication. Do not chown/chmod
  the workspace. Deliberately inaccessible retained files and unknown resources/
  hard-crash leftovers need operator inspection. Service-private data should use
  disposable owned volumes; workspace-writing services need compatible permissions.
- Preserve exact `factory/issue-<number>` PR/branch checks and create-only publication;
  the runner must not overwrite or delete remote branches. Uncertain writes require
  inspection, not blind retries. Human review/independent target CI remain required.
- Failed workspaces/logs are private retained diagnostics until operator deletion,
  never recovery state. Manual requeue must not erase them.
- Use existing `FactoryError`, `Commands`, and boundary classes/patterns. Maintain
  explicit return annotations and safe, actionable diagnostics without credential leaks.
- Update accepted specs/contracts before interface or policy changes. Keep durable
  operator/architecture guidance accurate without copying implementation status
  or story tracking out of the current slice.

## Commenting Convention

- Every production module and function must have a comment directly above it.
- The comment must state its purpose, key inputs/outputs, and externally visible
  effects or failure handling where applicable.
- Docstrings do not satisfy this rule.

Exemptions:

- Generated files.
