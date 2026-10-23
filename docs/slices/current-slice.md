# Current Slice

Status: active

## Slice Goal
- Let the operator submit a labeled issue and receive a linked draft PR containing sandbox-validated changes.

## Slice Boundary
- Actor: Operator.
- Trigger: An issue receives `agent:implement` while the configured local runner is running.
- Action: Submit the issue for unattended implementation.
- Visible outcome: A draft PR containing validated changes is linked from the issue.
- Authoritative state transition: Unclaimed labeled issue → GitHub-recorded successful issue run linked to a draft PR.
- One first-pass issue-to-PR outcome through terminal operation, GitHub coordination, a real Compose sandbox, Pi/Copilot implementation, repository verification, and host-side publication. Include an end-to-end success demonstration and automated safety/failure checks; no separate UI or database.

## Stories In Scope
- `US-01 Turn a labeled issue into a validated draft PR`

## Stories Completed In This Slice

## Stories Remaining In This Slice
- `US-01 Turn a labeled issue into a validated draft PR`

## Contract Inputs
- `docs/contracts.md`, Contract 1: terminal invocation, four-field TOML configuration, startup validation.
- `docs/contracts.md`, Contract 2: discovery, exact PR/branch identity, claim ordering, immutable issue input.
- `docs/contracts.md`, Contract 3: Compose isolation, noninteractive Pi invocation, Copilot-only credentials, lifecycle.
- `docs/contracts.md`, Contract 4: setup/verification exit protocol and shared deadline; repair cycles are deferred to US-02.
- `docs/contracts.md`, Contract 5: trusted host-side publication, draft PR identity, uncertain-write handling.
- `docs/contracts.md`, Contract 6: status comments, local diagnostics, no automatic requeue/resumption; successful manual-requeue demonstration is deferred to US-03.

## Decision Inputs
- None.

## Shared State Required Now
- One trusted target repository and one operator-managed runner instance; no distributed lock or database.
- Immutable per-run issue number/title/body and resolved default-branch commit.
- GitHub trigger-label presence, exact factory branch/open PR identity, and human-readable status comments as durable coordination.
- Fresh isolated workspace, run-owned Compose resources, and one monotonic 900-second deadline covering workspace creation through publication.
- Host-only publication credentials; privately supplied Copilot-only bearer and validated endpoint.
- Local failed-run workspace/log locations retained until operator deletion, never used as recovery checkpoints.
- US-02 will reuse the workspace and deadline for bounded repairs; no repair counter or repair execution is needed in US-01.

## Operations / Endpoints / Surfaces In This Slice
- `uv run --frozen python -m software_factory --config /path/to/factory.toml`; make the module importable without changing this invocation.
- Validate operator configuration and resolved Compose isolation before claiming issues.
- Poll GitHub every 30 seconds, process one issue run at a time, and handle duplicate PR/branch skips.
- Claim, snapshot, create workspace, start sandbox, run setup, invoke Pi, and verify once.
- Fail on verification failure in this slice; do not implement repair recovery yet.
- Publish validated nonempty changes using trusted host-owned Git metadata, then comment with the actual draft PR URL.
- Report failures locally and in GitHub as available; retain private diagnostics; stop/remove run-owned containers on completion, expiry, or operator stop.
- No factory-owned HTTP endpoints.
- Implemented under `src/software_factory/`: editable terminal package, configuration validation, GitHub coordination, private command budgets/logs, separate host Git metadata, isolated Compose/Pi bridge, and first-pass orchestration. Operator documentation is in `README.md`; the architecture diagram now links implementation evidence.
- Operator preparation is complete locally: target `main` contains merged baseline preparation at `6b5315e706831f5b1e6201d7cb4d0febe66d12fb`. The agent Dockerfile, Compose file, and build-context ignore rules now belong to `../factory-smoke-test/sandbox/agent/`; the root verification environment there is unchanged. Operator configuration stays outside the target checkout at ignored `artifacts/operator/factory-smoke-test.toml`, pointing to the trusted target Compose file. Build-time RUN_UID/RUN_GID match the host workspace owner; no factory runtime auto-provisioning was added. The target ignores private `artifacts/` and excludes them from Docker build contexts.
- Immediate next step: commit/push the moved agent assets in the target repository and the factory documentation/test updates plus Docker-test user-mapping correction, confirm a new green CI run, select a dedicated issue, obtain approval for the live GitHub-write test, and inspect PR/status/cleanup evidence before reconciling all US-01 acceptance gates. Do not start normal polling or mark done based on the preparation probe.

## Tests Required
- Automated configuration tests: exact required fields/types, unknown fields, relative paths, missing tooling/files/services, and actionable startup failure before claim.
- GitHub coordination tests: 30-second polling, serial execution, exact head repository/branch matching, existing-branch skip, confirmed label removal, immutable snapshot, and failed reads/writes without unsafe progression.
- Isolation tests against resolved Compose configuration, including dependency services: reject extra host mounts, Docker socket, privileged/host-process access, and host credential/config exposure.
- Pi invocation tests: snapshot-only task inputs, coding tools available, discovered resources disabled, explicit Copilot model/endpoint, private bearer input, and no provider fallback.
- Failure-gate tests: missing scripts, setup/sandbox/provider failure, verification nonzero, empty diff, deadline expiry, operator stop, and commit/push/PR/reporting failures. Assert no false success or unvalidated publication, no force push, retained failure diagnostics, and attempted cleanup.
- Host-publication security tests: sandbox-authored Git configuration, hooks, helpers, and filters cannot execute on the host; issue content is never interpolated into host shell commands.
- Real local integration tests using Docker Compose and actual setup/verify scripts, process termination, and container cleanup; mocks alone are insufficient.
- Explicit real end-to-end test: operator labels a dedicated issue in `TeroTS/factory-smoke-test`, runs the configured runner with real GitHub, Compose, Pi/Copilot, observes passing repository verification and a draft PR linked from the issue, and confirms cleanup. Record issue/PR URLs and sanitized results, never credentials or full transcripts.
- Run `./scripts/verify` and `make coverage`; CI must execute coverage with at least 80% application coverage, excluding generated/framework boilerplate only.
- Verified locally: real Git checkout/commit/non-overwrite tests; process deadline/interruption tests; real Compose setup/verify/isolation/dependency-service/failure/cleanup tests; real isolated Pi 1.3.0/Copilot coding using `software-factory-pi-feasibility:local` and `gpt-6.1-sol`. The Pi probe wrote only a local test-workspace file; it is not a GitHub end-to-end success demonstration.
- Latest local relocation verification: `FACTORY_DOCKER_TESTS=1 FACTORY_SMOKE_SANDBOX_TESTS=1 ./scripts/verify` passed with 167 Python tests, 97.15% Python coverage, and 100% Node Pi-bridge line/branch/function coverage. The moved target profile's real Pi/Copilot probe ran; the separate older empty-workspace Copilot probe and full issue-to-PR test were skipped. The target's existing root Compose verification also passed two tests with 100% line/branch coverage. The rebuilt agent profile uses the target-owned Compose file through the ignored host TOML; the factory suite does not require that local configuration in CI. Both coverage gates enforce 80%; reports are `coverage.xml` and `coverage.lcov`. Native Node coverage was also verified on CI's pinned Node 22.19.0. The real Copilot test passed separately; the live issue-to-PR test remains unpassed. The later CI run for committed implementation `b3c867f` failed during Docker setup: https://github.com/TeroTS/software-factory-v2/actions/runs/40012393862. The test fixture now explicitly uses the host UID/GID; the correction still needs a fresh CI run after push.
- Read-only live GitHub checks confirmed default-branch discovery and exact factory-branch lookup. No live GitHub labels/comments/branches/PRs were written during implementation.
- Prepared-environment validation passed: `FACTORY_SMOKE_SANDBOX_TESTS=1 uv run --frozen pytest tests/test_smoke_environment.py -s`. Actual versions: Node 22.19.0, Python 3.14.3, uv 0.5.13, Pi 1.3.0. Target setup and verification passed before and after Pi wrote only `smoke-sandbox-probe.txt`; all run containers were removed. The target checks included two tests with 100% line/branch coverage. Image ID: `sha256:9d4f8cad863e07cbae7478ecf89581717e58589c58fa8d2c0b47259a5d567634`; sanitized local evidence: `artifacts/smoke-sandbox-validation/probe-43g3fzrc/result.json`. This was local preparation, with no issue processing or publication.
- Still unpassed: `tests/test_e2e.py`, requiring a dedicated open issue and explicit approval for GitHub labels/comments/branch/draft-PR writes. No operator prerequisite was silently bypassed.

## Not Now
- US-02: verification repair loops, three-attempt exhaustion, and recovery-to-PR demonstration.
- US-03: successful manual-requeue end-to-end demonstration. US-01 still requires no automatic restart/requeue and fresh workspaces.
- Multiple repositories/runners, parallel runs, database/checkpoints, webhook/API/UI, automatic merge, and review-driven revisions.
- Automatic target preparation by the running factory. The operator has merged the target preparation branch; this task prepared and tested a local agent profile separately, as authorized. The factory continues to require operator-prepared environments rather than generating them per issue.

## Done When
- All US-01 acceptance criteria in `SPEC.md` have corresponding passing checks, including isolation, duplicate protection, deadline, publication, reporting, and cleanup gates.
- The explicit real issue-to-linked-draft-PR end-to-end test passes with sandboxed setup, Pi/Copilot implementation, and verification; CI and human review remain independent.
- Failed verification produces a visible failed issue run, no PR, retained local artifacts, and cleanup, without repairs in this slice.
- Local verification and CI coverage meet the repository policy. Any unavailable real dependency or outstanding operator prerequisite keeps the slice unfinished, not marked done on mocked evidence.

## Completion Summary

## Next Slice Recommendation
