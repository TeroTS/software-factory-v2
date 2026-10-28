# Current Slice

Status: complete

## Slice Goal
- Prepare a stopped EC2 factory host from a separately baked, tested private AMI.

## Slice Boundary
- US-01: Operator bakes/selects a private AMI and deploys CloudFormation; infrastructure becomes a prepared SSM-accessible host with retained storage and factory execution stopped. Live host acceptance, not stack creation alone, establishes completion.

## Stories In Scope
- US-01 Prepare a stopped EC2 factory host (approved AMI revision).

## Stories Completed In This Slice
- US-01 Prepare a stopped EC2 factory host (approved AMI revision).

## Stories Remaining In This Slice

## Contract Inputs
- SPEC.md US-01/US-02/US-03: persistent shared networking with separate builder/operational consumers, container-only runner/agent, private retained state, fixed /home/factory/artifacts and three-field TOML. No generated contracts.

## Decision Inputs
- DECISIONS.md Interfaces / Contracts and Operations / Deployment: explicit AWS CLI AMI capture, independent AMI/snapshot lifecycle, baked helpers, storage-first boot and explicit replacement/start.

## Shared State Required Now
- AMI identity/provenance, exact stack volume ID, factory 2000:2000, retained home/Docker state and independently selected container digests; no private state in the AMI.
- Operator deleted old volume/ECR images; the authorized clean deployment now has shared VPC vpc-094f5c157b4993b2d/subnet subnet-06726de96e4cd8f50 and operational host i-0949d809e65004a73 with new retained volume vol-0afa37da706f45fe9. Tested AMI/snapshot remain; fresh ECR repositories are empty. Prior US-03 uncommitted repository work is preserved.

## Operations / Endpoints / Surfaces In This Slice
- User authorized shared-network builder bake/finalization and deletion after operational deployment; no credential enrollment or factory execution was authorized.
- Approved refinement: persistent software-factory-shared owns VPC/subnet/gateway/routes; separate builder/factory consumers own their security groups and IAM roles. Destroy/recreate only the builder stack for a fresh instance/root disk each bake, preserving shared networking and AMIs/snapshots. Code/docs/tests, operational shared-network deployment and live builder lifecycle validation are complete.
- Implemented package/account installation versus boot storage/readiness split; bake generic host/service files, mask Docker/containerd during installation, enforce actual mount guards and supply only volume-specific boot settings. Repository shell files now live in infra/ec2/scripts/; the service unit stays in infra/ec2/. CDK/Makefile/tests use the relocated files; installed host paths are unchanged.
- Prerequisite alignment for the baked launcher: remove dynamic artifacts parsing container, fix same-path /home/factory/artifacts, reject removed TOML field and keep selected-agent validation in runner startup. Runner image rebuild/selection remains explicit.
- Reconcile SPEC/DECISIONS/AGENTS before code; update affected fixtures and operator procedure. Preserve signed-package/AWS installer rules and private-state modes; no automatic migration or artifact deletion.

## Tests Required
- Tests first for shared-network ownership/dependency direction, same-subnet/AZ placement, separate security/IAM and no custom AMI resource, exact baked files, source/parent provenance and UserData limits; builder failures must not select images.
- Execute shell code at privileged boundaries: masked package installation, clean finalization, exact-volume/mount safety and ordering, read-only readiness and no automatic factory execution.
- Three-field parsing/migration, fixed mount/single launcher container, selected-agent mismatch and existing failure/cleanup behavior; retain real container E2E paths.
- Run ./scripts/verify, shell syntax, Markdown links and git diff --check; never lower coverage. Real AWS bake/host/reboot/retained-volume tests and native Docker checks require the separate go-ahead/environment.
- Shared-network refinement: test-first ownership/dependency checks passed; targeted infrastructure/service tests 99 passed. ./scripts/verify passed (532 tests, 73 opt-in skips, 99.28% coverage; Ruff, all three CDK stacks and seven shell syntax checks); git diff --check and 31 local Markdown targets passed. Evidence: artifacts/shared-network/verify.log. CDK warned about Node 25, ambient credentials and default strong cross-stack references. No AWS migration or new-topology acceptance was performed; prior AWS evidence below validates baked host scripts only.
- Local verification passed after relocation: ./scripts/verify (531 passed, 73 opt-in Docker/image skips; 99.28% coverage, up from 99.25%), including Ruff format/lint, both CDK stacks and all seven shell syntax checks. Targeted infrastructure/service tests: 98 passed; git diff --check passed. Evidence: artifacts/base-ami/verify-scripts-move.log. Local Node 25/CDK and ambient-expired-credentials synthesis warnings remain; no AWS build/deployment or native Docker acceptance was performed.
- Implementation review found no blocking issues; rerun ./scripts/verify passed (531 tests, 73 opt-in skips, 99.28% coverage), git diff --check and 31 local Markdown targets passed. No native runner/agent image suite or live provider execution was performed.
- Authorized AWS acceptance passed on 2026-10-28: private AMI ami-04a85cd90740d9354, backing snapshot snap-0857f2ebab0d8bd30, Canonical parent ami-07a4d842baa6e2884, base revision 11f3adc plus reviewed working-tree files (hashes/patch retained). Builder i-0034c44aa30832005 finalized and stopped; Docker/containerd stayed masked during bake.
- Disposable hosts i-0f2da056867542bc1 and i-036d3c765fedb9afd passed SSM/first-boot readiness, fresh machine identity, factory 2000:2000/native Docker access, reboot, missing-volume engine blocking, conflicting-fstab rejection, and retained sentinel contents/private modes across fresh-instance replacement using scratch volume vol-0cd61b2c648f61a86. Factory execution stayed inactive/static. Evidence: artifacts/base-ami/acceptance-20261028/{builder-check,first-boot,reboot,missing,replacement,conflict}.json.
- Authorized cleanup on 2026-10-28: verified account/region and inactive factory/no running containers, inventoried deployed resources, deleted software-factory and software-factory-ami-builder (both DELETE_COMPLETE), terminated both acceptance hosts, and deleted scratch volume vol-0cd61b2c648f61a86. All four instances are terminated; both old VPCs and four root disks are absent. Evidence: artifacts/cleanup-20261028/.
- Subsequent operator deletion verified read-only: old volume vol-04a94116a9a0cde8e and both previous ECR repositories were absent; private ARM64 AMI ami-04a85cd90740d9354 remained available with completed snapshot snap-0857f2ebab0d8bd30.
- 2026-10-28 authorized clean deployment: software-factory-shared and software-factory CREATE_COMPLETE; read-only SSM/cloud-init/host-check passed on i-0949d809e65004a73, exact volume vol-0afa37da706f45fe9 mounted for home/Docker/containerd, factory 2000:2000/native Docker access, home 0700, service static/inactive and no containers. AWS read-back verified private tested AMI, shared subnet, IMDSv2, no inbound SG, encrypted attached 100 GiB gp3 volume in the subnet AZ, empty new ECR, and unchanged unrelated stacks. Baked script/unit hashes match the tested AMI. Evidence: artifacts/shared-network/deploy-20261028/.
- 2026-10-28 shared-network builder acceptance: freshly created i-0b47bc620ab62e357 used the shared subnet and a separate no-inbound security group, baked successfully with engines masked, finalized/stopped, and was removed with its disposable root disk by deleting only the builder stack. Read-back verified shared/factory stacks, host/volume, tested AMI/snapshot and unrelated stacks intact; SSM host readiness passed again with factory static/inactive. No new AMI was captured. Evidence: artifacts/shared-network/builder-acceptance-20261028/.
- Prior US-03 evidence: artifacts/us03/verify.log (523 passed, 73 opt-in skips, 99.25% coverage); artifacts/us03/final-install.json verifies the old loaded/static/inactive unit. Resume live US-03 acceptance only after operational AMI host preparation.

## Not Now
- US-03 live startup acceptance, US-04 health expansion, US-05 recovery expansion, enrollment, inference/target issues, scheduled builds/patching, automatic cleanup and rollback guarantees. Resume US-03 after AMI host preparation acceptance.

## Done When
- A tested private AMI deploys to an SSM-accessible, storage-ready stopped factory host; missing/conflicting storage fails closed, retained data survives test replacement and AMI/snapshot survive builder-stack destruction.
- Local checks and separately authorized real AWS acceptance pass; offline implementation alone does not complete US-01.

## Completion Summary
- US-01 accepted: shared-network builder lifecycle, tested private AMI, storage-first stopped factory host and required failure/retention checks passed. Existing AMI and snapshot survive builder deletion; no factory execution occurred.

## Next Slice Recommendation
- Resume US-03: explicitly publish/select runner and agent images and manually enroll credentials; separately authorize live startup after inspecting eligible issues and recovery state.
