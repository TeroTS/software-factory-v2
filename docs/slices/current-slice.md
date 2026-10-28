# Current Slice

Status: done

## Slice Goal
- Stop the deployed factory explicitly for maintenance while preserving interruption evidence and diagnostics.

## Slice Boundary
- US-05: On a maintenance request, the operator stops systemd through the existing interruption path; running becomes stopped, with bounded cleanup/failure evidence and no automatic requeue or resume.

## Stories In Scope
- US-05 Stop execution for maintenance.

## Stories Completed In This Slice
- US-05 Stop execution for maintenance.

## Stories Remaining In This Slice
- None.

## Contract Inputs
- None. SPEC.md US-05 defines stop behavior, recovery boundaries and real EC2 acceptance.

## Decision Inputs
- DECISIONS.md UX / Workflow and Operations / Deployment: prefer idle stops, preserve bounded interruption/cleanup and require explicit starts.

## Shared State Required Now
- EC2 i-0949d809e65004a73 is now stopped at the factory service level (instance remains running); selected deployment/configuration and credential metadata remain unchanged. Private startup log: /home/factory/.local/state/software-factory/start-6GrRTWYy/runner.log.

## Operations / Endpoints / Surfaces In This Slice
- Existing systemd stop helper, CLI signal handling, concise stop/recovery guidance and automated stop-path checks.

## Tests Required
- Targeted `uv run --frozen pytest tests/test_factory_service.py tests/test_cli.py tests/test_runner.py tests/test_failure_safety.py -q` passed (66): documented stop through scripted supervisor/Docker boundaries, invalid identity/stop errors, repeat stop, retained diagnostics, real process SIGTERM/exit 130 and existing cleanup/publication gates. Evidence: artifacts/us05-current/targeted.log.
- `./scripts/verify` passed (542 passed, 73 opt-in skips, 99.28% coverage; Ruff, CDK and shell syntax); 49 local links/anchors, 14 operator shell blocks and git diff --check passed. Existing Node/CDK warnings remain. Evidence: artifacts/us05-current/verify.log.
- After verifying AWS account 172318459814 and deployed helper/unit hashes, the documented EC2 stop passed: inactive/dead, Result=success, private runner_interrupted event, no factory container/native runner, and unchanged selection/configuration, credential metadata, retained log, networks/volumes. No issue was initiated; no run/cleanup failure was observed. Evidence: artifacts/us05-current/{before,stop,after}.json and acceptance.txt.
- Systemd briefly warned that launcher descendants remained at stop completion; follow-up inspection proved both PIDs absent. No forced removal or restart was used. Active-issue Docker E2E remains opt-in/unrun; live acceptance was an idle stop.

## Not Now
- Graceful draining, forced/broad resource deletion, automatic restart/requeue, live issue execution, new helpers or image/AMI changes unless an existing-path defect requires them.

## Done When
- Automated stop/failure checks and real EC2 stop acceptance pass; interruption/cleanup evidence remains available and recovery guidance makes uncertainty explicit.

## Completion Summary
- US-05 accepted: existing stop path verified, concise stop/recovery guidance added and factory service left stopped. No production code, image or AMI change was needed.

## Next Slice Recommendation
- No explicit next story remains in SPEC.md. Image updates or another start require a new explicit operator request.
