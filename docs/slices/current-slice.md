# Current Slice

Status: done

## Slice Goal
- Start the selected factory deployment explicitly and observe validated startup or a safe failure.

## Slice Boundary
- US-03: After checking eligible issues and recovery state, the operator explicitly starts the selected runner through systemd; successful startup changes the service from stopped to running and exposes startup evidence.

## Stories In Scope
- US-03 Explicitly start the selected deployment.

## Stories Completed In This Slice
- US-03 Explicitly start the selected deployment.

## Stories Remaining In This Slice

## Contract Inputs
- None. SPEC.md US-03 requires three-field TOML, fixed retained artifacts, manual credentials, fail-closed startup and no automatic restart.

## Decision Inputs
- DECISIONS.md Operations / Deployment: independent image selection, container-only runner, explicit start, private retained state and no automatic restart.

## Shared State Required Now
- Host i-0949d809e65004a73 and retained volume vol-0afa37da706f45fe9; baked static service and launcher, independently selected runner/agent digests, operator TOML, private App/Pi state and retained startup logs.
- Runner and agent version 2d35fed are published and selected by digest on the stopped host. Operator reports completing App/Pi enrollment and configuration; read-only host checks confirmed private file modes, repository TeroTS/factory-smoke-test, model gpt-6.1-sol and matching selected-agent reference.

## Operations / Endpoints / Surfaces In This Slice
- Existing baked `software-factory.service`, `factory-start-runner`, `factory-stop-runner`, runner startup validation and explicit-start operator procedure.
- User explicitly authorized live startup after read-only issue/recovery inspection; no live inference or issue run was initiated.

## Tests Required
- Service start/stop, selected-agent matching, private mounts/logs, signal/failure cases, TOML migration and fail-closed preflight; run `./scripts/verify` and `git diff --check`.
- Existing service/launcher and runner startup path inspected; targeted `uv run --frozen pytest tests/test_factory_service.py tests/test_cli.py tests/test_config.py tests/test_startup.py -q` passed (167). `./scripts/verify` passed (532 passed, 73 opt-in skips, 99.28% coverage; Ruff, CDK synthesis and shell syntax); `git diff --check` passed. Evidence: artifacts/us03-current/{targeted,verify}.log. Local Node 25/CDK warning persists.
- AWS account 172318459814 and native linux/arm64 local Docker engine verified. With approved version 2d35fed, `./scripts/publish-image` built/smoke-tested/pushed both images. Runner digest sha256:7d10e833bb9a5f24bdeaea1d927fdedcf94d8847813d5deb8e121fba720bc298; agent digest sha256:a17326455746b6eb293b8ba36add72dbbc373e4994b137965c2435fc1ae4b7ff. Stopped host pulled, validated and atomically selected both; read-back confirmed 0600 selection, no containers, inactive/static service and no persisted temporary ECR login. Evidence: artifacts/us03-current/publication/.
- An initial SSM wrapper incorrectly reported success despite no selection; read-back detected this. Reran the documented selection through stdin with failure propagation; verified the actual selected digests. Operator reports manual App/Pi enrollment; read-only SSM confirmed required files/modes and TOML/agent match without reading credentials; service remains inactive/static with no containers. Evidence: artifacts/us03-current/enrollment/check.json.
- User-authorized GitHub App read-only inspection found zero open trigger-labeled issues, seven factory branches and one open factory PR (#19 for issue 18); local inventory found no factory-named containers, networks, volumes or retained run/start directories. Evidence: artifacts/us03-current/recovery-inspection/{github,local}.json. A second pre-start inspection again found no eligible issues.
- User-authorized EC2 startup passed: systemd active/running, selected runner image and 2000:2000 identity confirmed, required mounts/permissions verified, private `runner_polling` and `poll_started` events observed with no polling error at inspection. Private startup log: /home/factory/.local/state/software-factory/start-6GrRTWYy/runner.log; evidence: artifacts/us03-current/live-start/{recheck,start,verify}.json. Runner remains active and will process newly labeled issues; inference and an issue run were not tested.

## Not Now
- US-04 health expansion, US-05 recovery expansion, automatic enrollment, live inference/issue execution or automatic restart.

## Done When
- Automated checks and separately authorized real EC2 startup acceptance pass; startup is observable and existing execution invariants remain intact.

## Completion Summary
- US-03 accepted: explicitly started the selected runner on EC2 and observed successful startup validation and polling, with private diagnostics and no automatic restart.

## Next Slice Recommendation
- US-04 Inspect operational health; keep US-05 stop/recovery behavior in view.
