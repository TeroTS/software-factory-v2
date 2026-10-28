# Product Specification

Source: [DECISIONS.md](DECISIONS.md)

## Summary
- Add repository-managed EC2 deployment with independently published runner and agent containers; this covers packaging and deployment, not a replacement execution backend.

## Goals
- Support deployment only on AWS EC2: CloudFormation UserData prepares one Ubuntu 24.04 ARM64 host, retained storage, Docker, and factory identity; deploy the runner only as a container.
- Supervise operator-started execution with systemd; expose status and private diagnostics.
- Publish independently versioned native ARM64 runner and agent images from the operator computer to ECR; explicitly select their immutable identities on a stopped EC2 host.
- Implement and deploy incrementally to AWS using profile `AWSAdministratorAccess-172318459814` in account `172318459814`, region `eu-central-1`; verify the authenticated account before creating resources. Run basic checks first, then obtain real AWS acceptance evidence for each deployed slice.

## Non-Goals
- Automatic credential enrollment or live GitHub/Copilot issue execution; AWS infrastructure deployment, EC2 host preparation, and live AWS acceptance are approved.
- Parallel workers, automatic scheduling, application deployment, CI publication, or automatic updates.
- Lima/local-host deployment, a separate host provisioner, native-runner deployment, or installing runner language/agent toolchains on the host. Developer test tooling and operator-local image publication are separate.
- V1 rollback guarantees, guaranteed old-image retention, or new compatibility negotiation.
- Graceful draining, automatic restart after crashes/reboots, automatic requeue, or restoration of interrupted runs.
- Backups or cross-Availability-Zone portability of retained EBS storage.

## User Stories

### US-01: Prepare a stopped EC2 factory host
Primary actor: Operator
Trigger: An approved request to provision the factory host.
Happy-path action: Deploy the repository's CloudFormation and host-preparation artifacts.
Visible outcome: One prepared host is available through Session Manager, with factory execution stopped.
Authoritative state transition: Undeployed infrastructure becomes a deployed stack with a prepared host and retained data volume.
Slice boundary: Infrastructure, storage attachment, host preparation, basic automated checks, and live AWS verification of Session Manager access, the retained volume, provisioning, and stopped factory execution. Stack creation alone does not demonstrate completion.
Acceptance criteria:
- Define `eu-central-1`, one `t4g.xlarge`, Ubuntu 24.04 ARM64, local native Docker, and factory UID/GID 2000:2000. CloudFormation UserData prepares retained storage before installing/starting Docker and installing AWS CLI from its official ARM64 HTTPS installer (without detached-signature verification) for EC2-role ECR authentication, then checks account/socket/engine and AWS CLI readiness. Provide read-only host readiness inspection without a separate provisioner. Runner Python/Node/Pi/Git/gh belong in images, not host setup. Do not uninstall existing tools or alter retained data.
- Provide a dedicated VPC, one public subnet, outbound internet connectivity, and a public IPv4 address; allow no inbound security-group access and use Session Manager rather than SSH.
- Provide a separate encrypted 100 GiB gp3 EBS volume retained on instance deletion/replacement and a disposable root disk; persist credentials, configuration, deployment state, Docker data, and diagnostics on retained storage.
- Preparation must not enroll credentials or start execution; failures remain visible and do not report a ready host. Existing data must not be silently erased or reformatted.
Deferred follow-ups:
- US-02 publishes and selects independently versioned runner and agent images.

### US-02: Publish and select container images
Primary actor: Operator
Trigger: Runner and/or agent versions are approved for initial installation or update.
Happy-path action: Publish each requested native image locally to ECR and explicitly select the independently chosen images while factory execution is stopped.
Visible outcome: An identifiable runner/agent deployment is selected for the next explicit start.
Authoritative state transition: The selected deployment changes from absent or the prior selection to the successfully validated requested image pair.
Slice boundary: Local build/test/publication, ECR infrastructure and scoped host pull access, stopped-host pull/validation/selection, automated failure checks, and live publication/deployment verification. Publication is preparation for this one deployment outcome, not a second execution flow.
Acceptance criteria:
- Publish runner OR agent with an explicit independent version; record source commit and immutable image identities. Agent instructions/skills belong to the agent image; the bridge belongs to the runner. Do not require matching commits/tags or add compatibility negotiation.
- Use one Python AWS CDK stack to generate CloudFormation, embedding repository shell files into first-boot UserData at synthesis. Keep local build/push commands and systemd-managed Docker execution; no Compose deployment, runtime source fetch, or build/push custom resources.
- Keep private credentials, four-field operator TOML, and diagnostics on retained storage outside images. Select the runner outside TOML; preserve independently configured `agent_image`.
- Validate native images before atomically changing selection. Preparation never starts execution; refuse active service/container state. Failed preparation preserves prior selection, configuration, and diagnostics. Do not delete images or prior artifacts implicitly.
- Preserve fail-closed startup, factory 2000:2000, local Docker socket access, same-path workspaces, read-only App credentials, writable Pi refresh state, and private retained diagnostics. Containerization is packaging, not host isolation.
Deferred follow-ups:
- US-03 explicitly starts the selected deployment; US-04 inspects health; US-05 stops execution.

### US-03: Explicitly start the selected deployment
Primary actor: Operator
Trigger: The operator authorizes execution after checking eligible issues and recovery state.
Happy-path action: Start the selected runner container through systemd using its selected agent image.
Visible outcome: The selected factory runs under systemd as factory 2000:2000 and reports startup success or a safe failure.
Authoritative state transition: The systemd service changes from stopped to running only after an explicit start and successful existing startup validation.
Slice boundary: Service invocation, existing startup validation, private log collection, and automated start-path checks; verify startup on EC2 after manual enrollment and explicit execution authorization.
Acceptance criteria:
- Use operator-supplied configuration and manually enrolled GitHub App/Copilot credentials; preserve the four-field TOML, fail-closed startup validation, local engine/image requirements, and existing execution behavior.
- Preserve one runner per target repository. Host preparation, image publication/selection, crashes, and reboots must not automatically start or restart the runner.
- Failed startup remains observable without credential disclosure or fallback identities; a process being active alone does not establish successful startup.
Deferred follow-ups:
- US-04 inspects operational health; US-05 stops execution.

### US-04: Inspect operational health
Primary actor: Operator
Trigger: The operator needs to determine whether the deployed factory is functioning or needs intervention.
Happy-path action: Follow the documented health-inspection procedure.
Visible outcome: The operator can distinguish stopped, failed-startup, and running states and locate available progress and failure evidence.
Authoritative state transition: None; inspection reads systemd state and existing factory logs without changing execution or GitHub state.
Slice boundary: Operator health procedure, automated checks of its read-only boundaries, and real service/log inspection on EC2.
Acceptance criteria:
- Show how to inspect the service, selected runner/agent image identities, startup/polling/run events, and private diagnostic locations using existing logging behavior.
- Explain that service liveness does not prove live GitHub/Copilot access, successful inference, cleanup, or publication; no inference or issue execution is triggered as a health probe.
- Missing evidence and access errors require inspection rather than an assumed healthy result; do not expose credentials or raw transcripts.
Deferred follow-ups:
- US-05 stops the service when intervention or an upgrade is needed.

### US-05: Stop execution for maintenance
Primary actor: Operator
Trigger: The operator requests maintenance, an update or emergency shutdown.
Happy-path action: Stop the systemd service using the existing interruption path.
Visible outcome: The runner stops, with interruption/cleanup evidence and retained diagnostics available for inspection when relevant.
Authoritative state transition: The service changes from running to stopped; interrupted work is not automatically requeued or resumed.
Slice boundary: Systemd stop behavior, existing signal/cleanup handling, recovery guidance, automated checks, and real stop verification on EC2 without initiating target issues.
Acceptance criteria:
- Recommend stopping while idle but explicitly state that idle inspection is not race-free draining; stopping during a run interrupts it.
- Allow the existing bounded cleanup and failure reporting rather than bypassing them; retain failed diagnostics and require inspection of uncertain publication or leftover resources before manual requeue.
- Stop/cleanup failures remain visible and require intervention; service exit alone is not proof that all Docker resources were removed. Do not introduce graceful-drain state or broad resource deletion.
Deferred follow-ups:
- US-02 publishes and selects an update; an older available image may be explicitly selected without a retention or rollback guarantee.

## Open Questions
- None for the accepted incremental AWS deployment scope. Deployment commands and exact filesystem layout remain implementation work; additional policy or dependency decisions require approval.
