# Contracts

## Purpose

Formalize the non-HTTP boundaries for US-04–US-07 in [SPEC.md](../SPEC.md),
using [DECISIONS.md](../DECISIONS.md) for locked policy and
[CONTEXT.md](../CONTEXT.md) for naming. The operator additionally approved the
resource-ownership identifiers defined in Contract 7 during contract generation.

These are target contracts, not acceptance evidence. They supersede the
prepared-target Compose execution contract. US-04 implements the startup portions
and US-05 implements first-pass execution/publication; US-06/US-07 remain deferred.
There is no selectable old backend. Historical US-01–US-03 acceptance does not
prove the new execution boundaries. See the current slice for verification.

Incremental delivery: US-05 removes the operator-approved US-04 pre-claim guard.
Already-labeled issues become eligible; inspect labels before upgrading. Execution
currently stops on first-pass verification failure without repair. Contract 4's
recovery and Contract 6's full manual-requeue scenario remain US-06/US-07 work.
The old backend is not selectable. Contracts define accepted behavior; the current
slice records verification evidence rather than assuming every future story is done.

Constants are not configuration options: one repository and runner instance,
one issue run at a time, 30-second polling, a 900-second issue-run deadline,
and at most three verification repairs after initial implementation.

## HTTP Contract Source

- None. GitHub and Copilot are existing external services, not factory-owned
  HTTP APIs. No OpenAPI artifact is required.

## Non-HTTP Contract Inventory

### Contract 1: Local runner invocation and repository configuration

- Kind: Terminal invocation and trusted operator-owned TOML configuration.
- Producers / Owners: Operator.
- Consumers: Local runner.
- Trigger / Direction: The operator starts the runner; validated startup enters
  polling until stopped.
- Payload / Shape:

  ```sh
  uv run --frozen python -m software_factory --config /path/to/factory.toml
  ```

  ```toml
  repository = "TeroTS/factory-smoke-test"
  model = "gpt-6.1-sol"
  agent_image = "software-factory-agent:pinned-version"
  artifacts_dir = "artifacts/runs"
  ```

  | Field | Required shape | Meaning |
  | --- | --- | --- |
  | `repository` | Nonempty GitHub.com `owner/name` string, not a URL | The single trusted target repository. |
  | `model` | Nonempty exact accessible Pi model ID under `github-copilot` | No provider prefix, patterns, or provider fallback. |
  | `agent_image` | Nonempty Docker image reference available locally | Operator-built shared agent image, resolved to an immutable image ID at startup. |
  | `artifacts_dir` | Nonempty directory path | Operator-owned diagnostic root; relative paths resolve against the TOML directory. |

  These are exactly four required string fields with no defaults. Reject missing,
  empty, wrong-type, unknown, or invalid values. Reject `compose_file` and
  `compose_service` with guidance to build/select the shared image and supply
  `artifacts_dir`; never reinterpret or automatically migrate legacy input.
  Configuration contains no credentials, default-branch override, or arbitrary
  command templates. Discover the default branch from GitHub.

  Preserve terminal exit semantics: usage help does not start polling; startup
  failure exits nonzero with a safe stderr diagnostic; operator interruption
  exits 130 after attempting active-run cleanup.
- Ordering / Idempotency expectations: Validate configuration, artifact-root
  usability, host tools/authentication, local engine readiness, and image
  compatibility before claiming issues where possible. Resolve the image once
  per runner session; restart to adopt an updated tag. Do not build/pull an agent
  image or install target tools on the host. Do not move/delete existing artifacts.
  The operator ensures only one runner instance; labels are not a distributed lock.
- Visibility / Security: Keep configuration outside the agent workspace and
  under operator control. Do not copy host authentication/configuration into the
  agent environment. This normal separation does not prevent deliberate access
  through the Docker engine (Contract 3).
- Failure / Retry expectations: Invalid configuration, unavailable host tooling,
  failed authentication/engine readiness, unusable artifact root, or a missing or
  incompatible local image prevents successful startup. Do not claim issues on
  guessed prerequisite state, silently fall back, or retain a legacy backend.

### Contract 2: Issue discovery, skip handling, and immutable task input

- Kind: GitHub label-driven request and captured issue snapshot.
- Producers / Owners: Operator owns label application and issue content; GitHub
  owns issue identity; the local runner owns the captured snapshot.
- Consumers: Local runner and Pi coding agent.
- Trigger / Direction: Serial polling discovers open issues labeled
  `agent:implement`; the captured task flows to Pi.
- Payload / Shape:

  | Value | Shape |
  | --- | --- |
  | Repository | Configured `owner/name`. |
  | Issue number | Positive integer identifying an issue in that repository. |
  | Title | Issue title string captured at claim time. |
  | Body | Issue body string or `null`, captured at claim time. |
  | Base commit | Resolved default-branch commit used for the fresh workspace. |

  This is a boundary data shape, not a new job API or mandatory on-disk format.
  Inputs are the title/body snapshot and repository contents; do not retrieve
  comments, attachments, or linked pages or add later issue edits to an active run.
- Ordering / Idempotency expectations:
  1. Check for an open PR matching the exact configured head repository and
     `factory/issue-<number>` head branch, not free-text body content.
  2. If found, remove the trigger, preserve the PR, skip execution, and comment
     with its actual URL. Draft and non-draft open PRs both count.
  3. Otherwise, if that remote branch exists, remove the trigger, skip execution,
     and request operator branch cleanup and explicit label reapplication.
  4. Otherwise remove the trigger, record running status, snapshot the task,
     and create a fresh default-branch workspace.

  Confirm trigger removal before execution or skip notification. A skip consumes
  the trigger; no repeat notification without reapplication. Other branch names
  are outside duplicate detection. Poll at 30-second intervals between completed
  batches without concurrent issue runs.
- Visibility / Security: Attempt every labeled issue without classification,
  eligibility analysis, or clarification. Treat task and repository content as
  untrusted; never interpolate them into host shell commands.
- Failure / Retry expectations: Required GitHub reads or trigger-removal failure
  blocks execution rather than authorizing guesses. Label/comment operations
  are not atomic and do not promise exactly-once notification through crashes
  or ambiguous responses. Never automatically restore a consumed trigger.

### Contract 3: Shared agent environment and Copilot credentials

- Kind: Local-runner-to-Docker execution boundary and unattended Pi invocation.
- Producers / Owners: The factory repository owns the shared image definition;
  the operator builds it and owns credentials; the local runner owns the
  per-issue-run agent environment and workspace.
- Consumers: Pi, target tooling, and application/dependency services.
- Trigger / Direction: A claimed issue starts one agent container using the
  runner session's resolved image. Task/credential input flows privately to Pi.
- Payload / Shape:
  - Shared image: native `linux/arm64`, versioned with pinned base/tool versions,
    containing Pi, Node.js/npm, Docker CLI/Compose, Python/uv, Bash, Git, Make,
    a C/C++ build toolchain, curl, CA certificates, tar, unzip, and standard Linux
    utilities. No credentials in image layers. Exact tested pins and build
    instructions belong with the factory-maintained build definition.
  - Agent container: start with the host UID/GID, access to the existing local
    Docker engine, the run workspace mounted at its same absolute host/container
    path, and the repository root as working directory. Setup, Pi, and verification
    run as that user with writable container-local home/caches. Explicit system
    installs use passwordless `sudo -n` from the pinned image snapshot; no automatic
    root fallback. Trusted root initialization configures only container identity,
    home, and socket-group access, never workspace permissions. No target-specific
    factory Compose definition/image is required. Host UID 0 still means root.
  - Supported engine: local Linux-container engine running native ARM64,
    including an Apple Silicon Mac's Docker Desktop/Rancher Desktop provider.
    No remote engine, additional factory-managed VM, or factory-selected emulation
    fallback. Startup validates the native engine/shared agent image; factory-owned
    containers explicitly request `--platform linux/arm64` and `--pull=never`.
    Target commands inherit `DOCKER_DEFAULT_PLATFORM=linux/arm64`, not Docker
    command interception or guaranteed rejection of explicit platform overrides.
  - Pi invocation: one-shot print interface, explicit configured
    `github-copilot` model, coding tools, and nonpersistent sessions. Each call
    receives the same immutable snapshot and current workspace; repairs also
    receive failed verification output. Disable discovered extensions, MCP,
    skills, prompt templates, themes, and trust-gated project configuration.
    Repository context may supply instructions, not additional security guarantees.
  - Credential input: host-resolved Copilot-only bearer with at least 20 minutes
    remaining, obtained privately through
    `pi auth print-bearer-token --provider github-copilot --min-expiry 20m`
    with host resource loading disabled. Deliver through stdin, never command
    arguments, image layers, copied auth directories, or printed output.
  - Endpoint: derive from validated bearer metadata; preserve supported
    individual/business/enterprise Copilot endpoint validation rather than
    assuming every account uses the individual endpoint. Temporary Pi
    configuration is removed after invocation. Do not supply the host OAuth
    refresh token or use another billing provider.
- Ordering / Idempotency expectations: Startup resolves the compatible local
  image ID without building/pulling. Each issue run gets a fresh agent container
  and workspace. Setup precedes Pi; every implementation/repair call shares
  that environment and the original deadline. Pi exit zero means that invocation
  completed, not that verification or the issue succeeded.
- Visibility / Security: Limit ordinary mounts/environment to workspace, engine
  access, and required run context; do not normally expose host SSH agents,
  GitHub CLI credentials, broader Pi home/settings, or other host directories.
  Allow internet access for dependencies and Copilot. Root plus Docker engine
  access provides effective engine control and potentially host control: neither
  workspace mounts nor credential separation enforce isolation against deliberate
  Docker-authorized commands. Do not claim the old sandbox guarantees remain.
- Failure / Retry expectations: Missing runtime, unusable workspace/socket,
  incompatible engine/shared agent image, provider rejection, expired/malformed credentials,
  unsupported endpoint, termination, or deadline expiry fails visibly without
  provider fallback or setup repair. Attempt bounded cleanup under Contract 7;
  these failures do not authorize verification repair cycles.

### Contract 4: Golden-path verification, repair allowance, and deadline

- Kind: Executable repository entrypoints and exit-status/feedback protocol.
- Producers / Owners: Target repository owns entrypoints and CI alignment;
  local runner owns ordering, deadline, and repair allowance.
- Consumers: Pi, local runner, and independent target CI.
- Trigger / Direction: Run setup before initial implementation; run verification
  after initial implementation and each permitted repair.
- Payload / Shape:

  | Command/result | Meaning |
  | --- | --- |
  | `./scripts/setup` | Deterministic, noninteractive dependency/toolchain preparation, including required nonbaseline installations. |
  | `./scripts/verify` | Canonical CI-aligned checks, including required real local dependency/service-backed tests. |
  | Exit `0` | That command succeeded. |
  | Nonzero exit, signal, missing entrypoint, or invalid execution result | That command did not succeed. |
  | Completed verification's stdout/stderr | Private repair feedback, redacted for known credentials. |

  Both entrypoints must be executable before implementation. Commands run as the
  host UID/GID from the repository root inside the agent environment. Target setup
  explicitly uses `sudo -n` for system installs, not whole scripts or workspace
  builds; permission errors never trigger automatic elevation. Additional runtimes/browser
  binaries belong in target setup; there is no pre-setup Pi bootstrap or guessed
  replacement command. Preserve explicit verification-result handling so Docker
  execution errors are not mistaken for completed repository check failures.
- Ordering / Idempotency expectations:
  - Start one 900-second wall-clock budget when the issue run begins, before
    workspace/environment setup. It includes installations/builds, setup, Pi,
    verification, repairs, required cleanup before publication, and publication.
  - Run setup, initial implementation, and verification in that order. Failed
    setup ends the run before Pi; do not introduce setup repair.
  - A completed verification failure permits Pi to repair the same workspace
    using the immutable task and failed output, then rerun the same verify
    command. Permit at most three repair-and-verify cycles, not counting initial
    implementation, and stop at the first pass. Neither deadline nor environment
    resets during recovery.
  - Verification must be safe to rerun. Passing still requires completed cleanup,
    time remaining, and nonempty changes before publication.
- Visibility / Security: Output may be sensitive and agent-influencing. Keep
  feedback private; do not execute it on the host or post transcripts to GitHub.
  Passing checks does not prove requirements, unchanged test quality, or merge
  readiness; independent CI and human review remain required.
- Failure / Retry expectations: Missing scripts, setup/provider/lifecycle errors,
  invalid results, cleanup errors, and publication failures do not authorize extra
  verification repairs. The third unsuccessful repair fails the run. Expiry
  terminates work even with repairs left; do not deliberately begin further work
  or publication after expiry. Attempt bounded cleanup after failure/expiry/stop
  even when the original run budget is exhausted; cleanup does not extend
  implementation, repair, or publication time.

### Contract 5: Host-side publication and draft PR identity

- Kind: Trusted host Git publication and GitHub draft PR creation.
- Producers / Owners: Local runner publishes; human reviewer owns merge decisions.
- Consumers: GitHub and human reviewer.
- Trigger / Direction: Passing verification, successful required cleanup, a
  nonempty diff, and remaining run time permit publication.
- Payload / Shape:
  - Head repository: exactly the configured target repository.
  - Head branch: `factory/issue-<number>`.
  - Base branch: the target's discovered default branch.
  - PR state on creation: draft; PR body includes `Closes #<number>`.
  - Result: the actual created PR URL, not a guessed location.
- Ordering / Idempotency expectations: Stop all known run-owned services/processes
  that can mutate the workspace and complete cleanup before reading changes for
  host commit/publication. Confirm required host traversal/read access without
  changing workspace modes/ownership; trusted staging/read failures block publication.
  Commit, atomically create the absent remote branch,
  create the draft PR, then record success with its URL. Preserve the empty
  expected-ref lease (`--force-with-lease=refs/heads/factory/issue-<number>:`)
  so even a fast-forward update of an existing branch is rejected. Do not overwrite
  or delete remote branches. Inspect remote PR/branch state after uncertain writes
  rather than blindly repeating them; manual requeue reapplies Contract 2.
- Visibility / Security: Use trusted host-owned Git metadata, not agent-controlled
  Git config, hooks, filters, credential helpers, or nested Git metadata. Do not
  run repository scripts on the host during publication. Keep publication
  credentials out of normal agent inputs, without claiming this protects them
  from an agent with Docker engine access.
- Failure / Retry expectations: No changes fails as `no changes produced` with no
  PR. Cleanup, commit, push, or PR-creation failure is not successful publication.
  A successful push followed by failed PR creation may leave a branch for operator
  inspection/deletion. Surface reporting errors rather than claiming an outcome
  was posted. Do not automatically merge, revise from review feedback, or retry
  uncertain publication writes.

### Contract 6: GitHub status, local diagnostics, and manual requeue

- Kind: Human-readable issue comments, trigger lifecycle, and private artifacts.
- Producers / Owners: Local runner records outcomes; operator owns requeue,
  artifact deletion, and remote branch cleanup; GitHub stores durable coordination.
- Consumers: Operator and human reviewer.
- Trigger / Direction: Claim/skip/completion produces status; explicit label
  reapplication after failure/interruption requests a fresh attempt.
- Payload / Shape:

  | Status | Required information | Trigger afterward |
  | --- | --- | --- |
  | Running | Issue reference and notice implementation started. | Absent. |
  | Skipped: open PR | Actual existing PR URL; no execution. | Absent. |
  | Skipped: existing branch | Factory branch name, operator cleanup, and reapplication guidance. | Absent. |
  | Succeeded | Actual created draft PR URL. | Absent. |
  | Failed | Concise reason: setup/provider/lifecycle failure, exhausted repairs, expiry, cleanup/publication failure, interruption, or no changes. | Absent. |

  The table assumes confirmed trigger removal. Do not report it absent if removal
  failed. Exact prose is not a machine-readable interface; no new status labels
  or event API are required.

  Artifacts live under configured `artifacts_dir`, with a fresh private directory
  for each run (0700) and private command logs (0600). Retain failed workspaces/logs
  until operator deletion and report their location locally, not as shared raw
  transcripts. Successful run directories may be removed. No successful-image
  manifest, tryout archive, or retained source snapshot is required.
- Ordering / Idempotency expectations: Never restore `agent:implement` on failure,
  interruption, or restart. Explicit reapplication repeats exact PR/branch checks;
  a closed PR does not bypass an existing remote branch. A clear requeue uses a
  new issue snapshot, current default-branch workspace, agent container, unique
  run identity, 900-second deadline, and three-repair allowance. Never resume the
  previous agent session/workspace or erase previous failure diagnostics.
- Visibility / Security: GitHub is durable coordination, not a recovery database.
  Artifacts may contain private source/sensitive output; keep them outside version
  control and redact known credentials. Never publish full logs/transcripts or
  credentials. The operator manually checks out PRs for local evaluation; exact
  reproduction of verified images/dependencies/configuration is not promised.
- Failure / Retry expectations: Report unavailable GitHub status locally rather
  than claiming it was posted. A hard interruption can leave running status and
  resources; manual inspection/cleanup is required, not automatic execution on
  restart. Deleting diagnostics does not stop Docker resources. Requeue must
  preserve previous artifacts and avoid deleting another run's resources.

### Contract 7: Run identity, Docker ownership, and scoped cleanup

- Kind: Agent-visible run context, Docker ownership metadata, and lifecycle gate.
- Producers / Owners: Local runner creates identity and host-owned cleanup records;
  target scripts/agent commands cooperate in resource labeling.
- Consumers: Compose, direct Docker commands, and host-controlled cleanup.
- Trigger / Direction: Supply context before setup; attach ownership when creating
  resources; use observed engine identities for cleanup after any run outcome.
- Payload / Shape:

  | Identifier | Shape and meaning |
  | --- | --- |
  | `FACTORY_RUN_ID` | Opaque unique per-issue-run identity, usable as a Compose project name and Docker label value. Not the issue number or a reusable per-issue identity. |
  | `COMPOSE_PROJECT_NAME` | Exactly the same value as `FACTORY_RUN_ID`; inherited by ordinary target Compose commands. |
  | `com.docker.compose.project` | Standard Compose ownership label, matched exactly to that project's run identity. |
  | `software-factory.run-id` | Factory ownership label for directly created containers, networks, and volumes; value exactly equals `FACTORY_RUN_ID`. |

  Direct resource creation uses `--label "software-factory.run-id=$FACTORY_RUN_ID"`.
  Each fresh manual requeue gets a different identity. The host tracks the agent
  container and enough resource type/engine identity/ownership information for
  cleanup without trusting agent-modified teardown configuration. No new public
  cleanup-record file format is introduced by this contract.
- Ordering / Idempotency expectations: Collect known owned resource identities
  independently of mutable target Compose files. Stop/remove owned containers
  before removing owned networks and disposable owned volumes. Target cleanup
  can already have removed a resource; confirm absence instead of broadening
  the deletion scope. Required cleanup must finish before host publication and
  is attempted with bounded execution on success, setup failure, verification
  failure/exhaustion, partial startup, deadline expiry, and operator interruption.
  Do not recursively change workspace ownership/permissions. After cleanup,
  inaccessible files/directories required for trusted host publication block
  publication; ignored caches need not be writable. Retain private host-owned logs
  and the unchanged workspace. Deliberately restricted files may need manual
  operator inspection. Service-private data should use disposable owned volumes;
  workspace-writing services need compatible UID/GID and permissions.
- Visibility / Security: Match exact ownership labels or recorded engine identity,
  never broad name prefixes or merely unused state. Delete only known owned
  disposable resources; preserve external/shared resources, unrelated containers,
  networks/volumes, images, and build cache. These labels are cooperation, not
  enforced access control: explicit `-p`, other contexts, unlabeled Docker calls,
  or deliberate misuse can bypass them. Do not run agent-authored teardown on
  the host or claim control of all resources the agent might have created.
- Failure / Retry expectations: Killing a Docker CLI process does not stop
  daemon-managed containers. Cleanup errors block publication, retain diagnostics,
  and require visible failure. Unknown/untracked resources require operator
  inspection, not daemon-wide pruning. Hard-crash cleanup is manual; it neither
  restores a trigger nor resumes execution. No new work/publication allowance is
  granted by the separate bounded cleanup attempt after run expiry.

### Contract 8: Target services, networking, and architecture

- Kind: Agent-to-local-Docker application/dependency execution and test connectivity.
- Producers / Owners: Target repository owns ordinary application Compose/build
  configuration, setup/verify scripts, and test endpoint configuration.
- Consumers: Agent-side repository tooling/tests, sibling services, and the operator
  checking a published port from macOS during acceptance.
- Trigger / Direction: Setup/agent/verification commands build/start services and
  run checks through the local engine during an issue run.
- Payload / Shape:
  - Target scripts must use native-compatible `linux/arm64` images/tools.
    The factory validates a native ARM64 engine/shared agent image, explicitly
    starts its own containers as `linux/arm64`, and supplies
    `DOCKER_DEFAULT_PLATFORM=linux/arm64` to target commands. It does not intercept
    Docker commands or guarantee rejection of explicit architecture overrides;
    overrides may invoke emulation if the operator's engine supports it.
    The factory never selects an emulation fallback or substitutes dependencies.
  - Same-absolute-path workspace mounts allow sibling containers to resolve
    relative workspace bind mounts to the intended host path. Do not assume
    `/workspace` or reuse host macOS `.venv`/`node_modules` as Linux dependencies.
  - Tests select explicit service addresses through target test configuration:
    Compose service DNS when the agent is attached to the relevant network, or
    the Docker host address for published ports. No universal test-endpoint
    environment variable or automatic localhost forwarding is introduced.
  - Ordinary Compose commands inherit Contract 7 identity. Direct Docker commands
    use its run label. Fixed container names/ports, external/shared resources,
    or explicit project overrides can require target adaptation.
- Ordering / Idempotency expectations: Builds, installations, startup, readiness
  checks, and service-backed verification consume the same run deadline. Tests
  must tolerate required verification reruns; teardown follows Contract 7.
  Ordinary application images may be built/pulled by target commands; the ban
  on automatic runner builds/pulls applies to the shared agent image.
- Visibility / Security: Agent and siblings have separate loopback interfaces;
  published host ports and Compose DNS are distinct connectivity paths. Published
  services can be reachable from the host according to the target's bindings;
  this model does not preserve the old sandbox's host-port/resource prohibitions.
  Do not promise arbitrary repositories run unchanged or that ownership conventions
  prevent destructive Docker commands.
- Failure / Retry expectations: Missing native dependencies, invalid mounts,
  file-ownership problems, service startup/readiness errors, or unreachable test
  endpoints fail visibly. Actual Docker/setup/verification failures are not retried
  with a different architecture or replacement dependencies. Do not reset the
  deadline or expand cleanup scope. Only completed canonical verification
  failures authorize the bounded repair flow in Contract 4.

## Slice Handoff

- Contract artifacts implementers must read:
  - `docs/contracts.md`
- US-04 delivers shared-image startup and US-05 replaces its temporary guard with
  first-pass Docker-enabled execution/publication. Consult `docs/slices/current-slice.md`
  for evidence. Next story: US-06 recovery, followed by US-07 manual requeue.
  List these contracts under `## Contract Inputs` for each story.
- Story mapping: US-04 uses Contracts 1 and 3 plus startup portions of Contract 6;
  US-05 uses all contracts; US-06 additionally exercises Contract 4 recovery;
  US-07 exercises Contract 6 fresh requeue with all inherited execution gates.
- Acceptance requires real ARM64 Docker build/Compose/service-backed checks,
  desktop-provider same-path sharing, tool installation, socket/file ownership,
  agent-to-service connectivity, and macOS browser access to a published port.
  Exercise cleanup success/failure/expiry/interruption/partial startup and preserve
  an unrelated sentinel container/network/volume. Linux CI is not desktop evidence.
- Retain format/lint/tests and the unchanged Python overall line/branch 80%
  coverage gate, including the standalone Python Pi wrapper. The operator-approved
  wrapper replacement retires the Node-only coverage harness/gates because no
  production JavaScript remains; Node remains in the shared image for Pi and
  target tooling. Docker integration CI must use ARM64.
  Preserve useful existing failure/publication/credential checks as old execution
  fixtures are replaced. Audit removal of obsolete callers/backend/configuration
  and update runtime documentation/instructions without stale isolation claims.
- No new live Copilot/GitHub-writing run is required or authorized. Scripted external
  boundaries must be distinguished from live acceptance. Exact tested build pins
  and local feasibility remain delivery evidence; report contradictions to the
  operator rather than silently changing accepted policy.
