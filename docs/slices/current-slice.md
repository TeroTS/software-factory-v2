# Current Slice

Status: done

## Slice Goal
- Generate a reviewable local ticket plan without GitHub writes.

## Slice Boundary
- US-01: The operator uses repo-local planning skills to turn a spec into one validated JSON artifact, with one proposed issue per story and explicit dependencies.

## Stories In Scope
- US-01 Generate a reviewable ticket plan.

## Stories Completed In This Slice
- US-01 Generate a reviewable ticket plan.

## Stories Remaining In This Slice
- None.

## Contract Inputs
- `docs/contracts.md` Contracts 1 and 2 (local validation only).

## Decision Inputs
- None.

## Shared State Required Now
- Stable spec/story IDs, source provenance, narrative fields and dependency graph in the local plan.

## Operations / Endpoints / Surfaces In This Slice
- Repo-local planning skills, spec template and `python -m software_factory.planning validate --plan PLAN`.

## Tests Required
- `./scripts/verify`: 577 passed, 73 opt-in Docker skips, 99.18% coverage, CDK and shell checks passed. Coverage decreased from 99.28% because the new CLI's `__main__` is exercised in a subprocess, outside coverage collection.
- Local Markdown links and `git diff --check` passed. CDK warned about Node 25 and expired AWS credentials.
- Manual skill exercise by the current agent: `artifacts/us01-planning-check.5LX50H/` contains a two-story spec and validated draft plan with correct identities/dependency; no GitHub calls were made. A second spec was flagged for missing dependencies, vague scope and missing verification; no plan was created for it. `uv run --frozen pytest tests/test_planning.py -q`: 35 passed.
- A separate automated agent-generation test was declined; the skill-generation exercise above was manual. `./scripts/verify` was not rerun at the user's request.

## Not Now
- US-02 publication, US-03 runner eligibility and US-04 activation.

## Done When
- Operator can generate and validate the authoritative plan locally; malformed plans fail without writes, and the focused generation exercise passes.

## Completion Summary
- Repo-local planning skills and spec template produce a reviewable local plan; the validator rejects malformed plans and dependency graphs without GitHub writes.

## Next Slice Recommendation
- US-02 Publish approved issues safely; keep US-03 eligibility and US-04 activation deferred.
