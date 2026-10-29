# Current Slice

Status: active

## Slice Goal
- Explicitly queue the entire published backlog for eligibility-controlled execution.

## Slice Boundary
- US-04: The operator activates a published backlog; confirmed issues receive the trigger label and terminal results.

## Stories In Scope
- US-04 Queue the published backlog.

## Stories Completed In This Slice

## Stories Remaining In This Slice
- US-04 Queue the published backlog.

## Contract Inputs
- `docs/contracts.md` Contracts 1–3, 5 and 6.

## Decision Inputs
- None.

## Shared State Required Now
- Valid committed ticket plan, published issue identities and current metadata/labels.

## Operations / Endpoints / Surfaces In This Slice
- Operator `python -m software_factory.planning activate --plan PLAN` and GitHub issue labels.

## Tests Required
- Scripted CLI activation and runner eligibility, authorization, invalid identities and uncertain label writes; `./scripts/verify`.

## Not Now
- Live GitHub/Copilot calls, automatic requeue and per-story activation.

## Done When
- All matched tickets, including blocked ones, are queued with confirmed results; failures stop safely.

## Completion Summary

## Next Slice Recommendation
