# Domain Vocabulary

Canonical names cover issue execution and the planning workflow accepted in [DECISIONS.md](DECISIONS.md).
Accepted decisions and specifications define behavior and interfaces; this file defines naming.

## Canonical Terms

### Autonomous coding factory

The local system that turns labeled GitHub issues into implemented, validated draft PRs for human review.

### Operator

The person who prepares the target repository, runs the factory, applies trigger labels, and handles manual requeue and cleanup.

### Target repository

The single trusted GitHub repository configured for the factory. It supplies the setup/verify entrypoints, application/dependency configuration, and tests used during issue runs.

### Issue

The GitHub work request attempted when labeled `agent:implement`. Its title and body are snapshotted at run start; comments, attachments, and linked pages are not task inputs.

### Local runner

The factory actor that polls for labeled issues, manages one issue run at a time, invokes the coding agent and verification, and publishes results.

### Issue run

One attempt to process an issue from claim to success or failure, including setup, initial implementation, and any repair attempts under one 15-minute deadline.

### Shared agent image

The factory-maintained, versioned Linux image providing Pi, instructions, skills, and baseline development tools across target repositories. The operator builds it or explicitly pulls it from ECR before starting the local runner; it is not a target application image. Its version is independent of the runner container, which supplies the bridge.

### Agent environment

The per-issue-run execution environment where setup, Pi implementation, verification, and repairs run. In the accepted Docker-enabled model, it uses the shared agent image and local Docker engine access; it is not a security boundary protecting the host.

### Run-owned resources

Docker containers, networks, and disposable volumes identified as belonging to one issue run by its unique Compose project or factory-provided run label. This identity scopes cooperative cleanup, not access control; shared images, build cache, and untracked resources are outside it.

### Repair attempt

One agent repair followed by verification after a verification failure. An issue run permits up to three repair attempts after the initial implementation.

### Factory branch

The branch `factory/issue-<number>` used to publish an issue's changes and detect an existing factory PR. Existing remote branches are never overwritten or force-pushed.

### Draft PR

The factory's reviewable result: a draft GitHub pull request containing changes that passed repository verification and linking the issue with `Closes #<number>`. It is not automatically merged.

### Human reviewer

The person who evaluates the draft PR, requirement fulfillment, tests, and CI results and decides whether to merge.

### Manual requeue

The operator's explicit reapplication of `agent:implement` after failure or interruption. It requests a fresh issue run, not resumption of the previous agent session; remote branch cleanup may be required first.

### User story

One independently demonstrable outcome in SPEC.md, identified by a stable `US-xx` within a stable spec ID. Each story maps to exactly one generated ticket.

### Ticket plan

The authoritative local JSON artifact mapping a committed spec revision to proposed issues and dependencies. The operator reviews dry-run output and explicitly requests publication of the current plan.

### Generated ticket

A GitHub issue published from a ticket plan for one user story, identified by `<spec-id>/<US-xx>`. It carries a dedicated label and planning metadata; it is not a separate work item from the issue.

### Planning metadata

The machine-readable section of a generated ticket recording story identity, source-spec provenance, and dependencies. The local runner validates it before claiming work; its exact format belongs in the contracts.

### Prerequisite

A story that must have a PR explicitly closing its issue merged into the target repository's default branch before a dependent ticket can execute. Closing the issue alone is insufficient.

### Published backlog

The generated tickets published from a ticket plan. Publication creates issues without queuing them; activation explicitly authorizes the backlog for execution.

### Activation

The operator's explicit action applying `agent:implement` to the published backlog, including blocked tickets. It queues work rather than starting it immediately; the local runner still checks prerequisites.

### Partial-publication reconciliation

Checking GitHub against stable story identities after interrupted or uncertain issue creation to establish what was published. Matching issues are reused; conflicts or unresolved outcomes require inspection rather than blind retries.
