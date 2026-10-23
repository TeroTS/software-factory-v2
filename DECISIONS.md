# Autonomous Coding Factory Decisions

Status: Draft v1

## Problem Summary

Turn labeled GitHub issues into implemented, locally validated draft pull requests using an existing GitHub Copilot subscription. The MVP runs locally against one trusted repository; a human reviews every PR and decides whether to merge.

## Goals and Success Criteria

- While running locally, discover issues labeled `agent:implement` every 30 seconds and process one at a time.
- Attempt any labeled issue without issue-type classification, scope analysis, requirements triage, or clarification questions.
- Demonstrate one real issue progressing through sandboxed implementation and successful validation to a draft PR.
- Test repair exhaustion, the 15-minute run limit, missing setup/verify scripts, unchanged output, duplicate-PR detection, and manual requeue after interruption.
- Use the existing Copilot subscription; do not require a separately billed model API.

## Primary Roles / Actors

- Operator: the sole person applying the trigger label, preparing repository configuration, running the factory, and requeueing failures.
- Local runner: polls GitHub, manages execution and status, runs validation, and publishes results.
- Pi coding agent: implements the issue and repairs validation failures using Copilot.
- Human reviewer: reviews the draft PR, implementation, tests, and CI results; owns merge decisions.
- GitHub: stores issues, labels, status comments, branches, PRs, and independent CI results.

## Non-Goals

- Multiple repositories, parallel issue execution, or multiple simultaneous runners.
- Issue eligibility analysis, authorization gates, requirements refinement, or clarification conversations.
- Automatic merging or autonomous PR revision from review feedback.
- Webhooks, public HTTP endpoints, dashboards, chat UI, or OpenHands Canvas.
- LangGraph, OpenHands, PostgreSQL, or a GitHub App in the MVP.
- Automatic checkpoint recovery or resumption of interrupted agent sessions.
- Automatic hardening or sandbox preparation of target repositories.
- Reading issue comments, attachments, or linked pages as task inputs.

## Locked Decisions

### Product / Scope

- One trusted repository, one operator applying labels, one issue executing at a time.
- The first target repository is `TeroTS/factory-smoke-test` (`https://github.com/TeroTS/factory-smoke-test`).
- Every labeled issue is attempted regardless of ticket type or apparent ambiguity.
- Passing repository validation plus a nonempty diff permits draft-PR publication; a human judges requirement fulfillment.
- Up to three repair attempts follow the initial implementation attempt.
- The complete issue run has a 15-minute wall-clock limit, including setup, implementation, and repairs.

### UX / Workflow

- A terminal-only runner polls every 30 seconds while running.
- GitHub issues and draft PRs are the user interface; Pi runs unattended.
- Claiming an issue removes `agent:implement` and records running status in GitHub.
- Failures and interruptions require manual requeue by reapplying `agent:implement`.
- When skipping because a matching open PR or existing remote factory branch is found, remove `agent:implement` and comment with the PR link or required branch cleanup. Another check requires explicit label reapplication.
- No automatic merge and no automatic follow-up work on PR review comments.

### Data / State / Ownership

- No database. Use GitHub labels/comments for progress and existing PRs/branches for duplicate protection.
- Snapshot the issue title and body at run start; later edits affect only a new run.
- Give the agent that snapshot and repository contents, not issue-thread or linked-page context.
- Retain failed-run workspaces and logs locally until the operator deletes them.
- Always stop and remove run-owned sandbox containers when the run finishes or is stopped.

### Interfaces / Contracts

- A Python runner orchestrates Pi and Docker Compose; no orchestration framework is required.
- Development uses Python 3.14 with uv, Ruff for formatting/linting, and pytest with pytest-cov for tests/coverage (operator-approved during environment bootstrap).
- Pi uses the existing GitHub Copilot subscription.
- Host-side GitHub CLI authentication handles issue access, Git publication, comments, and PR creation.
- Target repositories must already provide `./scripts/setup` and `./scripts/verify`, as defined by the Codex CLI Repo Hardening skill.
- A prepared repository-specific Docker Compose environment must support those commands and any required dependency services.
- Use branch `factory/issue-<number>` and include `Closes #<number>` in the PR body.

### Operations / Deployment

- Run locally; no hosted deployment or inbound network endpoint.
- Execute agent work, setup, and verification in the sandbox, not directly on the host.
- Allow sandbox internet access for dependencies and Copilot.
- Expose no host directories beyond the run workspace, no host Docker socket, and no GitHub write credentials to the sandbox.
- Supply Pi only the credentials needed for Copilot; keep host GitHub CLI credentials separate.
- Fail rather than silently switching to a separately billed provider.

## Core Business Rules

- A missing setup or verification entrypoint fails the run; do not invent substitute commands.
- Run setup before implementation. Setup failure prevents normal implementation/validation progression and must be reported.
- After the initial implementation, run `./scripts/verify`.
- On verification failure, give the failure output to Pi and permit up to three repair-and-verify cycles.
- All repair cycles share the original 15-minute deadline; the deadline does not reset between attempts.
- Passing verification with a nonempty change set leads to commit, push, and draft-PR creation.
- Passing verification with no changes fails with a `no changes produced` issue comment; no PR.
- Exhausted repairs or the run deadline fails the run; stop execution, record failure, and notify through an issue comment.
- Do not publish unvalidated results as a PR.
- Publication errors must be reported rather than represented as successful completion.
- Independent CI and human review follow PR publication; local validation is not proof that all issue requirements were fulfilled.

## UX / Workflow Rules

1. Operator prepares a trusted repository's setup/verify scripts and Compose sandbox, authenticates GitHub CLI and Copilot, and starts the local runner.
2. Runner discovers a labeled issue and checks for an existing factory PR or remote branch.
3. If an open PR matches the configured head repository and exact head branch `factory/issue-<number>`, remove `agent:implement`, skip execution, and comment with its link.
4. If that remote branch exists without a matching open PR, remove `agent:implement`, skip execution, and request operator branch deletion before retrying. Never force-push or overwrite it. Reapply the label after cleanup to request another check.
5. Otherwise claim the issue, record running status, snapshot its title/body, and create an isolated workspace from the default branch.
6. Start the prepared sandbox, run setup, then let Pi implement the issue without a separate triage or clarification stage.
7. Run verification and bounded repairs under the shared deadline.
8. On success with changes, commit and push the factory branch, open a draft PR, and record success with its link.
9. On failure, post a concise summary and retain local failure artifacts. Do not post full transcripts to GitHub.
10. Stop/remove run-owned containers. An interrupted run does not automatically restart; the operator explicitly requeues it and resolves any existing remote branch first.

## Data / State / Ownership Decisions

- GitHub is the durable coordination surface; local artifacts are diagnostic data, not a recovery database.
- Only one runner instance may operate on the configured repository. Label updates are not a distributed locking mechanism.
- Only exact factory branch matches in the configured head repository count for duplicate detection; manually created PRs with other branch names are not detected.
- Fresh attempts start from the repository default branch, not from interrupted workspaces.
- Remote branch history is never rewritten. The operator owns branch deletion when cleanup is required.
- Failed workspaces and logs may contain private source code or sensitive output; keep them local and out of version control.
- The operator owns credentials, repository preparation, artifact deletion, review, and merge decisions.

## Interface / Contract Expectations

- The golden-path contract is `./scripts/setup` followed by `./scripts/verify`, both noninteractive and deterministic.
- Verification matches CI and covers the repository's documented checks, including real local dependency-backed tests where required by the hardening skill.
- Missing commands or nonzero exits must never be treated as successful verification.
- Repository configuration identifies the target repository and prepared Compose execution environment; the factory does not infer or provision an unknown runtime.
- Compose supports repositories requiring databases or other local services without giving agent code access to the host Docker socket.
- Issue inputs are the title/body snapshot plus repository contents. No implicit retrieval of referenced content.
- Draft PRs link the source issue through `Closes #<number>`; branch identity, not free-text searching, drives duplicate detection.
- No new HTTP API is required for the MVP.

## Operational / Deployment Constraints

- Concrete MVP architecture: local Python polling/control process → host GitHub CLI for GitHub operations → per-run Docker Compose sandbox containing Pi and repository tooling → existing Copilot subscription.
- The host controls sandbox lifecycle and publication; repository scripts and model-generated commands execute inside the sandbox.
- The factory must not depend on the operator's interactive Pi conversations or broader host agent configuration.
- Pin implementation dependencies and runtimes when bootstrapping; verify exact supported versions rather than guessing them in this decision record.
- The verified bootstrap pins Python 3.14.3 in `.python-version`, uv 0.5.13 in CI, and resolved development dependencies in `uv.lock`.
- The 15-minute limit is a deliberate execution limit, not an inference that stalled output means a timeout.
- Internet-enabled sandboxing carries residual exfiltration risk. Docker and human review do not make repository code or issue text trustworthy.
- A minimal unattended Pi 1.3.0/Copilot request passed in Docker in 3.18 seconds using `github-copilot/gpt-6.1-sol`. Only a host-resolved Copilot bearer with at least 20 minutes of remaining lifetime was passed through stdin; no host directories, GitHub CLI credentials, or GitHub OAuth refresh token were mounted or supplied. The supplied bearer received HTTP 401 from GitHub's `/user` API.
- The probe required `https://api.business.githubcopilot.com`, derived from the Copilot token's validated endpoint; the default individual endpoint returned HTTP 401. Do not assume all accounts use the individual endpoint.
- A preliminary Compose check of this bootstrap repository passed `./scripts/setup` and `./scripts/verify` with seven tests in 2.96 seconds from a fresh workspace, plus an 11.72-second cold image build. The environment needed executable `/tmp` tmpfs for temporary executable test stubs; repository code was unchanged. This does not establish feasibility for the first target repository.
- Initial inspection of `TeroTS/factory-smoke-test` at commit `8f5492ec85b50733f49795e819f5f5f2a8c9c325` found only four Markdown files and no required entrypoints. Compose preflight correctly failed with exit 2 in 4.24 seconds.
- With operator approval, the local `chore/smoke-test-environment` checkout now includes a minimal Python readiness CLI, two behavior tests, locked tooling, setup/verify scripts, CI, and a Compose verification environment. Both tests were observed failing before the application was added.
- The prepared target passed setup/verify in Compose in 2.72 seconds with 100% line and branch coverage. An uncached image-layer rebuild took 5.77 seconds with the base image already available; rebuild, verification, CLI execution, and cleanup totaled 9.60 seconds. No host GitHub credentials were passed; containers were removed. Evidence is under local ignored `artifacts/feasibility/target-probe/`.
- Target preparation is committed as `c6d5b76` and pushed to `TeroTS/factory-smoke-test` on `chore/smoke-test-environment`; remote `main` still requires that branch to be merged before the factory can clone and use it. The smoke target has no dependency services. These probes do not establish a full issue-to-PR coding run or automatic credential renewal.
- Factory behavior changes require automated tests; its CI must execute coverage with at least 80% overall coverage for this new project, excluding generated/framework boilerplate rather than business logic.

## Assumptions

- The target repository, default branch, selected Copilot model, and prepared Compose configuration are operator-supplied or GitHub-discoverable setup inputs, not additional product policies.
- Target repositories already comply with the referenced Codex CLI Repo Hardening skill, including documented commands and local dependency setup.
- The operator's machine provides working Python, Pi, GitHub CLI, and Docker Compose. Executable presence alone does not establish authentication or runtime health.
- Existing Copilot access permits the intended Pi workflow and has sufficient allowance; account-specific restrictions may block execution.
- The agent may reason about and implement the issue internally; the excluded analysis is a separate factory eligibility/requirements-analysis stage.

## Open Questions

- None currently. Target preparation must still be merged into its default branch, and end-to-end factory behavior remains to be implemented and tested.

## Ready for Spec Generation

- Status: yes
- Reason: Product scope, workflow, validation gates, retry/deadline behavior, duplicate protection, state ownership, interfaces, and safety boundaries are explicit. `$decision-to-spec` can proceed without inventing policy. Minimal Copilot authentication and the locally prepared target's Compose validation have passed feasibility checks. Merging target preparation and proving the full factory workflow remain delivery work, not unresolved product policy.
