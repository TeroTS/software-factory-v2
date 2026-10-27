# Operator guide

Setup, target requirements, diagnostics, and extended verification.

## Operator setup

For a Linux host, use the [Lima configuration](../infra/lima/factory.yaml). Stop
Rancher Desktop before starting this VM:

```sh
limactl start --name=factory --tty=false infra/lima/factory.yaml
limactl shell factory
```

Transfer a trusted checkout onto the guest's Linux disk using SSH or clone it
there. From that checkout, explicitly provision/check the host as administrator:

```sh
sudo ./scripts/provision-host
sudo ./scripts/provision-host --check
```

Initial authentication is operator-controlled; provisioning does not authenticate.
Provisioning failures report a private command-log
path; inspect it without publishing transcripts. For HTTPS trust failures, obtain
operator approval for the correct CA rather than disabling verification.

Run inside the provisioned **Ubuntu 24.04 LTS ARM64 Lima guest** as `factory`,
with effective UID/GID **2000:2000**. Root, other identities, other host operating
systems/releases, and direct macOS runner execution are rejected before polling.
Startup requires Git, GitHub CLI, OpenSSL, curl, private GitHub App credentials,
authenticated host Pi/Copilot (tested Pi **1.3.0**), and a running
**local native Linux ARM64** Docker engine.
Remote engines and factory-selected emulation fallbacks are unsupported. Docker
must use an absolute local Unix socket endpoint. Keep the checkout and artifacts
on the guest's Linux disk; do not execute from macOS shared folders.
Explicit `DOCKER_CONTEXT` takes precedence over `DOCKER_HOST`; otherwise the host
override or active context selects the engine. Authentication/access approval
requires operator approval. Complete [authentication setup](#authentication)
before starting. Only one runner may operate on a configured repository; labels
are not a distributed lock.

1. Log in as the provisioned factory account (for example, an administrator can
   explicitly run `sudo -iu factory`), then use a factory-owned checkout on the
   guest's Linux disk. Build the credential-free [shared image](../agent/README.md):

   ```sh
   docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
   ```

2. Write trusted operator TOML outside the target checkout and run workspace,
   for example `artifacts/operator/factory.toml`:

   ```toml
   repository = "TeroTS/factory-smoke-test"
   model = "gpt-6.1-sol"
   agent_image = "software-factory-agent:1.0.0"
   artifacts_dir = "../runs"
   ```

   Exactly these four nonempty strings are required, without defaults/credentials.
   `repository` is GitHub.com `owner/name`, not a URL. `model` is an exact accessible
   `github-copilot` model ID, without provider prefix, patterns, or provider fallback.
   Relative artifact paths resolve against the TOML directory. No `.env` is loaded.
   Legacy `compose_file`/`compose_service` input is rejected with migration guidance;
   there is no automatic migration or target-specific factory Compose configuration.

3. Prepare the target as described below, inspect trigger labels, then start:

   ```sh
   uv run --frozen python -m software_factory --config /absolute/path/to/factory.toml
   ```

   Startup first validates the supported host and effective identity, then checks
   artifact-root usability, host tools, local engine architecture, GitHub App
   repository access, Copilot bearer endpoint/lifetime, local image architecture,
   and actual baked factory account/home/caches/npm prefix, native tools, and
   `sudo -n` with root HOME. The startup probe uses the image's default identity
   without runtime account initialization. Rebuild old/incompatible images and
   restart; startup never switches accounts or repairs permissions.
   Cleanup errors block startup; inspect named `factory-startup-*` leftovers only.

   The image resolves once to an immutable session ID. Restart to adopt a rebuilt
   tag; missing/incompatible images fail without build, pull, or fallback. Previous
   artifacts are never moved/deleted. New artifact roots are mode 0700; existing
   directory permissions are not silently changed.

4. Polling is serial at 30-second intervals. A labeled issue first receives exact
   open-PR/remote-branch checks for the configured head repository and
   `factory/issue-<number>`. Confirmed trigger removal precedes execution or skip
   notification. Existing PRs are preserved/linked; orphan branches block execution
   and require operator cleanup and label reapplication. The factory never overwrites
   or deletes remote branches.

5. A clear issue gets running status, an immutable title/body snapshot, a fresh
   default-branch workspace, and one original 900-second deadline. Setup → Pi →
   verification run as the baked factory account (2000:2000) inside one fresh agent.
   Before setup, the runner validates actual exec identity and Docker access using
   the selected socket's numeric GID, supplied at creation with `--group-add`.
   It does not initialize accounts, override the exec user, or retry as root.
   All work, including installations, builds, cleanup before publication, and
   publication, consumes that deadline.
   Missing entrypoints, setup/provider/lifecycle errors, or failed verification
   fail visibly without automatic repair.

6. The runner removes the agent and known owned services/resources, then confirms
   host access required for publication without changing workspace ownership/modes.
   It publishes only passing, nonempty changes with time remaining. Trusted
   host Git creates the absent factory branch, then a draft PR with `Closes #N`.
   Cleanup or required-access failure blocks publication. Uncertain push/PR results receive bounded
   read-only inspection rather than write retries. Status-reporting failures remain
   visible locally even if a branch/PR was already created.

7. Ctrl-C/SIGTERM attempts bounded cleanup, reports interruption when possible,
   retains diagnostics, and exits **130**. Startup failures exit nonzero with safe
   stderr diagnostics. Failure/stop/restart never restores a trigger or resumes
   retained work. Unknown resources and hard-crash leftovers need manual inspection.

## Authentication

Run this setup **inside the VM as factory**, not as the default Lima login user:

```sh
sudo -iu factory
cd "$HOME"
id  # require 2000:2000
```

### GitHub App (one-time)

1. In GitHub settings, open the installed App, record its App ID and installation
   ID, and generate/download a private key. The installation must include the target
   repository, with metadata read and contents/issues/pull requests read/write.
   Do not grant workflow-write permission.
2. Transfer the key privately to
   `/home/factory/.config/software-factory/github-app.pem`. Keep it outside checkouts,
   artifacts, images, and agent workspaces. Directory mode must be 0700 and key mode
   0600, owned by factory; symlinks are rejected. Never paste key contents into chat.
3. Create the sibling `github-app.json`, also mode 0600. For the approved
   `factory-example` installation, its complete content is:

   ```json
   {"app_id": 5430144, "installation_id": 174237987}
   ```

   These IDs are not secrets. Use your own installation's IDs for another target.
   The operator TOML still has exactly four fields; do not put credentials in it.

The runner signs a short-lived App JWT with OpenSSL and requests an installation
access token restricted to the configured repository and required permissions.
Token exchange uses curl with an explicit Bearer header supplied over stdin;
`gh`'s automatic token scheme is not suitable for App JWTs.
API requests and trusted HTTPS Git share this identity; inherited personal tokens
and saved personal `gh` login are not fallbacks. No `gh auth login` is required.
Tokens stay in memory and explicit host subprocess environments, not Git URLs or
arguments. Startup confirms repository access before polling. Local file checks
and read-only access do not prove every remote write will succeed.

### Pi/Copilot (one-time)

1. Start `pi --no-extensions --no-mcp --no-skills --no-context-files --no-session`
   from the factory home directory.
2. Enter `/login`, choose GitHub Copilot, and follow the device/browser flow using
   the approved GitHub identity (`TeroTS` for this installation). Open the supplied
   URL on your Mac if the VM cannot open a browser. Do not send an implementation task.
3. Exit Pi, then check without printing tokens:

   ```sh
   chmod 700 "$HOME/.pi/agent"
   chmod 600 "$HOME/.pi/agent/auth.json"
   pi auth check --provider github-copilot --no-extensions --no-mcp --no-context-files
   ```

Pi manages persistent login/refresh state in the factory home. Keep its default
agent directory for both login and runner execution; do not authenticate as root
or the default Lima user. A ready check is not a live inference/refresh acceptance
check. The agent receives only the short-lived Copilot bearer over stdin.

### Restart, expiry, rotation, and revocation

- **Stop/start:** host files remain; GitHub tokens are reacquired after restart and
  renewed before operations when at most 20 minutes remain. Pi performs supported
  refresh. No interactive login is attempted by the runner.
- **Unavailable/expired authorization:** operations fail safely without switching
  accounts or blindly replaying writes. Active failures still attempt cleanup.
  Stop the runner, fix access or log in to Pi again, then restart. Inspect uncertain
  remote writes before explicitly reapplying an issue's trigger label.
- **Planned App key rotation:** stop the runner and finish/clean active work;
  generate and privately replace the host key, preserve ownership/modes, validate
  the replacement, then revoke the old key in GitHub. Restart only after setup is
  correct. Do not delete the old authorization before a replacement is available
  unless responding to compromise.
- **Emergency:** revoke the affected App key/installation or Copilot authorization
  upstream, stop the runner/active agents, and inspect retained resources before
  replacing credentials. Previously issued tokens may remain usable until expiry;
  do not assume deleting a local file revokes them.
- **Host replacement/backups:** explicitly enroll the replacement host. Do not copy
  credentials through Git or restore failed workspaces as execution state. Treat
  any host backup or downloaded key copy as secret-bearing operator storage.

Private files are not encrypted storage. Docker access grants effective host
control, so these credentials are not protected from a malicious Docker-enabled
agent. App permissions also allow more than the runner intentionally does: branch
protection/stronger permission separation are deferred for the MVP. The runner
never merges or deploys and blocks `.github/workflows/` changes before commit.
Live GitHub/Copilot tests still require separate operator approval.

## Shared image and target preparation

The [image reference](agent-image.md) documents pinned baseline tools, reviewed TDD
and Ponytail full skills, provenance, and build checks. Both complete skills are loaded
for implementation; discovered/configured skills remain disabled. Rebuild the
shared image and restart after skill updates; missing or incompatible skill bundles
block startup/invocation. Skill loading does not prove model adherence to TDD.
Targets need executable, deterministic, noninteractive `./scripts/setup` and
`./scripts/verify`; verification must align with target CI. Setup installs any
nonbaseline tools/browser binaries **inside the agent**, not on the host. Both
scripts must exist before implementation; there is no setup repair or Pi bootstrap.
Do not reuse host macOS `.venv`/`node_modules` as Linux dependencies.

Setup, Pi, and verification run as factory UID/GID **2000:2000**, with a writable
container-local home, caches, and user-local tool path. Use explicit `sudo -n` for
system installs, not whole setup scripts or project builds. Permission errors do
not trigger automatic elevation. For example:

```sh
sudo -n apt-get update
sudo -n apt-get install -y libpq-dev
npm ci
uv sync --frozen
```

**Upgrade:** explicitly rebuild the shared image and restart the runner. It bakes
in factory 2000:2000, home/caches, the npm prefix, and account-scoped sudo; images
from the arbitrary-host-user model are incompatible. There is no automatic
account/configuration/artifact migration. Setup scripts must use explicit `sudo -n`
for system installs and the user-local prefix for npm tools. Workspace ownership
and permissions are never repaired automatically. Matching numeric user IDs is
not a security boundary.

The agent mounts the workspace at its same absolute host/container path and
connects to the selected local engine. The engine socket mount uses the
resolved local Linux socket path. Only the workspace and engine socket are ordinary
binds; host Git metadata, GitHub publication credentials, broader Pi settings, and
refresh credentials are not normal agent inputs. Copilot bearer delivery is stdin
only, using validated endpoint metadata and exact-model nonpersistent invocation.

Use ordinary application/dependency Compose definitions and native `linux/arm64`
images/tools. Startup validates a native ARM64 engine/shared agent image;
factory-owned containers explicitly request `--platform linux/arm64` and
`--pull=never`. Target commands inherit `DOCKER_DEFAULT_PLATFORM=linux/arm64`
and use the image's unmodified Docker executable directly. The factory does not
intercept Docker commands or guarantee rejection of explicit platform overrides,
which may invoke emulation if the operator's engine supports it. Actual
Docker/setup/verification failures remain visible; the factory never selects an
emulation fallback or substitutes dependencies. Existing containers retain their
current filesystem until removed; rebuilding an image does not update them.

Ordinary Compose commands inherit unique matching `FACTORY_RUN_ID` and
`COMPOSE_PROJECT_NAME`. Direct container/network/disposable-volume creation must
use `--label "software-factory.run-id=$FACTORY_RUN_ID"`. Keep these identities;
explicit project overrides, unlabeled calls, and other contexts bypass cleanup.
Avoid fixed container names/ports or adapt them for each run. External/shared
resources, images, and build cache are not disposable run resources. Put
service-private data in disposable owned volumes; services writing workspace binds
must use compatible UID/GID and permissions.

Select explicit service addresses: Compose DNS after joining the relevant network,
or the Docker host address for published ports. Sibling services do not share the
agent's localhost, and automatic forwarding/network attachment is not provided.
Same-path mounts let sibling containers resolve relative workspace bind mounts.
The factory does not promise arbitrary repositories run unchanged.

## Diagnostics and safety

Standard-library logging emits WARNING and above to stderr; [logging.ini](../logging.ini)
provides optional development defaults. Command output belongs only in private
run logs. New run directories use 0700 and logs 0600, with known-credential redaction.
Never post transcripts or secrets. Failed workspaces/logs remain retained until
operator deletion, not recovery state. Successful diagnostics may be removed.
Deleting artifacts does not stop leftover Docker resources.

Cleanup uses exact `software-factory.run-id` or `com.docker.compose.project` labels
and host-owned agent identity, never mutable target Compose teardown files. It
removes owned containers before networks/disposable volumes. It never recursively
changes workspace ownership or permissions. Required host publication access is
checked after cleanup; inaccessible required files/directories block publication.
Ignored caches need not be writable. Deliberately restricted retained files may
need manual operator inspection; private host-owned run logs remain separate.
Cleanup has a separate bounded budget after expiry/stop; this never extends
coding/publication allowance. Untracked resources and hard-crash leftovers need operator inspection;
never use daemon-wide pruning. Independent target CI and human review remain
mandatory, even after passing local verification.

## Verification beyond unit tests

The explicit host-provisioning E2E, `FACTORY_PROVISION_TESTS=1 uv run --frozen pytest
tests/test_provision_lima.py -q`, installs/checks the existing authorized Lima instance
named `factory` as administrator and repeats provisioning to check data preservation.
It does not allocate a VM or authenticate. Enable it only with explicit permission
to modify that guest; it is not an ordinary non-mutating test. Configuration-only
validation skips where Lima is absent.

Docker/CLI tests use real local dependencies and scripted Pi/GitHub boundaries;
they make no live Copilot request or GitHub write. Run them as factory 2000:2000
inside the Lima guest; Linux CI alone does not verify macOS-to-VM service access.
Live authenticated checks require separate explicit approval.

## Docker and CLI tests

Build the shared image explicitly before running the native Docker suite:

```sh
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 ./scripts/verify
```

Run these Docker/CLI checks inside the provisioned Ubuntu 24.04 ARM64 guest as
`factory` (UID/GID **2000:2000**). Unit checks can still run on a development host.
`FACTORY_AGENT_IMAGE` overrides the already-built fixture image reference for both
Docker suites. [CI](../.github/workflows/verify.yml) uses `ubuntu-24.04-arm`, Python
3.14.3 and uv 0.5.13; it stages a fresh factory-owned checkout and explicitly builds
the image and verifies as `factory` 2000:2000, without granting host sudo to that account.
The runner itself never builds/pulls the shared image.

[Docker tests](../tests/test_docker_integration.py) exercise actual target builds,
ordinary Compose services, service-backed verification, a target-installed npm
tool, same-path sibling mounts, socket access, host file usability, exact ownership
cleanup, preservation of an unrelated sentinel container/network/volume, and
use of the image's original Docker executable with the native platform default.
[Issue E2E tests](../tests/test_issue_docker.py) run the real CLI with a labeled fixture
issue through publication to a local Git remote and a scripted draft-PR response;
they also interrupt setup using SIGTERM. Pi/authentication/GitHub are scripted,
not live service acceptance. Tests remove only their own fixtures; factory cleanup
leaves application images/build cache intact.

See the [README](../README.md) for development commands.
