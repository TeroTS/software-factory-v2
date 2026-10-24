# Current Slice

Status: done

## Slice Goal
- Let the operator receive a validated draft PR after the factory repairs an initial verification failure without intervention.

## Slice Boundary
- Actor: Operator.
- Trigger: Verification fails after the initial implementation of a submitted issue.
- Action: Let the factory repair the failed verification without intervention.
- Visible outcome: A draft PR is published after a permitted repair passes verification.
- Authoritative state transition: Running issue run with failed verification → GitHub-recorded successful issue run linked to a draft PR.
- One recovery-to-PR outcome in the existing issue run, including failure feedback to Pi, re-verification, publication, exhaustion checks, and shared-deadline checks.

## Stories In Scope
- `US-02 Recover a verification failure through bounded repairs`

## Stories Completed In This Slice
- `US-02 Recover a verification failure through bounded repairs`

## Stories Remaining In This Slice
- None.

## Contract Inputs
- `docs/contracts.md`, Contracts 3–4: immutable task and current workspace, failed verification feedback, nonpersistent Pi calls, at most three repair-and-verify cycles, one original 900-second deadline.
- `docs/contracts.md`, Contracts 1–2 and 5–6: preserve configuration, serial coordination, duplicate protection, isolation, publication, concise reporting, local diagnostics, and no automatic requeue.

## Decision Inputs
- None.

## Shared State Required Now
- Existing immutable issue snapshot, workspace, sandbox, Copilot-only bearer, and original issue-run deadline.
- Latest failed verification output and a bounded in-memory repair count; no new persistent recovery state or configuration.

## Operations / Endpoints / Surfaces In This Slice
- Existing runner verification/publication path, sandbox verification result handling, and noninteractive Pi repair prompt.
- Automated runner, Pi bridge, and real Docker verification/recovery tests; explicit opt-in live recovery-to-PR acceptance.
- Operator documentation describing repair limits and acceptance status.
- Operator-approved live acceptance processed dedicated issue 9 only: add `--repeat N`, with a temporary initial off-by-one defect requested in its immutable task snapshot. The actual first verification failure was formatting, before pytest; Pi repaired formatting and the temporary defect, and the next canonical verification passed. Issue body: ignored `artifacts/operator/us02-repair-issue.md`.
- Preflight passed against target `main` at `44a3e90e1ebb32909ff085ff6fdbd0902bf4915b`; no other trigger-labeled issues or factory runner were found. Existing PR 8 was open and non-draft and was left unchanged. No normal polling service was left running; US-03 was not started.

## Tests Required
- First-pass success still invokes no repairs.
- Recovery on any of the three permitted attempts stops at the first success, supplies the latest failed verification output and unchanged task snapshot, and preserves publication gates.
- Exactly three unsuccessful repairs fail visibly, retain diagnostics, and create no PR.
- Setup, provider, missing-entrypoint, sandbox, and publication failures do not become verification repairs.
- Deadline expiry during repair or re-verification prevents further work/publication; cleanup and retained diagnostics remain intact.
- Real Docker checks exercise failed verification feedback, repeated canonical verification, dependency-backed checks, deadline termination, and cleanup.
- Explicit real end-to-end acceptance: one operator-approved dedicated smoke-target issue must encounter a genuine initial verification failure, repair it with Pi/Copilot, pass verification, and produce a linked draft PR. Requires explicit approval for live GitHub/Copilot writes; do not rerun US-01 issue 7 / PR 8.
- Passed: `FACTORY_DOCKER_TESTS=1 FACTORY_E2E_APPROVED=0 FACTORY_COPILOT_TESTS=0 FACTORY_SMOKE_SANDBOX_TESTS=0 ./scripts/verify` — format/lint clean, 197 Python tests passed, 3 opt-in live checks skipped; Node bridge tests passed with 100% line/branch/function coverage. Both 80% gates remain unchanged.
- Python coverage is 97.11% versus the previous slice's recorded 97.15% (down 0.04 percentage points). Investigation: all new sandbox branches are covered; the bounded runner loop adds an unreachable normal-exhaustion branch because every final iteration either breaks on success or raises on failure. No coverage exclusions were added. Reports: `coverage.xml`, `coverage.lcov`.
- Real Docker recovery tests use a scripted agent and mocked GitHub/publication boundaries, not Pi/Copilot or remote writes. They passed success, exhaustion, deadline expiry during repair/re-verification, and cleanup. All test-owned containers were removed; an unrelated stopped Compose container was left untouched.
- The live harness supports `FACTORY_E2E_REQUIRE_REPAIR=1` and rejects first-pass success as US-02 evidence. Two offline regression checks prove this assertion.
- Passed live acceptance: `FACTORY_E2E_APPROVED=1 FACTORY_E2E_REQUIRE_REPAIR=1 FACTORY_E2E_CONFIG="$PWD/artifacts/operator/factory-smoke-test.toml" FACTORY_E2E_ISSUE=9 uv run --frozen pytest tests/test_e2e.py -q -s` — 1 passed in 115.63 seconds. A private local monitor copied the redacted run log before normal successful-run deletion; it did not replace or mock any runtime operation. Evidence: ignored `artifacts/operator/us02-issue-9/` (`acceptance.log`, `run.log`, `summary.json`, PR diff, and CI logs).
- Inspected real phase sequence: setup → initial implementation → canonical verification exit 2 (format check) → one Pi/Copilot repair → canonical verification exit 0 → sandbox cleanup → host commit/create-only push → draft PR → success comment. The repaired target passed 18 tests with 100% line/branch coverage.
- Independent target push CI passed: https://github.com/TeroTS/factory-smoke-test/actions/runs/40081442415. Independent target PR CI passed: https://github.com/TeroTS/factory-smoke-test/actions/runs/40081445595. Both verified head `f4971d235e7f273b61ab1601bf8ed2f965eb005d`, with 18 tests and 100% line/branch coverage.
- At live acceptance, factory changes were uncommitted/unpushed; no remote factory CI result was claimed. Local CI-equivalent verification is recorded above. The operator subsequently requested commit and push of the completed US-02 changes.

## Not Now
- US-03: successful manual-requeue end-to-end demonstration; no automatic requeue or session recovery.
- Additional repositories/runners, parallel runs, new configuration, databases/checkpoints, credential renewal, UI/API, automatic target preparation, merging, or review-driven revisions.
- US-01 is already complete (issue 7 → draft PR 8); do not modify or merge that PR.

## Done When
- Automated success, exhaustion, failure-classification, and shared-deadline checks pass with coverage gates intact.
- Real recovery-to-linked-draft-PR acceptance passes, with inspected failure/repair/verification logs, GitHub status, independent target CI, and container cleanup.
- Acceptance evidence is inspected; leave the draft PR for independent human review and do not begin another story automatically.

## Completion Summary
- Operator-approved [issue 9](https://github.com/TeroTS/factory-smoke-test/issues/9) produced [draft PR 10](https://github.com/TeroTS/factory-smoke-test/pull/10), branch `factory/issue-9`, head `f4971d235e7f273b61ab1601bf8ed2f965eb005d`, from baseline `44a3e90e1ebb32909ff085ff6fdbd0902bf4915b`.
- One real initial implementation failed canonical verification; one unattended repair received that failure output, corrected the changes, and passed the same verification command. No manual workspace intervention, session resumption, provider fallback, or extra issue run was used.
- The actual recovery trigger was a Ruff formatting failure; pytest did not run in that first verification. Do not describe this evidence as an observed off-by-one test failure. The final inspected diff fixes the temporary staged defect and adds the requested positive-integer flag, preserved default/callable behavior, invalid-input handling, documentation, and meaningful tests without modifying verification/configuration.
- The issue records [running](https://github.com/TeroTS/factory-smoke-test/issues/9#issuecomment-6382441630) and [success with the PR link](https://github.com/TeroTS/factory-smoke-test/issues/9#issuecomment-6382457159). The trigger label is absent; run-owned containers and the successful run directory were removed. An unrelated stopped Compose container was preserved.
- Both independent target CI runs are green. PR 10 remains open and draft; issue 9 remains open pending human review/merge. The operator subsequently authorized committing and pushing the factory source changes and completion documentation; this does not authorize merging the target PR.

## Next Slice Recommendation
- `US-03 Manually requeue a failed or interrupted issue` is the next explicit story in `SPEC.md`.
- Reuse fresh-workspace, new-snapshot, duplicate/branch checks, and per-run deadline/repair allowances; do not resume retained sessions or erase earlier failure artifacts. No additional explicit story follows US-03; do not start it without a new delivery request.
