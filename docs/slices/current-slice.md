# Current Slice

Status: done

## Slice Goal
- Let the operator manually requeue a failed or interrupted issue and receive a validated draft PR from a fresh issue run.

## Slice Boundary
- Actor: Operator.
- Trigger: The operator reapplies `agent:implement` after failure or interruption.
- Action: Request a fresh attempt after any required remote branch cleanup.
- Visible outcome: A new issue run produces a validated draft PR without resuming the earlier agent session.
- Authoritative state transition: Failed or interrupted issue awaiting manual requeue → GitHub-recorded successful fresh issue run linked to a draft PR.
- One retry-to-PR outcome through the existing polling/execution path, including restart inactivity, fresh inputs/workspace, duplicate/branch checks, and retained diagnostics.

## Stories In Scope
- `US-03 Manually requeue a failed or interrupted issue`

## Stories Completed In This Slice
- `US-03 Manually requeue a failed or interrupted issue`

## Stories Remaining In This Slice
- None.

## Contract Inputs
- `docs/contracts.md`, Contracts 2 and 6: explicit trigger reapplication, fresh snapshot/workspace/budget, no session recovery, repeated duplicate/branch checks, retained failed artifacts.
- `docs/contracts.md`, Contracts 1 and 3–5: preserve serial execution, isolation, nonpersistent Pi calls, per-run 900-second deadline, three repair attempts, verification and create-only publication gates.

## Decision Inputs
- None.

## Shared State Required Now
- Existing GitHub trigger label, exact factory PR/branch identity, immutable per-run snapshot, fresh default-branch workspace, deadline, and repair count.
- Prior local failure artifacts are diagnostics only, never a source of executable recovery state. No new database, checkpoint, configuration, or session state.

## Operations / Endpoints / Surfaces In This Slice
- Existing runner polling, GitHub coordination, fresh checkout, sandbox execution, and publication path. No production-code changes were required.
- `tests/test_requeue.py` combines real local Git/command budgets with scripted agent and GitHub boundaries; two variants use real Compose setup/verification and cleanup.
- `tests/test_e2e.py` supports `FACTORY_E2E_REQUIRE_REQUEUE=1` plus `FACTORY_E2E_REQUEUE_FROM=<retained failed run directory>`. It requires prior failure evidence and an absent trigger before explicit reapplication, observes current issue/default-branch inputs in a different run directory, and checks retained diagnostics.
- Operator approved live US-03 acceptance in this session. Preflight passed against target `main` at `44a3e90e1ebb32909ff085ff6fdbd0902bf4915b`; no trigger-labeled issues or active factory runner were found. PRs 8 and 10 were open and non-draft at preflight (operator changes since their acceptance); they were left unchanged.
- The first monitor missed the active process, so dedicated issue 11 completed normally and produced draft PR 12 (`3f05dbbda98b58f69f3c51f7361c6e7db468f95b`). This is first-pass success, not US-03 evidence. Both target CI runs passed (40087114159 and 40087116303). The runner was stopped and that PR/branch were preserved, never requeued or deleted. The corrected monitor's child-process self-check passed before a second dedicated issue was created.

## Tests Required
- Failed and interrupted issues stay unqueued across polling and runner restart until explicit label reapplication.
- Requeue captures edited title/body, checks out the current default branch into a new workspace, starts a new 900-second budget and repair allowance, and preserves previous failure artifacts.
- Reapplied triggers repeat open-PR and orphan-branch checks, consume the trigger on skip, and do not repeat notifications without another reapplication. An orphan branch requires operator deletion plus label reapplication.
- Passed targeted checks: `FACTORY_DOCKER_TESTS=1 uv run --frozen pytest tests/test_requeue.py tests/test_runner.py tests/test_e2e_harness.py -q` — 57 passed, including real local Git plus real Compose failure/interruption-to-requeue cases. Earlier non-Docker run: 5 passed, 2 Docker cases skipped.
- Passed full CI-equivalent verification: `FACTORY_DOCKER_TESTS=1 FACTORY_E2E_APPROVED=0 FACTORY_COPILOT_TESTS=0 FACTORY_SMOKE_SANDBOX_TESTS=0 ./scripts/verify` — format/lint clean, 211 Python tests passed, 3 explicit-opt-in live checks skipped. Node bridge tests passed with 100% line/branch/function coverage; Python coverage 97.28% (up from US-02's recorded 97.11%). Both 80% gates are unchanged. Repeated after live acceptance/documentation updates with the same results (211 passed in 64.80 seconds; 3 live opt-in checks deliberately disabled in this repeat).
- Offline harness tests reject stale inputs, workspace reuse, modified logs, and missing prior failure evidence. Local scripted/mocked publication is not presented as live acceptance.
- Passed real interruption: issue 13's normal CLI run reached Pi implementation, then the operator's controller sent SIGTERM after five seconds. CLI exited 130; GitHub recorded `Failed: operator interruption`; trigger absent; no factory branch or PR; run-owned containers removed. Setup passed and implementation exited -9 in the retained log. Source had not changed before interruption; this was not a partially coded change.
- Passed real restart inactivity: CLI ran again for 35 seconds (longer than one poll interval), then stopped with SIGTERM/exit 130. No new run directory, comment, trigger, or retained-log change occurred. The operator then edited issue 13's title/body from `--uppercase` to `--lowercase` while it remained unqueued.
- Passed live requeue acceptance: `uv run --frozen python artifacts/operator/us03-requeue.py` — controller invoked `python -m pytest tests/test_e2e.py -q -s` with `FACTORY_E2E_APPROVED=1`, `FACTORY_E2E_REQUIRE_REQUEUE=1`, `FACTORY_E2E_REQUIRE_REPAIR=0`, issue 13, the operator TOML, and `FACTORY_E2E_REQUEUE_FROM=/Users/terosuhonen/omat/factory-smoke-test/sandbox/agent/artifacts/issue-13-bucn4klp`. Result: 1 passed in 87.59 seconds. Its read-only private monitor copied redacted run logs before successful-run deletion; no runtime operation or external service was replaced or mocked.
- Inspected real requeue sequence: explicit label reapplication → fresh claim/snapshot/default-branch checkout → Compose setup → Pi/Copilot implementation → canonical verification exit 0 → sandbox cleanup → host commit/create-only push → draft PR → issue success link. No repair was needed in the fresh run. Canonical target verification passed 8 tests with 100% line/branch coverage.
- Independent target push CI passed: https://github.com/TeroTS/factory-smoke-test/actions/runs/40087578087. Independent target PR CI passed: https://github.com/TeroTS/factory-smoke-test/actions/runs/40087580186. Both verified head `d985c291e19214d2d0431cb33c93cb12937bc40d`, with 8 tests and 100% line/branch coverage.
- Final cleanup inspection found no test-owned containers or active factory runner. The unrelated stopped `hh-application-v2-postgres-1` container was left untouched. No trigger-labeled issues remained.
- At live acceptance, factory changes were uncommitted/unpushed; no remote factory CI result was claimed. Full local CI-equivalent verification is recorded above. Live evidence and CI apply to the target PR, not a factory commit. The operator subsequently authorized committing and pushing the completed US-03 changes.

## Not Now
- Automatic retries/requeue, interrupted-session recovery, artifact deletion, branch deletion by the runner, configuration expansion, databases, parallel runners, credential renewal, additional targets, merging, and PR review revisions.
- US-01 (issue 7 → draft PR 8) and US-02 (issue 9 → draft PR 10 after one verification failure/repair) were already complete. Their detailed evidence is in completed slice git history and summarized in `README.md`; neither PR was modified or merged during this slice.
- No explicit story follows US-03 in `SPEC.md`; do not infer new delivery work.

## Done When
- Automated restart/requeue/freshness/duplicate/branch/retention checks and real dependency-backed checks pass with coverage gates intact.
- Real manual-requeue-to-linked-draft-PR acceptance passes with inspected GitHub state, independent target CI, and cleanup; leave merging to human review.

## Completion Summary
- Operator-approved [issue 13](https://github.com/TeroTS/factory-smoke-test/issues/13) produced [draft PR 14](https://github.com/TeroTS/factory-smoke-test/pull/14), branch `factory/issue-13`, head `d985c291e19214d2d0431cb33c93cb12937bc40d`, from baseline `44a3e90e1ebb32909ff085ff6fdbd0902bf4915b`.
- The first run was genuinely interrupted during Pi execution; restarting alone did nothing. Explicit manual requeue created a fresh run at `issue-13-n6hvahch`, used the edited `--lowercase` request, passed verification, and linked the draft PR without resuming the earlier workspace/session.
- Inspected diff contains only README, application code, and meaningful tests: preserved default output/no-argument callable behavior, the requested lowercase flag, invalid-input rejection (including the superseded uppercase flag), and documentation. Verification scripts, dependencies, coverage policy, and sandbox configuration were unchanged.
- The issue records [interruption failure](https://github.com/TeroTS/factory-smoke-test/issues/13#issuecomment-6383286716), [fresh running status](https://github.com/TeroTS/factory-smoke-test/issues/13#issuecomment-6383310539), and [success with the PR link](https://github.com/TeroTS/factory-smoke-test/issues/13#issuecomment-6383317119). The trigger is absent, successful workspace deleted, and prior failed workspace/log retained unchanged at `/Users/terosuhonen/omat/factory-smoke-test/sandbox/agent/artifacts/issue-13-bucn4klp` until operator deletion.
- Both target CI runs are green. PR 14 and incidental first-pass PR 12 remain open and draft for human review. No target branch deletion, PR closure/merge, or target default-branch update was performed. Subsequent authorization to commit/push the factory changes does not authorize merging either target PR.
- Private evidence is ignored under `artifacts/operator/us03-issue-13/`: interruption/restart logs and summary, acceptance log/result, copied redacted requeue log, PR diff, final GitHub state/comments, head-matched CI results/logs, and `summary.json`. The initial unsuccessful interruption monitor's console is under `artifacts/operator/us03-issue-11/`.

## Next Slice Recommendation
- No explicit next story remains in `SPEC.md`; US-01, US-02, and US-03 are complete. Stop implementation unless the operator explicitly requests additional work.
