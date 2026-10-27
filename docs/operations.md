# Operator guide

## Operator setup

Run the factory inside a provisioned **Ubuntu 24.04 ARM64 VM**, as **factory
2000:2000**. Direct macOS execution, root/other runner identities, and remote Docker
engines are unsupported. Keep checkouts and artifacts on the VM's Linux disk,
not macOS shared folders.

1. Stop Rancher Desktop, then start the [Lima VM](../infra/lima/factory.yaml)
   from your Mac:

   ```sh
   limactl start --name=factory --tty=false infra/lima/factory.yaml
   limactl shell factory
   ```

2. Clone or transfer a trusted factory checkout into the VM. From that checkout,
   provision and check the host as administrator:

   ```sh
   sudo ./scripts/provision-host
   sudo ./scripts/provision-host --check
   ```

   Provisioning installs tools but does not authenticate. If it fails, inspect the
   reported private log. Fix HTTPS trust with an approved CA; never disable it.

3. Switch accounts, use a factory-owned checkout, and install project dependencies:

   ```sh
   sudo -iu factory
   cd /absolute/path/to/factory-checkout
   ./scripts/setup
   ```

4. Complete [authentication](#authentication), [build the shared image](agent-image.md),
   and prepare the [target repository](#shared-image-and-target-preparation).
5. Create the four-field operator TOML shown in [README](../README.md#run-the-factory).
   Keep it outside the target checkout/workspace. Relative artifact paths resolve
   against the TOML directory; no credentials or `.env` loading are supported.
6. **Inspect existing `agent:implement` labels:** already-labeled issues are eligible.
   Run only one runner per repository, then start:

   ```sh
   uv run --frozen python -m software_factory --config /absolute/path/to/factory.toml
   ```

Startup checks host identity, tools, credentials, Docker, and the local image before
polling. Docker must use a local native Linux ARM64 engine and an absolute Unix
socket; `DOCKER_CONTEXT` takes precedence over `DOCKER_HOST` when explicitly set.

The runner polls every 30 seconds and runs issues serially under a 900-second
setup → Pi → verification → cleanup → publication deadline. It publishes only
verified, nonempty changes as draft PRs. Workflow-file changes are blocked; target
CI and human review remain required. It never merges or deploys.

**Stop:** Ctrl-C/SIGTERM attempts bounded cleanup, retains failed diagnostics, and
exits 130. Restart does not resume work or restore consumed trigger labels.

## Authentication

Perform setup **inside the VM as factory**, not as the default Lima login user.
Requires `gh`, OpenSSL, curl, and Pi **1.3.0**, supplied by host provisioning.

### GitHub App (one-time)

1. In GitHub settings, open the installed App and generate/download a private key.
   Its installation must include the target repository with metadata read and
   contents/issues/pull requests read/write. Do not grant workflow-write permission.
2. Transfer the key privately to
   `/home/factory/.config/software-factory/github-app.pem`. The directory must be
   factory-owned, mode **0700**; the key must be factory-owned, mode **0600**.
   Symlinks are rejected. Keep keys out of Git, images, workspaces, logs, and chat.
3. Create `github-app.json` beside the key, also factory-owned and mode **0600**.
   For the approved `factory-example` installation, use:

   ```json
   {"app_id": 5430144, "installation_id": 174237987}
   ```

   Use the appropriate IDs for another installation. These IDs are not secrets.

The runner acquires repository-scoped App tokens for both API calls and HTTPS Git;
no personal `gh auth login` is required or used as fallback. App JWT exchange uses
an explicit Bearer header over curl stdin, not `gh`'s automatic token scheme.

### Pi/Copilot (one-time)

1. From the factory home directory, run:

   ```sh
   cd "$HOME"
   pi --no-extensions --no-mcp --no-skills --no-context-files --no-session
   ```

2. Enter `/login`, select GitHub Copilot, and follow the authorization instructions
   as `TeroTS` for this installation. Open the supplied URL on your Mac if needed.
3. Exit Pi, then check without printing tokens:

   ```sh
   chmod 700 "$HOME/.pi/agent"
   chmod 600 "$HOME/.pi/agent/auth.json"
   pi auth check --provider github-copilot --no-extensions --no-mcp --no-context-files
   ```

Keep Pi's default agent directory for login and runner execution. Pi manages its
persistent login/refresh state; the agent receives only a short-lived bearer over
stdin. A `ready` result is not proof of live inference or unattended refresh.

### Restart, expiry, rotation, and revocation

- **Restart:** host credentials persist. GitHub tokens are reacquired and renewed
  when at most 20 minutes remain; Pi performs supported refresh without prompts.
- **Access failure:** stop the runner, fix App access or log in to Pi again, then
  restart. No account fallback, automatic requeue, or blind write retry occurs.
- **Rotate an App key:** stop/clean active work, privately replace the key with the
  same ownership/modes, validate it, then revoke the old key in GitHub.
- **Compromise:** revoke upstream immediately, stop runner/agents, and inspect
  resources before replacing credentials. Deleting a local file does not revoke
  issued tokens; some may remain valid until expiry.
- **Backups/replacement hosts:** treat backups and downloaded keys as secret-bearing
  storage. Enroll a replacement explicitly; never restore workspaces as run state.

**Docker access grants effective engine/host control, not isolation.** Private file
permissions are not encryption or protection against a malicious Docker-enabled
agent. App permissions also allow more than the runner uses; stronger server-side
permission separation is deferred.

## Shared image and target preparation

See the [image reference](agent-image.md) for tools, instructions, skills, and rebuilds.
Targets must already provide executable, noninteractive `./scripts/setup` and
`./scripts/verify`, with verification matching target CI. Setup failure is not
repaired automatically.

- Install extra tools **inside the agent**, not on the host. Use ordinary user
  commands for builds/packages and explicit `sudo -n` only for system installs.
  Do not run entire setup scripts as root or reuse macOS `.venv`/`node_modules`.
- Setup, Pi, and verification run as **2000:2000**, with container-local writable
  home/caches. Workspace ownership and permissions are never repaired; services
  writing workspace files must use compatible permissions.
- Use ordinary application Compose definitions and native `linux/arm64` images/tools,
  not target-specific factory images. Target commands inherit
  `DOCKER_DEFAULT_PLATFORM=linux/arm64`; explicit overrides are not intercepted and
  may invoke engine-supported emulation.
- Keep the inherited matching `FACTORY_RUN_ID` and `COMPOSE_PROJECT_NAME`. Label
  directly created containers/networks/disposable volumes with
  `--label "software-factory.run-id=$FACTORY_RUN_ID"`. Overrides, other contexts,
  and unlabeled resources bypass scoped cleanup. Avoid fixed names/ports.
- Put service-private data in disposable owned volumes. Shared resources, images,
  and build cache are not disposable run resources.
- Use Compose DNS after joining its network, or Docker-host published ports.
  Sibling services do not share the agent's localhost; automatic forwarding and
  network attachment are not provided. Workspace mounts use the same host/container
  path so sibling bind mounts resolve correctly.

## Diagnostics and safety

The runner emits application logs as **JSON Lines on stderr**, with **INFO**
progress enabled by default; WARNING/ERROR indicate problems. Logging does not
write to stdout or create application log files. There is no format switch or
logging configuration field in operator TOML.

Every record includes a UTC `timestamp`, standard `level`, stable `event`, and
readable `message`. Optional `repository`, `issue`, `phase`, `run_id` (the existing
sandbox identity), and validated `pr_url` are included when available; missing
context is omitted. Startup failures may lack repository/issue context.

To collect logs, explicitly redirect stderr to an operator-managed path:

```sh
uv run --frozen python -m software_factory --config /absolute/path/to/factory.toml 2>factory.jsonl
```

Logs are synchronous diagnostic output, not recovery state or proof of a remote
operation. A slow destination can block; lost output is not recovered. Standard
logging handler error handling applies. Keep collected logs private and manage
their retention yourself; `2>` overwrites an existing file.

Only selected fields and factory-controlled messages or sanitized failure
summaries are serialized, not arbitrary extras, exception details, or transcripts.
The formatter is not a general secret redactor. Command output stays in private
run logs with known-secret redaction. New run directories use **0700**, logs
**0600**. Never publish raw transcripts.
[logging.ini](../logging.ini) supplies equivalent optional development defaults.

| Problem | Operator action |
| --- | --- |
| Startup/image failure | Check credentials, tools, and local image; rebuild/restart if incompatible. Inspect named `factory-startup-*` leftovers. |
| Failed/interrupted run | Inspect retained workspace/logs and run-owned resources. Fix the cause, then explicitly reapply the trigger for a fresh run. |
| Existing factory branch/PR | Inspect `factory/issue-<number>`; the runner never overwrites/deletes remote branches. Clean orphan branches manually before requeue. |
| Uncertain push/PR result | Inspect remote state before retrying anything; a branch/PR may already exist. |
| Cleanup or file-access failure | Inspect exact resource labels and required workspace permissions. Publication stays blocked; no automatic chown/chmod repair. |

Cleanup stops the agent/owned containers before networks/disposable volumes, using
host-owned identities rather than target teardown scripts. Failure cleanup has a
separate bounded budget, not extra coding/publication time. Hard-crash leftovers
and unknown resources need manual inspection; **never use daemon-wide pruning**.
Failed diagnostics remain until operator deletion; deleting them does not stop
leftover containers. Successful diagnostics may be removed.

## Docker and CLI tests

Inside the provisioned VM as **factory 2000:2000**:

```sh
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 ./scripts/verify
```

`FACTORY_AGENT_IMAGE` selects another already-built test image. Tests exercise real
Docker/services/Git with scripted GitHub/Pi boundaries; they are not live provider
acceptance. [CI](../.github/workflows/verify.yml) runs as the same identity without
host sudo. Ordinary development checks need no Docker; see [README](../README.md#development).

## Verification beyond unit tests

Live GitHub/Copilot checks and privileged provisioning tests require **explicit
operator approval**. To install/check the existing Lima VM as administrator and
verify repeated provisioning preserves state, run from your Mac:

```sh
FACTORY_PROVISION_TESTS=1 uv run --frozen pytest tests/test_provision_lima.py -q
```

This modifies the guest but does not allocate a VM or authenticate. Linux tests
also do not prove macOS-to-VM browser/service access; check that separately.
