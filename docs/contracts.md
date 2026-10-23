# Contracts

## Purpose

Formalize the non-HTTP boundaries required by [SPEC.md](../SPEC.md), using
[DECISIONS.md](../DECISIONS.md) for locked policy and [CONTEXT.md](../CONTEXT.md)
for naming. These contracts cover US-01 through US-03; they do not introduce an
HTTP server, external job queue, database, or public event stream.

Constants are not configuration options: one repository and runner instance,
one issue run at a time, 30-second polling, a 900-second issue-run deadline, and
at most three repair attempts after the initial implementation.

## HTTP Contract Source

- None. GitHub and Copilot are existing external services, not factory-owned HTTP APIs.

## Non-HTTP Contract Inventory

### Contract 1: Local runner invocation and repository configuration

- Kind: Terminal invocation and operator-owned TOML configuration.
- Producers / Owners: Operator.
- Consumers: Local runner.
- Trigger / Direction: Operator starts the runner; the runner polls until stopped.
- Payload / Shape:

  ```sh
  uv run --frozen python -m software_factory --config /path/to/factory.toml
  ```

  ```toml
  repository = "TeroTS/factory-smoke-test"
  compose_file = "/path/to/operator-prepared/compose.yaml"
  compose_service = "agent"
  model = "gpt-6.1-sol"
  ```

  | Field | Required shape | Meaning |
  | --- | --- | --- |
  | `repository` | Nonempty `owner/name` string, not a URL | The single target repository on GitHub.com. |
  | `compose_file` | Nonempty path to a readable Compose file | Absolute, or relative to the configuration file's directory. |
  | `compose_service` | Nonempty name present in the resolved Compose configuration | The service used for agent work and golden-path commands. |
  | `model` | Nonempty exact Pi model ID under `github-copilot` | Account-accessible Copilot model; no provider fallback. |

  All four fields are required. Reject unknown fields, wrong types, missing
  files/services, and unavailable configured tooling with an actionable diagnostic.
  The configuration contains no credentials or arbitrary command templates.
  The default branch is discovered from GitHub, not configured separately.
  The module is implemented under `src/software_factory/`; US-01's live acceptance
  passed for issue 7 and draft PR 8. Evidence is in `docs/slices/current-slice.md`.
- Ordering / Idempotency expectations: Validate configuration before claiming
  issues. The operator runs only one instance for the target repository; this
  interface does not provide distributed coordination or automatic resumption.
- Visibility / Security: Configuration is trusted operator input and must not be
  replaced by agent-authored configuration. Do not inherit the host's broader Pi
  settings, extensions, sessions, or GitHub credentials into the sandbox.
- Failure / Retry expectations: Invalid configuration or inability to operate
  safely produces a nonzero startup exit and a stderr diagnostic, not a successful
  launch. Operator stop ends polling and stops/removes run-owned containers.
  Issue-level failure is recorded through Contract 6; it is not a successful PR.

### Contract 2: Issue discovery, skip handling, and immutable task input

- Kind: GitHub label-driven work request and issue snapshot.
- Producers / Owners: Operator owns label application and issue content; GitHub
  owns issue identity; the local runner owns the captured snapshot.
- Consumers: Local runner and Pi coding agent.
- Trigger / Direction: Each 30-second poll discovers `agent:implement` issues in
  the configured repository. Snapshot input flows from GitHub to the coding agent.
- Payload / Shape:

  | Value | Shape |
  | --- | --- |
  | Repository | Configured `owner/name`. |
  | Issue number | Positive integer identifying the issue within that repository. |
  | Title | GitHub issue title string, captured at claim time. |
  | Body | GitHub issue body string or `null`, captured at claim time. |
  | Base commit | Resolved default-branch commit used to create the fresh workspace. |

  This is a boundary data shape, not a new public job API or required on-disk
  file format. The title/body snapshot and repository contents are the task
  inputs. Comments, attachments, linked pages, and subsequent issue edits are
  not added to the running task.
- Ordering / Idempotency expectations:
  1. Check for an open PR with the exact configured head repository and head
     branch `factory/issue-<number>`. Do not infer identity from PR-body text.
  2. If found, remove `agent:implement`, skip execution, and comment with its link.
  3. Otherwise, if that remote branch exists, remove `agent:implement`, skip
     execution, and comment that the operator must delete it before retrying.
  4. Otherwise, remove `agent:implement`, record running status, capture the
     snapshot, and create a fresh workspace from the default branch.

  Confirm trigger removal before proceeding with execution or posting a skip
  notification. Subsequent polls do not repeat the notification without explicit
  label reapplication. PRs with other branch names are outside duplicate detection.
- Visibility / Security: Attempt every labeled issue without type classification,
  eligibility analysis, or clarification. Treat title, body, and repository content
  as untrusted data; never interpolate them into host shell commands.
- Failure / Retry expectations: If required GitHub reads or trigger removal fail,
  do not guess the result or proceed with implementation. Surface the failure.
  Label/comment operations are not an atomic transaction and do not promise
  exactly-once notification through crashes or ambiguous API responses.

### Contract 3: Sandboxed Pi execution and Copilot credentials

- Kind: Host-to-Compose execution boundary and noninteractive Pi process.
- Producers / Owners: Operator prepares the environment; local runner owns its
  lifecycle and the per-run workspace; the host owns credentials.
- Consumers: Pi coding agent, repository tooling, and required dependency services.
- Trigger / Direction: A claimed issue starts sandbox execution. The runner sends
  implementation instructions or verification-failure feedback to Pi.
- Payload / Shape:
  - The configured service provides Pi, the target's runtime/tools, and a working
    directory containing the per-run repository workspace. Commands must be
    noninteractive and support reporting exit status and stdout/stderr.
  - Use Pi's one-shot print interface, an explicit `github-copilot` model, and
    nonpersistent sessions. Every call receives the same immutable task snapshot
    and current workspace contents; repair calls additionally receive the failed
    verification output. No interactive prompts or host conversation are required.
  - Disable discovered extensions, MCP, skills, prompt templates, themes, and
    trust-gated project configuration for the unattended invocation. Repository
    context files may still provide coding instructions; they are not a security
    boundary. The agent needs coding tools, unlike the tools-disabled auth probe.
  - Pi process exit zero means that invocation completed, not that the issue is
    implemented correctly. A nonzero exit, termination, or deadline expiry must
    not be represented as successful implementation or successful verification.
  - The host resolves a Copilot-only bearer before the run. The proven mechanism
    is `pi auth print-bearer-token --provider github-copilot --min-expiry 20m`,
    captured privately with host resource loading disabled. Do not print the
    returned token, put it in command arguments, or copy host auth directories.
  - Supply only that bearer through a private input channel. Set the Copilot
    API endpoint from validated credential metadata; the proven account uses
    `https://api.business.githubcopilot.com`, not the individual endpoint.
    The GitHub OAuth refresh token stays on the host.
- Ordering / Idempotency expectations: All Pi and repository execution shares
  the same workspace and original issue-run deadline. A repair call does not
  create another issue run or reset the clock. Fresh manual requeue never resumes
  an earlier agent session.
- Visibility / Security:
  - No GitHub write credentials, host SSH agent, GitHub CLI auth files, broader
    Pi home, host Docker socket, or host-directory mounts beyond the workspace.
  - Enforce the boundary for the resolved Compose configuration and dependency
    services, not just the named service. Reject privileged/host-process access
    or other settings that defeat workspace and credential isolation.
  - Allow network access for dependencies and Copilot; this is not an
    exfiltration-proof environment. Credentials available to Pi remain available
    to processes inside its sandbox and must be Copilot-only.
  - Startup, dependency lifecycle, commands, and cleanup are host-controlled;
    repository scripts and generated commands execute only inside the sandbox.
- Failure / Retry expectations: Missing Pi/runtime, unsafe configuration, provider
  rejection, missing/expired credentials, or an unsupported endpoint fails visibly.
  Do not fall back to another provider, expose broader credentials, or count a
  provider failure as another verification-repair allowance. Stop/remove run-owned
  containers on completion, expiry, or operator stop. A hard host crash can leave
  resources/status behind; it does not authorize automatic session recovery.

### Contract 4: Golden-path verification, repair allowance, and deadline

- Kind: Repository executable entrypoints and exit-status protocol.
- Producers / Owners: Target repository maintains the commands and CI alignment;
  local runner owns invocation order, deadline, and repair count.
- Consumers: Coding agent, local runner, and target repository CI.
- Trigger / Direction: Setup runs before implementation; verification runs after
  the initial implementation and after each permitted repair.
- Payload / Shape:

  | Command/result | Meaning |
  | --- | --- |
  | `./scripts/setup` | Noninteractive, deterministic dependency/runtime preparation. |
  | `./scripts/verify` | The repository's canonical CI-aligned checks, including required real local dependency-backed tests. |
  | Exit `0` | That command succeeded. |
  | Nonzero exit, signal, or missing entrypoint | That command did not succeed. |
  | Verification stdout/stderr | Failure feedback for the next permitted repair, retained locally rather than posted in full. |

  Commands run from the repository root inside the prepared sandbox. No guessed
  replacements or success-by-default behavior. Both scripts must exist before
  implementation; setup must succeed before Pi implements the issue.
- Ordering / Idempotency expectations:
  - Start one 900-second wall-clock budget when the issue run begins, before
    workspace/sandbox setup; it covers setup, implementation, all repairs/checks,
    and publication. It does not restart between phases.
  - Verify the initial implementation. After a verification failure, allow up to
    three repair-and-verify cycles. Stop at the first successful verification.
  - Successful verification still requires a nonempty change set before
    publication. An empty result fails as `no changes produced`.
  - Verification must be safe to rerun in the workspace. Setup/verification
    services are prepared in advance; the factory does not design them per issue.
- Visibility / Security: Treat command output as potentially sensitive and
  agent-influencing. Do not execute it on the host or publish raw transcripts.
  Verification success is an execution gate, not a guarantee of requirement
  fulfillment or unchanged test quality; human review remains mandatory.
- Failure / Retry expectations: Missing commands or failed setup fails the run.
  A third unsuccessful repair fails the run. Expiry fails the run even when
  repairs remain; terminate work rather than deliberately starting further phases
  after expiry. Never publish unvalidated changes. Cleanup must still be attempted
  after expiry; the deadline is not permission to leave processes running.

### Contract 5: Host-side publication and draft PR identity

- Kind: Git branch publication and GitHub draft PR creation.
- Producers / Owners: Local runner performs publication on the host; human reviewer
  owns review and merge decisions.
- Consumers: GitHub and human reviewer.
- Trigger / Direction: Successful verification of a nonempty diff, with time
  remaining, leads from workspace changes to a remote branch and draft PR.
- Payload / Shape:
  - Head repository: exactly the configured target repository.
  - Head branch: `factory/issue-<number>`.
  - Base branch: the target repository's default branch.
  - PR state on creation: draft.
  - PR body includes `Closes #<number>`.
  - Successful publication yields the actual created PR's URL for the issue
    status comment; a guessed URL is not a successful result.
- Ordering / Idempotency expectations: Commit, atomically create the remote
  factory branch, create the draft PR, then record success with its link. Use an
  empty expected-ref lease (`--force-with-lease=refs/heads/factory/issue-<number>:`)
  to require branch absence at push time; this never permits updating an existing
  branch, even by fast-forward. Recheck observed remote state when publication outcomes are uncertain;
  the next explicitly requeued attempt applies Contract 2 before any execution.
  A push that succeeds before PR creation fails may leave a branch requiring
  operator cleanup. Do not create duplicate PRs or rewrite history to recover.
- Visibility / Security: GitHub CLI credentials stay on the host. Publication
  must use trusted host-owned Git metadata; sandbox-controlled Git configuration,
  hooks, credential helpers, or filters must not execute on the host. Do not run
  repository setup/tests on the host as part of committing or publishing.
- Failure / Retry expectations: A failed commit, push, or PR creation is not
  successful publication and must be reported. Do not blindly repeat uncertain
  writes or force-push. Independent CI and human review follow PR creation;
  the factory neither waits for a merge decision nor automatically merges or
  implements PR review feedback.

### Contract 6: GitHub status, local diagnostics, and manual requeue

- Kind: Human-readable issue comments, trigger-label lifecycle, and retained
  local diagnostic artifacts. No additional status-label taxonomy is required.
- Producers / Owners: Local runner records outcomes; operator owns requeue and
  artifact/branch cleanup; GitHub stores durable coordination state.
- Consumers: Operator and human reviewer.
- Trigger / Direction: Claim, skip, success, or failure produces visible status;
  operator label reapplication requests another check.
- Payload / Shape:

  | Status | Required information | Trigger label afterward |
  | --- | --- | --- |
  | Running | Issue reference and notice that implementation has started. | Absent. |
  | Skipped: open PR | Existing PR URL; no implementation performed. | Absent. |
  | Skipped: existing branch | Factory branch name and instruction to delete it and reapply the label. | Absent. |
  | Succeeded | Actual draft PR URL. | Absent. |
  | Failed | Concise reason, such as missing command, setup/provider failure, exhausted repairs, deadline expiry, publication failure, operator interruption, or `no changes produced`. | Absent. |

  The table assumes trigger removal succeeded; a failure before removal must
  not be reported as if the label were absent. Comments are human-readable
  reports, not a new machine-readable event API. Exact prose is not an interface.
  Trigger-label presence controls polling eligibility; remote PR/branch identity
  controls duplicate protection.
- Ordering / Idempotency expectations: Remove `agent:implement` before execution
  or skip notification. Do not automatically add it back on failure, interruption,
  or runner restart. Explicit reapplication requests fresh input/workspace and
  a fresh budget/repair allowance, subject to duplicate/branch checks.
- Visibility / Security: Keep failed workspaces and logs locally until operator
  deletion, outside version control. Report their local location to the operator;
  never publish full logs/transcripts, credentials, or sensitive output in issue
  comments. Requeue does not delete previous failure artifacts.
- Failure / Retry expectations: If GitHub reporting fails, report locally rather
  than claiming the status was posted. A hard interruption may leave the last
  GitHub comment as running; restarting must not interpret that as permission to
  resume. This MVP does not promise atomic label/comment changes, exactly-once
  notifications through failure, a recovery database, or automatic cleanup of
  interrupted remote branches.

## Slice Handoff

- Contract artifacts implementers must read:
  - `docs/contracts.md`
- Current implementation: `docs/slices/current-slice.md`, US-01 done with real
  issue-to-PR evidence and automated failure/isolation checks. US-02 repair recovery and US-03 manual-requeue delivery
  remain deferred. Implementation limits and operator preparation are in `README.md`.
- List `docs/contracts.md` under `## Contract Inputs` in
  `docs/slices/current-slice.md` when slice planning creates that file. No slice
  note or implementation is created by this contract-writing step.
- Deployment prerequisite satisfied locally: smoke-test preparation is merged
  into `main` at `6b5315e706831f5b1e6201d7cb4d0febe66d12fb`, and the agent profile
  owned by the local target checkout at `sandbox/agent/` passed setup, real Pi/Copilot
  implementation, verification, and cleanup against it. The operator-owned four-field
  `factory.toml` stays outside the target checkout (locally at ignored
  `artifacts/operator/factory-smoke-test.toml`) and references the trusted Compose
  path, preserving Contracts 1 and 3. The complete approved issue-to-PR test passed
  for issue 7 → draft PR 8, with green independent CI and verified cleanup.
  Human review/merge remains external; repair recovery and successful manual-requeue
  acceptance remain US-02/US-03 work.
