# Product Specification

Source: [DECISIONS.md](DECISIONS.md). Canonical names: [CONTEXT.md](CONTEXT.md).
Spec ID: `spec-to-tickets`

## Summary
- Turn a target repository's spec into reviewed GitHub issues, explicitly queue the published backlog, and execute only tickets whose prerequisites are merged.

## Goals
- Provide operator-invoked planning, safe create-only publication, runner eligibility enforcement, and explicit whole-backlog activation.
- Preserve handwritten-issue behavior, serial execution, and existing execution/publication safety gates.
- Define the JSON plan, issue metadata/template, and command contracts before implementation.

## Non-Goals
- Unattended planning, queuing without explicit approval, cross-repository publication, automatic issue updates, parallel execution, or distributed locking.
- Deployment redesign, shared agent image changes, automatic merges, or changes to the existing runner entrypoint/configuration.

## User Stories

### US-01: Generate a reviewable ticket plan
Primary actor: Operator

Depends on: None.

Trigger: The operator requests a ticket plan from the target repository's SPEC.md.

Happy-path action: Generate one local JSON ticket plan through the repo-local planning skills.

Visible outcome: The operator can review proposed issues and their dependencies without creating anything on GitHub.

Authoritative state transition: No ticket plan → locally generated ticket plan ready for review.

Slice boundary: Operator planning through a validated JSON artifact, including repo-local skills, spec-template changes, and valid/invalid generation tests.

Acceptance criteria:
- `.agents/skills/` supplies grill-me → decision-to-spec → spec-to-tickets as operator tools, outside the shared agent image.
- The spec template includes a stable Spec ID, stable US-xx story IDs, and explicit Depends on fields; each story maps to exactly one proposed issue identified by `<spec-id>/<US-xx>`.
- The ticket plan records source repository, spec path/revision, scope, acceptance criteria, verification, and dependencies; publication requires a full committed source SHA under US-02.
- Reject unknown dependency IDs, self-dependencies, and cycles. Flag oversized or ambiguous stories for spec revision; never silently split them or invent dependencies/policy.
- The JSON artifact is authoritative for review and approval; planning skills do not publish issues or queue work.
- A focused test demonstrates spec-to-plan generation, stable identity, dependency validation, and absence of GitHub writes; relevant malformed-input cases are covered.

Deferred follow-ups:
- US-02 publishes the reviewed ticket plan.

### US-02: Publish approved issues safely
Primary actor: Operator

Depends on: US-01.

Trigger: The operator explicitly requests publication of a reviewed ticket plan.

Happy-path action: Publish the approved plan as a create-only GitHub backlog, reconciling existing or uncertain results by stable story identity.

Visible outcome: The operator can identify the published issue for each story without duplicate creation or automatic queuing.

Authoritative state transition: Reviewed ticket plan → published backlog with known story-to-issue mappings.

Slice boundary: Dry-run preview and explicit approval through GitHub issue creation/reconciliation, with scripted-boundary success, conflict, and partial-write tests.

Acceptance criteria:
- Dry-run renders the exact proposed issue content from a fixed template without writes. The operator reviews it, then explicitly publishes the current plan.
- Before writes, validate the operator's authenticated gh identity, the source's full committed SHA, and that SPEC.md belongs to the same GitHub repository receiving the issues.
- Issues include stable identity, source repository/path/SHA, scope, acceptance criteria, verification, and dependencies, plus a dedicated generated-ticket label and embedded planning metadata.
- Skip matching existing issues. If only the source commit changes and the story is otherwise identical, retain the existing issue and original provenance; changed scope, criteria, verification, or dependencies is a conflict for operator review.
- Never overwrite existing issues. Reconcile interrupted/uncertain issue creation by stable identity; never blindly retry uncertain writes. Conflicting or unresolved outcomes require operator inspection.
- Publication never applies agent:implement. Exactly one publisher operates per repository; no distributed publication lock is required.
- A focused test demonstrates explicit publication after dry-run review; failure tests cover invalid plans/provenance, duplicate prevention, conflicts, and partial-publication reconciliation without blind retries.

Deferred follow-ups:
- US-03 enforces generated-ticket eligibility before US-04 exposes backlog activation.

### US-03: Enforce execution eligibility
Primary actor: Local runner

Depends on: US-02.

Trigger: A poll discovers an issue labeled agent:implement.

Happy-path action: Validate a generated ticket and its prerequisites before claiming it for serial execution.

Visible outcome: Eligible work can start while blocked tickets wait without preventing independent work.

Authoritative state transition: Eligible labeled issue → claimed issue run; blocked or invalid tickets do not enter an issue run.

Slice boundary: GitHub discovery and eligibility checks through the existing claim boundary, including edited-issue, blocked-work, API-failure, and handwritten-issue tests.

Acceptance criteria:
- Process labeled issues serially in ascending GitHub issue number. Skip valid blocked tickets silently, retain their trigger labels, and reconsider them on later polls without blocking independent eligible work.
- Either the dedicated generated-ticket label or embedded metadata identifies a generated ticket. Missing/invalid required metadata blocks execution and produces an actionable error, including for manually labeled tickets.
- A prerequisite is complete only when a PR explicitly closing its issue is merged into the target repository's default branch; issue closure, an open/draft PR, or passing CI alone is insufficient.
- Check prerequisites before claiming. Failed GitHub dependency lookups produce actionable errors and prevent the affected ticket's execution; they are not evidence of completion.
- Permit deliberate operator edits: use the current title/body snapshot and validate current metadata/dependencies. Edited issues need not match the originally approved plan.
- Preserve handwritten-issue behavior and runtime App-only API/Git authentication. Repository editors remain trusted: removing both generated identifiers makes a ticket indistinguishable from a handwritten issue.
- Preserve existing claim, execution, cleanup, and publication safety gates. No routine blocked-ticket comments, notifications, or INFO events are added.
- A focused test shows a lower-numbered blocked ticket being skipped while independent eligible work is claimed; tests also cover later eligibility after merge, malformed metadata, manual labeling, lookup failures, operator edits, and handwritten issues.

Deferred follow-ups:
- US-04 lets the operator explicitly queue the published backlog once this enforcement exists.

### US-04: Queue the published backlog
Primary actor: Operator

Depends on: US-03.

Trigger: The operator explicitly requests activation of the published backlog.

Happy-path action: Apply agent:implement to the published backlog, including tickets with unmet prerequisites.

Visible outcome: The backlog is queued without per-story selection; the terminal reports queuing results, and the runner determines execution eligibility.

Authoritative state transition: Published, unqueued backlog → labeled backlog authorized for serial execution.

Slice boundary: Explicit operator activation through GitHub label writes and terminal results, with blocked-ticket and label-write failure tests.

Acceptance criteria:
- Require an explicit operator request separate from publication; use the operator's authenticated gh identity, checked before writes.
- Queue the whole published backlog, not only currently eligible stories. Unmet prerequisites do not reject activation or require per-story selection.
- Report queuing results in the terminal. GitHub label-write failures must not be presented as confirmed success.
- Require US-03 enforcement before exposing this workflow: blocked tickets retain their labels and become eligible after prerequisite merges without another activation.
- Preserve the single-runner requirement, serial execution, and existing manual-requeue policy; backlog activation introduces no automatic retry after a claimed run fails or is interrupted.
- A focused test activates a backlog containing independent and blocked tickets, confirms the reported label results, and demonstrates that runner enforcement still prevents premature execution; cover relevant authorization and label-write failures.

Deferred follow-ups:
- None.

## Open Questions
- None at the product-policy level. Exact JSON schema, issue metadata/template, dependency representation, command interfaces, and reconciliation contracts must be defined before implementation.
