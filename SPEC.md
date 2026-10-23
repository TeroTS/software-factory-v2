# Product Specification

Source: `DECISIONS.md`

## Summary
- A local autonomous coding factory turns labeled GitHub issues into implemented, validated draft PRs for human review. A Python local runner orchestrates Pi using an existing Copilot subscription, Docker Compose sandboxes, and host-side GitHub CLI operations. Domain names follow `CONTEXT.md`.
- The first target repository is `TeroTS/factory-smoke-test`. Feasibility evidence in `DECISIONS.md`: a minimal unattended Pi/Copilot Docker request passed without host GitHub write credentials. After operator-approved local preparation, the target's setup/verify passed in Compose in 2.72 seconds, with two tests and 100% line/branch coverage; image rebuild, validation, CLI execution, and cleanup totaled 9.60 seconds. Target preparation was merged into `main` at `6b5315e706831f5b1e6201d7cb4d0febe66d12fb`. The operator-prepared agent profile is owned by the local `factory-smoke-test` checkout under `sandbox/agent/`; operator `factory.toml` stays outside that checkout. The profile has passed setup, a real Pi/Copilot local coding probe, verification, and cleanup against that commit. These checks do not establish the full issue-to-PR flow.

## Goals
- Poll one trusted target repository every 30 seconds and execute one issue run at a time.
- Attempt every issue labeled `agent:implement`, without ticket classification, requirements triage, or clarification questions.
- Publish a draft PR only when repository verification passes and changes exist.
- Permit three repair attempts after the initial implementation, within one 15-minute issue-run deadline.
- Demonstrate a real issue-to-PR run and test failure, timeout, duplicate-protection, and manual-requeue behavior.
- Keep durable coordination in GitHub, without a database or automatic session recovery.
- Use automated tests and CI coverage of at least 80% for application code; exclude generated/framework boilerplate, not business logic.

## Non-Goals
- Multiple repositories, simultaneous runners, or parallel issue runs.
- A separate authorization/eligibility gate, issue refinement, or interactive agent conversations.
- Automatic merging or PR revisions from review feedback.
- Webhooks, HTTP APIs, dashboards, chat UI, or OpenHands Canvas.
- LangGraph, OpenHands, PostgreSQL, a GitHub App, or separately billed model APIs.
- Automatic target-repository hardening, sandbox preparation, or interrupted-session resumption.
- Using issue comments, attachments, or linked pages as task inputs.

## User Stories

### US-01: Turn a labeled issue into a validated draft PR
Primary actor: Operator

Trigger: An issue receives `agent:implement` while the configured local runner is running.

Happy-path action: Submit the issue for unattended implementation.

Visible outcome: A draft PR containing validated changes is linked from the issue.

Authoritative state transition: Unclaimed labeled issue → GitHub-recorded successful issue run linked to a draft PR.

Slice boundary: One first-pass issue-to-PR outcome through terminal operation, GitHub coordination, a real Compose sandbox, Pi/Copilot implementation, repository verification, and host-side publication. Include an end-to-end success demonstration and automated checks of its safety and failure gates; no separate UI or database.

Acceptance criteria:
- With the runner configured and authenticated for one trusted target repository, a poll discovers the labeled issue and starts no concurrent issue run. Only one runner instance may operate on that repository; labels are not a distributed lock.
- Before implementation, detect an open PR by exact head repository and head branch `factory/issue-<number>`. If found, remove `agent:implement`, skip execution, preserve the PR, and comment with its link. Do not use PR-body text for duplicate detection; other branch names are outside detection.
- If that remote factory branch exists without a matching open PR, remove `agent:implement`, skip execution, and request operator branch deletion before retrying. Never overwrite or force-push the branch. After either skip, another check requires explicit label reapplication; subsequent polls do not repeat the notification without it.
- Claim the issue by removing `agent:implement` and recording running status in GitHub. Snapshot its title/body and start a fresh isolated workspace from the default branch. Later issue edits do not change this run's inputs.
- Pi receives the snapshot and repository contents, attempts the work regardless of issue type or ambiguity, and asks no clarification questions. Do not retrieve issue-thread, attachment, or linked-page context.
- Use an operator-prepared repository-specific Compose environment, including required databases or other local services. Execute repository setup, agent commands, and verification inside the sandbox, not on the host.
- Allow internet access for dependencies and Copilot, but expose no host directories beyond the run workspace, no host Docker socket, and no GitHub write credentials. Supply only Copilot-required credentials; host publication credentials and broader host Pi configuration remain outside the sandbox. Internet access retains an exfiltration risk.
- Require noninteractive, deterministic `./scripts/setup` and `./scripts/verify`, with verification matching CI and the repository's documented dependency-backed checks. Missing scripts, setup failure, sandbox failure, or unavailable Copilot access fail visibly; do not invent commands or switch billing providers.
- Run setup before implementation and verification after implementation. A nonzero verification exit is not success; repair recovery is specified in US-02.
- When verification passes with changes, commit and push `factory/issue-<number>`, open a draft PR containing `Closes #<number>`, and record success with its link. Do not claim success when commit, push, or PR creation fails.
- When verification passes without changes, fail with a `no changes produced` issue comment and no PR.
- Enforce one 15-minute wall-clock deadline for the complete issue run, including setup and implementation. Expiry stops execution and fails the run; do not publish unvalidated results or deliberately continue publication after expiry.
- For failures, record a concise issue summary and retain the failed workspace and logs locally until operator deletion. Do not post full transcripts or expose credentials in shared output. Publication/reporting errors must remain visible rather than being represented as success.
- Stop and remove run-owned containers on completion or operator stop. An interruption must not cause automatic restart; retained work is diagnostic, not a checkpoint for resumption.
- Independent CI and human review follow publication. Passing checks does not prove requirement fulfillment; the human reviewer owns merge decisions. The factory neither merges nor revises the PR from review comments.

Deferred follow-ups:
- US-02: Recover a verification failure through bounded repairs.
- US-03: Manually requeue a failed or interrupted issue.

### US-02: Recover a verification failure through bounded repairs
Primary actor: Operator

Trigger: Verification fails after the initial implementation of a submitted issue.

Happy-path action: Let the factory repair the failed verification without intervention.

Visible outcome: A draft PR is published after a permitted repair passes verification.

Authoritative state transition: Running issue run with failed verification → GitHub-recorded successful issue run linked to a draft PR.

Slice boundary: One recovery-to-PR outcome within the issue run established by US-01, including failure feedback to Pi, re-verification, and publication. Demonstrate recovery end to end and test exhaustion and shared-deadline behavior.

Acceptance criteria:
- Give Pi the failed verification output, let it repair the changes, and run the same `./scripts/verify` again. Do not require operator interaction.
- Permit at most three repair-and-verify cycles after the initial implementation; do not count the initial implementation as a repair attempt.
- Stop repairing at the first successful verification and publish only if changes exist, using all US-01 publication and isolation gates.
- If the third repair still fails verification, mark the issue run failed, post a concise failure summary, retain local failure artifacts, and create no PR.
- The original 15-minute deadline includes every repair and verification cycle; it never resets. Expiry fails the run even when repair attempts remain.
- Automated tests cover successful repair, exactly three unsuccessful repairs, and deadline expiry during recovery. Setup, provider, or publication failures do not silently consume extra repair cycles as if they were verification failures.

Deferred follow-ups:
- US-03: Manually requeue an issue after recovery fails or execution is interrupted.

### US-03: Manually requeue a failed or interrupted issue
Primary actor: Operator

Trigger: The operator reapplies `agent:implement` after failure or interruption.

Happy-path action: Request a fresh attempt after any required remote branch cleanup.

Visible outcome: A new issue run produces a validated draft PR without resuming the earlier agent session.

Authoritative state transition: Failed or interrupted issue awaiting manual requeue → GitHub-recorded successful fresh issue run linked to a draft PR.

Slice boundary: One operator-initiated retry-to-PR outcome using the existing polling and execution path. Include an end-to-end requeue demonstration and automated checks that restarting the runner alone does not resume interrupted work.

Acceptance criteria:
- Failure, interruption, and runner restart do not automatically requeue the issue; explicit label reapplication is required.
- Requeue uses a new title/body snapshot and a fresh workspace from the current default branch. Do not resume the previous agent session or use its workspace as the new baseline.
- Apply US-01 duplicate and branch checks again, removing `agent:implement` when skipping. Preserve a matching open PR and return its link instead of executing. An existing remote branch without an open PR blocks execution until the operator deletes it and reapplies the label, including after a closed PR or an interrupted push/PR-creation step.
- A genuinely new issue run receives its own 15-minute deadline and up to three repair attempts, with all US-01 and US-02 safety, verification, reporting, and publication rules preserved.
- Previous failed-run artifacts remain local until operator deletion; requeue does not require a database or erase those artifacts.

Deferred follow-ups:
- None.

## Open Questions
- None. Target preparation is merged and the agent environment has passed a local coding/verification probe. Testing automatic credential renewal and demonstrating the full issue-to-PR flow remain delivery work; the completed probes do not prove those capabilities.
