# Product Specification

Source: [DECISIONS.md](DECISIONS.md)

## Summary
- Migrate the autonomous coding factory from arbitrary-host-user initialization to one fixed-identity Linux deployment. Use Ubuntu Server 24.04 LTS ARM64 and account/group `factory`, UID/GID `2000:2000`, on both the host and shared agent image.
- The persistent Lima VM on Apple Silicon is the only deployment/acceptance environment. The runner and Docker engine execute inside Linux, with execution data on its native filesystem; no separate production-like host is required.
- This backlog covers only the migration, not previously delivered features or unrelated future work. Only [the current slice](docs/slices/current-slice.md) records implementation state and verification evidence. Reconcile affected contracts before production changes. Domain names follow [CONTEXT.md](CONTEXT.md).
- Docker access grants effective engine/host control. Fixed identity and limited ordinary mounts are not security isolation. Preserve existing first-pass behavior, credential handling, cleanup/publication safeguards, and human review requirements from DECISIONS.md.

## Goals
- Provision the local Linux host through one explicit entrypoint/runbook and repository-maintained Lima configuration.
- Bake the fixed account, writable home/caches, and account-scoped sudo configuration into the existing shared image; remove runtime account/shadow/group initialization.
- Validate the fixed host/image identity and prove Docker socket supplementary-group access through actual issue execution.
- Preserve existing CLI/TOML, serial coordination, original deadline, private diagnostics, scoped cleanup, and trusted create-only publication without permission repair.
- Verify the migration in the local Linux VM, with ARM64 CI under the fixed identity and the unchanged Python overall line/branch 80% coverage gate.

## Non-Goals
- Reimplementing existing issue coordination/publication, adding verification repairs, or delivering the full manual-requeue acceptance scenario.
- Direct macOS runner execution, arbitrary host UID/GID support, parallel identity/backends, automatic account/configuration/artifact migration, or recursive workspace permission repair.
- Runner-managed VM/cloud creation, remote Docker engines, ECS Fargate, x86-64/emulation support, or a cloud deployment framework. A systemd service, AMI pipeline, Terraform, and configuration-management framework are not required.
- Changes to polling, concurrency, task inputs, provider selection, automatic requeue/recovery, merging, or review-feedback handling.
- Target-specific tools installed on the host, setup repair, automatic shared-image builds/pulls, Docker command interception, transparent sibling localhost, or broad resource cleanup.
- Implicit installation, VM allocation, paid-resource creation, network exposure, or live authenticated Copilot/GitHub checks; these require separate operator authorization.

## User Stories

### US-08: Provision a Linux factory host
Primary actor: Operator

Trigger: An explicitly authorized Ubuntu Server 24.04 LTS ARM64 host is available for factory setup.

Happy-path action: Prepare the host using the supplied provisioning entrypoint and runbook.

Visible outcome: The host has the fixed factory account and validated factory prerequisites, ready for manual authentication and runner startup.

Authoritative state transition: Unprepared Linux host → provisioned factory host with verified identity/tool access.

Slice boundary: One provisioning-to-readiness outcome on the local Lima VM through the explicit host provisioning entrypoint. No separate production-like host, issue processing, or automatic authentication is required to demonstrate readiness.

Acceptance criteria:
- Supply repository-maintained configuration/run instructions for a persistent Ubuntu Server 24.04 LTS ARM64 Lima VM with SSH and explicit host-to-guest service access. Keep execution data on its Linux disk and disable unnecessary macOS directory sharing. Installation/allocation is explicit, not a runner startup side effect.
- Provision account/group `factory` as `2000:2000`, with local Docker access but no general host passwordless sudo. Administrator execution is limited to explicit provisioning. Name/ID conflicts fail clearly without renumbering existing accounts, making the socket world-writable, or migrating previous artifacts.
- Use Ubuntu's signed APT repositories for Git, Make, sudo, curl, certificates, and build dependencies; Docker's official signed Ubuntu APT repository for Engine/CLI/Compose/buildx; GitHub CLI's official signed APT repository for gh. Verify availability and record exact APT versions before implementing installation commands.
- Install Python 3.14.3 from the checksum-verified official python.org source separately from system Python; official Node.js 22.19.0 ARM64 binaries with checksum/signature verification; official uv 0.5.13 binaries with checksum verification; and npm `@earendil-works/pi-coding-agent@1.3.0` under the factory account. Validate trust sources; do not use unversioned `curl | sh`, replace system Python, silently substitute unverifiable versions/sources, or introduce automatic upgrades.
- Validate tools, fixed identity, native engine, and factory-account Docker access. Repeated provisioning validates/reuses correct state without erasing credentials, repositories, or diagnostics. Partial failures are reported, not claimed as readiness. Leave gh/Pi authentication manual and private; never acquire/copy credentials automatically.
- A focused provisioning check observes readiness without live service access. Cover repeated provisioning, conflicting IDs, unavailable/unverifiable releases, installation failures, and unusable Docker access. The local Lima VM is the acceptance environment; no separate EC2/equivalent repetition or cloud validation is required.

Deferred follow-ups:
- US-09: Start the runner with the fixed image identity.
- US-10: Execute issue runs without runtime account initialization.

### US-09: Start the runner with the fixed factory identity
Primary actor: Operator

Trigger: A provisioned host has manual authentication, existing operator configuration, and an explicitly built updated shared agent image.

Happy-path action: Start the runner under the factory account.

Visible outcome: The runner validates the fixed host/image identity and enters polling.

Authoritative state transition: Stopped configured runner → validated fixed-identity runner polling the repository.

Slice boundary: One startup-to-polling migration outcome through the existing CLI/preflight path, without processing an issue or redesigning configuration.

Acceptance criteria:
- Preserve the existing terminal invocation and four-field TOML. UID/GID are deployment constants, not new settings. Reject an unsupported host or effective UID/GID other than `2000:2000`, including root, before issue claims; never switch accounts or elevate the host runner automatically.
- Build the fixed account/group, writable container-local home/caches/npm prefix, and account-scoped `sudo -n` with root HOME selection into the shared image. Preserve its Debian base and pinned tools. Validate actual account identity, writable home/tool execution, and explicit elevation without runtime account/shadow/group initialization.
- Reject old/mismatched images with explicit rebuild/restart guidance. Preserve already-local native ARM64 validation, immutable session image ID, explicit operator image builds, and no automatic build/pull/emulation fallback.
- Retain existing configuration, authentication, artifact-access, startup cleanup, polling, and interruption behavior. Do not alter previous diagnostics or workspace permissions. Any socket-mounted probe is engine-authorized, not host-isolated.
- A focused real CLI check enters polling using scripted authentication/GitHub boundaries. Test root/wrong identity, incompatible images/home/sudo, and cleanup failures alongside existing preflight regressions. Run ARM64 CI under the fixed account rather than assuming the hosted runner's default identity matches.

Deferred follow-ups:
- US-10: Verify the fixed identity and socket groups through a complete issue run.

### US-10: Execute issue runs without runtime account initialization
Primary actor: Operator

Trigger: The fixed-identity runner is polling and an issue is labeled for implementation.

Happy-path action: Submit the issue through the existing first-pass workflow.

Visible outcome: The issue links to a verified draft PR produced using the fixed agent account and Docker socket access, without runtime account mutation.

Authoritative state transition: Labeled issue on a validated fixed-identity runner → successful issue run linked to a draft PR after required cleanup.

Slice boundary: One migration regression E2E through the existing issue-to-PR workflow, real local Git/Docker services, and scripted Pi/GitHub boundaries. No new coordination, repair, or publication feature is introduced.

Acceptance criteria:
- Start the agent as the image's fixed factory identity, with existing same-absolute-path Linux workspace mounts and container-local home/caches. Setup, Pi, and verification use that identity. Remove runtime account/shadow/group initialization and its obsolete callers/fixtures; retain one execution path.
- Discover the selected local socket's numeric GID and pass it at agent creation using `--group-add`. Prove access through the actual `docker exec` path, including when the socket GID differs from the primary GID. Missing access fails visibly without socket chmod, account mutation, root retry, or engine fallback. Return to the operator if the accepted mechanism fails feasibility checks.
- Preserve setup → Pi → canonical verification, explicit `sudo -n` only for system installs, native target defaults/unmodified Docker CLI, explicit service addressing, and existing stdin-only ephemeral Copilot credential handling. Do not elevate whole phases, repair setup, or add verification repairs.
- Keep service-private data in disposable run-owned volumes. Workspace-writing services need compatible ownership/permissions, not a blanket UID requirement for every image. Inaccessible required publication files block publication and remain unchanged; no recursive chown/chmod or requirement to make ignored caches writable.
- Retain the original 900-second deadline, exact duplicate/claim checks, immutable task snapshot, trusted create-only Git/PR publication, private redacted diagnostics, and no automatic retry/requeue/recovery. Stop workspace mutators and complete scoped cleanup before publication; preserve unrelated resources/images/cache and previous artifacts. Cleanup/access failure blocks publication.
- A focused real CLI E2E observes the existing verified draft-PR result through the new identity/group path. Exercise sibling mounts, target-installed tools, explicit sudo, service volumes/ownership, and a macOS browser reaching a fixture port through the VM's explicit network path. Run these real boundaries in the local Lima VM; no separate production-like host repetition is required.
- Preserve failure regressions for setup, verification, provider/credentials, deadline, SIGTERM, partial startup, cleanup/access, and uncertain publication, including unrelated sentinel resources. Keep current instructions accurate and all Python business logic within the unchanged 80% coverage gate; distinguish scripted service boundaries from live authenticated evidence.

Deferred follow-ups:
- None within this migration.

## Open Questions
- No unresolved choice among OS/architecture, fixed identity, VM tool, or installation sources. Local allocation/image pins belong in the repository-maintained Lima configuration; provisioning source-verification evidence belongs in the [current slice](docs/slices/current-slice.md). Acceptance is local-VM-only, without a cloud validation claim.
- Docker supplementary-group behavior through the actual exec path remains unproven. If verification contradicts `--group-add`, return to the operator rather than silently choosing a fallback.
- Cloud deployment/testing is outside this migration's scope, not a pending acceptance prerequisite. No paid instance, new network exposure, or live Copilot/GitHub-writing check is authorized by this specification.
