# Shared-image startup and the issue-to-draft-PR workflow

## Active workflow: US-04 startup

1. The operator authenticates host GitHub CLI/Pi and prepares local native ARM64
   Docker, then explicitly builds the [shared agent image](../../agent/README.md).
2. The operator supplies exactly `repository`, `model`, `agent_image`, and
   `artifacts_dir` in trusted TOML outside the target workspace. Legacy Compose
   fields are rejected; artifact paths resolve against the TOML directory.
3. The unchanged terminal invocation validates the artifact root, tools,
   authentication, local engine/image compatibility, and actual root/tool execution.
   It resolves the local image once to an immutable session ID without building,
   pulling, or emulating. Updating the image requires restart.
4. A short uniquely named startup container runs with no network access, mounts,
   or credentials. Bounded cleanup is attempted even after failure/interruption;
   cleanup failure prevents successful startup. Previous artifacts are untouched.
5. The runner reports that polling is active but issue execution is disabled
   until US-05. Polling discovers issues serially every 30 seconds.
6. The operator-approved temporary pre-claim guard leaves discovered issues
   unchanged: no trigger removal, issue status, workspace, implementation,
   branch, or PR. Direct issue dispatch is guarded too. There is no selectable
   prepared-Compose backend.
7. Ctrl-C/SIGTERM exits 130 after attempting active startup-probe cleanup. Invalid
   startup inputs or other startup failures exit nonzero with safe diagnostics.

Use the [real startup E2E](../../tests/test_startup_docker.py) with scripted
GitHub/authentication to demonstrate startup-to-polling. It does not process a real
issue or establish acceptance of the target workflow below. When US-05 enables
execution, already-labeled issues become eligible: inspect labels before upgrading.

## Target workflow: US-05–US-07, deferred

[The spec](../../SPEC.md) and [contracts](../contracts.md) remain authoritative:

1. Check exact configured repository and `factory/issue-<number>` PR/branch
   identity before claiming. Consume the trigger before execution or skip
   notification. Preserve existing PRs/branches; never blindly retry uncertain writes.
2. Snapshot immutable title/body only and create a fresh default-branch workspace
   under one 900-second deadline.
3. Start one root container from the resolved shared image, with same-path workspace
   and local engine access. Supply Copilot-only credentials privately via stdin;
   do not normally expose GitHub publication credentials or broader host settings.
4. Run executable deterministic `./scripts/setup`, Pi implementation, and CI-aligned
   `./scripts/verify`, including target builds/services and explicit test addresses.
   Missing entrypoints/setup errors fail before implementation.
5. US-06 permits at most three repair-and-verify cycles after completed verification
   failure, using the same environment/workspace/snapshot/deadline. Other failures
   do not grant repair attempts.
6. Complete scoped host-controlled cleanup of known run-owned resources and ensure
   host-usable files before publication. Cleanup failure blocks publication. Keep
   unrelated resources/images/cache and unknown resources intact; no broad pruning.
7. With remaining time and nonempty verified changes, commit using trusted host
   metadata, create the absent factory branch, open a draft PR with `Closes #N`,
   and report its actual URL. Human review and independent target CI follow.
8. Failures retain private diagnostics and report concise status when possible;
   never post transcripts or secrets. No automatic trigger restoration, retry,
   recovery, merge, or review-feedback revision is introduced.

## Manual requeue

US-07 will prove explicit label reapplication creates fresh inputs/workspace,
run identity, deadline, and repair allowance after required duplicate/branch checks.
Old diagnostics remain unchanged, not resumable state. Restart alone does not
execute retained work. The operator handles unknown resources/hard-crash leftovers
and orphan remote branches before requesting another attempt.

During the current US-04 guard, even explicit label reapplication does not execute
work or consume the label. Historical manual-requeue acceptance from the previous
runtime does not establish Docker-enabled US-07 acceptance.

## Trust boundary

The Docker-authorized agent is not a security boundary protecting the host.
Normal credential separation and cooperative resource ownership remain useful
but can be bypassed by deliberate engine access. Socket/mount/network/file-ownership
and cleanup feasibility must be proved on the actual local provider in US-05;
Linux CI is not macOS browser or filesystem-sharing evidence.

## References

- [Operator setup](../../README.md#operator-setup)
- [Product specification](../../SPEC.md)
- [Non-HTTP contracts](../contracts.md)
- [Current slice](../slices/current-slice.md)
- [Architecture](../architecture/service-architecture.md)
