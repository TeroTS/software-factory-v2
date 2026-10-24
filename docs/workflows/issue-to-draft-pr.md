# Shared-image issue-to-draft-PR workflow

## Startup: US-04

1. The operator authenticates host GitHub CLI/Pi, prepares local native ARM64
   Docker, and explicitly builds the [shared image](../../agent/README.md).
2. Trusted TOML supplies exactly `repository`, `model`, `agent_image`, and
   `artifacts_dir`, outside the target workspace. Legacy Compose fields fail with
   migration guidance; relative artifacts resolve against the TOML directory.
3. Startup validates artifacts, host tools/authentication, local engine/image
   compatibility, and actual root/tool execution, pinning an immutable image ID.
   The runner never builds/pulls the shared image or uses an emulation fallback.
4. A uniquely named startup probe has no mounts/network/credentials. Bounded cleanup
   is attempted on failure/stop; cleanup errors block startup. Previous artifacts
   remain untouched. Polling is serial at 30-second intervals.

US-05 removes the temporary pre-claim guard. **Inspect existing trigger labels
before starting/upgrading**: already-labeled issues are eligible for execution.

## First-pass execution: US-05

1. The operator applies `agent:implement`. The runner checks the exact configured
   head repository and `factory/issue-<number>` open PR, then remote branch. Confirmed
   trigger removal precedes execution or skip notification. Existing PRs are linked
   and preserved; orphan branches require operator cleanup and label reapplication.
2. A clear issue receives running status, a fresh private run directory/workspace,
   and an immutable title/body snapshot from the current default branch. Comments,
   attachments, linked content, and later issue edits are not task inputs. Start
   one original 900-second budget before workspace preparation.
3. Start one root shared-image agent with same-path workspace and local engine
   socket access. The host retains trusted Git metadata outside the ordinary mount.
   Normal environment/mounts exclude GitHub publication credentials and broader host
   Pi settings; root/engine access can still bypass that separation.
4. Require executable deterministic `./scripts/setup` and `./scripts/verify`.
   Setup runs before Pi and installs nonbaseline tools inside the agent. Missing
   entrypoints or setup failure ends the run without guessed commands/setup repair.
5. Invoke exact-model Copilot Pi through the private stdin bridge with validated
   bearer endpoint/lifetime, temporary config, disabled discovered resources, and
   nonpersistent sessions. Run canonical CI-aligned verification, including ordinary
   native target Docker builds/Compose services and explicit service addresses.
6. A completed verification failure currently fails the run; Docker transport,
   missing-script, provider, lifecycle, and deadline failures are also terminal.
   No verification repair loop is included in US-05.
7. Remove the agent, then exact run-owned containers before owned networks and
   disposable volumes. Cleanup uses host-owned identity/exact labels, not mutable
   Compose teardown files. Restore host file ownership/access with a trusted,
   mount-only, network-free helper. Cleanup failure blocks publication.
8. With passing verification, completed cleanup, time remaining, and nonempty
   changes, trusted host Git commits and creates the absent remote factory branch.
   Create a draft PR containing `Closes #N`, then comment with its actual URL.
   Empty output fails as `no changes produced`. Uncertain push/PR writes receive
   bounded read-only inspection, not automatic retries.
9. Failure/stop reports a concise reason where possible and retains private
   diagnostics locally. Status-reporting errors remain visible, even after a
   branch/PR exists. Never post transcripts or secrets. Successful diagnostics may
   be removed. The factory never merges or revises from human review feedback.

All installations/builds/execution/checks, required cleanup before publication,
and publication share the original deadline. After expiry or Ctrl-C/SIGTERM,
bounded cleanup is still attempted; this grants no additional coding/publication
time. SIGTERM/interruption exits 130. Unknown resources and hard-crash leftovers
require operator inspection, not pruning or automatic recovery.

## Target resource/network conventions

- Ordinary Compose inherits unique matching `FACTORY_RUN_ID`/`COMPOSE_PROJECT_NAME`.
- Direct resources use `--label "software-factory.run-id=$FACTORY_RUN_ID"`.
- Preserve unrelated/external/shared resources, images, and build cache. Overrides,
  other contexts, and unlabeled commands can bypass cooperative cleanup.
- Target scripts must use native-compatible `linux/arm64` images/tools. Startup
  validates the native engine/shared agent image; factory-owned containers request
  `--platform linux/arm64` and `--pull=never`. Target commands inherit
  `DOCKER_DEFAULT_PLATFORM=linux/arm64` and use the unmodified image Docker client.
  Explicit platform overrides are not intercepted and may invoke engine-supported
  emulation. Actual Docker/setup/verification failures remain visible; the factory
  never selects an emulation fallback or substitutes dependencies.
- Use Compose DNS after joining its network or the Docker host address for published
  ports. Siblings do not share the agent's localhost. Same-path mounts support
  relative sibling workspace binds; transparent forwarding is not provided.

## Deferred recovery and manual requeue

US-06 will add up to three repair-and-verify cycles after completed verification
failure, preserving environment/workspace/snapshot/deadline and all publication
gates. Other failures will not grant repair attempts.

US-07 will prove the complete explicit manual-requeue outcome with fresh title/body,
current default branch, new run identity/deadline, and unchanged earlier diagnostics.
Failure/interruption/restart does not restore the trigger, resume sessions, or
interpret artifacts as executable state. Remote branches and unknown resources
need operator inspection before requesting another attempt. Historical acceptance
from the previous runtime does not establish these future outcomes.

## Evidence and trust boundary

[Startup E2E](../../tests/test_startup_docker.py),
[Docker checks](../../tests/test_docker_integration.py), and
[CLI issue E2E](../../tests/test_issue_docker.py) use real local dependencies with
scripted external boundaries. No live Copilot request or GitHub write is made.
The current slice records local provider/browser evidence separately from ARM64
CI; Linux alone is not proof of macOS sharing/networking.

Docker-authorized root execution is not a boundary protecting the host. Normal
credential separation, trusted Git metadata, and ownership labels remain useful
but can be bypassed through engine access. Independent target CI and human review
remain mandatory.

## References

- [Operator setup](../../README.md#operator-setup)
- [Product specification](../../SPEC.md)
- [Non-HTTP contracts](../contracts.md)
- [Current slice](../slices/current-slice.md)
- [Architecture](../architecture/service-architecture.md)
