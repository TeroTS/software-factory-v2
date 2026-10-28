# EC2 Factory Deployment Decisions

Status: Accepted planning baseline
## Problem Summary
Move the existing single-runner factory to a reproducibly prepared EC2 host with explicit independent runner/agent container publication and selection.

## Goals and Success Criteria
Repository-managed infrastructure, supervised operation, independently versioned images, and documented health checks, updates, and interruption handling.

## Primary Roles / Actors
The operator provisions infrastructure, enrolls credentials, deploys releases, starts/stops the service, and handles recovery; the existing factory executes issue runs.

## Non-Goals
No parallel workers, application deployment, CI publication, V1 rollback/old-image retention guarantees, compatibility negotiation, or graceful-draining implementation. GitHub App/Copilot credential enrollment and live issue execution remain manual, separately authorized steps.

## Locked Decisions
### Product / Scope
- Implement repository-managed CloudFormation, deployment scripts, systemd supervision, and operator procedures, and deploy incrementally to AWS now. The operator approved AWS resource creation, EC2 host preparation, and live AWS validation using profile `AWSAdministratorAccess-172318459814` in account `172318459814`; verify the authenticated account before creating resources.
### UX / Workflow
- Publish independently versioned runner OR agent images from the operator computer to private ECR; explicitly pull/validate/select on stopped EC2. Record source commits and immutable image IDs without requiring matching versions. Prefer stopping while idle; existing interruption and cleanup behavior applies if a run is active.
### Data / State / Ownership
- Use a separate encrypted 100 GiB gp3 EBS volume, retained on instance deletion/replacement, with a disposable root disk. Retained storage is not a backup.
- Retain configuration, diagnostics, deployment selection, Docker data, and private home under `/srv/software-factory`; credentials/configuration remain outside images. No on-instance release environments or builds.
### Interfaces / Contracts
- Use a persistent Python CDK shared-network stack plus separate builder and operational stacks that depend only on that network, not on each other. Keep VPC/subnet/gateway/routes across bakes; destroy/recreate only the builder stack for a fresh instance/root disk each bake. Keep security groups and IAM roles in their respective consumer stacks. Bake repository host scripts/service files into a private Ubuntu ARM64 AMI; operational UserData supplies the retained volume ID and invokes baked boot preparation. Lock existing CDK tooling; no Packer, scheduled pipeline, custom image-creation resource or runner toolchains on the host. Capture/test the AMI explicitly through AWS CLI; AMI/snapshot lifecycle is independent of builder-stack destruction. Keep local container publication and systemd-managed execution.
- Operator TOML contains exactly `repository`, `model`, `agent_image`; artifacts are fixed at `/home/factory/artifacts`. Reject removed `artifacts_dir` with actionable migration guidance, never migrate/delete previous diagnostics. Runner selection stays outside TOML; preserve selected-agent matching at startup.
### Operations / Deployment
- Deploy in `eu-central-1` on one `t4g.xlarge` instance (4 ARM vCPUs, 16 GiB RAM), using Ubuntu 24.04 ARM64 and factory UID/GID 2000:2000.
- Use one dedicated VPC and public subnet shared by builder and factory; assign a public IPv4 address for outbound access, with no inbound security-group access. Administration uses Session Manager, not SSH.
- Runner and agent update independently: runner owns its bridge; agent owns its instructions/skills. Pull/validate before atomic selection; failures preserve prior selection. No implicit deletion/lifecycle automation or guaranteed retention/rollback.
- Install current AWS CLI v2 as an EC2 deployment tool from AWS's official ARM64 HTTPS installer, without a detached-signature check as explicitly directed by the operator. Ubuntu ARM64 has no `awscli` candidate. Use the instance role for ECR authentication; do not save operator AWS credentials or add AWS tooling to runner/agent images. Preserve existing unrelated checks and tools.
- Host packages use current candidates from signed Ubuntu/Docker repositories, without exact version pins. The disposable AMI builder installs them with Docker/containerd masked; first boot performs no package installation. Read-only readiness inspection does not install/upgrade. Image/toolchain pins and Docker signing-key verification remain unchanged.
- AWS EC2 is the only supported deployment environment; operator-local publication and development checks are separate. The AMI contains Docker/prerequisites, factory 2000:2000/socket access and host service/helpers; CloudFormation UserData verifies/mounts storage before starting Docker and checking readiness. Never bake private/deployment state or attach the factory data volume to the builder. Baked helper changes require a tested replacement AMI; preserve explicit host replacement and factory-start approval. Retire Lima deployment and the separate Python host provisioner; runner tools remain in images. Existing host tools/data are not uninstalled or deleted.
- The operator approved scoped deletion of the old unused test deployment and its identified retained resources for CDK migration. Inventory first; unrelated resources remain untouched. No import, migration, logical-ID preservation, or compatibility machinery; new data volumes and ECR repositories retain their deletion/replacement policies.
- Runner packaging preserves factory 2000:2000, local socket supplementary GID, same-path workspaces, read-only App credentials, writable Pi refresh state, and retained private diagnostics. Container checks do not replace actual host preparation.
- Require explicit operator starts after crashes and reboots; no automatic service restart. Graceful draining is deferred.
## Core Business Rules
Preserve one runner per target repository, serial execution, manual requeue, create-only publication, cleanup gates, and human review.
## UX / Workflow Rules
Document health checks and safe start/stop, updates, and interruption inspection; do not describe idle checks as race-free draining.
## Data / State / Ownership Decisions
Keep credentials and diagnostics private and outside images. Do not silently delete retained diagnostics, images, or previous deployment artifacts. EBS retention does not provide backup or cross-Availability-Zone portability.
## Interface / Contract Expectations
Deployment must not silently start issue execution, automatically migrate operator TOML or introduce a second execution backend. The approved three-field change requires an explicit operator configuration update and rebuilt runner image.
## Operational / Deployment Constraints
Run basic local checks before deployment, then validate each implemented slice on AWS; offline/scripted checks alone do not establish deployment success. AWS and EC2 host-preparation operations are approved within this deployment scope; unrelated resources and live GitHub/Copilot checks are not. Docker grants effective host control, not isolation. Public IPv4, EBS, EC2, and possible burst-credit usage incur charges.
## Assumptions
The operator supplies a valid AWS SSO session for the approved profile, repository source access, target configuration, and manual GitHub App/Copilot enrollment. Exact AMI selection and deployment command details remain implementation work.

## Open Questions
- None currently for incremental AWS deployment; any additional policy, dependency, or public-interface decisions require approval.

## Ready for Spec Generation
- Status: yes
- Reason: The deployment scope now includes approved live AWS acceptance; preserve existing execution behavior and do not treat infrastructure approval as permission to execute target issues.
