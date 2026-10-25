# Contracts

## Purpose

Define the factory's valid non-HTTP contracts: existing behavior still in use and
accepted changes to implement next under US-08–US-10 in [SPEC.md](../SPEC.md).
[DECISIONS.md](../DECISIONS.md) is the source of accepted policy;
[CONTEXT.md](../CONTEXT.md) supplies domain naming. Contracts are not a historical
backlog: retain working interfaces, update changed requirements, and remove
superseded or out-of-scope contracts.

Each contract states its implementation status. Existing coordination,
credentials, first-pass verification, diagnostics, cleanup, and publication
remain in use. Fixed-identity provisioning/startup/execution are planned changes,
not claims about the current runtime. Within mixed contracts, the fixed identity,
image-build account setup, socket `--group-add`, and Linux-host/Lima development requirements
are planned; other existing guarantees remain applicable. No parallel runtime
backend, verification repair loop, or new manual-requeue workflow is introduced.

Planned deployment constants are account/group `factory`, UID/GID `2000:2000`,
and Ubuntu Server 24.04 LTS ARM64. Existing execution constants remain one
repository/runner, one issue run at a time, 30-second polling, and the original
900-second deadline. No new identity, retry, or backend settings enter TOML.
Previously recorded desktop-provider evidence does not prove planned Linux VM/
fixed-identity behavior.

## HTTP Contract Source

- None. GitHub and Copilot are existing external services, not factory-owned
  HTTP APIs. No OpenAPI artifact is required.

## Non-HTTP Contract Inventory

### Contract 1: Local runner invocation and repository configuration

Status: in use; fixed host/image identity validation is planned under US-09.
Existing interfaces: [config](../src/software_factory/config.py) and
[CLI/preflight](../src/software_factory/runner.py).

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
- Ordering / Idempotency expectations: Require the provisioned Ubuntu Server
  24.04 LTS ARM64 host and effective UID/GID `2000:2000`; root, wrong IDs, or an
  unsupported host fail before issue claims. Do not switch accounts or elevate
  the host runner. Host preparation is explicit under Contract 9, not startup.
  Validate configuration, artifact-root usability, host tools/authentication,
  local engine readiness, and fixed image account/home/tool/sudo compatibility
  before claiming issues where possible. Probe failures/interruption require
  bounded cleanup; probe cleanup failure blocks startup. Resolve the image once
  per runner session; restart to adopt an updated tag. Do not build/pull an agent
  image or install target tools on the host. Do not move/delete existing artifacts.
  The operator ensures only one runner instance; labels are not a distributed lock.
- Visibility / Security: Keep configuration outside the agent workspace and
  under operator control. Do not copy host authentication/configuration into the
  agent environment. This normal separation does not prevent deliberate access
  through the Docker engine (Contract 3).
- Failure / Retry expectations: Unsupported host, root/wrong runner identity,
  invalid configuration, unavailable host tooling, failed authentication/engine
  readiness, unusable artifact root, or a missing/incompatible image prevents
  startup. Images lacking the fixed account, writable home, or working `sudo -n`
  require explicit rebuild/restart guidance; do not mutate them into compatibility.
  Do not claim issues on guessed prerequisite state, silently fall back, or retain
  a legacy backend.

### Contract 2: Issue discovery, skip handling, and immutable task input

Status: in use, unchanged by the migration. Implemented by
[GitHub coordination](../src/software_factory/github.py) and
[the runner](../src/software_factory/runner.py).

- Kind: GitHub label-driven request and captured issue snapshot.
- Producers / Owners: Operator owns label application and issue content; GitHub
  owns issue identity; the local runner owns the captured snapshot.
- Consumers: Local runner and Pi coding agent.
- Trigger / Direction: Serial polling discovers open issues labeled
  `agent:implement`, including existing labels on startup; the captured task
  flows to Pi. Paginate discovery/PR reads and exclude PRs from issue discovery.
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

Status: shared-image execution and credentials are in use. Build-time fixed
identity and socket-group launch/exec changes are planned under US-09/US-10;
current runtime account initialization is to be replaced, not retained as a
fallback. Existing boundaries: [agent lifecycle](../src/software_factory/sandbox.py)
and [Python Pi wrapper](../src/software_factory/sandbox_agent.py).

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
    instructions belong with the factory-maintained build definition. Preserve
    the Debian-based image; it need not match the host distribution.
  - Image identity: account/group `factory`, UID/GID `2000:2000`, is created at
    build time and selected for ordinary container execution. Build writable
    `/tmp/factory-home`, XDG caches, and npm user-local prefix into the image;
    keep the prefix's bin directory on PATH. Passwordless `sudo -n` is scoped to
    the factory account with root HOME selection. No account/shadow/group editing
    or root account-setup exec occurs at runtime.
  - Agent container: start as the image's fixed factory identity, with local
    engine access, the run workspace mounted at its same absolute Linux host/
    container path, and repository root as working directory. Setup, Pi, and
    verification use that identity/home/caches. Explicit system installs use
    `sudo -n`; no automatic elevation or root fallback. No target-specific factory
    Compose definition/image is required.
  - Socket membership: discover the selected local Unix socket's actual numeric
    GID on the Linux host; pass it with `--group-add` at agent creation. The
    actual `docker exec` path must retain UID/GID `2000:2000` and supplementary
    socket access, including when socket GID differs from 2000. Do not hard-code
    the socket group, change socket permissions, or modify account files to make
    access work. The exact exec form must be proven, not assumed from image
    metadata or a successful container start.
  - Supported engine: local native ARM64 Docker inside the provisioned Linux
    host, including the Lima guest. There is no macOS desktop socket-translation
    path, remote engine, or factory-selected emulation fallback. Startup validates
    native engine/shared image; factory-owned containers explicitly request
    `--platform linux/arm64` and `--pull=never`. Target commands inherit
    `DOCKER_DEFAULT_PLATFORM=linux/arm64`, not Docker command interception or
    guaranteed rejection of explicit platform overrides.
  - Pi invocation: one-shot print interface, explicit configured
    `github-copilot` model, coding tools, and nonpersistent sessions. Each call
    receives the immutable snapshot and current workspace. Preserve the standalone
    Python wrapper; the migration does not introduce repair invocations. Disable
    discovered extensions, MCP, skills, prompt templates, themes, and trust-gated
    project configuration.
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
  and workspace. Validate per-run identity/socket access before target setup;
  a host engine read or socket-free startup probe does not prove agent exec access.
  Setup precedes Pi, followed by verification under the original deadline. Pi
  exit zero means that invocation completed, not that the issue succeeded.
- Visibility / Security: Limit ordinary mounts/environment to workspace, engine
  access, and required run context; do not normally expose host SSH agents,
  GitHub CLI credentials, broader Pi home/settings, or other host directories.
  Allow internet access for dependencies and Copilot. Root plus Docker engine
  access provides effective engine control and potentially host control: neither
  workspace mounts nor credential separation enforce isolation against deliberate
  Docker-authorized commands. Do not claim the old sandbox guarantees remain.
- Failure / Retry expectations: Missing runtime, unusable workspace/socket,
  wrong image/exec identity, lost socket membership, incompatible engine/image,
  provider rejection, expired/malformed credentials, unsupported endpoint,
  termination, or deadline expiry fails visibly without fallback/setup repair.
  Attempt bounded cleanup under Contract 7. If `--group-add` does not work through
  actual exec, return feasibility evidence to the operator before selecting an
  alternative; never silently restore runtime account mutation or root retries.

### Contract 4: First-pass entrypoints, verification result, and deadline

Status: in use; only execution identity/socket membership changes under US-10.
Implemented by [verification](../src/software_factory/sandbox.py),
[orchestration](../src/software_factory/runner.py), and
[command deadlines](../src/software_factory/process.py).

- Kind: Executable repository entrypoints and exit-status/feedback protocol.
- Producers / Owners: Target repository owns entrypoints and CI alignment;
  local runner owns first-pass ordering and deadline.
- Consumers: Pi, local runner, and independent target CI.
- Trigger / Direction: Run setup before Pi implementation, then canonical
  verification. This migration does not add a repair loop.
- Payload / Shape:

  | Command/result | Meaning |
  | --- | --- |
  | `./scripts/setup` | Deterministic, noninteractive dependency/toolchain preparation, including required nonbaseline installations. |
  | `./scripts/verify` | Canonical CI-aligned checks, including required real local dependency/service-backed tests. |
  | Exit `0` | That command succeeded. |
  | Nonzero exit, signal, missing entrypoint, or invalid execution result | That command did not succeed. |
  | Completed verification's stdout/stderr | Private diagnostics, redacted for known credentials. |

  Both entrypoints must be executable before implementation. Commands run as the
  fixed UID/GID `2000:2000` from repository root inside the agent environment,
  retaining the socket membership defined in Contract 3. Target setup explicitly
  uses `sudo -n` for system installs, not whole scripts or workspace builds;
  permission errors never trigger automatic elevation. Additional runtimes/browser
  binaries belong in target setup; there is no pre-setup Pi bootstrap or guessed
  replacement command. Preserve the existing private verification-result protocol:
  the container shell runs the script, captures its exit status, and appends
  `FACTORY_VERIFY_EXIT=<status>` as a final newline-terminated output line, with
  decimal status in 0–255. Zero means checks passed; nonzero means completed check
  failure. The wrapper's final print allows the outer command to complete even
  when checks fail. An outer execution failure or missing/invalid marker is an
  execution/result error, not a completed check result. This marker distinguishes
  script status from Docker errors; it is not authentication of untrusted output.
- Ordering / Idempotency expectations:
  - Start one 900-second wall-clock budget when the issue run begins, before
    workspace/environment setup. It includes installations/builds, setup, Pi,
    verification, required cleanup before publication, and publication.
  - Run setup, initial implementation, and verification in that order. Failed
    setup ends the run before Pi; do not introduce setup repair.
  - A completed verification failure fails this first-pass issue run. Do not add
    implicit repairs, reset the environment/deadline, or automatically requeue.
    Preserve the distinction between completed check failure and Docker execution
    failure; neither authorizes an extra implementation attempt in this migration.
  - Verification must be safe to rerun. Passing still requires completed cleanup,
    time remaining, and nonempty changes before publication.
- Visibility / Security: Output may be sensitive and agent-influencing. Keep
  feedback private; do not execute it on the host or post transcripts to GitHub.
  Passing checks does not prove requirements, unchanged test quality, or merge
  readiness; independent CI and human review remain required.
- Failure / Retry expectations: Missing scripts, setup/provider/lifecycle errors,
  invalid results, failed verification, cleanup errors, and publication failures
  fail visibly without repair/retry. Expiry terminates work; do not begin further
  implementation or publication after expiry. Attempt bounded cleanup after
  failure/expiry/stop even when the original budget is exhausted; cleanup does
  not extend implementation or publication time.

### Contract 5: Host-side publication and draft PR identity

Status: in use, unchanged by the migration. Implemented by
[trusted Git publication](../src/software_factory/repository.py),
[PR creation](../src/software_factory/github.py), and
[publication gates](../src/software_factory/runner.py).

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

### Contract 6: GitHub status and private diagnostic lifecycle

Status: in use, unchanged by the migration. Implemented by
[runner status/artifact handling](../src/software_factory/runner.py) and
[private command diagnostics](../src/software_factory/process.py).

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
  | Failed | Concise reason: setup/provider/lifecycle or verification failure, expiry, cleanup/publication failure, interruption, or no changes. | Absent. |

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
  run identity, and 900-second deadline. Never resume the previous agent session/
  workspace or erase previous diagnostics. These preserve existing trigger/input
  semantics; no repair allowance or new manual-requeue workflow is added.
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

Status: in use, retained by the migration. Existing boundaries:
[resource identity/cleanup](../src/software_factory/sandbox.py) and
[required publication access](../src/software_factory/repository.py).

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
  failure, partial startup, deadline expiry, and operator interruption.
  Do not recursively change workspace ownership/permissions. After cleanup,
  inaccessible files/directories required for trusted host publication block
  publication; ignored caches need not be writable. Retain private host-owned logs
  and the unchanged workspace. Deliberately restricted files may need manual
  operator inspection. Service-private data should use disposable owned volumes;
  workspace-writing services need compatible UID/GID and permissions. Do not
  require every service image to run as UID 2000; validate the files it writes.
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

Status: native Docker/Compose execution and explicit service addressing are in
use. Native Linux-disk execution and Lima host-to-guest acceptance replace the
direct macOS desktop-provider model under US-08/US-10. Existing defaults/mounts:
[agent lifecycle](../src/software_factory/sandbox.py).

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
  - Same-absolute-path Linux workspace mounts allow sibling containers to resolve
    relative binds to the intended host path. Workspace/artifacts live on the VM/
    host's native Linux disk, not macOS shared folders. Do not assume `/workspace`
    or reuse host macOS `.venv`/`node_modules` as Linux dependencies.
  - A fixture port reached from macOS uses the Lima guest's explicit reachable
    address or authorized forwarding; Mac localhost and guest localhost are not
    assumed interchangeable. Network exposure/allocation requires operator approval.
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
  deadline or expand cleanup scope. A completed verification failure remains
  terminal under the first-pass Contract 4; no repair flow is added.

### Contract 9: Explicit Linux host provisioning and Lima environment

Status: planned under US-08; no provisioning entrypoint or Lima configuration is
implemented yet. This is the new host-preparation boundary, not a replacement for
existing target setup or runner configuration.

- Kind: Operator-invoked host provisioning entrypoint/runbook and repository-owned
  VM configuration. No new HTTP API, operator TOML fields, or job schema.
- Producers / Owners: The factory repository owns provisioning instructions,
  version/source verification, and Lima configuration; the operator authorizes
  installation, VM resources/network exposure, and host administration.
- Consumers: A persistent local Lima guest or an authorized production-like
  EC2/equivalent host, the factory account, and later runner startup.
- Trigger / Direction: An explicitly authorized Ubuntu Server 24.04 LTS ARM64
  host is prepared using the same provisioning entrypoint/runbook. Provisioning
  is separate from runner startup and target `./scripts/setup`.
- Payload / Shape:

  | Boundary value | Required shape / meaning |
  | --- | --- |
  | Host OS/architecture | Ubuntu Server 24.04 LTS ARM64; no emulated/x86-64 or direct macOS runner path. |
  | Factory account/group | `factory`, UID/GID `2000:2000`, on host and agent image; constants, not configurable overrides. |
  | Host privileges | Explicit administrative provisioning; ordinary runner has Docker access but no general passwordless host sudo. |
  | Local VM | Persistent Lima Ubuntu ARM64 guest with SSH and explicitly configured service access; configuration kept in the repository. |
  | Execution storage | Repository/workspaces/artifacts on the guest/host Linux disk; no macOS shared-folder execution data or unnecessary host-directory sharing. |
  | Readiness result | Fixed account, validated toolchain, native engine, and successful factory-account Docker access; authentication remains manual. |

  | Host tools | Accepted installation source / verification |
  | --- | --- |
  | Git, Make, sudo, curl, CA certificates, build dependencies | Ubuntu signed APT repositories. |
  | Docker Engine, CLI, Compose/buildx | Docker's official signed Ubuntu APT repository. |
  | GitHub CLI | GitHub CLI's official signed APT repository. |
  | Python 3.14.3 | Checksum-verified official python.org source; separate from system Python. |
  | Node.js 22.19.0 | Official ARM64 binary release with checksum/signature verification. |
  | uv 0.5.13 | Official release binary with checksum verification. |
  | Pi 1.3.0 | npm `@earendil-works/pi-coding-agent@1.3.0`, installed under the factory account. |

  Verify release availability, exact APT versions, and checksum/signature trust
  sources before implementing installation commands; record resolved versions
  and verification evidence. Exact Lima/Ubuntu image pins, resource allocation,
  and network settings remain the provisioning details identified in SPEC.md,
  not inferred defaults or newly approved policy. No mandatory JSON report,
  additional configuration format, or fixed provisioning script filename is
  introduced here; the implementation must document its invocation/results.
- Ordering / Idempotency expectations: Provision only through explicit operator
  action on the designated host. Detect account/name/ID conflicts without
  renumbering existing accounts. Repeated execution validates/reuses correct
  state without erasing credentials, repositories, or previous artifacts. Verify
  tools/native engine and Docker access as the factory account before reporting
  readiness; an administrator-only Docker read is insufficient. Explicit image
  build, manual authentication, and runner startup remain subsequent actions.
- Visibility / Security: Use signed repositories and verified versioned releases;
  no unversioned `curl | sh`, replacement of system Python, silent source/version
  substitution, automatic upgrade policy, or general host passwordless sudo.
  Never acquire/copy gh/Pi credentials automatically or make the socket world-
  writable. No VM/cloud creation, paid instance, or network exposure is implied
  by a provisioning contract. Docker access remains effective engine/host control.
- Failure / Retry expectations: Unsupported host, conflicting identity,
  unavailable/unverifiable releases, installation failure, or unusable factory
  Docker access yields a visible unsuccessful provisioning result, not readiness.
  Report partial preparation; do not promise transactional rollback or perform
  destructive account/artifact migration. If a release cannot be verified, ask
  the operator before changing source/version. Subsequent explicit provisioning
  must preserve existing correct state; it is not an automatic runner retry.

## Slice Handoff

- Contract artifacts implementers must read:
  - `docs/contracts.md`
- Next step: `$lean-story-delivery`, starting with US-08. List the relevant
  contract numbers and this artifact under `## Contract Inputs` in
  `docs/slices/current-slice.md` when planning the slice. Existing slice evidence
  describes the previous runtime and must not be treated as migration acceptance.
- Story mapping:
  - US-08: Contract 9, with Contract 1's manual-authentication/startup boundary.
  - US-09: Contracts 1 and 3, plus startup diagnostic/cleanup requirements in
    Contracts 6 and 7; Contract 9 supplies the provisioned host prerequisite.
  - US-10: Contracts 2–8 through the unchanged first-pass workflow on the fixed
    host/image identity, preserving Contract 1's validated startup/configuration.
- Required evidence: readiness from explicit/repeated provisioning; fixed-account
  CLI startup; real Linux ARM64 Git/Docker/Compose/service-backed issue E2E with
  scripted Pi/GitHub; actual exec supplementary socket access when socket and
  primary GIDs differ; native-disk sibling mounts; writable home/user-local tools;
  explicit sudo; compatible workspace output/disposable service volumes; and
  macOS access to a fixture port through the Lima VM's explicit network path.
- Cover identity conflicts/root/wrong IDs, old images, failed release verification,
  unavailable engine/socket membership, setup/verification/provider failures,
  timeout/SIGTERM/partial startup, cleanup/access failure, and uncertain publication.
  Preserve unrelated sentinel resources and old diagnostics. Remove obsolete
  runtime-account initialization/callers/fixtures without losing useful regressions.
- Repeat provisioning and real boundaries on an authorized disposable production-
  like host using the same entrypoint. VM/CI evidence does not establish cloud
  networking/storage; no paid resources or live authenticated services are
  authorized by these contracts. If exec group feasibility contradicts the
  accepted mechanism, return evidence to the operator instead of choosing a fallback.
- Preserve format → lint → tests/coverage and the unchanged Python overall
  line/branch 80% gate, including the standalone Python wrapper and new business
  logic. ARM64 CI executes under the fixed identity. Update current instructions
  and distinguish target requirements, actual verification, and remaining gaps.
