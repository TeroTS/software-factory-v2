# SPEC-to-Tickets Workflow Decisions

Status: Accepted
## Problem Summary
Turn a committed target-repository SPEC.md into approved GitHub issues without duplicate publication or premature execution.
## Goals and Success Criteria
- Deliver four user stories: generate a reviewable plan; publish approved issues safely; enforce runner execution eligibility; explicitly queue the published backlog. Runner enforcement must precede queuing.
- Demonstrate safe repeat publication, partial-write reconciliation, dependency gating, and compatibility with handwritten issues.
## Primary Roles / Actors
- Operator: approves plans and requests publication/activation. Local runner: serially executes eligible issues using its existing App identity.
## Non-Goals
- Unattended planning, queuing without explicit operator approval, cross-repository publication, automatic issue updates, parallel execution, or multi-runner locking.
## Locked Decisions
### Product / Scope
- Use grill-me → decision-to-spec → spec-to-tickets; maintain all three operator-invoked skills under this repository's `.agents/skills/`, outside the execution image.
- Generate exactly one issue per US-xx story; return oversized or ambiguous stories for spec revision rather than splitting them during ticket generation.
### UX / Workflow
- Generate one authoritative local JSON plan; dry-run renders exact issue previews from a fixed template. Skills never publish directly.
- The operator reviews dry-run output, then explicitly publishes the current plan. Publication never applies agent:implement.
- After publication, explicit operator activation queues the entire published backlog with agent:implement, including blocked tickets; no per-story selection is required. The runner checks eligibility and can execute dependents after prerequisite merges without another activation.
### Data / State / Ownership
- SPEC.md and destination issues belong to the same GitHub repository. Publication requires a committed spec revision.
- Add stable `Spec ID` and per-story `Depends on` fields to the spec template; identity is `<spec-id>/<US-xx>`, independent of source revision.
- Record source repository, spec path, and full commit SHA in the plan and issues. GitHub remains durable coordination; no database is introduced.
### Interfaces / Contracts
- Define the JSON schema, issue metadata/template, and operator command contracts before implementation; preserve the existing runner entrypoint/configuration.
- Issue content covers stable identity, source revision, scope, acceptance criteria, verification, and explicit dependencies.
### Operations / Deployment
- Operator publication/activation uses the operator's authenticated gh identity, checked before writes; runtime API/Git authentication remains App-only.
- No deployment redesign or shared agent image change is required by this workflow.
## Core Business Rules
- Reject unknown dependency IDs, self-dependencies, and cycles; never infer or silently invent dependency edges during ticket generation.
- Publication is create-only: skip otherwise identical stories when only the source commit changes, retaining original issue provenance. Changed scope, acceptance criteria, verification, or dependencies is a conflict for operator review; never overwrite existing issues or duplicate them solely for a new revision.
- Reconcile partial publication using stable identities; never blindly retry uncertain issue-creation writes.
## UX / Workflow Rules
- A prerequisite is complete only when a PR explicitly closing its issue is merged into the target repository's default branch; closure or passing CI alone is insufficient.
- Silently skip valid blocked tickets, retaining their trigger label for reconsideration on later polls. Activation reports queuing results in the terminal. Invalid metadata or failed dependency lookups produce actionable errors and prevent execution. No routine blocked-ticket comments, notifications, or INFO events.
## Data / State / Ownership Decisions
- Preserve handwritten-issue behavior; generated tickets carry a dedicated label and embedded metadata. Either identifier triggers required metadata validation; missing/invalid metadata blocks execution. Repository editors are trusted: removing both identifiers makes a generated ticket indistinguishable from a handwritten issue.
## Interface / Contract Expectations
- Allow deliberate operator edits: the runner uses the current title/body snapshot and rechecks generated metadata/dependencies before claiming, including manually labeled tickets. Edited issues need not match the approved plan; conflicting republication reports rather than overwrites edits.
## Operational / Deployment Constraints
- Process labeled issues serially by ascending GitHub issue number; skip blocked tickets without preventing independent eligible work. Preserve the single-runner requirement and existing execution/publication safety gates.
## Assumptions
- Exactly one publisher operates per repository at a time; concurrent publication and distributed locking are out of scope. Stable spec/story IDs persist across revisions; each story includes relevant failure-path tests.
## Open Questions
- None at the product-policy level; exact schema, metadata, command, and reconciliation contracts remain to be defined before implementation.
## Ready for Spec Generation
- Status: yes
- Reason: product-policy questions are resolved; generate the four user stories above, then define contracts before implementation.
