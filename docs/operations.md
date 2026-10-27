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

Startup validates the host, credentials, and local image before polling. Docker
requires a local native Linux ARM64 engine and absolute Unix socket; explicit
`DOCKER_CONTEXT` overrides `DOCKER_HOST`. See [README](../README.md#run-the-factory)
for runtime behavior and [recovery](#manual-inspection-and-recovery) for stopping/requeueing.

## EC2 host setup

Use the same Ubuntu ARM64 runtime on EC2; no second execution backend is involved.
Run AWS commands from an authenticated operator machine, not from an agent:

```sh
export AWS_PROFILE=AWSAdministratorAccess-172318459814 AWS_REGION=eu-central-1
aws sts get-caller-identity  # require account 172318459814
aws cloudformation validate-template --template-body file://infra/ec2/factory.yaml
aws cloudformation deploy --stack-name software-factory --template-file infra/ec2/factory.yaml \
  --parameter-overrides UbuntuAmi=ami-07a4d842baa6e2884 --capabilities CAPABILITY_IAM --disable-rollback
aws cloudformation describe-stacks --stack-name software-factory --query 'Stacks[0].Outputs'
aws ssm start-session --target '<InstanceId from stack outputs>'
```

The AMI pin is Canonical (`099720109477`) Ubuntu 24.04 ARM64; verify it before deployment.
The template uses JSON-form YAML so ordinary tests need no YAML dependency. It prepares
retained storage, not the full toolchain: transfer trusted committed factory source via
Session Manager, run `scripts/provision-host` and `--check` as administrator, then follow
[manual authentication](#authentication). Never start the runner implicitly.
Check `cloud-init status --wait` and mounts before provisioning. Stack completion alone
is not host readiness. The data volume retains factory home, Docker/containerd data,
and future releases/artifacts; root is disposable. Docker services require these mounts.
Retained volumes incur charges after deletion; no backups or cross-AZ restore are provided.

## Authentication

Perform setup **inside the VM as factory**, using the provisioned tools.

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

The runner uses repository-scoped App tokens for API calls and HTTPS Git, never
personal `gh auth login` or inherited-token fallback.

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

Keep Pi's default agent directory; Pi manages login/refresh state. A `ready`
result is not proof of live inference or unattended refresh.

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

**Docker access grants effective engine/host control, not isolation.** Private
file modes do not protect against a malicious Docker-enabled agent; App scopes
also allow more than the runner uses.

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

Logs are **JSON Lines on stderr**, at **INFO** by default; see
[README](../README.md#run-the-factory) for fields. To collect them:

```sh
uv run --frozen python -m software_factory --config /absolute/path/to/factory.toml 2>factory.jsonl
```

Keep collected logs private and manage retention; `2>` overwrites existing files.
A slow destination can block. Logs are not recovery state or proof of remote
success. Command output stays in private run logs (**0700** directories, **0600**
files), with known-secret redaction—not a guarantee. Never publish raw transcripts.
[logging.ini](../logging.ini) provides optional development defaults.

| Problem | Operator action |
| --- | --- |
| Startup/image failure | Check credentials, tools, and local image; rebuild/restart if incompatible. Inspect named `factory-startup-*` leftovers. |
| Failed/interrupted run or uncertain publication | Follow [manual recovery](#manual-inspection-and-recovery) before requeueing. |
| Cleanup or file-access failure | Publication is blocked. Inspect ownership labels and workspace permissions; no automatic chown/chmod repair. |

## Manual inspection and recovery

Run **inside the VM as factory**; replace example paths/IDs with inspected values.

### 1. Stop and inspect

Use Ctrl-C, or find the runner PID and send SIGTERM. Wait for exit before manual
cleanup; allow its separate **60-second cleanup budget** plus failure reporting.

```sh
pgrep -af 'python -m software_factory'
kill -TERM '<confirmed-runner-pid>'
grep -F '"event": "run_started"' /absolute/path/to/factory.jsonl
find /absolute/path/to/artifacts_dir -maxdepth 1 -type d -name 'issue-42-*' -print
less /absolute/path/to/selected-run/run.log
```

The `run_started` record names the issue, `run_id`, and private directory. Use the
configured artifacts path; keep diagnostics private and never execute retained
workspace scripts on the host. A crash may leave containers running.

### 2. Identify leftovers

Use the **same local Docker endpoint selected at startup** (an explicit
`DOCKER_CONTEXT` overrides `DOCKER_HOST`). If logs are missing, discover candidates
and inspect labels/mounts to match them to the retained workspace:

```sh
docker container ls --all --filter 'name=factory-'
docker container inspect '<candidate-id>' --format '{{json .Config.Labels}} {{json .Mounts}}'
```

Copy the confirmed issue-run identity below. List both labels separately (**OR**):

```sh
RUN_ID=factory-0123456789abcdef0123456789abcdef
for LABEL in software-factory.run-id com.docker.compose.project; do
    docker container ls --all --filter "label=$LABEL=$RUN_ID" --format '{{.ID}} {{.Names}} {{.Status}}'
    docker network ls --filter "label=$LABEL=$RUN_ID"
    docker volume ls --filter "label=$LABEL=$RUN_ID"
done
```

Confirm ownership with `docker network inspect <id>` / `docker volume inspect <name>`.
Names alone are not proof. Unknown/unlabeled resources need investigation.
For `factory-startup-*` probes, confirm the exact container against startup logs;
do not infer ownership of other resources from its name.

### 3. Resolve publication on GitHub

In the configured repository's web UI, inspect branch `factory/issue-42` and search
PRs with `is:pr head:factory/issue-42`, including closed/merged results. Confirm the
head repository and exact branch. A failed push/PR request may have succeeded;
access errors mean **unknown**, not absent. Do not replay writes from the workspace.
Preserve any existing PR for inspection; if only an orphan branch remains, inspect
its commits before explicitly deciding whether to delete it for a fresh attempt.

### 4. Clean and requeue

With the runner stopped, remove **only confirmed owned resources**, agent first,
then other containers, networks, and disposable volumes. Volume data is deleted:

```sh
docker container rm --force '<confirmed-agent-container-id>'
docker container rm --force '<confirmed-other-owned-container-id>'
docker network rm '<confirmed-owned-network-id>'
docker volume rm '<confirmed-disposable-owned-volume-name>'
```

Repeat the exact-label listings and confirm the agent is absent. Errors require
inspection, not broader deletion. Never prune the daemon, remove shared resources,
or recursively chown/chmod the workspace. Keep failed diagnostics until explicit
deletion; they are not resumed and deleting them does not clean Docker.

Fix the cause and resolve branch/PR state before explicitly reapplying
`agent:implement` for a fresh run. Inspect all trigger-labeled issues before
[restarting](#operator-setup): every eligible issue can be picked up.

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
