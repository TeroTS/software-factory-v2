# Operator guide

## Operator setup

Deploy runner and agent containers **only on AWS EC2**, using **Ubuntu 24.04 ARM64**,
**factory 2000:2000**, and a local Docker engine. Native-runner deployment, Lima/local-host
deployment, root/other runner identities, and remote engines are unsupported.

1. Complete [EC2 host setup](#ec2-host-setup); no host checkout or manual provisioner is needed.
2. Switch to `factory` with `sudo -iu factory`, [publish/pull images](#ec2-image-publication),
   complete [authentication](#authentication), and prepare the [target](#shared-image-and-target-preparation).
3. Create the four-field operator TOML shown in [README](../README.md#run-the-factory),
   outside the target checkout/workspace. No credentials or `.env` loading are supported.
4. **Inspect existing `agent:implement` labels:** already-labeled issues are eligible.
   Start the selected runner container only through an explicit supervisor start;
   run only one runner per repository. Never deploy by invoking host Python.

Startup validates the host, credentials, and local image before polling. Docker
requires a local native Linux ARM64 engine and absolute Unix socket; explicit
`DOCKER_CONTEXT` overrides `DOCKER_HOST`. See [README](../README.md#run-the-factory)
for runtime behavior and [recovery](#manual-inspection-and-recovery) for stopping/requeueing.

## EC2 host setup

The Python CDK app in `infra/ec2/` generates CloudFormation and embeds the three local shell
files into first-boot UserData; it never fetches source at boot. The runner remains container-only.
Run `./scripts/setup` first (Python/uv plus Node 22 LTS/npm on the operator computer).
Run AWS commands from an authenticated operator machine, not from an agent:

```sh
export AWS_PROFILE=AWSAdministratorAccess-172318459814 AWS_REGION=eu-central-1
aws sts get-caller-identity  # require account 172318459814
test "$(aws sts get-caller-identity --query Account --output text)" = 172318459814
npm run cdk -- synth --quiet
aws cloudformation validate-template --template-body file://infra/ec2/cdk.out/software-factory.template.json
npm run cdk -- diff --parameters UbuntuAmi=ami-07a4d842baa6e2884
# Inspect the diff before approving the deployment:
npm run cdk -- deploy --parameters UbuntuAmi=ami-07a4d842baa6e2884
aws cloudformation describe-stacks --stack-name software-factory --query 'Stacks[0].Outputs'
aws ssm start-session --target '<InstanceId from stack outputs>'
```

The AMI pin is Canonical (`099720109477`) Ubuntu 24.04 ARM64; verify it before deployment.
Do not hand-edit generated templates. This asset-free stack uses CDK's bootstrapless synthesizer:
no `cdk bootstrap`, bootstrap roles/buckets, or associated storage costs are needed.
UserData mounts retained storage before installing Docker from signed repositories and AWS CLI v2
from AWS's official ARM64 HTTPS installer, without detached-signature verification. It then creates/checks
factory access. AWS CLI uses the EC2 role for ECR; no operator AWS credentials are saved on the host.
Host tool versions are unpinned; image pins remain independent.
In Session Manager, run `sudo cloud-init status --wait`, then `sudo /usr/local/sbin/factory-host-check`.
The latter checks actual storage/identity/socket/native-engine access and AWS CLI availability without
repairing, authenticating, or starting services.
Stack completion alone is not readiness: inspect `sudo journalctl -u cloud-final` on failure;
never bypass disk/signature checks or repository trust. Then follow [manual authentication](#authentication).
UserData runs on first boot, not automatically after template updates; use a replacement test instance
for preparation changes. The data volume retains factory home, Docker/containerd data,
and settings/artifacts; root is disposable. Docker services require these mounts.
For teardown, inspect `aws cloudformation list-stack-resources --stack-name software-factory`,
then explicitly approve `npm run cdk -- destroy`. Data volumes and both ECR repositories are retained;
inventory them before teardown and delete only individually confirmed disposable resources, if authorized.
Retained volumes/images incur charges after deletion; no backups or cross-AZ restore are provided.

## EC2 image publication

Use AWS CLI and a local native ARM64 Docker engine (including a local VM) on the
operator computer. Authenticate the approved AWS SSO profile, then publish independently:

```sh
export AWS_PROFILE=AWSAdministratorAccess-172318459814 AWS_REGION=eu-central-1 AWS_DEFAULT_REGION=eu-central-1
./scripts/verify
./scripts/publish-image runner runner-v1
./scripts/publish-image agent agent-v2
```

The script checks the AWS account and native engine, builds only the requested image,
smoke-tests it without network/credentials, then uses `aws ecr get-login-password`,
`docker login --password-stdin`, and `docker push`. Temporary Docker login state is
removed on exit. Agent smoke checks reuse the existing runner check through `uv`.
OCI revision records the checkout's base commit, not uncommitted edits. Tags can change;
use ECR digests to identify published contents. No snapshot/manifest manager, automatic
updates, lifecycle deletion, or rollback guarantee is provided.

Inspect host readiness separately with `sudo /usr/local/sbin/factory-host-check`.
Host pulls/selection are explicit operator CLI steps, not publication side effects.
Keep service, runner containers, and native runners stopped; pull and validate both
chosen images before changing selection or operator TOML. Failed pulls must leave the
prior settings intact. Never copy operator AWS credentials to EC2 or start execution
as an installation test.

Set `RUNNER_IMAGE` and `AGENT_IMAGE` to the requested ECR digest references. On EC2 as factory,
use the prepared AWS CLI and instance role to authenticate and explicitly pull, without retaining login state:

```bash
(
  set -euo pipefail
  umask 077
  DOCKER_CONFIG=$(mktemp -d)
  export DOCKER_CONFIG
  trap 'rm -rf -- "$DOCKER_CONFIG"' EXIT
  aws ecr get-login-password --region eu-central-1 |
    docker --host unix:///var/run/docker.sock login --username AWS --password-stdin \
      172318459814.dkr.ecr.eu-central-1.amazonaws.com
  docker --host unix:///var/run/docker.sock pull --platform linux/arm64 "${RUNNER_IMAGE:?set a runner digest reference}"
  docker --host unix:///var/run/docker.sock pull --platform linux/arm64 "${AGENT_IMAGE:?set an agent digest reference}"
)
```

Runner execution needs the local socket plus its supplementary GID, same-absolute-path
workspace/artifact binds, read-only `~/.config/software-factory`, writable `~/.pi/agent`,
and private retained logs. Do not mount ECR login state into runner/agent containers.

### Stopped-host selection
After pulling, run this as factory with the same digest references; do not start concurrently.
It atomically records both images in `~/.config/software-factory/deployment.env`, not credentials
or operator TOML. Before a later explicit start, set TOML `agent_image` to the recorded `AGENT_IMAGE`.

```bash
(
  set -euo pipefail; umask 077
  test "$(id -u):$(id -g)" = 2000:2000
  unset DOCKER_CONTEXT; export DOCKER_HOST=unix:///var/run/docker.sock
  # Reject active factory work or inspection errors; never stop or repair anything.
  stopped() {
    service=$(systemctl show software-factory.service --property=ActiveState --value)
    case "$service" in inactive|failed) ;; *) return 1;; esac
    containers=$(docker ps --quiet --filter 'name=^/(software-factory|factory-.*)$'); test -z "$containers"
    if pgrep -u 2000 -f '[p]ython.*-m software_factory' >/dev/null; then return 1; else test "$?" = 1; fi
  }
  stopped
  state="$HOME/.config/software-factory"
  test ! -L "$state"; mkdir -p "$state"
  work=$(mktemp -d "$state/.selection.XXXXXX")
  trap 'test ! -s "$work/cid" || timeout 60s docker rm --force --volumes "$(<"$work/cid")"; rm -rf -- "$work"' EXIT
  trap 'exit 1' HUP INT TERM
  check='test "$(id -u):$(id -g)" = 2000:2000; test "$(uname -m)" = aarch64; python -m software_factory --help >/dev/null; gh --version; pi --version; docker compose version'
  for image in "${RUNNER_IMAGE:?}" "${AGENT_IMAGE:?}"; do
    [[ "$image" =~ ^172318459814[.]dkr[.]ecr[.]eu-central-1[.]amazonaws[.]com/software-factory-(runner|agent)@sha256:[a-f0-9]{64}$ ]]
    platform=$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image"); test "$platform" = linux/arm64
    timeout 60s docker run --detach --name "factory-selection-${work##*/}" --cidfile "$work/cid" --pull=never --platform linux/arm64 --network none --entrypoint sleep "$image" infinity
    cid=$(<"$work/cid")
    timeout 60s docker exec "$cid" sh -ec "$check"
    if [ "$image" = "$RUNNER_IMAGE" ]; then
      check=$(timeout 60s docker exec "$cid" python -c 'from software_factory.runner import RUNTIME_CHECK; print(RUNTIME_CHECK)')
    fi
    timeout 60s docker rm --force --volumes "$cid"
    rm -- "$work/cid"
  done
  stopped
  test ! -L "$state/deployment.env"; test ! -d "$state/deployment.env"
  printf 'RUNNER_IMAGE=%s\nAGENT_IMAGE=%s\n' "$RUNNER_IMAGE" "$AGENT_IMAGE" > "$work/deployment.env"
  mv -f -- "$work/deployment.env" "$state/deployment.env"
)
```

## Authentication

Keep private state on EC2 as factory. Use tools from the selected runner image,
not host-installed Pi/Node/Git/gh.

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

1. As factory, open an authentication-only shell in the selected local runner image
   (`RUNNER_IMAGE`), mounting only persistent Pi state—not Docker or workspaces:

   ```sh
   install -d -m 0700 "$HOME/.pi/agent"
   docker run --rm -it --pull=never --platform linux/arm64 \
     --mount "type=bind,src=$HOME/.pi/agent,dst=/home/factory/.pi/agent" \
     --entrypoint sh "$RUNNER_IMAGE"
   pi --no-extensions --no-mcp --no-skills --no-context-files --no-session
   ```

2. Enter `/login`, select GitHub Copilot, and follow the authorization instructions
   as `TeroTS` for this installation. Open the supplied URL on your Mac if needed.
3. Exit Pi, then check inside that container shell without printing tokens:

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
docker logs '<confirmed-runner-container>' 2>factory.jsonl
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

Run **on EC2 as factory**; replace example paths/IDs with inspected values.

### 1. Stop and inspect

Stop the runner container through its supervisor's SIGTERM path. Wait for exit before
manual cleanup; allow its separate **60-second cleanup budget** plus failure reporting.

```sh
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

On an Ubuntu ARM64 test host as **factory 2000:2000**, with Python/uv test dependencies installed
separately (not supplied by host provisioning):

```sh
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
docker build --platform linux/arm64 -f runner/Dockerfile -t software-factory-runner:test .
FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 FACTORY_RUNNER_IMAGE_TESTS=1 ./scripts/verify
```

`FACTORY_AGENT_IMAGE` and `FACTORY_RUNNER_IMAGE` select other already-built test images.
Issue-outcome and polling E2E tests run the runner in a container and signal that container;
unit tests may call its Python entrypoint directly. Tests exercise real
Docker/services/Git with scripted GitHub/Pi boundaries; they are not live provider
acceptance. [CI](../.github/workflows/verify.yml) runs as the same identity without
host sudo. Ordinary development checks need no Docker; see [README](../README.md#development).

## Verification beyond unit tests

Live GitHub/Copilot checks require **explicit operator approval**. EC2 preparation acceptance
must inspect cloud-init, retained mounts, factory Docker access, and stopped runner state;
scripted UserData tests do not prove first-boot behavior on AWS.
