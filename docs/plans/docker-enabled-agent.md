# Docker-enabled agent: initial implementation plan

Status: initial plan, not implemented. The agreed direction below comes from the
operator discussion; proposed implementation details and open decisions are not
yet accepted contracts. This document does not override the current
[specification](../../SPEC.md) or [contracts](../contracts.md).

## Goal and agreed direction

Make the agent work more like a developer on a Linux machine, without requiring
a factory-specific image or Compose definition for each target repository.

- Use one shared Linux agent image with baseline development tools. Default to
  native `linux/arm64` on the local Apple Silicon Mac for agent, application, and
  dependency images. Surface unsupported tools/images explicitly; AMD64 emulation
  or replacements require an explicit decision, not a silent fallback.
- Run operator local tryouts in Docker too, reusing the application/dependency
  image IDs or digests that passed agent verification, not just mutable tags.
  These are distinct from the shared agent development image. Use a separate
  Compose project, local data volumes, and nonconflicting published ports.
- Allow target-specific tool installation during setup/runs; commonly needed
  tools can later be added to the shared image.
- Give the agent access to the existing host Docker engine. It can build images,
  run the target's ordinary `docker compose up`, and execute E2E tests.
- Mount the workspace at the same absolute path on the host and in the agent
  container so sibling containers can bind-mount workspace files correctly.
- Preserve setup/verify entrypoints, serial issue processing, the original
  900-second run deadline, at most three verification repairs, host-side
  publication, duplicate protection, and manual requeue behavior.
- Identify run-owned resources for cleanup; never use broad Docker pruning.

The operator accepts that Docker access gives the agent control over the engine
and potentially its host. The agent container is an execution environment, not a
security boundary protecting host files, credentials, or other containers.
Keeping publication credentials out of the normal agent environment remains
useful, but cannot prevent deliberate access through Docker.

Start locally, including a macOS host running Linux containers through its local
Docker provider. Docker Desktop/Rancher Desktop supplies the Linux VM and engine;
no additional factory-managed VM is required. Validate this local workflow before
considering EC2 deployment. ECS Fargate and a separately hosted remote Docker
engine are outside this initial scope. Validate native ARM64 support and host
filesystem sharing locally. Future native ARM64 EC2 deployment would use Graviton;
cloud deployment and general multi-architecture support are not initial deliverables.

## Refactor strategy: replace the sandbox in this project

Refactor the existing project; do not start a new project or retain parallel
old/new sandbox backends. The `ver-1.0.0` Git tag preserves the previous
implementation without keeping obsolete runtime paths in the new version.

Reuse the existing GitHub coordination, host Git publication, command deadlines,
diagnostics/redaction, Pi/Copilot invocation, polling, repair loop, manual requeue,
and development tooling. Change their environment wiring only where necessary.

Replace the prepared-target Compose lifecycle and remove its restricted Compose
validation, mount rewriting, and superseded configuration handling. Retain useful
verification-feedback and credential-validation logic rather than rewriting it
merely because it currently lives in `sandbox.py`.

Delete superseded code, fixtures, and architecture-specific tests as replacements
land. Preserve tests for behavior that remains required. Do not introduce a
backend framework, legacy execution mode, unused compatibility helpers, or a
second implementation kept "just in case". Configuration migration is still an
explicit decision; it must not preserve the old execution backend.

## Current implementation and affected areas

| Area | Current coupling | Planned change |
| --- | --- | --- |
| [config.py](../../src/software_factory/config.py) | Requires `compose_file` and `compose_service` alongside repository/model. | Replace per-target sandbox configuration after approving a migration contract. |
| [runner.py](../../src/software_factory/runner.py) | Preflight resolves/restricts target Compose; rewrites mounts; stores artifacts beside that Compose file. | Preflight shared image/engine access; create the shared agent environment; decouple artifact location from Compose. |
| [sandbox.py](../../src/software_factory/sandbox.py) | Starts a prepared restricted Compose project at `/workspace`; rejects socket mounts and builds. | Replace that lifecycle with a Docker-enabled agent container, preserving setup, implementation, verification feedback, and cleanup interfaces where practical. |
| Historical `sandbox_agent.mjs` (now [sandbox_agent.py](../../src/software_factory/sandbox_agent.py)) | Invokes Pi with temporary Copilot configuration. | Retain exact-model invocation, stdin credentials, temporary configuration, and nonpersistent sessions; supply run context where needed. |
| [process.py](../../src/software_factory/process.py), [repository.py](../../src/software_factory/repository.py) | Shared command deadline and trusted host publication. | Reuse; verify container processes and file ownership still support deadline termination and publication. |
| Tests and CI | Fixtures/assertions assume prepared Compose, `/workspace`, and socket exclusion. | Update affected configuration, sandbox, boundary, runner, CLI, Docker, requeue, and live-test fixtures; preserve unrelated failure/publication checks and coverage gates. |

The shared image definition/build instructions belong in this factory repository,
not in target repositories. Exact paths and image contents remain proposed.

## Implementation sequence

### 1. Prove the Docker execution model with a disposable local fixture

Before changing application contracts, validate a generic Linux container with
Docker CLI/Compose connected to the host engine:

- Build an image and start a tiny application/dependency through ordinary Compose.
- Use a relative workspace bind mount; confirm files written by a sibling
  container are visible to both the agent and host at the expected path.
- Reach the application from the agent's test process. Explicitly test the
  difference between Compose service DNS, published host ports, and `localhost`:
  sibling containers do not share the agent's loopback interface.
- Exercise package installation, socket permissions, and host-readable/writable
  files; test cleanup while an unrelated disposable sentinel resource exists.

Start with the intended local macOS Docker Desktop/Rancher Desktop setup and
record the provider/CPU architecture actually tested. Validate shared absolute
paths against the desktop provider's filesystem sharing. Linux CI checks remain
necessary but do not substitute for desktop path-sharing/networking checks.
Only disposable test resources may be changed.

Also validate the operator's Docker-based local tryout: open a published
application port from a Mac browser, and use a separate checkout/project, local
data volumes, and ports without colliding with the agent's resources or cleanup.
Reuse the verified application/dependency images by ID/digest without rebuilding;
record their identities before cleanup so the operator can select them afterward.
Do not substitute the agent development image for application images or reuse
macOS-native `.venv`/`node_modules` inside Linux containers. If application source
is bind-mounted, use the verified source revision as well: image identity alone
does not reproduce it. Do not edit the agent's active run workspace.

### 2. Resolve the small set of contract decisions

Use the probe results to settle these before production implementation:

- **Configuration migration:** propose removing `compose_file`/`compose_service`
  and selecting a shared image instead. Decide the exact fields/defaults and
  whether old configuration is migrated or rejected with guidance; do not
  silently reinterpret old fields or retain a second execution backend.
- **Artifacts:** choose a stable operator-owned location now that Compose no
  longer supplies its parent directory. Preserve private permissions and failed
  diagnostics; do not move/delete existing artifacts implicitly.
- **Image/bootstrap:** choose pinned baseline tools and the container user/install
  permissions. Setup currently runs before Pi: a missing tool that makes setup
  fail cannot be installed by the later implementation call. Decide whether setup
  owns those installations or a separate bootstrap step is needed; do not silently
  introduce setup-repair behavior.
- **Networking:** select and document how agent-side E2E tests reach sibling
  services, especially repositories expecting published ports at `localhost`.
- **Ownership:** define the supported Compose/run labeling convention and what
  happens when commands override it or create untracked resources.

Then update the relevant specification, decision record, contracts, and standing
agent safety instructions to reflect the accepted model. Do not label old
host-isolation guarantees as still effective after socket access is introduced.

### 3. Add the shared image and replace target-specific startup

- Build one versioned `linux/arm64` image containing Pi, Node, Docker CLI/Compose,
  shell, Git, and the approved baseline/install tools; no credentials baked into
  image layers. Check target application/dependency images for native ARM64 support.
- Start one agent container per issue run with the host engine socket and the
  same-path workspace mount. Keep normal mounts/environment limited despite
  the accepted ability to bypass those limits through Docker.
- Validate engine/image availability and workspace usability before claiming work
  where possible; report missing prerequisites without exposing credentials.
- Keep setup, initial implementation, verification, and repairs in that container
  under the original run deadline. Include per-run installation/build time in it.
- Preserve Copilot credential delivery and host-owned Git publication. Stop run
  processes/services that could mutate workspace files before committing.

### 4. Implement scoped lifecycle and cleanup

- Give each run a unique identity; propose `COMPOSE_PROJECT_NAME` for ordinary
  Compose commands and ownership labels for directly created resources.
- Treat naming/labels as cooperation conventions, not enforced access controls:
  explicit `-p`, other Docker contexts, or unlabeled `docker run` can bypass them.
- Record enough host-owned resource identity for cleanup independent of mutable
  agent-authored Compose files. Do not execute modified teardown scripts on the host.
- Stop/remove owned containers, then owned networks and disposable volumes when
  no longer used. Define volume deletion explicitly; do not infer ownership from
  a resource merely being unused. Leave shared images/build cache alone initially.
- Use bounded cleanup after success, setup failure, verification failure, timeout,
  and SIGTERM. Killing a Docker CLI process does not stop daemon-managed containers.
- On cleanup failure, retain diagnostics and report failure rather than publish
  while known run-owned services remain active. Unknown resources require operator
  inspection, not daemon-wide deletion. Hard-crash cleanup remains manual initially.

### 5. Test, document, and demonstrate

Write failing tests before behavior changes, then implement the smallest passing
change. Update existing tests rather than discarding their safety/failure coverage.

Required checks:

- Configuration/preflight errors, changed artifact paths, socket/mount arguments,
  credential handling, run identity, setup/verify exits, and repair feedback.
- Real Docker build + Compose startup + service-backed E2E verification from the
  agent environment, with no factory-specific Compose definition in the target.
- Same-path bind mounts and a target-specific tool installation.
- macOS browser access to a published application port and an independent
  Docker-based local tryout using the exact verified application/dependency image
  IDs/digests and source revision where bind-mounted. Check native `linux/arm64`
  execution, file ownership, dependency directories, distinct projects/data volumes,
  and nonconflicting ports. Verify unsupported ARM64 dependencies are reported
  rather than silently run under AMD64 emulation.
- Cleanup on success, setup failure, exhausted repairs, timeout, interruption,
  and partial startup; preserve an unrelated sentinel container/network/volume.
- Cleanup error blocks publication; no new deadline or extra repair allowance;
  duplicate protection, fresh manual requeue, and retained failed diagnostics remain.
- Existing full verification and both unchanged 80% coverage gates. Align CI with
  the new shared-image integration fixture.

Update README for durable setup/usage/testing and AGENTS.md for stable coding and
operating rules only. Keep this implementation plan and any run-specific evidence
out of those files. Update architecture/workflow docs after behavior is implemented.
A real Pi/Copilot-to-PR demonstration still requires separate operator approval;
local scripted/Docker tests must not be presented as live acceptance.

## Completion boundary and remaining risks

Complete when a target using ordinary setup/verify and application Compose can
build/start services, pass E2E checks, and reach the unchanged publication gates
without a prepared target sandbox. Failure/stop paths must clean known owned
resources while leaving unrelated resources intact.

The refactor is not complete until the removal audit confirms:

- Exactly one supported agent execution path; no old/new mode switches or unused
  backend abstractions.
- No remaining callers/imports of removed target Compose preparation or validation.
- No active fixtures/tests that require the abandoned execution model solely to
  keep obsolete code alive; retained behavior and failure tests still pass.
- Old `compose_file`/`compose_service` fields appear only where required by the
  approved migration/error handling or clearly historical records.
- Current setup/configuration docs and agent instructions describe the new model,
  not prepared-target sandboxes or the previous host-isolation guarantees.
- Useful existing coordination/publication logic remains shared rather than
  duplicated in a new runner. Unrelated user work and retained run artifacts are
  untouched.

This is not a promise that arbitrary repositories run unchanged: fixed container
names/ports, external volumes, explicit project overrides, localhost assumptions,
missing tools, architecture differences, and long cold installations/builds can
still require adaptation. One run remains serial; no new queue, database,
concurrency layer, VM backend, automatic credential renewal, cache service, or
cloud provisioning is included.

A shared daemon cannot enforce ownership boundaries against Docker-authorized
agent commands. Cooperative cleanup can be tested; protection from deliberate
host access or destructive Docker commands cannot be claimed under this model.
