# Agent Guide

## Start of work

- Read [README.md](README.md) for commands; consult [operator guidance](docs/operations.md)
  and the [image reference](docs/agent-image.md) when changing those areas.
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
- `auth.py`: private host GitHub App credentials and scoped token renewal.
- `github.py`, `repository.py`: App-authenticated host GitHub CLI and trusted Git publication.
- `process.py`: command deadlines, safe errors, private/redacted diagnostics.
- `sandbox.py`, `sandbox_agent.py`: shared-image agent lifecycle, scoped cleanup, credentials/Pi/verification.
- `tests/`: pytest unit, real local Git/process/Docker, scripted external-boundary CLI E2E;
  `tests/test_agent_wrapper.py` exercises the standalone Python bridge and measures its coverage.
- `scripts/`, `Makefile`, `.github/workflows/verify.yml`: development entrypoints and CI.
- `scripts/provision-host`, `infra/lima/`: explicit Ubuntu host preparation;
  privileged provisioning checks require operator authorization.

## Development workflow

- Follow [README development commands](README.md#development); run `./scripts/verify`
  in order: Ruff format check → lint → tests/coverage. `make format` mutates files.
- Use the locked dependencies and pinned toolchain/backend; host verification needs no Node.js.
- Maintain the **80%** overall line/branch coverage gate, including the Pi bridge.
  Never lower thresholds or exclude business logic.
- Add meaningful tests for behavior changes and relevant failures. Use existing pytest
  patterns; retain real Git/process and Docker boundary checks where applicable.
- Unit checks may run on a development host. Docker/CLI checks require the provisioned
  Ubuntu 24.04 ARM64 guest, factory 2000:2000, and an explicitly built shared image.
  CI verifies as the same identity without host sudo.
- Distinguish scripted boundaries from real services. Live authenticated checks
  (including Copilot probes) and privileged provisioning tests require explicit
  approval. See [extended verification](docs/operations.md#verification-beyond-unit-tests).

## Configuration and local requirements

- Runtime invocation: `uv run --frozen python -m software_factory --config /absolute/path/to/factory.toml`.
  Inspect trigger labels before starting/upgrading: already-labeled issues are
  eligible for execution. Verification failures end the run without automatic repair.
- Operator TOML requires exactly `repository`, `model`, `agent_image`, and
  `artifacts_dir`; no credentials/defaults. Relative artifact paths resolve against
  the TOML; model IDs exactly match an accessible `github-copilot` model. Reject
  legacy Compose fields with migration guidance; never automatically migrate.
- Runner execution requires the provisioned Ubuntu 24.04 LTS ARM64 Linux host
  and effective factory UID/GID 2000:2000. Reject root/other IDs and unsupported
  hosts before claims; never switch accounts or elevate the host runner.
  Git, `gh`, OpenSSL, curl, private host GitHub App credentials, authenticated Pi/Copilot
  (tested Pi **1.3.0**), and Docker Compose are required. Initial authentication/
  access approval is manual. Repository API and HTTPS Git use the same App identity,
  never saved personal login or inherited-token fallback. Preserve private host-file
  modes and scoped token renewal; credentials never belong in operator TOML.
- The operator builds the shared `agent/Dockerfile` image before startup. Require
  a local native linux/arm64 engine/image and retain the resolved immutable image
  ID for the session. Bake factory 2000:2000, writable home/caches/npm prefix,
  and account-scoped sudo with root HOME into the image. Startup validates the
  actual default identity without root account setup or account-file mutation;
  incompatible images require explicit rebuild/restart, not compatibility repair.
  Factory-owned containers request `--platform linux/arm64`
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
- Setup → Pi → verification run inside the agent as factory 2000:2000, with writable
  container-local home/caches and explicit `sudo -n` for system installs. No automatic
  root fallback or recursive workspace permission repair. Do not introduce runtime
  account/shadow/group initialization; never execute workspace code in root initialization.
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
- Block `.github/workflows/` changes before host commit/publication in this version;
  do not request workflow-write permission. Branch protection and stronger permission
  separation are deferred; do not claim App scopes prevent merging/deployment.
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
