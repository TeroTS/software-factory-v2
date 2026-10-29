# Current Slice

Status: done

## Slice Goal
- Publish a reviewed ticket plan safely without queuing issues.

## Slice Boundary
- US-02: The operator previews and explicitly publishes a committed plan; GitHub holds a create-only backlog with known story-to-issue mappings.

## Stories In Scope
- US-02 Publish approved issues safely.

## Stories Completed In This Slice
- US-02 Publish approved issues safely.

## Stories Remaining In This Slice
- None.

## Contract Inputs
- `docs/contracts.md` Contracts 1–4.

## Decision Inputs
- None.

## Shared State Required Now
- Validated plan, committed source provenance, stable story identities and existing GitHub issues.

## Operations / Endpoints / Surfaces In This Slice
- `python -m software_factory.planning publish --plan PLAN [--dry-run]`.

## Tests Required
- `./scripts/verify`: 600 passed, 73 opt-in Docker skips, 95.77% coverage, CDK synthesis and shell checks passed. Coverage decreased from 99.18% because new publication boundary failure branches are not all exercised; new module coverage is 83%. CDK warned about Node 25 and expired AWS credentials.
- Scripted-boundary and subprocess tests cover preview, provenance, conflicts, repeat publication, partial writes and interruption; no live GitHub calls were made.

## Not Now
- US-03 runner eligibility and US-04 activation; live GitHub writes.

## Done When
- Preview is exact and read-only; explicit publication safely reports confirmed mappings or actionable failures without queuing or blind retries.

## Completion Summary
- Preview and explicitly publish committed plans with create-only GitHub reconciliation; publication does not queue work.

## Next Slice Recommendation
- US-03 Enforce execution eligibility; keep US-04 activation deferred.
