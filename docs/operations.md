# Operator guide

## Operator setup

Deploy only on **AWS EC2, Ubuntu 24.04 ARM64, factory 2000:2000**, with local native Docker.
Complete [host setup](#ec2-host-setup), [image configuration](#ec2-image-publication),
[authentication](#authentication) and [target preparation](#shared-image-and-target-preparation),
then create the [three-field TOML](../README.md#run-the-factory) outside the target checkout.
Use Session Manager for administration and `sudo -iu factory` for factory commands; runner tools
belong in images, not on the host. **Docker access grants effective engine/host control, not isolation.**

## EC2 host setup

Run `./scripts/setup` on the operator computer. Keep `software-factory-shared` networking across
bakes; builder and factory stacks have separate security groups/IAM roles. Name stacks explicitly,
use `--exclusively` for consumers, and review/authorize diffs before deployment. Existing network
ownership changes need separate approval. Each bake requires a fresh builder instance/root disk;
inventory and destroy only the previous builder stack first, never `destroy --all`.

```sh
export AWS_PROFILE=AWSAdministratorAccess-172318459814 AWS_REGION=eu-central-1
test "$(aws sts get-caller-identity --query Account --output text)" = 172318459814
# Set UBUNTU_AMI to an available Canonical Ubuntu 24.04 ARM64 image; verify owner/architecture.
aws ec2 describe-images --owners 099720109477 --image-ids "${UBUNTU_AMI:?}" --query 'Images[*].[ImageId,Architecture,State,Name]'
npm run cdk -- synth --quiet
npm run cdk -- diff software-factory-shared
# Initial networking deployment only, after approval:
npm run cdk -- deploy software-factory-shared
npm run cdk -- diff --exclusively software-factory-ami-builder --parameters UbuntuAmi="$UBUNTU_AMI" --parameters SourceRevision="$(git rev-parse HEAD)"
# After builder approval:
npm run cdk -- deploy --exclusively software-factory-ami-builder --parameters UbuntuAmi="$UBUNTU_AMI" --parameters SourceRevision="$(git rev-parse HEAD)"
BUILDER=$(aws cloudformation describe-stacks --stack-name software-factory-ami-builder --query "Stacks[0].Outputs[?OutputKey=='BuilderInstanceId'].OutputValue | [0]" --output text)
aws ssm start-session --target "$BUILDER"
```

In SSM, run `sudo cloud-init status --wait`; inspect `/etc/software-factory/image-info`,
`sudo journalctl -u cloud-final` and masked Docker/containerd state. Never attach factory storage,
enroll credentials or select images on the builder. Host packages use signed repositories; AWS CLI
uses its approved official ARM64 HTTPS installer without detached-signature verification.
On success, finalize explicitly; this clears host identity and powers off:

```sh
sudo systemd-run --unit factory-finalize-image --on-active=5s /usr/local/sbin/factory-finalize-image
```

Back on the operator computer, capture only after successful finalization and shutdown:

```sh
aws ec2 wait instance-stopped --instance-ids "$BUILDER"
AMI=$(aws ec2 create-image --instance-id "$BUILDER" --name "software-factory-base-${VERSION:?}" --query ImageId --output text)
aws ec2 wait image-available --image-ids "$AMI"
aws ec2 describe-images --owners 172318459814 --image-ids "$AMI" --query 'Images[*].[ImageId,Architecture,State,BlockDeviceMappings]'
```

Record AMI/parent/source/tool versions and backing snapshot. Test a disposable AMI host with scratch
storage: fresh identity, SSM, mounts/sentinel/modes, factory Docker access, reboot, missing-storage
failure and stopped execution. Remove test hosts, then destroy only the builder stack;
AMI/snapshot survive independently and require separate deletion approval.

Select the tested account-owned ARM64 AMI with `--parameters FactoryAmi="$AMI"` on
`npm run cdk -- diff --exclusively software-factory`, then approved `deploy --exclusively software-factory`.
Replacement requires approval, a stopped/inspected old host and clean detachment of its exact retained volume.
On the new host, `sudo cloud-init status --wait` and `sudo /usr/local/sbin/factory-host-check`
establish readiness, not stack completion. Storage must mount before Docker starts; failures stay closed.
Baked helper/package/unit changes require a tested replacement AMI, not runtime copying.
Retained EBS/ECR and AMI snapshots incur charges; retention is not backup or cross-AZ portability.

## EC2 image publication

On the operator computer, use AWS CLI and a local native ARM64 Docker engine:

```sh
export AWS_PROFILE=AWSAdministratorAccess-172318459814 AWS_REGION=eu-central-1 AWS_DEFAULT_REGION=eu-central-1
./scripts/verify
./scripts/publish-image runner runner-v1
./scripts/publish-image agent agent-v2
```

Publish either image independently with an explicit version. The script checks account/platform,
builds, smoke-tests and pushes with temporary ECR login state. Record immutable digests and source
commit; OCI revision identifies the base commit, not uncommitted changes. Tags are mutable;
there are no automatic updates, image deletion or rollback/retention guarantees.

On EC2, check `sudo /usr/local/sbin/factory-host-check`. Keep service, containers and native runners
stopped while pulling and configuring images; never start as an installation test. As factory,
set `RUNNER_IMAGE` and `AGENT_IMAGE` to the published ECR references, for example
`172318459814.dkr.ecr.eu-central-1.amazonaws.com/software-factory-runner:runner-v1` and
`172318459814.dkr.ecr.eu-central-1.amazonaws.com/software-factory-agent:agent-v2`.
Digest references remain supported. Pull using the instance role:

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
  docker --host unix:///var/run/docker.sock pull --platform linux/arm64 "${RUNNER_IMAGE:?}"
  docker --host unix:///var/run/docker.sock pull --platform linux/arm64 "${AGENT_IMAGE:?}"
)
```

Never copy operator AWS credentials to EC2 or mount ECR login state into runner/agent containers.

### Stopped-host configuration

As factory, record the references directly in `deployment.env` while stopped. Set TOML `agent_image`
to the same `AGENT_IMAGE`; runner configuration stays outside TOML. Startup checks local availability
and platform; there is no separate selection smoke test.

```bash
(
  set -euo pipefail; umask 077
  state="$HOME/.config/software-factory"
  test ! -L "$state"; mkdir -p "$state"
  test ! -L "$state/deployment.env"; test ! -d "$state/deployment.env"
  work=$(mktemp "$state/.deployment.XXXXXX")
  trap 'rm -f -- "$work"' EXIT
  printf 'RUNNER_IMAGE=%s\nAGENT_IMAGE=%s\n' "${RUNNER_IMAGE:?}" "${AGENT_IMAGE:?}" > "$work"
  mv -f -- "$work" "$state/deployment.env"
)
```

## Explicit start

After image configuration/authentication, keep TOML factory-owned, mode **0600**, at
`/home/factory/.config/software-factory/factory.toml`; its agent reference must match `AGENT_IMAGE`.
The launcher binds same-path `/home/factory/artifacts`, read-only App/config state, writable Pi
state and the local socket with its supplementary GID. It never pulls images or changes configuration.
**Inspect all eligible `agent:implement` issues and [recovery state](#manual-inspection-and-recovery)
before authorizing execution.** Run only one runner per repository. From the administrative SSM shell:

```sh
sudo systemctl start software-factory.service
```

Confirm [validated startup](#operational-health), not just service liveness. Startup has a five-minute
limit. The service is static with `Restart=no`: preparation, image configuration, reboot and crashes
never authorize a start. Inspect container-name conflicts rather than removing them implicitly.

## Operational health

Read-only inspection; never trigger inference or issues as a probe. From administrative SSM:

```bash
sudo systemctl show software-factory.service --property=ActiveState,SubState,Result,ExecMainStatus,ExecMainStartTimestamp
sudo journalctl -u software-factory.service --no-pager -n 30
```

As factory (`sudo -iu factory`), compare the actual runner image ID with the local ID resolved from
`RUNNER_IMAGE` using `docker image inspect`; a mutable tag may have changed since startup.
`AGENT_IMAGE` is configuration, not evidence of a running agent. An absent runner is expected when stopped.

```bash
set -euo pipefail
grep -E '^(RUNNER_IMAGE|AGENT_IMAGE)=' "$HOME/.config/software-factory/deployment.env"
find "$HOME/.local/state/software-factory" -maxdepth 2 -name runner.log -print
docker --host unix:///var/run/docker.sock container inspect --format 'runner={{.Config.Image}} image_id={{.Image}} status={{.State.Status}}' software-factory
```

Set `LOG` to the journal's path for this invocation, not an older successful start or newest filename:

```bash
set -euo pipefail
: "${LOG:?set the confirmed invocation runner.log path}"
grep -E '"event": "(runner_polling|runner_failed|runner_interrupted)"' "$LOG"
grep -E '"event": "(poll_started|poll_failed|issue_eligibility_failed|run_started|phase_started|issue_succeeded|issue_failed|issue_interrupted|cleanup_failed|publication_completed|publication_observation_failed|diagnostics_retained|failure_reporting_failed)"' "$LOG" | tail -n 40
```

| State/evidence | Interpretation |
| --- | --- |
| `inactive/dead` | Stopped; inspect result/exit status and invocation evidence to establish why. |
| `failed`, non-success result, `runner_failed` or launcher error | Inspect startup log; `activating` still awaits validation. |
| `active/running` + this invocation's `runner_polling` | Startup validation passed, not proof of current provider access. |
| `poll_started` / `poll_failed` | Poll attempt / error; no polling-success heartbeat. Polling pauses during issue runs. |
| `issue_eligibility_failed` | Generated ticket or dependency lookup needs inspection; its trigger label remains. |
| `run_started` / `phase_started` | Issue-run identity, private diagnostic location and progress. |

Missing/stale evidence, no matches or access errors mean **inspect**, not healthy. Liveness proves
neither GitHub/Copilot access, inference, cleanup nor publication. Follow [recovery](#manual-inspection-and-recovery)
for run failures/uncertain writes; successful workspaces may already be removed.

## Authentication

Use the existing [enrollment steps](authentication-steps.md) for App/Pi files and TOML.
Keep configuration/App directories factory-owned **0700**, credential files **0600**, without symlinks.
The App installation needs metadata read and contents/issues/pull requests read/write, not workflow-write;
API and HTTPS Git use this identity, never personal `gh` login or inherited-token fallback.
Use the selected runner image for Pi enrollment, mounting only Pi state—not Docker or workspaces.
A Pi `ready` result is not proof of live inference or unattended refresh.

Credentials persist across stops; scoped App tokens renew automatically. On access failure, stop,
repair access/enrollment and explicitly restart. For key rotation, stop/clean work, replace with the
same modes, validate, then revoke the old key upstream. On compromise, revoke upstream immediately,
stop runner/agents and inspect; deleting local files does not revoke issued tokens. Backups are
secret-bearing; never restore workspaces as resumable state.

## Shared image and target preparation

Targets supply executable, noninteractive `./scripts/setup` and `./scripts/verify` matching target CI.
Use the [shared image](agent-image.md); setup failure is not automatically repaired.

- Run builds/setup as factory with writable container-local home/caches, `sudo -n` only for system
  installs. No host installs, macOS dependency directories or workspace permission repair.
- Use ordinary application Compose services and native ARM64 images/tools. Targets inherit
  `DOCKER_DEFAULT_PLATFORM=linux/arm64`; explicit overrides are not intercepted and may invoke emulation.
- Preserve matching `FACTORY_RUN_ID`/`COMPOSE_PROJECT_NAME`; label directly created containers/networks/volumes
  with `--label "software-factory.run-id=$FACTORY_RUN_ID"`. Other contexts/unlabeled resources bypass cleanup.
- Service-private data belongs in disposable owned volumes; workspace writers need compatible permissions.
  Shared images/cache are not disposable. Avoid fixed names/ports; use Compose DNS or host-published ports,
  not the agent's localhost. Workspace bind paths must match host paths.

## Diagnostics and safety

Runner logs are INFO JSON Lines on stderr: UTC `timestamp`, `level`, `event`, `message` and selected
repository/issue/phase/run/PR context. The service retains them in private `start-*/runner.log` files;
Docker logging is disabled, so use [health inspection](#operational-health), not `docker logs`.
Command output stays in retained `/home/factory/artifacts/issue-*/run.log` diagnostics
(**0700** directories, **0600** files). Keep credentials/logs/transcripts private; redaction is not a guarantee.
Logs survive container replacement, are not recovery state and are never implicitly deleted.
[logging.ini](../logging.ini) provides equivalent development defaults.

## Stop for maintenance

Prefer stopping while idle using [health evidence](#operational-health); this is not race-free draining.
Stopping during a run interrupts it. From administrative SSM, wait for the bounded stop:

```sh
sudo systemctl stop software-factory.service
```

Docker allows 120 seconds, including the runner's 60-second cleanup budget; systemd allows 150.
Then inspect [service/log evidence](#operational-health): expect stopped state and `runner_interrupted`
(exit 130 is accepted). Stop/cleanup errors or missing evidence require intervention, not forced removal.
Service exit alone does not prove resource cleanup; retain failed diagnostics and follow recovery below.
Do not automatically restart, requeue or resume interrupted work.

## Manual inspection and recovery

1. **[Stop](#stop-for-maintenance) and wait before manual cleanup.**
2. **Inspect retained evidence as factory.** `run_started`/`diagnostics_retained` name the issue,
   run identity and private directory. Never execute retained workspace scripts on the host.
3. **Identify leftovers using the startup Docker endpoint.** Explicit `DOCKER_CONTEXT` overrides
   `DOCKER_HOST`; confirm the local endpoint before cleanup. Discover candidates and inspect labels/mounts:

```sh
docker container ls --all --filter 'name=factory-'
docker container inspect '<candidate-id>' --format '{{json .Config.Labels}} {{json .Mounts}}'
# Replace with the confirmed run identity; query both labels separately (OR).
RUN_ID=factory-0123456789abcdef0123456789abcdef
for LABEL in software-factory.run-id com.docker.compose.project; do
    docker container ls --all --filter "label=$LABEL=$RUN_ID" --format '{{.ID}} {{.Names}} {{.Status}}'
    docker network ls --filter "label=$LABEL=$RUN_ID"
    docker volume ls --filter "label=$LABEL=$RUN_ID"
done
```

Confirm network/volume ownership with `docker network inspect` / `docker volume inspect`.
Names alone are not proof; unknown/unlabeled resources need investigation. Match `factory-startup-*`
probes to startup logs rather than inferring ownership from names.

4. **Resolve uncertain publication in GitHub's UI.** Inspect exact `factory/issue-<number>` branch
   and PR head repository, including closed/merged PRs. Failed writes may have succeeded;
   access errors mean unknown. Never replay writes. Inspect orphan commits before deciding on branch deletion.
5. **Remove only confirmed owned resources**, agent first, then other containers, networks and
   disposable volumes. This deletes volume data:

```sh
docker container rm --force '<confirmed-agent-container-id>'
docker container rm --force '<confirmed-other-owned-container-id>'
docker network rm '<confirmed-owned-network-id>'
docker volume rm '<confirmed-disposable-owned-volume-name>'
```

Repeat exact-label listings and confirm agent absence. Errors require intervention, not broader
cleanup: never prune, remove shared resources or recursively chown/chmod the workspace.
Retain failed diagnostics until explicit deletion. Resolve cause/branch/PR state before manually
reapplying `agent:implement` for a fresh attempt; no automatic requeue or resume.
Inspect all eligible issues again before [starting](#explicit-start).

## Docker and CLI tests

On Ubuntu ARM64 as factory 2000:2000, with development dependencies installed separately:

```sh
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
docker build --platform linux/arm64 -f runner/Dockerfile -t software-factory-runner:test .
FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 FACTORY_RUNNER_IMAGE_TESTS=1 ./scripts/verify
```

`FACTORY_AGENT_IMAGE`/`FACTORY_RUNNER_IMAGE` select other prebuilt images. Tests use real Docker/Git
with scripted GitHub/Pi boundaries; [CI](../.github/workflows/verify.yml) runs without host sudo.

## Verification beyond unit tests

Live tests require **explicit approval**. Stop the runner and inspect the test repository first;
activation queues issues and could otherwise start issue runs. Supply a dedicated committed test spec
in `TeroTS/factory-smoke-test` and a matching local ticket plan with a fresh `e2e-` spec ID for
**each run**. Use one publisher and inspect uncertain writes rather than retrying blindly.

```sh
FACTORY_LIVE_PLANNING_TESTS=1 FACTORY_LIVE_TEST_PLAN=/absolute/path/to/plan.json \
  uv run --frozen pytest -s tests/test_planning_publish.py -k live
# Requires AWS credentials for account 172318459814 and a local native ARM64 Docker engine:
FACTORY_LIVE_IMAGE_TESTS=1 uv run --frozen pytest -s tests/test_publish_image.py
```

Tests leave generated issues, trigger labels and uniquely tagged images for operator inspection;
remove or close only confirmed test resources manually before restarting the runner. ECR storage
can incur charges. Failed or interrupted tests can leave partial results; inspect before retrying.
AWS host acceptance must inspect cloud-init, retained mounts, factory Docker access and stopped
execution; scripted checks do not prove first boot.
