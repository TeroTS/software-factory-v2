# Host-user agent execution without workspace permission repair

Status: implemented. The operator approved the simplified approach and `sudo -n`
inside the container, including adding sudo to the shared image. Current local
verification and remaining Linux/live-service gaps are recorded in the
[current slice](../slices/current-slice.md#host-user-correction-evidence).

## Approach

1. Start the agent container using the host UID/GID.
2. Configure a writable container home and caches.
3. Run setup, Pi, and verification as that user.
4. Support explicit root execution for system installs using `sudo -n` inside
   the container.
5. Remove `restore_ownership()` entirely.
6. Clean up the agent, owned service containers, networks, and disposable volumes
   before publication.
7. Block publication if the host cannot access required files.

No root-start-and-drop bootstrap, automatic permission repair, automatic retry as
root, or new backend. Keep this a US-05 correction; US-06/US-07 remain deferred.
Docker access and explicit root execution still grant effective engine/host
control. This change improves file handling, not security isolation.

## Implementation

### 1. Update accepted behavior

Before production changes, update `DECISIONS.md`, `SPEC.md`, and
`docs/contracts.md` to replace root-by-default execution and guaranteed recursive
access restoration with the approach above.

Preserve the four-field TOML, same-path workspace mount, immutable ARM64 image ID,
original 900-second deadline, bounded scoped cleanup, ownership labels, private
logs, Copilot credential handling, and trusted create-only host publication.

### 2. Run ordinary work as the host user

In `src/software_factory/sandbox.py`:

- Replace `--user 0:0` with the host's numeric UID/GID. Ensure every target
  `docker exec` runs as that identity, including setup, Pi, and verification.
- Provide writable HOME/cache locations inside the disposable container, without
  mounting host home directories or placing caches in the source tree.
- Preserve direct Docker/Compose access through the selected engine socket.
  Supply socket group access if required; verify the actual engine-side socket
  on macOS rather than assuming the host proxy has the same group. Do not change
  host socket permissions or silently fall back to root.

Use fixed trusted root initialization only for disposable container account,
shadow, group, and home setup. Start the container as the host UID/GID, then use
isolated Python for that initialization without workspace imports or permission
changes. UID-only target exec resolves the configured primary/socket groups.

Update `agent/Dockerfile` only as needed for home/cache configuration and the
approved `sudo -n` mechanism. Update `runner.py` startup checks and image tests:
root is no longer the required ordinary execution identity. Verify tools, writable
home/caches, and explicit root capability without target scripts or credentials.

### 3. Make system installs explicit

Target setup scripts own the choice of which commands require root. Ordinary
project dependency installs, builds, and tests run as the host user. Do not infer
required elevation from a permission error or elevate the whole setup script.

Use `sudo -n` inside the container for explicit root commands. Add `sudo` from
the image's existing signed Debian snapshot and configure passwordless elevation
for the run user. Missing or misconfigured elevation must fail without prompting.
Verify this works with the numeric host UID/GID, not just a fixed image user.
Do not introduce a host command broker, Docker CLI wrapper, or command-classification
framework. Elevation is not technically restricted to system installs.

Document that elevated commands must not leave inaccessible root-owned output in
the workspace. Prefer disposable owned volumes for service-private data; services
writing workspace binds need compatible ownership/permissions. These are target
requirements, not enforced isolation guarantees.

Host UID 0 remains UID 0 when matched. Do not silently select another identity or
add a new root-runner rejection policy without confirmation.

### 4. Delete repair; keep cleanup and publication gates

- Remove `Sandbox.restore_ownership()`, its helper container, and helper-only
  cleanup budget. Do not replace it with another recursive chown/chmod pass.
- Keep `Sandbox.stop()` focused on scoped Docker resource cleanup, including
  failure, timeout, interruption, and partial startup. Preserve unrelated
  resources, images, cache, and earlier diagnostics.
- After known mutators stop and cleanup succeeds, check host access required for
  publication. Reuse trusted host Git's staging/read failures; handle required
  directory-traversal errors explicitly rather than silently skipping them.
- Do not require every ignored dependency/cache file to be writable merely to
  publish. The gate concerns files and directories needed by trusted host
  publication, not a new universal workspace-permission policy.
- Checks must not change file content, ownership, or modes, follow symlinks outside
  the workspace, or run repository scripts on the host.
- Required-access or cleanup failure blocks commit/push/PR, retains private logs
  and the unchanged workspace, and reports a concise failure. Deliberately
  inaccessible files may require manual operator inspection; do not promise
  they have been repaired. Preserve the original execution error when reporting
  additional cleanup/access failures.

### 5. Tests and documentation

Add failing regressions first, then update production behavior and fixtures.

- Unit tests: correct UID/GID for setup/Pi/verify, home/cache configuration, no
  implicit elevation, no ownership helper, cleanup/access failures block publication.
- Real image/Docker tests: non-root execution with representative host UID/GID
  values, writable caches, explicit root system installation, socket/Compose access,
  same-path sibling mounts, and host-usable ordinary output on success and failure.
- Metadata regression: cleanup leaves ownership/modes and the verified Git diff
  unchanged, including executable-bit and intentionally read-only fixtures.
- Access failures: inaccessible required files/directories block publication
  without repair. Run these tests as a non-root host user so root privileges do
  not mask failures.
- Preserve cleanup failure/timeout/interruption/partial-start tests and unrelated
  sentinel resources. Keep real CLI/local Git/Docker publication coverage with
  scripted Pi/GitHub boundaries; assert cleanup and access checks precede publication.
- Adapt `tests/tests_support.py`: user-local tool installation and a fixture Pi
  path rather than ordinary setup overwriting `/usr/local/bin/pi`. Separate
  mode-000 negative tests from the ordinary success fixture.

Affected tests: `tests/test_sandbox.py`, `tests/test_runner.py`,
`tests/test_startup.py`, `tests/test_startup_docker.py`,
`tests/test_docker_integration.py`, `tests/test_issue_docker.py`,
`tests/test_repository.py`, and bridge tests as needed.

Update `sandbox_agent.mjs` instructions, `README.md`, `AGENTS.md`,
`agent/README.md`, architecture/workflow guidance, and slice evidence. Document
setup-script adaptation and the required explicit image rebuild/runner restart.
Audit CI/image references and remove stale root/permission-restoration claims.
Do not change image version policy or previous artifacts implicitly.

## Verification and completion

```sh
./scripts/verify
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 ./scripts/verify
uv run --frozen python -m software_factory --help
git diff --check
```

Keep format → lint → coverage ordering and unchanged Python/Node 80% gates.
Verify actual macOS provider UID/GID, socket access, mounts, networking, and host
file access as well as native Linux CI. Record failures and gaps rather than
assuming UID matching proves compatibility. Check changed documentation links.

Done when ordinary work runs as the host user, explicit root installs work,
cleanup performs no permission repair, and only verified accessible changes reach
publication after scoped cleanup. No live authenticated checks, commit, push,
US-06/US-07 work, or edits to the unrelated
`docs/workflows/simplified_worflow.md` are included.
