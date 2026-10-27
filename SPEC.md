# Product Specification

Source: [DECISIONS.md](DECISIONS.md)

## Summary
- Add repository-managed EC2 deployment and explicit release/rollback procedures for the existing single-runner factory; this specification covers deployment, not a replacement execution model.

## Goals
- Reproducibly prepare one Ubuntu 24.04 ARM64 host using CloudFormation and existing provisioning.
- Supervise operator-started execution with systemd; expose status and private diagnostics.
- Deploy an exact Git commit with its image, instructions, skills, and Python environment; retain the previous release for rollback.
- Implement and deploy incrementally to AWS using profile `AWSAdministratorAccess-172318459814` in account `172318459814`, region `eu-central-1`; verify the authenticated account before creating resources. Run basic checks first, then obtain real AWS acceptance evidence for each deployed slice.

## Non-Goals
- Automatic credential enrollment or live GitHub/Copilot issue execution; AWS infrastructure deployment, EC2 host preparation, and live AWS acceptance are approved.
- Parallel workers, automatic scheduling, application deployment, container registry, or release pipeline.
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
- Define `eu-central-1`, one `t4g.xlarge`, Ubuntu 24.04 ARM64, local native Docker, and factory UID/GID 2000:2000; reuse existing host provisioning rather than a second execution backend.
- Provide a dedicated VPC, one public subnet, outbound internet connectivity, and a public IPv4 address; allow no inbound security-group access and use Session Manager rather than SSH.
- Provide a separate encrypted 100 GiB gp3 EBS volume retained on instance deletion/replacement and a disposable root disk; persist credentials, configuration, releases, Docker data, and diagnostics on retained storage.
- Preparation must not enroll credentials or start execution; failures remain visible and do not report a ready host. Existing data must not be silently erased or reformatted.
Deferred follow-ups:
- US-02 installs a selectable software release.

### US-02: Install and select an exact release
Primary actor: Operator
Trigger: A specific Git commit is approved for initial installation or upgrade.
Happy-path action: Install and select that commit while the factory service is stopped.
Visible outcome: A complete, identifiable release is selected for the next explicit start, with the previous release retained.
Authoritative state transition: The selected release changes from absent or the prior release to the successfully prepared requested commit.
Slice boundary: Checkout, release-specific Python environment, explicit on-instance image build, release selection, automated failure checks, and installation verification on the EC2 host.
Acceptance criteria:
- Identify the release by its exact Git commit and built immutable image ID; the runner, image, instructions, and skills come from the same commit.
- Keep the previous checkout, Python environment, and shared image on retained storage; keep private credentials, operator configuration, and diagnostics outside release contents and images.
- Installation does not start execution. Failed preparation must not replace the previously selected release or silently delete prior releases or diagnostics; running service state must not be changed underneath an active runner.
Deferred follow-ups:
- US-03 explicitly starts the selected release; US-06 selects a retained previous release.

### US-03: Explicitly start the selected release
Primary actor: Operator
Trigger: The operator authorizes execution after checking eligible issues and recovery state.
Happy-path action: Start the selected release through systemd.
Visible outcome: The selected factory runs under systemd as factory 2000:2000 and reports startup success or a safe failure.
Authoritative state transition: The systemd service changes from stopped to running only after an explicit start and successful existing startup validation.
Slice boundary: Service invocation, existing startup validation, private log collection, and automated start-path checks; verify startup on EC2 after manual enrollment and explicit execution authorization.
Acceptance criteria:
- Use operator-supplied configuration and manually enrolled GitHub App/Copilot credentials; preserve the four-field TOML, fail-closed startup validation, local engine/image requirements, and existing execution behavior.
- Preserve one runner per target repository. Host preparation, release installation, rollback, crashes, and reboots must not automatically start or restart the runner.
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
- Show how to inspect the service, selected release identity, startup/polling/run events, and private diagnostic locations using existing logging behavior.
- Explain that service liveness does not prove live GitHub/Copilot access, successful inference, cleanup, or publication; no inference or issue execution is triggered as a health probe.
- Missing evidence and access errors require inspection rather than an assumed healthy result; do not expose credentials or raw transcripts.
Deferred follow-ups:
- US-05 stops the service when intervention or an upgrade is needed.

### US-05: Stop execution for maintenance
Primary actor: Operator
Trigger: The operator requests maintenance, an upgrade, rollback, or emergency shutdown.
Happy-path action: Stop the systemd service using the existing interruption path.
Visible outcome: The runner stops, with interruption/cleanup evidence and retained diagnostics available for inspection when relevant.
Authoritative state transition: The service changes from running to stopped; interrupted work is not automatically requeued or resumed.
Slice boundary: Systemd stop behavior, existing signal/cleanup handling, recovery guidance, automated checks, and real stop verification on EC2 without initiating target issues.
Acceptance criteria:
- Recommend stopping while idle but explicitly state that idle inspection is not race-free draining; stopping during a run interrupts it.
- Allow the existing bounded cleanup and failure reporting rather than bypassing them; retain failed diagnostics and require inspection of uncertain publication or leftover resources before manual requeue.
- Stop/cleanup failures remain visible and require intervention; service exit alone is not proof that all Docker resources were removed. Do not introduce graceful-drain state or broad resource deletion.
Deferred follow-ups:
- US-02 installs an upgrade; US-06 selects a previous release.

### US-06: Roll back to a retained release
Primary actor: Operator
Trigger: The operator chooses a retained previous release after stopping the service.
Happy-path action: Select that release's checkout, Python environment, and shared image.
Visible outcome: The previous complete software bundle is selected for the next explicit start without losing private state or diagnostics.
Authoritative state transition: The selected release changes from the current release to the chosen retained previous release; the service remains stopped.
Slice boundary: Release selection, rollback guidance, automated failure checks, and real rollback verification on EC2 while execution remains stopped.
Acceptance criteria:
- Restore the previous runner/image/instructions/skills bundle together; reject missing or incomplete release components without reporting successful rollback or silently rebuilding a substitute.
- Preserve credentials, configuration, diagnostics, and existing GitHub state; rollback does not resume interrupted work, undo remote publication, or delete newer releases.
- Require an explicit US-03 start after inspection. Document that retained EBS is not a backup and cannot simply be reattached across Availability Zones.
Deferred follow-ups:
- None.

## Open Questions
- None for the accepted incremental AWS deployment scope. Deployment commands and exact filesystem layout remain implementation work; additional policy or dependency decisions require approval.
