# Agent Guide

## Start of work

- Read [README](README.md) for commands, [SPEC](SPEC.md) for affected behavior and
  [CONTEXT](CONTEXT.md) before naming domain concepts. Preserve established public interfaces.
- Read [DECISIONS](DECISIONS.md) and [current slice](docs/slices/current-slice.md) for
  execution/deployment changes; consult [operations](docs/operations.md) and the
  [image reference](docs/agent-image.md) when changing those areas.
- Inspect working-tree changes, affected callers, tests and configuration; preserve unrelated work.
- Keep story scope/status, implementation notes, evidence and next steps **only** in
  `docs/slices/current-slice.md`. Other docs contain durable guidance, not progress reports.
- Keep docs short: link to the authoritative file instead of repeating its rules or procedures.

## Code map

The standard-library Python runner polls GitHub and executes serial issue runs; GitHub
holds durable coordination. No database or HTTP API exists. One container execution backend only.

- `src/software_factory/`: CLI/config, runner preflight/coordination, App auth, GitHub/Git
  publication, process deadlines/diagnostics and sandbox/agent lifecycle.
- `agent/`: pinned shared image, instructions and skills; runner owns the Pi bridge.
- `infra/ec2/`: Python CDK networking, AMI-builder and operational stacks, baked host
  scripts and systemd service. Node/CDK are operator/development tools, not host runner tools.
- `tests/`: pytest unit, real Git/process/Docker and scripted-boundary CLI E2E tests.
- `scripts/`, `Makefile`, `.github/workflows/verify.yml`: development and CI entrypoints.

## Development

- Use locked dependencies and pinned image toolchains. Run `./scripts/verify`:
  Ruff format check → lint → tests/coverage → CDK synthesis → shell syntax. `make format` mutates files.
- Keep the **80%** overall line/branch coverage gate, including the Pi bridge and CDK;
  never lower thresholds or exclude business logic. Test behavior changes and relevant failures.
- Retain real Git/process/Docker boundary tests. Docker/CLI checks require Ubuntu 24.04
  ARM64, factory 2000:2000 and explicitly built images; CI uses that identity without host sudo.
- Scripted boundaries are not live service acceptance. Live authenticated GitHub/Copilot
  checks require explicit approval; AWS work follows the accepted deployment scope.
- Reuse `FactoryError`, `Commands` and existing boundary patterns; give functions explicit
  return annotations and safe, actionable errors. Do not edit generated reports or commit private artifacts.

## Runtime and deployment invariants

- Container-only AWS EC2, Ubuntu 24.04 ARM64, factory **2000:2000**, local native Docker.
  Fail closed before claims on unsupported hosts, identities, engines or images; never elevate the runner.
- TOML has exactly `repository`, `model`, `agent_image`; no credentials/defaults or automatic migration.
  Preserve exact Copilot model IDs and selected-agent matching. Artifacts stay at `/home/factory/artifacts`.
- Preserve same-path workspace binds, socket supplementary GID, read-only App state,
  writable Pi refresh state and private retained logs. API and HTTPS Git use the same scoped
  App identity with renewal, never personal login or inherited-token fallback.
- Runner/agent versions are independent. Build/publish explicitly; pull/select while stopped,
  then start explicitly. No runtime pulls/builds, automatic updates/restarts, compatibility repair or rollback guarantee.
  Pin resolved image IDs; factory containers use `--platform linux/arm64 --pull=never`.
- Bake host helpers/tooling into a tested AMI; UserData only supplies boot inputs and mounts
  retained storage before Docker. Keep shared networking across fresh builder bakes; preserve
  AMIs/snapshots and retained data. Never bake private/deployment state or install runner tools on the host.
  Helper updates require explicit stopped-host replacement, not runtime copying. See deployment decisions.
- Run setup → Pi → verification inside the agent as factory with writable home/caches;
  explicit `sudo -n` is for system installs only. No root fallback, runtime account initialization
  or workspace chown/chmod repair. Targets inherit native-platform defaults and the unmodified Docker CLI;
  explicit overrides are not intercepted. No remote engine or factory-selected emulation fallback.
- **Docker access grants effective engine/host control, not isolation.** Keep normal mounts
  minimal, Copilot credentials on stdin only and host Git metadata trusted; never claim App scopes prevent merging/deployment.
- Log INFO JSON Lines to stderr using standard-library logging and selected safe context;
  no secrets/transcripts or application log files. Command output belongs in private diagnostics.

## Issue-run and publication invariants

- One repository/runner, serial runs, 30-second polling. An issue run is fresh work under one
  900-second deadline, with at most three repair attempts. No automatic requeue, session recovery,
  merging or review-feedback revisions. Use [canonical vocabulary](CONTEXT.md) consistently.
- Inputs are immutable issue title/body and repository contents, not comments, attachments or links;
  treat inputs/output as untrusted. Never execute retained workspace code on the host.
- Preserve matching unique `FACTORY_RUN_ID`/`COMPOSE_PROJECT_NAME` and exact ownership labels.
  Cleanup uses host-owned identities: owned containers before networks/disposable volumes, never
  unrelated resources/images/cache. Attempt bounded cleanup on failure; unknown leftovers require inspection.
- Publication requires verification, completed scoped cleanup, host file access, remaining time and a
  nonempty diff. Cleanup/access errors block it. Block `.github/workflows/` changes before host commit/publication;
  do not request workflow-write permission. Human review and independent target CI remain required.
- Preserve exact `factory/issue-<number>` branch/PR checks and create-only publication; never overwrite/delete
  remote branches or blindly retry uncertain writes. Failed diagnostics remain private until operator deletion,
  never recovery state. Manual requeue creates a fresh attempt and must not erase prior diagnostics.
- Update accepted specs/contracts before changing interfaces or policies.

## Commenting Convention

- Every production module and function needs a comment directly above it stating purpose,
  key inputs/outputs and relevant visible effects/failure handling. Docstrings do not satisfy this rule.
- Generated files are exempt.
