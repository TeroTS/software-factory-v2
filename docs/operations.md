# Operator guide

## Operator setup

Deploy runner and agent containers **only on AWS EC2**, using **Ubuntu 24.04 ARM64**,
**factory 2000:2000**, and a local Docker engine. Native-runner deployment, Lima/local-host
deployment, root/other runner identities, and remote engines are unsupported.

1. Complete [EC2 host setup](#ec2-host-setup); no host checkout or manual provisioner is needed.
2. Switch to `factory` with `sudo -iu factory`, [publish/pull images](#ec2-image-publication),
   complete [authentication](#authentication), and prepare the [target](#shared-image-and-target-preparation).
3. Create the three-field operator TOML shown in [README](../README.md#run-the-factory),
   outside the target checkout/workspace. No credentials or `.env` loading are supported.
4. **Inspect existing `agent:implement` labels:** already-labeled issues are eligible.
   Start the selected runner container only through an explicit supervisor start;
   run only one runner per repository. Never deploy by invoking host Python.

Startup validates the host, credentials, and local image before polling. Docker
requires a local native Linux ARM64 engine and absolute Unix socket; explicit
`DOCKER_CONTEXT` overrides `DOCKER_HOST`. See [README](../README.md#run-the-factory)
for runtime behavior and [recovery](#manual-inspection-and-recovery) for stopping/requeueing.

## EC2 host setup

Run `./scripts/setup` on the operator computer. The bootstrapless CDK app defines persistent
`software-factory-shared` networking plus separate `software-factory-ami-builder` and `software-factory`
consumers, each with its own security group/IAM role. Deploy shared networking first and keep it across bakes.
Always name the intended stack; use `--exclusively` for consumer operations so networking is not updated implicitly.
Existing deployments need a separately reviewed/authorized network-ownership migration; do not apply this as a routine update.
The builder embeds reviewed repository files at synthesis, installs signed Docker packages and AWS CLI
from its approved official ARM64 HTTPS installer (no detached-signature verification), and keeps engines masked.
Never attach factory storage or enroll credentials on the builder. Host tool versions are recorded, not pinned.
Every bake must start with the builder stack absent: explicitly destroy the previous builder stack after inventory/approval,
then deploy it afresh. Do not update/restart a previously baked instance. AMIs/snapshots remain outside the stack.

```sh
export AWS_PROFILE=AWSAdministratorAccess-172318459814 AWS_REGION=eu-central-1
test "$(aws sts get-caller-identity --query Account --output text)" = 172318459814
# Set UBUNTU_AMI to an available Canonical (099720109477) Ubuntu 24.04 ARM64 image; verify owner/architecture first.
aws ec2 describe-images --owners 099720109477 --image-ids "${UBUNTU_AMI:?}" --query 'Images[*].[ImageId,Architecture,State,Name]'
npm run cdk -- synth --quiet
npm run cdk -- diff software-factory-shared
# After reviewing/authorizing persistent networking (initial deployment only):
npm run cdk -- deploy software-factory-shared
npm run cdk -- diff --exclusively software-factory-ami-builder --parameters UbuntuAmi="$UBUNTU_AMI" --parameters SourceRevision="$(git rev-parse HEAD)"
# After reviewing/authorizing builder creation:
npm run cdk -- deploy --exclusively software-factory-ami-builder --parameters UbuntuAmi="$UBUNTU_AMI" --parameters SourceRevision="$(git rev-parse HEAD)"
BUILDER=$(aws cloudformation describe-stacks --stack-name software-factory-ami-builder --query "Stacks[0].Outputs[?OutputKey=='BuilderInstanceId'].OutputValue | [0]" --output text)
aws ssm start-session --target "$BUILDER"
```

In SSM, run `sudo cloud-init status --wait`; inspect `sudo cat /etc/software-factory/image-info`,
`sudo journalctl -u cloud-final` and masked Docker/containerd state. Source revision records the base commit,
not an assertion of a clean checkout. On success, explicitly run
`sudo systemd-run --unit factory-finalize-image --on-active=5s /usr/local/sbin/factory-finalize-image`.
It rejects private/mounted factory data, clears cloud-init/machine/SSM/SSH identity and powers off.
Failure to stop is not capture success; inspect/rebuild rather than bypass finalization checks.

```sh
aws ec2 wait instance-stopped --instance-ids "$BUILDER"
AMI=$(aws ec2 create-image --instance-id "$BUILDER" --name "software-factory-base-${VERSION:?}" --query ImageId --output text)
aws ec2 wait image-available --image-ids "$AMI"
aws ec2 describe-images --owners 172318459814 --image-ids "$AMI" --query 'Images[*].[ImageId,Architecture,State,BlockDeviceMappings]'
```

Record the AMI ID, parent, source/installed versions and backing snapshot. Before selection, launch a disposable
AMI test host with scratch storage and volume-specific UserData: verify fresh identity/capture-ready file,
SSM, retained mounts/sentinel/modes, factory Docker access, reboot and missing-storage failure, and stopped execution.
Then inventory and explicitly destroy only `software-factory-ami-builder`; its AMI/snapshot survive destruction.
Keep `software-factory-shared` and the factory stack; never use `destroy --all`. Remove separately created test hosts first.
Build/test failures never change the selected factory AMI. AMIs/snapshots require separately approved deletion.

Select the tested, available, account-owned ARM64 AMI through `--parameters FactoryAmi="$AMI"` on explicit
`npm run cdk -- diff --exclusively software-factory`, then reviewed `deploy --exclusively software-factory`. Replacement needs approval:
stop/inspect the old host and cleanly detach only its exact retained volume before applying the change.
In the new host's SSM shell run `sudo cloud-init status --wait` and `sudo /usr/local/sbin/factory-host-check`;
this read-only check, not stack completion, establishes readiness. UserData mounts storage before Docker,
without installs/source fetches. Rebuild/test the AMI for baked helper/package updates; container releases stay independent.
Factory teardown must name its stack explicitly; retained EBS/ECR and AMI snapshots incur charges until approved deletion.

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

## Explicit start

After [selection](#stopped-host-selection) and [manual authentication](#authentication), place the
three-field TOML at `/home/factory/.config/software-factory/factory.toml` (factory-owned, mode 0600).
Its `agent_image` must exactly match selected `AGENT_IMAGE`; the runner validates this before preflight.
Artifacts use fixed retained `/home/factory/artifacts`. Remove legacy `artifacts_dir` explicitly and rebuild/select
the updated runner image; previous diagnostics are not moved/deleted. The launcher binds this same-path directory,
read-only configuration/App state, writable Pi
state, and the local socket with its supplementary GID. It never pulls images or changes selection.

**Before authorizing start**, inspect all eligible `agent:implement` issues and any uncertain
publication/leftover resources using [manual recovery](#manual-inspection-and-recovery).
From the administrative Session Manager shell (not the unprivileged factory shell):

```sh
sudo systemctl start software-factory.service  # explicit authorization to poll/execute eligible issues
sudo systemctl status software-factory.service --no-pager
sudo journalctl -u software-factory.service --no-pager -n 20
```

The journal names a fresh private `/home/factory/.local/state/software-factory/start-*/runner.log`.
Read that file as factory: JSON event `runner_polling` proves existing startup validation passed
and releases systemd's `activating` state. Startup has a five-minute supervisor limit;
`runner_failed` or a nonzero service exit requires inspection. **Liveness alone does not prove
live inference/refresh, cleanup or publication.** No health probe runs issues.
Logs append within that start directory and survive container removal/replacement; prior logs remain.
The unit is deliberately static (`systemctl enable` is unsupported), has `Restart=no`, and is not
started by preparation, image selection, reboot or crash recovery. A stopped/failed container name
conflict requires inspection, not implicit removal. The service's Docker stop allows 120 seconds
(including the existing 60-second cleanup budget), with a 150-second supervisor limit.

The AMI contains the unit/launcher without starting them. Baked helper/unit changes require a rebuilt,
tested AMI and explicit stopped-host replacement, not runtime source copying or rerunning the installer.
Preserve retained state and independently selected container images throughout replacement.

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
find /home/factory/artifacts -maxdepth 1 -type d -name 'issue-42-*' -print
less /absolute/path/to/selected-run/run.log
```

The `run_started` record names the issue, `run_id`, and private directory. Use the
fixed `/home/factory/artifacts` path; keep diagnostics private and never execute retained
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
