# Product Specification

Source: [DECISIONS.md](DECISIONS.md)

## Summary
- Replace target-specific factory sandboxes with one shared Linux agent image connected to the existing local Docker engine. The autonomous coding factory still turns labeled GitHub issues into verified draft PRs using Pi/Copilot and trusted host publication. Domain names follow [CONTEXT.md](CONTEXT.md).
- This is the accepted target behavior, not a claim of implementation. Historical US-01–US-03 cover the previous execution model; their recorded acceptance does not establish the Docker-enabled model. US-04–US-07 below are the new backlog. Existing contracts must be updated before implementation.
- Docker access grants effective engine control and potentially host control. The agent environment is not a security boundary protecting host files, credentials, or other containers. The operator accepts this exposure; normal credential separation remains useful but cannot prevent deliberate Docker-mediated access.

## Goals
- Use one factory-maintained, versioned, native `linux/arm64` agent image across target repositories, without target-specific factory agent images or Compose definitions.
- Build target images, start ordinary application/dependency Compose services, and execute service-backed E2E verification from the agent environment.
- Support local ARM64 Linux containers, including Apple Silicon macOS with a local Docker provider; use the same absolute workspace path on host and agent.
- Preserve one repository/runner, serial issue runs, 30-second polling, a shared 900-second deadline, three verification repairs, duplicate protection, create-only publication, and fresh manual requeue.
- Clean known run-owned resources on success and failure while preserving unrelated resources and private failed-run diagnostics.
- Validate real local Docker/macOS boundaries, run Docker integration CI on ARM64, and preserve format/lint/tests and the Python and Node 80% coverage gates.
- Replace the old execution path completely, reusing coordination/publication logic and removing obsolete validation, configuration, fixtures, and tests as replacements land.

## Non-Goals
- Multiple repositories, simultaneous runners, parallel issue runs, eligibility analysis, or clarification conversations.
- Automatic merging, PR review-feedback revisions, automatic requeue, or interrupted-session recovery.
- A database, HTTP API, dashboard, new orchestration framework, parallel legacy backend, or automatic configuration migration.
- Remote Docker engines, factory-managed VMs, cloud provisioning/deployment, AMD64 emulation, or general multi-architecture support.
- Transparent sibling-service `localhost` compatibility, a Pi bootstrap phase before setup, setup repair, or host-side target-tool installation.
- Automatic shared-agent-image builds/pulls by the runner, daemon-wide pruning, automatic deletion of untracked resources, or hard-crash cleanup.
- Exact-image local tryouts, retained verified-image manifests, image archives, or a tryout launcher. The operator manually checks out the PR instead.
- A new live Copilot-to-GitHub-PR demonstration as a completion gate. Live authenticated checks require separate approval.
- Issue comments, attachments, or linked pages as task inputs; separately billed provider fallback.

## Incremental Delivery Constraint
- During US-04 delivery, the operator approved a temporary pre-claim guard until US-05 is implemented. Validated startup enters read-only polling; discovered issues and direct issue dispatch produce a local execution-unavailable warning without consuming labels, writing GitHub status, creating workspaces, or invoking the old backend. This guard is not the final US-05 issue-processing behavior.

## User Stories

### US-04: Start the runner with a shared agent image
Primary actor: Operator

Trigger: The operator is ready to run the factory against one trusted target repository.

Happy-path action: Start the runner with operator-owned configuration and a locally built shared agent image.

Visible outcome: The runner validates its prerequisites and begins polling without requiring a target-specific factory sandbox.

Authoritative state transition: Stopped runner with supplied configuration → validated runner polling the configured repository.

Slice boundary: One terminal startup-to-polling outcome through configuration, shared-image availability, local Docker readiness, artifact-root usability, and actionable startup failures. Test startup without processing a real GitHub issue.

Acceptance criteria:
- Preserve the existing terminal invocation. Require exactly four nonempty TOML strings: `repository`, `model`, `agent_image`, and `artifacts_dir`, with no credentials or defaults. Preserve GitHub `owner/name` and exact accessible `github-copilot` model semantics; reject invalid, missing, wrong-type, or unknown fields.
- Reject old `compose_file`/`compose_service` configuration with migration guidance. Do not reinterpret it, automatically migrate it, or retain the old backend.
- Resolve relative artifact paths against the TOML directory. Validate artifact-root usability before claims where possible; never move/delete previous artifacts implicitly.
- Supply the shared image definition/build instructions in this factory repository. Its pinned baseline includes Pi, Node.js/npm, Docker CLI/Compose, Python/uv, Bash, Git, Make, a C/C++ toolchain, curl, CA certificates, tar, unzip, and standard Linux utilities, without baked-in credentials.
- The operator builds the image before startup. Require a compatible local native `linux/arm64` image and resolve it to an immutable image ID for the runner session. Updating it requires restart; missing/incompatible images fail startup without automatic builds, pulls, or fallback.
- Check host tools/authentication and local engine/execution prerequisites before claiming issues where possible. Reject unsupported architecture rather than silently using emulation. Fail startup nonzero with safe, actionable diagnostics.
- Retain one runner instance per configured repository, serial execution, and 30-second polling. Labels are not a distributed lock; authentication/access approval remains manual.
- A focused startup test reaches polling using the new configuration and shared image; negative tests cover legacy configuration, invalid fields, unavailable/incompatible images, unusable artifact paths, and engine failures.

Deferred follow-ups:
- US-05: Publish a first-pass result using Docker-enabled execution.
- US-06: Recover failed verification in that environment.
- US-07: Manually requeue failed or interrupted work.

### US-05: Turn a labeled issue into a Docker-verified draft PR
Primary actor: Operator

Trigger: An issue receives `agent:implement` while the validated runner is polling.

Happy-path action: Submit the issue for unattended implementation and verification using the target's ordinary application services.

Visible outcome: The issue links to a draft PR containing nonempty verified changes, after owned execution resources are cleaned up.

Authoritative state transition: Unclaimed labeled issue → GitHub-recorded successful issue run linked to a draft PR.

Slice boundary: One first-pass issue-to-draft-PR outcome through existing GitHub coordination, a fresh shared-image agent environment, real Docker build/Compose/service-backed verification, scoped cleanup, and trusted host publication. Required failure and trust-boundary checks belong in this slice, not a later cleanup story.

Acceptance criteria:
- Attempt every labeled issue without classification or clarification. Before execution, check for an open PR matching the exact configured head repository and `factory/issue-<number>`. If found, remove the trigger, preserve the PR, and comment with its link; do not infer identity from body text or other branch names.
- If that remote branch exists without a matching open PR, remove the trigger, skip execution, and request operator branch cleanup and label reapplication. Never overwrite/delete the branch. Confirm trigger removal before execution or skip notification; do not blindly retry uncertain writes.
- Otherwise claim the issue, record running status, snapshot title/body, and create a fresh workspace from the discovered default branch. Later edits, issue-thread content, attachments, and linked pages do not become run inputs.
- Start one root agent container per issue run using the session's resolved image, local Docker engine access, and a workspace mount at the same absolute path on host and agent. Normal mounts/environment exclude broader host directories/configuration and GitHub publication credentials, despite Docker access being able to bypass these limits.
- Run setup → Pi implementation → verification inside that environment. Require executable, deterministic, noninteractive `./scripts/setup` and `./scripts/verify`, with verification aligned to target CI. Setup installs any nonbaseline toolchain prerequisites; missing entrypoints or setup failure fails before Pi runs. Do not invent replacement commands or setup repair.
- Allow target image builds, ordinary Compose startup, and service-backed checks. Native `linux/arm64` is required for application/dependency execution; unsupported images/tools fail visibly instead of silently using AMD64 emulation or replacements.
- Use explicit test service addresses: Compose DNS when the agent joins the relevant network, or the Docker host address for published ports. Sibling containers do not share the agent's localhost; transparent forwarding is not required.
- Preserve exact-model Copilot invocation, stdin-only bearer delivery, validated endpoint metadata, temporary configuration, disabled discovered resources, and nonpersistent sessions. Keep broader host Pi settings, refresh credentials, and GitHub write credentials out of normal agent inputs; never fall back to another billing provider.
- All phases, including workspace preparation, installation/builds, execution, checks, and publication, share one original 900-second deadline. Expiry stops work and fails the run; do not deliberately continue publication after expiry. Bounded cleanup is still required after expiry or interruption.
- Assign a unique run identity. Ordinary Compose commands inherit `COMPOSE_PROJECT_NAME`; direct containers/networks/volumes must use the factory-provided run label. These are cooperative conventions, not security controls; overrides, unlabeled commands, or other contexts can bypass them.
- Keep sufficient host-owned identity for cleanup independent of agent-modified Compose files. Stop/remove owned containers before owned networks and disposable owned volumes. Never execute agent-authored teardown scripts on the host, infer ownership from disuse, or prune broadly. Leave unrelated/shared resources, images, build cache, and untracked resources alone; unknown resources and hard-crash leftovers require operator inspection.
- Stop workspace-mutating processes/services and finish required cleanup before host commit/publication. Cleanup failure blocks publication and retains diagnostics. Workspace files must remain readable/writable by the host operator after success or failure.
- With passing verification, completed cleanup, time remaining, and a nonempty diff, commit using trusted host Git metadata, create the absent remote factory branch, open a draft PR containing `Closes #<number>`, and comment with the actual URL. Ignore agent-authored Git hooks/configuration during host publication. Empty output fails as `no changes produced`; commit/push/PR/reporting failures remain visible, with inspection rather than blind retries of uncertain publication.
- Failures receive concise issue summaries when possible and retain private local workspaces/logs until operator deletion. Use 0700 run directories, 0600 logs, and known-credential redaction; never publish full transcripts or secrets. Successful diagnostics/workspaces may be removed. Independent target CI and human review remain required; the factory neither merges nor revises from review feedback.
- Demonstrate the focused flow with real Docker build/Compose/service-backed verification and scripted Pi/GitHub boundaries. Also verify same-path sibling bind mounts, target-specific installation, socket access, host file ownership, and a macOS browser reaching a published application port on the actual local provider. Linux CI alone does not prove desktop sharing/networking.
- Test cleanup on success, setup/verification failure, timeout, interruption, and partial startup, including cleanup failure blocking publication. Preserve an unrelated sentinel container/network/volume. Test credentials, architecture failures, deadline, duplicates, empty output, publication failures, and private diagnostic retention.
- Preserve useful existing coordination, deadline, credential-validation, verification-feedback, and publication logic. Complete the removal audit: one execution path, no obsolete callers/compatibility backend, and no obsolete fixtures retained solely to keep removed code alive. Update current instructions, configuration guidance, and architecture/workflow docs to the new model without obsolete isolation claims.
- Run format/lint/tests and real Docker integration checks on ARM64 with unchanged Python overall line/branch and Node line/branch/function 80% coverage gates. Distinguish scripted boundaries from real services; no live Copilot/GitHub-writing demonstration is required or implicitly authorized.

Deferred follow-ups:
- US-06: Recover a verification failure using bounded repairs.
- US-07: Manually requeue failed or interrupted work.

### US-06: Recover a Docker-enabled verification failure
Primary actor: Operator

Trigger: Verification fails after the initial implementation in the Docker-enabled agent environment.

Happy-path action: Allow the factory to repair failed verification without intervention.

Visible outcome: A draft PR is linked after a permitted repair passes verification and cleanup succeeds.

Authoritative state transition: Running issue run with failed verification → GitHub-recorded successful issue run linked to a draft PR.

Slice boundary: One recovery-to-PR outcome using the same agent environment, workspace, canonical verification command, and original deadline. Preserve all US-05 ownership, credential, cleanup, and publication gates.

Acceptance criteria:
- Give Pi the failed verification output, unchanged issue snapshot, and current workspace; run the same `./scripts/verify` after the repair. Do not reset the agent environment, issue run, or deadline.
- Permit at most three repair-and-verify cycles after initial implementation. Stop at the first passing verification and publish only nonempty changes after required cleanup, using US-05 gates.
- Setup, missing entrypoints, provider, Docker lifecycle, cleanup, deadline, and publication failures do not authorize extra verification repair attempts.
- A third unsuccessful repair or deadline expiry fails the run, attempts bounded cleanup, retains private diagnostics, and creates no PR. Installing/building during repairs consumes the original deadline.
- A focused recovery test demonstrates service-backed verification failing, receiving repair feedback, then passing and reaching publication. Tests also cover exactly three unsuccessful repairs, deadline expiry during recovery, cleanup after exhaustion, and cleanup failure blocking publication. Scripted Pi/GitHub boundaries are not live acceptance.

Deferred follow-ups:
- US-07: Manually requeue after failed or interrupted work.

### US-07: Manually requeue Docker-enabled work
Primary actor: Operator

Trigger: The operator reapplies `agent:implement` after failure or interruption.

Happy-path action: Request a fresh attempt after inspecting diagnostics and resolving any blocking remote branch.

Visible outcome: A new issue run produces a verified draft PR without resuming earlier work or deleting earlier diagnostics.

Authoritative state transition: Failed or interrupted issue awaiting manual requeue → GitHub-recorded successful fresh issue run linked to a draft PR.

Slice boundary: One explicit retry-to-PR outcome through the same Docker-enabled execution and publication path. Include restart inactivity, resource isolation between runs, and preservation of the earlier failed workspace/logs.

Acceptance criteria:
- Failure, interruption, and restart do not automatically restore the trigger, resume a session, or interpret retained diagnostics as work to execute. Hard-crash resource inspection/cleanup remains manual.
- Repeat US-05 exact PR/branch checks. Preserve and link matching open PRs; a factory branch without an open PR blocks execution even after a closed PR or uncertain publication. A skip consumes the trigger and requires explicit label reapplication after operator cleanup.
- A clear requeue takes a fresh title/body snapshot and current default-branch workspace, with a new run identity, 900-second deadline, and up to three verification repairs. Never reuse the failed workspace/session as the baseline.
- Preserve previous failed artifacts and unrelated Docker resources. Apply all US-05/US-06 architecture, setup ordering, credential, ownership, cleanup, verification, and publication requirements.
- A focused test interrupts a run, confirms restart alone performs no work, reapplies the label with edited issue content, and reaches a draft PR through fresh Docker execution. Verify old diagnostics remain unchanged and new cleanup cannot remove another run's resources. Scripted external boundaries do not establish live Copilot/GitHub acceptance.

Deferred follow-ups:
- None.

## Open Questions
- None requiring product policy. Local provider feasibility and exact tested image/tool pins remain implementation and verification work, not proven acceptance. If validation contradicts these decisions, return to the operator rather than silently changing scope or guarantees.
