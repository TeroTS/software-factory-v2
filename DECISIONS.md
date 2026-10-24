# Docker-enabled Autonomous Coding Factory Decisions

Status: Draft v1 — decisions accepted; implementation and acceptance evidence pending

## Problem Summary

Replace the prepared, target-specific Compose sandbox with one shared Linux agent image connected to the existing local Docker engine. A target repository should need ordinary setup/verify entrypoints and its application Compose configuration, not a factory-specific agent image or Compose definition. Preserve the existing issue-to-draft-PR workflow.

This record supersedes the previous execution-model decisions. It consolidates `docs/plans/docker-enabled-agent.md` and the operator interview. In particular, exact-image local tryouts proposed in that plan are excluded. Existing `SPEC.md`, contracts, and implementation still describe the old model and require subsequent updates; this interview does not change them.

## Goals and Success Criteria

- Build images, start ordinary target Compose services, and execute service-backed E2E checks from the shared agent environment.
- Support native `linux/arm64` locally, including an Apple Silicon Mac using a local Linux-container Docker provider.
- Eliminate target-specific factory sandbox preparation and retain exactly one execution path.
- Preserve serial issue processing, the 900-second issue-run deadline, three verification repairs, host-side publication, duplicate protection, and fresh manual requeue.
- Demonstrate same-path workspace mounts, target-specific tool installation, explicit service networking, host-usable files, and scoped cleanup across success and failure paths.
- Pass the existing format/lint/test checks and unchanged Python and Node 80% coverage gates, with Docker integration CI exercising ARM64.

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
- A factory-managed VM, remote Docker engine, EC2/cloud deployment, or ECS Fargate support.
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
- Native `linux/arm64` is required for the agent and target application/dependency execution. Unsupported architectures fail visibly rather than silently invoking emulation.

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
- Run the agent as root so setup can install system packages. Files must remain readable/writable by the host operator after success and failure.
- The image baseline includes Pi, Node.js/npm, Docker CLI/Compose, Python/uv, Bash, Git, Make, a C/C++ build toolchain, curl, CA certificates, tar, unzip, and standard Linux utilities. Pin the image's base and installed tool versions in its build definition.
- Additional runtimes and browser binaries belong in target setup when required; do not introduce host-side tool installation or a new bootstrap phase.
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
6. Start the root agent container with the same-path workspace mount and local Docker access. Run setup, implementation, verification, and permitted repairs under the shared deadline.
7. Clean owned resources, ensure host-usable workspace files, and publish passing nonempty changes through trusted host Git operations.
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

- Support local native ARM64 Linux containers, including an Apple Silicon Mac with Docker Desktop/Rancher Desktop providing the engine/VM. No additional factory-managed VM is required.
- Verify desktop filesystem sharing, sibling relative bind mounts, root-created file ownership, socket access, and agent-to-service networking on the actual local provider. Linux CI does not substitute for those checks.
- Require real local Docker evidence of image build, ordinary Compose startup, service-backed E2E verification, target-specific installation, and browser access from macOS to a published application port.
- Test cleanup after success, setup failure, exhausted repairs, timeout, interruption, and partial startup. Include an unrelated sentinel container/network/volume and verify preservation.
- Test cleanup failure blocking publication and preserve deadline, duplicate protection, credential handling, fresh manual requeue, and private retained-diagnostic behavior.
- Move Docker integration CI to ARM64 and retain existing format/lint/tests and unchanged Python/Node 80% coverage gates.
- A live Copilot request or GitHub-writing issue-to-PR demonstration requires separate explicit approval. Scripted boundaries and local Docker checks must not be presented as live acceptance.
- Remove superseded Compose validation, mount rewriting, configuration handling, fixtures, and tests as replacements land; preserve tests for unchanged behavior and useful existing credential/verification-feedback logic.
- Completion includes a removal audit: one execution path, no obsolete callers or compatibility backend, and current documentation describing the new trust model.

## Assumptions

- The operator accepts engine/host exposure from Docker-authorized untrusted task and repository execution.
- The operator supplies a trusted target, suitable setup/verify scripts, working local Docker, host Git/GitHub CLI/Pi authentication, and accessible Copilot model.
- The local provider supports same-absolute-path workspace sharing; this remains to be demonstrated rather than assumed proven by engine availability.
- Target setup can install nonbaseline tools within the shared 900-second budget. The factory does not promise arbitrary repositories work unchanged.
- Targets may require adaptation for architecture, explicit network addresses, fixed names/ports, external resources, and resource-label conventions.
- The existing engine reported `linux/aarch64` during the interview. This alone is not evidence for mount, network, cleanup, image, or live coding acceptance.
- Manually rebuilding/running a checked-out PR may differ from the agent's verified images, dependencies, data, or runtime configuration; exact reproduction is not required.

## Open Questions

- None requiring additional product policy. Local feasibility demonstrations and exact tested build pins remain delivery/verification work, not established evidence. If those checks contradict the accepted model, return to the operator rather than silently changing it.

## Ready for Spec Generation

- Status: yes
- Reason: Scope, configuration migration, image lifecycle/baseline, setup ordering, root execution, ARM64 support, networking expectations, resource ownership/deletion, trust boundaries, manual local evaluation, and acceptance gates are explicit. `$decision-to-spec` can proceed without inventing policy. Production implementation and the required Docker/macOS demonstrations have not been performed by this interview.
