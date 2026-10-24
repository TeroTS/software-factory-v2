# Remove the native Docker wrapper

Status: implemented as US-05 cleanup. The operator's implementation request approved
this plan's native-request clarification; accepted specifications/contracts and
current guidance now reflect it. Fresh verification is recorded in the
[current slice](../slices/current-slice.md).

## Goal

Use the shared image's ordinary Docker executable directly. Delete the wrapper,
its installation code, and its dedicated tests without replacing them with another
interception or architecture-enforcement mechanism.

## Behavior to retain

- Startup rejects a nonnative engine or shared agent image and retains the resolved
  immutable image ID for the session.
- Factory-created agent and ownership-helper containers explicitly request
  `--platform linux/arm64` and `--pull=never`.
- Target commands inherit `DOCKER_DEFAULT_PLATFORM=linux/arm64`.
- Agent instructions continue to request native tools/images without emulation.
- Setup → Pi → verification, deadlines, credentials, same-path mounts, ownership
  labels, scoped cleanup, file-access restoration, and publication gates are unchanged.
- Actual Docker/setup/verification failures remain visible; the factory does not
  retry them with a different architecture or substitute dependencies.

## Explicit limitation and contract clarification

The factory will request native execution, not police arbitrary target Docker
commands. Target scripts remain responsible for using compatible native images
and tools. Explicit platform overrides can bypass the default and may invoke
emulation if the operator's engine supports it.

The implementation request confirmed this clarification. The architecture wording
in [SPEC.md](../../SPEC.md) US-05 and [contracts](../contracts.md), particularly
Contracts 3 and 8, now reflects:

> The factory validates a native ARM64 engine/shared agent image, explicitly starts
> its own containers as linux/arm64, and supplies a native platform default to
> target commands. It never selects an emulation fallback. Target scripts must use
> native-compatible images/tools; the factory does not intercept Docker commands
> or guarantee rejection of explicit architecture overrides.

This supersedes the earlier universal-rejection wording for target images/tools.
Actual Docker/setup/verification failures must still fail visibly. No replacement
guard or universal-rejection guarantee was added.

## Implementation steps

1. **Remove the interception.**
   - In [sandbox.py](../../src/software_factory/sandbox.py), delete the second
     command in `Sandbox.start()` that renames Docker and writes the Python shim.
   - Delete `src/software_factory/native_docker.py`.
   - Keep the native default and explicit factory-owned container platform flags.
   - No image definition, image pins, operator TOML, dependencies, or new options
     need to change. No image rebuild is required for this removal.

2. **Replace wrapper assertions with a direct-execution regression.**
   - In [test_sandbox.py](../../tests/test_sandbox.py), replace installation/source
     assertions with an assertion that `start()` only starts the agent and performs
     no Docker executable rewrite. Keep its mount/environment/platform assertions.
   - Add a small real-container assertion in the existing
     [Docker suite](../../tests/test_docker_integration.py):
     `/usr/local/bin/docker` remains the image's original executable, the relocated
     `/usr/local/libexec/factory/docker` does not exist, and the native default is
     present. Then use ordinary Docker/Compose through the existing fixture.
   - Observe the new no-rewrite regression fail before removing installation code.

3. **Delete tests and fixtures whose only purpose was the wrapper.**
   - Delete `tests/test_native_docker.py`.
   - Remove `test_nonnative_platform_fails_before_container_creation` and
     `test_local_nonnative_image_is_rejected_even_if_its_executable_could_run`
     from the Docker suite, including synthetic architecture-image creation.
   - Remove documentation about the synthetic Alpine rootfs fixture; it has no
     remaining purpose after those tests are removed.
   - Do not replace these with tests that deliberately run AMD64/emulated workloads.
   - Preserve startup rejection tests and real native build/Compose/service,
     cleanup/failure, credential, deadline, Git/publication, and CLI E2E coverage.

4. **Align documentation with the actual guarantees.**
   - Update [README](../../README.md), [AGENTS](../../AGENTS.md),
     [image guide](../../agent/README.md),
     [architecture](../architecture/service-architecture.md), and
     [workflow](../workflows/issue-to-draft-pr.md): no CLI shim, help-text parser,
     executable relocation, or claim of policing target platform overrides.
   - After implementation, update the [current slice](../slices/current-slice.md)
     with the removal and fresh verification evidence. Clearly supersede its
     wrapper-specific claims; do not present earlier test counts as current.
   - Keep this as US-05 cleanup. Do not invent a new story ID or start US-06/US-07.

5. **Verify and audit the removal.**
   - Run focused sandbox/startup tests and the existing Docker/CLI E2E suite using
     the already-built native shared image.
   - Run the full format → lint → coverage workflow:

     ```sh
     FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 ./scripts/verify
     ```

     If the local uv certificate issue recurs, use `UV_NATIVE_TLS=true` as in the
     previous verification; do not disable certificate verification.
   - Retain all 80% coverage gates. Report the new test count and coverage, and
     investigate any decrease rather than changing thresholds or exclusions.
   - Build the package and check that it no longer contains `native_docker.py`
     while still including `sandbox_agent.mjs`.
   - Run `git diff --check`, check affected documentation links, and search runtime,
     tests, and current guidance for dangling wrapper references. This proposal
     may retain its explanatory references to deleted files.

## Done when

- New agent containers use the unmodified image Docker executable directly.
- No wrapper module, installation code, parser tests, synthetic architecture
  fixtures, or replacement interception mechanism remains.
- Native startup validation, explicit factory container platforms, native target
  defaults, and all execution/cleanup/publication safeguards remain intact.
- Accepted specs and current guidance distinguish native requests from enforcement
  against target overrides.
- Focused and full verification pass with unchanged coverage gates and updated
  completion evidence.

## Out of scope and precautions

- No new dependencies, architecture policy options, daemon/binfmt changes, socket
  proxy, command interception, backend selector, or image rebuild workflow.
- No live Copilot request, GitHub write, commit, or push is required.
- Preserve the existing US-05 working-tree changes and the unrelated untracked
  `docs/workflows/simplified_worflow.md`; do not reset or revert the broader work.
- Running agent containers retain their current filesystem until removed. The
  simplified startup applies to newly created agents after upgrading/restarting;
  do not mutate existing containers or inspect/delete unrelated resources.
