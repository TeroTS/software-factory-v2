# Docker-enabled Autonomous Coding Factory Decisions

Status: decisions accepted

## Problem Summary

Replace the prepared, target-specific Compose sandbox with one shared Linux agent image connected to the existing local Docker engine. A target repository should need ordinary setup/verify entrypoints and its application Compose configuration, not a factory-specific agent image or Compose definition. Preserve the existing issue-to-draft-PR workflow.

This record defines accepted product/deployment policy. It supersedes arbitrary-host-ID initialization, direct macOS runner support, and prepared target-specific Compose environments. Exact-image local tryouts are excluded. `SPEC.md` and contracts define the accepted behavior/interfaces; implementation status and verification evidence belong only in `docs/slices/current-slice.md`. Update affected specification/contracts before implementation changes.

## Goals and Success Criteria

- Build images, start ordinary target Compose services, and execute service-backed E2E checks from the shared agent environment.
- Run and verify the factory in the persistent Ubuntu Server 24.04 LTS ARM64 Lima VM on Apple Silicon. The operator selected this local VM as the only deployment/acceptance environment; a separate production-like host is not required.
- Eliminate target-specific factory sandbox preparation and retain exactly one execution path.
- Preserve serial issue processing, the 900-second issue-run deadline, three verification repairs, host-side publication, duplicate protection, and fresh manual requeue.
- Demonstrate same-path workspace mounts, target-specific tool installation, explicit service networking, host-usable files, and scoped cleanup across success and failure paths.
- Pass the existing format/lint/test checks and unchanged Python 80% coverage gate, with Docker integration CI exercising ARM64.

## Primary Roles / Actors

- Operator: builds the shared image, prepares target entrypoints, configures/authenticates and runs the factory, labels issues, inspects failures, and manually checks out PRs for local evaluation.
- Local runner: polls GitHub, owns issue-run lifecycle and private diagnostics, invokes agent work/checks, cleans owned resources, and publishes validated changes.
- Pi coding agent: implements issues and repairs failed verification using the existing GitHub Copilot subscription.
- Target repository: supplies setup/verify entrypoints, ordinary application/dependency configuration, and required test configuration.
- Human reviewer: evaluates changes and independent CI and owns merge decisions.
- GitHub: stores issues, labels, comments, branches, draft PRs, and independent CI results.
- Local Docker engine: executes the agent and its sibling application/dependency containers.

## Non-Goals

- Multiple target repositories, simultaneous runners, or parallel issue runs.
- Issue eligibility analysis, clarification conversations, automatic merging, or PR revisions from review feedback.
- Webhooks, HTTP APIs, dashboards, a database, or session recovery.
- A legacy sandbox backend, backend selection framework, or automatic configuration migration.
- Automatic VM/cloud resource provisioning by the runner, a remote Docker engine, ECS Fargate, or a cloud deployment framework. Explicit host provisioning for Lima is in scope; deployment/testing on EC2 or another production-like host is not.
- Direct macOS runner execution, arbitrary host UID/GID support, parallel fixed/dynamic identity backends, and automatic host-account or retained-artifact migration.
- AMD64 emulation or general multi-architecture support.
- Transparent compatibility for tests that hardcode sibling services at the agent's `localhost`.
- A pre-setup Pi bootstrap phase, setup repair, or host-runner installation of target tools.
- Automatic shared-image builds or pulls by the runner.
- Exact-image local tryout reproduction, a tryout launcher, retained verified-image records, or image archives. The operator manually checks out the PR instead.
- Automatic cleanup of untracked resources, daemon-wide pruning, or hard-crash recovery.
- A new live Pi/Copilot-to-GitHub-PR demonstration as a completion requirement.

## Locked Decisions

### Product / Scope

- Refactor this project rather than creating a replacement project or parallel execution backend. The `ver-1.0.0` tag preserves the previous implementation.
- One trusted target repository, one runner instance, one issue run at a time, and 30-second polling remain unchanged.
- Every trigger-labeled issue is attempted without eligibility classification or clarification.
- The execution environment is one shared, versioned Linux agent image maintained in this factory repository.
- Native `linux/arm64` is required for the agent and target application/dependency execution. Clarified by the operator-approved wrapper-removal plan: validate the native engine/shared agent image, explicitly request native factory-owned containers, and supply a native target default without intercepting Docker commands. Target scripts must use native-compatible images/tools; explicit platform overrides may invoke engine-supported emulation and are not guaranteed to be rejected. The factory never selects an emulation fallback or substitutes dependencies; actual Docker/setup/verification failures remain visible.

### UX / Workflow

- Preserve setup → Pi implementation → verification, followed by at most three verification repair-and-verify cycles.
- Setup must succeed before Pi runs. Target-specific prerequisites belong in the shared baseline or the target's setup script.
- All run work, including installations/builds and publication, shares the original 900-second deadline.
- The operator builds the shared image before starting the runner and restarts the runner to adopt an updated image.
- The operator evaluates published changes by manually checking out the PR; the factory provides no local tryout automation or exact-image reproduction feature.

### Data / State / Ownership

- GitHub remains the durable coordination surface; private local artifacts are diagnostics, not resumable state.
- Every issue run has a unique resource identity. Ordinary Compose commands inherit a unique `COMPOSE_PROJECT_NAME`; directly created containers, networks, and volumes must carry the factory-provided run label.
- Cleanup may delete owned containers, networks, and disposable run-owned volumes. Leave shared images, build cache, external/shared resources, and resources lacking the ownership identity alone.
- Preserve failed workspaces/logs until operator deletion; successful run diagnostics/workspaces can be removed as before.
- Artifact configuration changes do not move or delete existing artifacts.

### Interfaces / Contracts

- Operator TOML requires exactly four nonempty fields: `repository`, `model`, `agent_image`, and `artifacts_dir`.
- Preserve the existing repository and exact Copilot model semantics. `agent_image` selects the shared local image; `artifacts_dir` selects the operator-owned diagnostic root.
- Resolve relative artifact paths against the TOML directory. Configuration contains no credentials.
- Reject old `compose_file`/`compose_service` configurations with actionable migration guidance; do not convert or reinterpret them automatically.
- Require executable, noninteractive `./scripts/setup` and `./scripts/verify`; verification remains aligned with target CI.
- Tests use explicit service addresses through the target's test configuration: Compose DNS after the agent joins the appropriate network, or the Docker host address for published ports. No transparent localhost forwarding is required.

### Operations / Deployment

- Connect the agent to the existing local host Docker engine and mount the workspace at the same absolute host/container path.
- Fixed-identity deployment supersedes the earlier arbitrary-host-user correction: use account/group `factory`, UID/GID `2000:2000`, on both the Ubuntu host and shared agent image. Reject a mismatched or root runner identity before issue claims; do not switch accounts automatically. Provisioning must fail on name/ID conflicts rather than renumber existing accounts. The IDs are deployment constants, not new TOML fields.
- Build the agent account, home/caches, and sudo configuration into the image. Remove runtime account/shadow/group initialization. Ordinary setup, Pi, and verification run as the fixed non-root user; explicit `sudo -n` system installs retain root HOME selection. Do not elevate whole phases, retry permission failures as root, or grant the host factory account general passwordless sudo. Docker access/elevation remain effective engine/host control, not isolation.
- Discover the selected local Docker socket's numeric group and supply it with `--group-add` when creating the agent. Verify supplementary-group access through the actual `docker exec` path before relying on the mechanism. Do not change socket permissions or retain account-mutation/root fallbacks if the mechanism fails.
- Use Lima for a persistent local Ubuntu Server 24.04 LTS ARM64 VM with SSH access. Run the runner and Docker engine inside the VM and keep repository/workspaces/artifacts on its native Linux disk, not macOS shared folders. Keep VM configuration in the repository, disable unnecessary host-directory sharing, and use explicit host-to-guest service access. Installing Lima or provisioning hosts requires explicit operator action.
- Use one small explicit host provisioning entrypoint and runbook for the Lima VM. Acceptance uses the local VM only; no separate production-like host is required and no cloud validation is implied. Preserve the terminal runner; no systemd service, AMI pipeline, Terraform, or configuration-management framework is required. Keep gh/Pi authentication manual and private under the factory account.
- Remove recursive workspace ownership/permission restoration. Clean known owned resources before publication and fail visibly if the host cannot access required publication files. Preserve unchanged failed workspaces/private host-owned logs; deliberately inaccessible files require operator inspection. Do not require ignored caches to be writable or silently repair them. Service-private data belongs in disposable run-owned volumes; workspace-writing services need compatible ownership/permissions, not a blanket requirement to run every service as UID 2000.
- Host installation sources: Ubuntu signed APT repositories for Git, Make, sudo, curl, CA certificates, and build dependencies; Docker's official signed Ubuntu APT repository for Engine/CLI/Compose/buildx; GitHub CLI's official signed APT repository for gh. Verify availability and record exact APT versions before implementing provisioning; no automatic upgrade policy is established. Verify download checksums/signatures and their trust sources; if a selected release cannot be verified, return to the operator instead of silently substituting a version or source.
- Install host Python 3.14.3 from the checksum-verified official python.org source release, separately from Ubuntu's system Python. Use official ARM64 Node.js 22.19.0 binaries with checksum/signature verification and the official uv 0.5.13 release binary with checksum verification. Install `@earendil-works/pi-coding-agent@1.3.0` from npm under the factory account. No unversioned `curl | sh` installers or replacement of system Python; verify release availability and verification metadata before installation.
- The image baseline includes Pi, Node.js/npm, Docker CLI/Compose, Python/uv, Bash, Git, Make, a C/C++ build toolchain, curl, CA certificates, tar, unzip, and standard Linux utilities. Pin the image's base and installed tool versions in its build definition.
- Target-specific runtimes and browser binaries belong in target setup when required; do not install target prerequisites on the host or introduce a pre-setup Pi bootstrap. Explicit host provisioning installs only the factory's host prerequisites.
- Startup requires a compatible agent image already available locally and resolves it to an immutable image ID for the runner session. Missing/incompatible images fail startup; the runner does not build, pull, or fall back.
- Docker access grants effective engine control and potentially host control. The agent container is an execution environment, not a host-file or credential security boundary.

## Core Business Rules

- Use the immutable issue title/body snapshot and repository contents as task inputs, not issue comments, attachments, linked pages, or subsequent issue edits.
- Missing entrypoints or failed setup fails the issue run before implementation; do not guess replacement commands or add setup repair.
- A completed verification failure supplies feedback to Pi and permits at most three repairs after initial implementation. Setup, provider, lifecycle, and publication failures do not authorize verification repairs.
- Repairs never reset the deadline. Expiry stops work and fails the run; bounded cleanup must still be attempted.
- Passing verification and a nonempty diff are necessary for publication. Passing with no changes fails as `no changes produced`.
- Stop processes/services that could mutate the workspace and complete required cleanup before committing/publishing. Cleanup failure blocks publication and retains diagnostics.
- Commit/push/PR/reporting failures remain visible; do not claim success or blindly retry uncertain writes.
- Independent target CI and human review remain required; verification is not proof of requirement fulfillment.

## UX / Workflow Rules

1. The operator prepares target setup/verify scripts, builds the shared image, authenticates host GitHub CLI and Pi/Copilot, and supplies the new TOML configuration.
2. Startup validates configuration, local engine access, image availability/architecture, and execution prerequisites before claiming issues where possible.
3. Poll for `agent:implement`, applying the existing exact factory-PR/branch checks before execution.
4. Remove the trigger before execution or skip notification. Preserve a matching open PR and return its link; an existing factory branch without an open PR requires operator cleanup and label reapplication.
5. Claim a clear issue, record running status, snapshot its title/body, and create a fresh default-branch workspace and unique resource identity.
6. Start the agent container as the fixed `factory` UID/GID `2000:2000`, with same-path workspace mount, writable container home/caches, and local Docker access through the discovered socket group. Run setup, implementation, verification, and permitted repairs as that user under the shared deadline; system installs explicitly use `sudo -n`.
7. Clean owned resources, confirm host access required for publication without rewriting workspace ownership/modes, and publish passing nonempty changes through trusted host Git operations.
8. Record success with the draft PR link, or a concise failure with private local diagnostics. Never post full transcripts or secrets.
9. Failure, interruption, or restart never automatically requeues/resumes work. Explicit label reapplication starts a fresh snapshot/workspace, deadline, and repair allowance after duplicate checks.

## Data / State / Ownership Decisions

- Resource names/labels are cooperative ownership conventions, not access controls. Explicit project overrides, unlabeled Docker commands, or other contexts can bypass them.
- Record sufficient host-owned resource identity to clean known owned resources without executing agent-modified Compose teardown files/scripts on the host.
- Stop/remove owned containers before removing owned networks and disposable volumes. Never infer ownership merely because a resource is unused.
- Unknown/untracked resources require operator inspection, not broader deletion. Hard-crash cleanup remains manual.
- Preserve unrelated resources, checkouts, and previous failure diagnostics. Manual requeue does not erase old artifacts.
- Keep new run directories private (0700) and logs private (0600); known credential redaction remains required, but source/output may still be sensitive.
- Do not retain a successful-run image manifest or source snapshot for local tryouts. Existing PR source history is the operator's manual evaluation starting point.

## Interface / Contract Expectations

- Preserve terminal invocation and existing `repository`/`model` semantics; update only the approved configuration fields and execution wiring.
- Preserve `factory/issue-<number>` branch identity, exact configured head-repository matching, create-only remote publication, and draft PR bodies containing `Closes #<number>`.
- Never overwrite/delete remote factory branches. Uncertain publication requires inspection, not automatic retries.
- Keep trusted publication Git metadata and normal GitHub credentials outside the ordinary agent mounts/environment.
- Preserve exact-model Copilot invocation, stdin-only bearer delivery, validated endpoint metadata, temporary Pi configuration, nonpersistent sessions, and no billing-provider fallback.
- Normal mounts/environment remain limited despite Docker access being able to bypass those limits. Do not describe credential separation or trusted Git metadata as protection against a deliberately Docker-authorized agent.
- Setup, repository tooling, Pi, and verification execute inside the agent environment; host publication does not execute repository scripts or untrusted Git hooks/configuration.
- Update the accepted specification/contracts and standing safety instructions before production implementation changes these interfaces and guarantees.

## Operational / Deployment Constraints

- Use Ubuntu Server 24.04 LTS ARM64 for the Lima VM, with the fixed factory account. The shared agent image remains Debian-based; its distribution need not match the host.
- Verify native Linux workspace/sibling mounts, fixed ownership, actual socket supplementary-group access through exec, and agent-to-service networking in the VM. CI must execute runtime checks under the fixed identity; the hosted runner's default account is not assumed compatible.
- Require real local Docker evidence of image build, ordinary Compose startup, service-backed E2E verification, target-specific installation, and browser access from macOS to a fixture port exposed by the VM. Run migration acceptance in that local VM only; no separate EC2/equivalent repetition is required. Do not infer cloud storage/networking validation.
- Test cleanup after success, setup failure, exhausted repairs, timeout, interruption, and partial startup. Include an unrelated sentinel container/network/volume and verify preservation.
- Test cleanup failure blocking publication and preserve deadline, duplicate protection, credential handling, fresh manual requeue, and private retained-diagnostic behavior.
- Move Docker integration CI to ARM64 and retain existing format/lint/tests and the unchanged Python 80% coverage gate.
- Operator-approved Python Pi-wrapper replacement: use a standalone standard-library Python script instead of the JavaScript CLI wrapper, preserving invocation/credential behavior. Measure the wrapper in Python line/branch coverage; retire the Node-only coverage harness/gates because no production JavaScript remains. Node stays in the shared image for Pi and target tooling.
- A live Copilot request or GitHub-writing issue-to-PR demonstration requires separate explicit approval. Scripted boundaries and local Docker checks must not be presented as live acceptance.
- Remove superseded Compose validation, mount rewriting, configuration handling, fixtures, and tests as replacements land; preserve tests for unchanged behavior and useful existing credential/verification-feedback logic.
- Completion includes a removal audit: one execution path, no obsolete callers or compatibility backend, and current documentation describing the new trust model.

## Assumptions

- The operator accepts engine/host exposure from Docker-authorized untrusted task and repository execution.
- The operator supplies a trusted target, suitable setup/verify scripts, working local Docker, host Git/GitHub CLI/Pi authentication, and accessible Copilot model.
- The provisioned Linux host can run the required pinned tools and local Docker engine under the fixed factory identity. Same-path mounts and socket access must be demonstrated, not inferred from successful provisioning.
- Target setup can install nonbaseline tools within the shared 900-second budget. The factory does not promise arbitrary repositories work unchanged.
- Targets may require adaptation for architecture, explicit network addresses, fixed names/ports, external resources, and resource-label conventions.
- Earlier macOS desktop-provider evidence belongs to the previous host-user model. It does not prove the new Lima/provisioned-host identity, socket, networking, or cleanup behavior.
- Manually rebuilding/running a checked-out PR may differ from the agent's verified images, dependencies, data, or runtime configuration; exact reproduction is not required.

## Open Questions

- No unresolved choice among the four deployment decisions: distribution/architecture, account IDs, VM tool, and host installation sources are accepted. Exact Lima release/image pin, VM resources/network settings, APT package versions, release verification metadata, and Docker exec group behavior remain provisioning/verification work. Obtain operator agreement before installing tools, allocating the VM, or creating cloud resources. If feasibility checks contradict the accepted model, return to the operator rather than silently changing it.

## Ready for Spec Generation

- Status: yes
- Reason: The fixed-identity Linux deployment, Ubuntu/ARM64 baseline, `factory` UID/GID 2000:2000, Lima VM, installation sources/pins, preserved workflow/safety invariants, and validation boundaries are accepted. `$decision-to-spec` can update the affected specification without inventing these policies, followed by contract updates. SPEC/contracts define behavior and interfaces; only the current slice records implementation state, verification, and next steps.
