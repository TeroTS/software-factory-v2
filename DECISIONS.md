# EC2 Factory Deployment Decisions

Status: Accepted planning baseline
## Problem Summary
Move the existing single-runner factory to a reproducibly prepared EC2 host with explicit release and rollback procedures.

## Goals and Success Criteria
Repository-managed infrastructure, supervised operation, release-specific software, and documented health checks, upgrades, interruption handling, and rollback.

## Primary Roles / Actors
The operator provisions infrastructure, enrolls credentials, deploys releases, starts/stops the service, and handles recovery; the existing factory executes issue runs.

## Non-Goals
No live AWS deployment in this task, parallel workers, application deployment, container registry/release pipeline, or graceful-draining implementation.

## Locked Decisions
### Product / Scope
- Implement and test repository artifacts only: CloudFormation, deployment scripts, systemd unit, and operator procedures. AWS creation, credential enrollment, and live validation require separate approval.
### UX / Workflow
- Deploy an exact Git commit and explicitly build its shared image on EC2. Prefer stopping while idle; existing interruption and cleanup behavior applies if a run is active.
### Data / State / Ownership
- Use a separate encrypted 100 GiB gp3 EBS volume, retained on instance deletion/replacement, with a disposable root disk. Retained storage is not a backup.
- Proposed layout on `/srv/software-factory`: `releases/<commit>/` with its own `.venv`, `current` symlink, `config/`, `artifacts/`, `docker/`, and `home/`. Exact layout remains an implementation proposal.
### Interfaces / Contracts
- Use CloudFormation YAML and systemd; preserve existing runner configuration and execution contracts except for separately accepted deployment interfaces.
### Operations / Deployment
- Deploy in `eu-central-1` on one `t4g.xlarge` instance (4 ARM vCPUs, 16 GiB RAM), using Ubuntu 24.04 ARM64 and factory UID/GID 2000:2000.
- Use a dedicated VPC and one public subnet; assign a public IPv4 address for outbound access, with no inbound security-group access. Administration uses Session Manager, not SSH.
- Keep the previous checkout, Python environment, and shared image on retained storage. Version the runner, image, instructions, and skills together; rollback restores software, not issue-run state.
- Require explicit operator starts after crashes and reboots; no automatic service restart. Graceful draining is deferred.
## Core Business Rules
Preserve one runner per target repository, serial execution, manual requeue, create-only publication, cleanup gates, and human review.
## UX / Workflow Rules
Document health checks and safe start/stop, upgrade, rollback, and interruption inspection procedures; do not describe idle checks as race-free draining.
## Data / State / Ownership Decisions
Keep credentials and diagnostics private and outside releases/images. Do not silently delete retained diagnostics or previous releases. EBS retention does not provide backup or cross-Availability-Zone portability.
## Interface / Contract Expectations
Deployment must not silently start issue execution, change operator TOML fields, or introduce a second execution backend.
## Operational / Deployment Constraints
No AWS resources, privileged provisioning, or authenticated live checks without separate approval. Docker grants effective host control; IAM and private file modes do not isolate agents from the host. Public IPv4, EBS, EC2, and possible burst-credit usage incur charges.
## Assumptions
The operator supplies AWS access, repository source access, target configuration, and manual GitHub App/Copilot enrollment. Exact AMI selection and deployment command details are implementation work, not permission for live deployment.

## Open Questions
- None currently for repository-only implementation; any additional policy, dependency, or public-interface decisions require approval.

## Ready for Spec Generation
- Status: yes
- Reason: `$decision-to-spec` can describe the agreed deployment scope without inventing policy; preserve existing execution behavior and defer live acceptance until separately approved.
