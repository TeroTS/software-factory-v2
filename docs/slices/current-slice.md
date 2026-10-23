# Current Slice

Status: done

## Slice Goal
- Let the operator submit a labeled issue and receive a linked draft PR containing sandbox-validated changes.

## Slice Boundary
- Actor: Operator.
- Trigger: An issue receives `agent:implement` while the configured local runner is running.
- Action: Submit the issue for unattended implementation.
- Visible outcome: A draft PR containing validated changes is linked from the issue.
- Authoritative state transition: Unclaimed labeled issue → GitHub-recorded successful issue run linked to a draft PR.
- One first-pass issue-to-PR outcome through terminal operation, GitHub coordination, a real Compose sandbox, Pi/Copilot implementation, repository verification, and host-side publication; include end-to-end success and automated safety/failure checks, without a UI or database.

## Stories In Scope
- `US-01 Turn a labeled issue into a validated draft PR`

## Stories Completed In This Slice
- `US-01 Turn a labeled issue into a validated draft PR`

## Stories Remaining In This Slice
- None.

## Contract Inputs
- `docs/contracts.md`, Contracts 1–6: terminal configuration, GitHub coordination, sandbox/Pi/Copilot isolation, setup/verification/deadline, trusted host publication, status/diagnostics/no automatic requeue.
- Contract 4's repair cycles remain US-02 work; Contract 6's successful manual-requeue acceptance flow remains US-03 work.

## Decision Inputs
- None.

## Shared State Required Now
- One trusted repository and operator-managed runner instance; no distributed lock or database.
- Immutable issue title/body and default-branch base commit, fresh workspace, one 900-second issue-run budget, and run-owned Compose resources.
- GitHub trigger label, exact factory branch/PR identity, concise status comments, and actual draft PR URL as durable coordination.
- Host-only GitHub credentials and private Copilot-only bearer; failed-run diagnostics are local, not recovery checkpoints.

## Operations / Endpoints / Surfaces In This Slice
- Contracted terminal entrypoint, strict four-field operator TOML, serial 30-second polling, exact duplicate/branch skips, confirmed claim, and immutable task snapshot.
- Prepared Compose setup → noninteractive Pi/Copilot → one verification, container cleanup, nonempty-diff gate, trusted host commit/create-only push, draft PR, and success/failure reporting.
- Target-owned agent assets: `../factory-smoke-test/sandbox/agent/`; ignored host configuration: `artifacts/operator/factory-smoke-test.toml`.
- No HTTP server, repair execution, automatic session resumption, merge, or review-driven revisions.
- The approved acceptance run processed issue 7 only; no normal polling service was left running.

## Tests Required
- Existing automated checks cover configuration, serial coordination, exact PR/branch identity, label-removal ordering, task snapshots, Compose/service isolation, private credentials, Pi invocation, setup/provider/verification/no-change/publication/reporting failures, deadline/interruption, local retention, and cleanup.
- Real Git/process/Docker checks cover trusted metadata and hook/filter isolation, non-overwrite publication, dependency-backed verification, failure exits, deadline termination, and cleanup.
- Live acceptance: `FACTORY_E2E_APPROVED=1 FACTORY_E2E_CONFIG="$PWD/artifacts/operator/factory-smoke-test.toml" FACTORY_E2E_ISSUE=7 uv run --frozen pytest tests/test_e2e.py -q -s` passed once in 72.83 seconds. Do not rerun against the existing PR; the test's duplicate guards intentionally reject that state.
- Initial harness-only failure: the first discovery poll returned no issue immediately after labeling; no claim, workspace, or implementation occurred. The harness now allows bounded 30-second discovery polling while the trigger remains present, never reapplies it after claim, and stops after a claimed failure. Five offline regression checks cover delayed discovery, an already queued issue, no automatic requeue/retry, bounded waiting, and unrelated queued-issue protection.
- Factory verification after the harness correction: `FACTORY_DOCKER_TESTS=1 FACTORY_E2E_APPROVED=0 ./scripts/verify` passed with 171 Python tests; three opt-in live checks were skipped in that repeatable suite. Python coverage: 97.15%; Node Pi bridge line/branch/function coverage: 100%. Reports: `coverage.xml`, `coverage.lcov`; both coverage gates enforce 80%.
- Factory application commit `38805c9` passed CI: https://github.com/TeroTS/software-factory-v2/actions/runs/40017443406. No production application code changed during live acceptance; the new harness regression tests and completion documentation still need commit/push and their own CI run.
- Draft PR head `2a008b2319866dc2e8d54aca0405742359791e0c` passed both independent target CI runs: https://github.com/TeroTS/factory-smoke-test/actions/runs/40019483495 and https://github.com/TeroTS/factory-smoke-test/actions/runs/40019477428. Target verification: 13 tests, 100% line/branch coverage.

## Not Now
- US-02: up to three verification repair cycles and recovery-to-PR acceptance.
- US-03: successful manual-requeue end-to-end demonstration; US-01 already prevents automatic requeue/resumption.
- Multiple repositories/runners, parallel runs, database/checkpoints, webhook/API/UI, automatic target preparation, merging, and review-driven revisions.
- Do not merge PR 8 or automatically begin another story; the human reviewer owns merge decisions.

## Done When
- All US-01 acceptance gates have automated coverage, the real issue-to-linked-draft-PR path passes, and verification/reporting/cleanup evidence is inspected.
- Independent target CI and factory application CI meet coverage policy; human review/merge remains external.

## Completion Summary
- Operator-approved [issue 7](https://github.com/TeroTS/factory-smoke-test/issues/7) produced [draft PR 8](https://github.com/TeroTS/factory-smoke-test/pull/8), branch `factory/issue-7`, head `2a008b2319866dc2e8d54aca0405742359791e0c`, from default-branch baseline `44a3e90`.
- One actual first-pass issue run implemented the optional `--name` readiness greeting, passed repository verification, and published only README/application/test changes. No repair attempt was used.
- The issue records [running](https://github.com/TeroTS/factory-smoke-test/issues/7#issuecomment-6374067424) and [success with the PR link](https://github.com/TeroTS/factory-smoke-test/issues/7#issuecomment-6374085419). The trigger label is absent; run-owned agent containers and the successful run directory were removed.
- PR inspection confirmed preserved default/callable behavior, named output, blank-name error handling, meaningful tests, and no verification/configuration changes. Independent CI is green. PR 8 remains open and draft; issue 7 remains open pending human review/merge.

## Next Slice Recommendation
- `US-02 Recover a verification failure through bounded repairs`.
- Keep `US-03 Manually requeue a failed or interrupted issue` in view; reuse the existing fresh-workspace, GitHub coordination, and shared-deadline invariants without implementing that follow-up now.
