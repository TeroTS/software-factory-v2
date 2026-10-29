# Contracts

## Purpose

Define the non-HTTP boundaries for [SPEC.md](../SPEC.md) US-01–US-04 using [DECISIONS.md](../DECISIONS.md) and [canonical vocabulary](../CONTEXT.md).
These contracts define required behavior, not available commands. They do not change the existing runner CLI, TOML, App authentication, or execution safety gates.

## HTTP Contract Source

- None. GitHub API calls are external integrations, not a factory-hosted HTTP API.

## Non-HTTP Contract Inventory

### Contract 1: Ticket plan

- Kind: Versioned UTF-8 JSON file; one authoritative artifact, not a local coordination database.
- Producers / Owners: Operator-invoked `.agents/skills/grill-me`, `decision-to-spec`, and `spec-to-tickets`; only spec-to-tickets emits the ticket plan.
- Consumers: Operator review and deterministic validation/publication/activation tooling.
- Trigger / Direction: Target-repository SPEC.md → local ticket plan.
- Payload / Shape: Required fields are exactly those shown below; all objects reject duplicate or unknown keys and incorrect types.

```json
{
  "version": 1,
  "repository": "owner/repository",
  "spec_id": "checkout",
  "source": {"path": "SPEC.md", "commit": null},
  "stories": [
    {"id": "US-01", "title": "View checkout", "scope": "Show the current checkout.",
     "acceptance_criteria": ["The customer sees the current total."],
     "verification": ["Run the checkout behavior tests."], "depends_on": []}
  ]
}
```

- `version` is integer 1, not a boolean. `repository` is a GitHub.com owner/name with exactly two nonempty path segments, neither `.` nor `..`; confirm the returned repository full name before writes. Repository identity comparisons ignore case.
- `spec_id` matches `[a-z0-9]+(?:-[a-z0-9]+)*`. Story IDs are `US-` plus at least two digits representing a positive integer; IDs are unique within the plan.
- `source.path` is a repository-relative POSIX path without empty, `.` or `..` components. `source.commit` is null for a draft or a complete lowercase Git object ID (40 or 64 hexadecimal digits); abbreviated revisions are invalid.
- `stories`, `acceptance_criteria`, and `verification` are nonempty arrays; narrative values and titles are nonempty strings. `depends_on` is an array of unique story IDs in this same plan; reject unknown IDs, self-dependencies, and cycles.
- Narrative strings cannot contain the reserved metadata opener from Contract 3. Planning flags ambiguity or oversized stories for spec revision instead of inventing policy or splitting stories.
- Ordering / Idempotency expectations: Preserve array order. Publish prerequisites first, breaking ties by story ID; array order does not control runner priority.
- Visibility / Security: Plan content is untrusted repository/task data; never execute it or interpolate it into shell commands. Committing a plan is not required; committing its source spec is required for publication.
- Failure / Retry expectations: Invalid plans have no GitHub write effects. Draft plans can be validated locally but cannot be published or activated.

### Contract 2: Operator commands and results

- Kind: Separate Python module CLI, leaving `python -m software_factory --config ...` unchanged.
- Producers / Owners: Operator with this project's Python environment available; commands do not run target setup/verification code.
- Consumers: Terminal users and scripted-boundary tests.
- Trigger / Direction: Explicit invocation using the following command forms; PLAN supplies the repository, without runner TOML or deployment credentials.

```text
python -m software_factory.planning validate --plan PLAN
python -m software_factory.planning publish --plan PLAN --dry-run
python -m software_factory.planning publish --plan PLAN
python -m software_factory.planning activate --plan PLAN
```

- Payload / Shape: `validate` reports whether the plan is valid. `publish --dry-run` prints exact proposed issue titles, bodies, and generated labels; it performs reads only. Dry-run and publication require a committed source revision.
- `publish` without `--dry-run` is the operator's explicit approval to publish the current plan after reviewing its preview; revalidate the plan before writes. There is no separate approval state or interactive confirmation; publication never chains activation. Changes since preview are not automatically detected.
- Results identify each story, outcome, and confirmed issue number/URL where available. Outcomes distinguish existing/created issues, conflicts, queued/already-queued tickets, and uncertain writes; diagnostics never imply unknown success.
- Exit codes: 0 means the requested validation/preview completed or all requested writes are confirmed; 1 means validation, authorization, conflicts, remote failures, partial or uncertain results; 2 means invalid CLI usage; 130 means operator interruption.
- Ordering / Idempotency expectations: Publication follows Contract 4; activation follows Contract 6. Multiple writes are not atomic and completed writes are never rolled back.
- Visibility / Security: Operator GitHub calls use the authenticated gh identity, verified through GitHub's authenticated-user response, never factory App files. Use explicit GitHub.com repository endpoints, not ambient GH_REPO selection; never silently change the checked identity.
- Before writes, confirm the authenticated login and destination repository and report them to the operator. Supply request payloads on stdin; never echo credentials, raw API errors, or issue text in error diagnostics.
- Failure / Retry expectations: Stop on uncertain writes; report confirmed progress and the unresolved story/action. No automatic write retries or credential fallback.

### Contract 3: Generated-ticket issue template and metadata

- Kind: GitHub issue title/body plus dedicated `factory:generated` label, distinct from `agent:implement`.
- Producers / Owners: Publisher; repository editors may deliberately edit issues afterward.
- Consumers: Human reviewers, duplicate reconciliation, and runner eligibility checks.
- Trigger / Direction: One planned story → one GitHub issue with title `[<spec-id>/<story-id>] <title>`.
- Payload / Shape: Render the body in the following fixed section order, with LF line endings and a final newline.

```text
## Story
<spec-id>/<story-id>
## Source
<repository>:<source.path> at <source.commit>
## Scope
<scope>
## Acceptance criteria
- [ ] <one entry per criterion>
## Verification
- <one entry per verification instruction>
## Dependencies
- <spec-id>/<dependency-story-id>, or None.
<!-- software-factory:planning
<single JSON object described below>
-->
```

- Metadata fields: `version: 1`, `repository`, `spec_id`, `story_id`, `source: {path, commit}`, `depends_on: [story IDs]`. Types/validation follow Contract 1; published commit cannot be null. No issue numbers are embedded.
- Serialize metadata as one JSON line using `json.dumps(metadata, sort_keys=True)`, additionally escaping `<` and `>` as JSON Unicode escapes so strings cannot terminate the HTML comment.
- Dependency identities, rather than unknown future issue numbers, make previews exact and allow create-only publication without later body patching.
- The metadata object is authoritative for identity, provenance, and prerequisites; readable dependency text is explanatory. Operator dependency edits must update metadata. Current title/body remain execution inputs, not executable host instructions.
- Exactly one metadata block is required. Presence of either the generated label or reserved `<!-- software-factory:planning` opener triggers validation; missing/malformed/multiple blocks, unsupported versions, or repository mismatch fail closed.
- Ordering / Idempotency expectations: Identity is repository plus `<spec-id>/<story-id>`, independent of revision, title, labels, and issue state. No prefix, title-only, or text-search identity matching.
- Visibility / Security: These fields are public issue content, not secrets or signatures. Repository editors are trusted; removing both identifiers defeats generated-ticket recognition by design.
- Failure / Retry expectations: Never repair or overwrite existing issue content automatically. Metadata edits remain subject to runner validation and publication conflict checks.

### Contract 4: Publication and partial-publication reconciliation

- Kind: Create-only GitHub boundary, including exhaustive identity lookup.
- Producers / Owners: Exactly one operator publisher per repository at a time.
- Consumers: GitHub issues and the operator's confirmed story-to-issue results.
- Trigger / Direction: Explicit publication of a reviewed, valid committed plan → published backlog; no trigger labels are applied.
- Payload / Shape: Read the committed source path through the destination repository at the supplied full SHA; require a regular file and matching returned commit identity. The spec ID, story IDs, and declared dependency edges must match the plan; do not infer missing declarations. Failure to establish source provenance blocks writes.
- Preflight every story against paginated open and closed issues, excluding PRs, without relying on search-index freshness. Resolve identities from valid metadata; malformed generated candidates or duplicate identities are conflicts, not evidence of absence.
- One matching identity is reused only when title, rendered prose, and parsed metadata match, ignoring only metadata `source.commit` and the corresponding readable source revision. Ignore unrelated issue labels; preserve original provenance on reuse.
- Differences in title, scope, criteria, verification, dependencies, or other source identity fields are conflicts. Preflight conflicts block new issue writes; never overwrite, delete, reopen, or create a replacement issue for the same identity.
- Ordering / Idempotency expectations: Ensure the dedicated generated label exists, then create missing issues with that label and metadata in the same issue-create request. Process stories in prerequisite order; report confirmed existing/new mappings.
- Confirm creation only from a valid returned issue identity, positive integer number, same-repository GitHub issue URL, and expected title/body/generated label; invalid or incomplete responses are uncertain outcomes.
- A failed create, invalid response, or interruption may have succeeded remotely. Stop further writes; read-only reconciliation may establish one exact match. Zero matches after an uncertain write do not establish that it failed; multiple/conflicting matches require inspection.
- Visibility / Security: Use the operator identity and explicit destination; creation sends title/body/labels as JSON stdin. The issue label and metadata are coordination, not protection against repository editors.
- Failure / Retry expectations: Keep successful issues. Operator inspection must resolve prior uncertain writes before another publication attempt; do not infer retry permission merely from an absent lookup result. Local output is evidence, not resumable execution state.

### Contract 5: Runner eligibility and prerequisite evidence

- Kind: Fail-closed pre-claim GitHub checks; existing issue execution/publication remains unchanged afterward.
- Producers / Owners: Single local runner using the existing scoped App identity for all runtime API/Git access.
- Consumers: Existing claim/issue-run lifecycle.
- Trigger / Direction: Open issues labeled agent:implement → checked immutable title/body snapshot → claim only when eligible.
- Payload / Shape: Discover all pages, sort issue numbers ascending, and read current labels/title/body before the claim. Use the same checked title/body snapshot during execution; do not replace it with an unchecked later body.
- Neither generated identifier means handwritten behavior. Either identifier means Contract 3 validation, including current operator-edited metadata; no comparison with the originally approved plan is required for execution.
- Resolve prerequisite story identities to unique issues in the same repository/spec, including closed issues; validate the reachable dependency graph for unknown identities, self-edges, and cycles. Missing/duplicate identities or invalid referenced metadata are errors.
- For each direct prerequisite, require a GitHub-reported closing relationship to at least one merged PR whose base repository and base branch match the target repository and its currently discovered default branch. Branch naming or prose mentioning an issue is not sufficient evidence.
- Issue closure, PR approval, CI success, and unmerged or wrong-base PRs do not satisfy the prerequisite. Missing prerequisite merge evidence means blocked; API/decoding failures mean error, never completion.
- Ordering / Idempotency expectations: Blocked tickets keep their trigger labels and are reconsidered on later polls. Continue to independent eligible tickets; invoke the existing label-removal/claim path only after successful checks. No parallel issue runs.
- Visibility / Security: Valid blocked tickets produce no routine comments, notifications, or INFO events. Faults emit ERROR JSON Lines on stderr with `event: issue_eligibility_failed`, repository, issue number, and a safe reason; no raw body/metadata/API response.
- Failure / Retry expectations: Metadata/dependency errors do not claim or execute the affected ticket; preserve its label and continue to independent work. Later polls retry reads only; existing claimed-run failures still require manual requeue.

### Contract 6: Whole-backlog activation

- Kind: Explicit operator command adding the execution trigger; not an execution or dependency-completion operation.
- Producers / Owners: Operator's authenticated gh identity, after runner enforcement is deployed.
- Consumers: GitHub issue labels, terminal results, and the runner's next polls.
- Trigger / Direction: `activate --plan PLAN` → queue the published backlog represented by that plan, without story-ID selection.
- Payload / Shape: Resolve every planned story to one published issue using its stable identity; check current generated metadata and repository, allowing deliberate content/dependency edits. Missing, ambiguous, or invalid tickets block activation before label writes.
- Add agent:implement to every matched issue, including dependency-blocked tickets; do not wait for prerequisites to merge. Preserve all unrelated labels. Existing trigger labels count as already queued, not new writes.
- Ordering / Idempotency expectations: Apply labels by ascending issue number; confirm returned labels before reporting queued. Repeating an add does not duplicate a label, but repeating the command authorizes the backlog again and is not automatic recovery.
- Visibility / Security: Report each confirmed/uncertain label result in the terminal using story identity and issue number. Queuing authorizes every independent eligible ticket; it does not start parallel runs or merge PRs.
- Failure / Retry expectations: Stop on unconfirmed label writes and report partial results without rollback or blind retries. No background activation, automatic restart/requeue, or branch/PR cleanup is introduced; existing claim checks still apply.

## Slice Handoff

- Contract artifacts implementers must read: `docs/contracts.md`, alongside [SPEC.md](../SPEC.md) and [DECISIONS.md](../DECISIONS.md).
- Next step: `$lean-story-delivery`; when planning a slice, list this file under `## Contract Inputs` in `docs/slices/current-slice.md`.
- No OpenAPI, clients, runtime implementation, or live GitHub verification is required to produce these contracts.
