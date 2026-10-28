# Current Slice

Status: done

## Slice Goal
- Let the operator inspect deployed factory health without changing execution or GitHub state.

## Slice Boundary
- US-04: The operator follows a read-only service/log procedure to distinguish stopped, failed-startup and running states and locate progress/failure evidence; no authoritative state changes.

## Stories In Scope
- US-04 Inspect operational health.

## Stories Completed In This Slice
- US-04 Inspect operational health.

## Stories Remaining In This Slice
- None.

## Contract Inputs
- None. SPEC.md US-04 constrains the inspection procedure and evidence limits.

## Decision Inputs
- DECISIONS.md Operations / Deployment and UX / Workflow: private diagnostics, explicit starts and no live issue health probes.

## Shared State Required Now
- Existing systemd state, selected deployment digests, private per-start runner logs and retained issue-run diagnostics on EC2 i-0949d809e65004a73.

## Operations / Endpoints / Surfaces In This Slice
- Operator health procedure and executable documentation boundary tests; existing service and logging remain unchanged.

## Tests Required
- Execute documented commands against scripted read-only service/Docker boundaries and private log fixtures, including stopped, failed-startup, missing evidence and access failures.
- Verification passed: ./scripts/verify (Ruff format/lint, 541 passed, 73 opt-in skips, 99.28% coverage, CDK synthesis and shell syntax); git diff --check and affected documentation links passed. Existing Node 25/CDK warnings remain. Evidence: artifacts/us04-current/verify.log.
- Real read-only EC2 acceptance passed after verifying account 172318459814: service active/running with successful result; actual runner digest matches selection, both selected digests visible, current invocation's private log contains runner_polling and continuing poll_started events, with no error/run events in the inspected output. Evidence: artifacts/us04-current/{service,log}.json. No service changes, direct GitHub/Copilot probes or issue execution were initiated; the existing runner remains active.

## Not Now
- US-05 stop/recovery expansion, new health daemons/helpers, credential probes, inference or issue execution.

## Done When
- Automated procedure checks and real read-only EC2 service/log inspection pass; evidence limits and failure handling are documented.

## Completion Summary
- US-04 accepted: documented service/selection/log inspection distinguishes operational states and evidence limits; nine executable documentation tests cover read-only boundaries, failures and private evidence without new runtime helpers or an AMI update.

## Next Slice Recommendation
- US-05 Stop execution for maintenance; retain the existing bounded interruption/cleanup path and inspect uncertain publication before manual requeue.
