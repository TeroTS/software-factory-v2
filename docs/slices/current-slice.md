# Current Slice

Status: done

## Slice Goal
- Deploy and verify one prepared, stopped factory host on AWS.

## Slice Boundary
- US-01: Operator deploys the approved infrastructure and host preparation; undeployed infrastructure becomes a prepared EC2 host accessible through Session Manager, with retained storage and factory execution stopped.

## Stories In Scope
- US-01 Prepare a stopped EC2 factory host

## Stories Completed In This Slice
- US-01 Prepare a stopped EC2 factory host

## Stories Remaining In This Slice
- None.

## Contract Inputs
- None.

## Decision Inputs
- `DECISIONS.md`: approved live AWS deployment, profile/account, infrastructure, retained storage, and manual execution controls.

## Shared State Required Now
- CloudFormation stack and resource identities; encrypted retained volume; verified AWS account `172318459814` in `eu-central-1`.

## Operations / Endpoints / Surfaces In This Slice
- Repository-managed CloudFormation, existing host provisioning, and Session Manager administration; no inbound ports or runner startup.
- AWS STS verifies account `172318459814`. Stack `software-factory` is CREATE_COMPLETE: instance `i-067be56713e09d753`, volume `vol-0bf82c03e7a531517`, AZ `eu-central-1a`, Canonical AMI `ami-07a4d842baa6e2884`.
- The operator approved updating unavailable `gh=2.103.2` to `2.103.3`; a regression assertion failed before the pin update and passed afterward. Provisioning used base commit `a54e28d230548e0a386ab323ca11d9eca6456cb0` plus that uncommitted approved change, transferred as a checksum-verified source archive (SHA256 `41aa3cdbc338b0e15681e71a7401b0ddf0eb35ad3ed8ade54191c4785e6c9d52`). This is host bootstrap, not a US-02 release.
- Evidence: provisioning/check command `2a6ecb5d-8011-4baf-a4ac-8d9141d70ed6`, repeat-provision command `bec0f5fc-09de-4854-a712-dce8f373cabe`, and post-reboot acceptance `db8aa502-cdf9-40ec-a3fc-cc2c82f96c88` succeeded. Private host logs remain under `/var/tmp/factory-provision-*.log`; source/payloads remain under retained `bootstrap/` and local ignored `artifacts/deployment/`. AWS charges are accruing.

## Tests Required
- Basic infrastructure/security/storage checks, repository verification for changed code, and live AWS checks of Session Manager, provisioning, volume attachment, and stopped execution.
- Final `./scripts/verify`: format/lint passed; 461 passed, 73 skipped (opt-in Docker/image/Lima checks), 99.42% coverage. All 9 EC2 tests passed. AWS template validation, real no-inbound/IMDSv2 checks, Session Manager execution, repeated provisioning, and post-reboot readiness/mount/home-marker checks passed.

## Not Now
- US-02 release installation and US-03 startup; later health/stop/rollback stories, GitHub/Copilot enrollment, target issue execution, and graceful draining.

## Done When
- The approved profile resolves to the expected account; CloudFormation deploys the specified host/network/storage; Session Manager and real host checks demonstrate preparation without starting the factory.

## Completion Summary
- US-01 is live-verified: factory 2000:2000, pinned host tools including gh 2.103.3, native Docker/Compose, and encrypted retained home/Docker/containerd mounts survive a confirmed reboot. No runner execution or GitHub/Copilot credentials enrolled; no release/image deployed yet.

## Next Slice Recommendation
- US-02: install/select an exact committed release and build its shared image; keep US-03 explicit startup/manual enrollment and US-06 retained-release rollback in view without implementing them in that slice.
