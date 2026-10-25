# Autonomous Coding Factory

A local Python runner turns GitHub issues labeled `agent:implement` into verified
draft PRs using one factory-maintained Linux agent image and Pi/Copilot. GitHub
holds durable coordination; there is no database, HTTP server, or hosted deployment.
Human review and independent target CI remain required; the factory never merges.

**Current delivery: US-04 startup and US-05 first-pass execution.** The temporary
pre-claim guard is removed: already-labeled issues are eligible when the runner
starts. Inspect labels before upgrading. A completed verification failure currently
fails the run; bounded verification repairs (US-06) and the full manual-requeue
acceptance scenario (US-07) remain deferred. Historical US-01–US-03 acceptance
belongs to the previous runtime, not this execution model.

Root plus Docker engine access grants effective engine control and potentially
host control. The agent environment is **not a security boundary** protecting
host files, credentials, or other containers. Ordinary credential/mount separation
cannot prevent deliberate Docker-mediated access.

## Quick start

Development prerequisites:

- Python **3.14.3**, selected by [`.python-version`](.python-version).
- **uv 0.5.13**, Make, a POSIX shell, and Git.
- Local native ARM64 Docker with Compose for integration checks. Ordinary local
  verification needs neither Docker nor service credentials.

Install tools separately, then run from the repository root:

```sh
./scripts/setup
uv run --frozen python -m software_factory --help
./scripts/verify
```

Setup uses `uv sync --locked` to install the editable package and locked development
dependencies in `.venv`. It does not install global tools or provision credentials.
Help does not start polling.

## Development and testing

[Makefile](Makefile) owns commands; the scripts work from any working directory.

| Command | Purpose |
| --- | --- |
| `./scripts/setup` | Synchronize dependencies; reject a stale lockfile. |
| `./scripts/verify` | Ruff format check → Ruff lint → Python coverage/tests, including the Pi bridge. |
| `make format` | Apply Ruff formatting. |
| `make format-check` | Check formatting without modifying files. |
| `make lint` | Check Ruff lint rules. |
| `make test` | Run pytest without coverage enforcement. |
| `make coverage` | Run Python coverage checks, including the Pi bridge. |
| `uv run --frozen pytest tests/test_runner.py tests/test_sandbox.py -q` | Focused execution, failure, and cleanup checks. |

Python overall line/branch coverage, including the standalone Python Pi bridge,
must meet its **80%** gate. Do not lower it or exclude business logic. Node.js
remains in the shared image for Pi and target tooling; host verification does not
require Node.js. Reports, workspaces, and caches are ignored. No standalone type checker or Markdown linter
is configured. Packaging uses pinned Hatchling; there is no release workflow.

Build the shared image explicitly before running the native Docker suite:

```sh
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 ./scripts/verify
```

`FACTORY_AGENT_IMAGE` overrides the already-built fixture image reference for both
Docker suites. [CI](.github/workflows/verify.yml) uses `ubuntu-24.04-arm`, Python
3.14.3 and uv 0.5.13; it explicitly builds the image before verifying.
The runner itself never builds/pulls the shared image.

[Docker tests](tests/test_docker_integration.py) exercise actual target builds,
ordinary Compose services, service-backed verification, a target-installed npm
tool, same-path sibling mounts, socket access, host file usability, exact ownership
cleanup, preservation of an unrelated sentinel container/network/volume, and
use of the image's original Docker executable with the native platform default.
[Issue E2E tests](tests/test_issue_docker.py) run the real CLI with a labeled fixture
issue through publication to a local Git remote and a scripted draft-PR response;
they also interrupt setup using SIGTERM. Pi/authentication/GitHub are scripted,
not live service acceptance. Tests remove only their own fixtures; factory cleanup
leaves application images/build cache intact.

Obsolete prepared-Compose helpers, fixtures, skipped orchestration/requeue tests,
and historical live harnesses are removed. Their scenarios remain in git history
for US-06/US-07; there is no compatibility backend.

## Operator setup

Startup requires Git, authenticated GitHub CLI, authenticated host Pi/Copilot
(tested Pi **1.3.0**), and a running **local native Linux ARM64** Docker engine.
Apple Silicon with Rancher Desktop/Docker Desktop is supported; remote engines
and factory-selected emulation fallbacks are not. Docker must use an absolute
local Unix socket endpoint.
Explicit `DOCKER_CONTEXT` takes precedence over `DOCKER_HOST`; otherwise the host
override or active context selects the engine. Authentication/access approval
remains manual. Only one runner may operate on a configured repository; labels
are not a distributed lock.

1. Build the credential-free [shared image](agent/README.md):

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

   Startup checks artifact-root usability, host tools, local engine architecture,
   GitHub authentication, Copilot bearer endpoint/lifetime, local image architecture,
   and actual native host-user/tool execution with writable home/caches and `sudo -n`. The uniquely named startup probe has no
   network, mounts, or credentials and receives bounded cleanup on failure/stop.
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
   verification run as the host UID/GID inside one fresh agent. All work, including installations,
   builds, cleanup before publication, and publication, consumes that deadline.
   Missing entrypoints, setup/provider/lifecycle errors, or failed verification
   fail visibly without repair in this delivery.

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

## Shared image and target preparation

[agent/README.md](agent/README.md) documents pinned baseline tools and build checks.
Targets need executable, deterministic, noninteractive `./scripts/setup` and
`./scripts/verify`; verification must align with target CI. Setup installs any
nonbaseline tools/browser binaries **inside the agent**, not on the host. Both
scripts must exist before implementation; there is no setup repair or Pi bootstrap.
Do not reuse host macOS `.venv`/`node_modules` as Linux dependencies.

Setup, Pi, and verification run as your numeric host UID/GID, with a writable
container-local home, caches, and user-local tool path. Use explicit `sudo -n` for
system installs, not whole setup scripts or project builds. Permission errors do
not trigger automatic elevation. For example:

```sh
sudo -n apt-get update
sudo -n apt-get install -y libpq-dev
npm ci
uv sync --frozen
```

**Upgrade:** explicitly rebuild the shared image and restart the runner. Older
images without configured `sudo` fail startup. Adapt setup scripts that assumed
root; global npm installs now use the user-local prefix. Fixed trusted root code
initializes only the container account/home and socket groups, not the workspace.
UID-only Docker exec resolves the configured primary/supplementary groups. Running
the host runner as UID 0 still means root; UID matching is not a security boundary.

The agent mounts the workspace at its same absolute host/container path and
connects to the selected local engine. On macOS the engine-side socket mount is
`/var/run/docker.sock`, not the host provider's proxy socket. On Linux it uses the
resolved local socket path. Only the workspace and engine socket are ordinary
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
current filesystem until removed; the host-user/sudo change requires the explicit
image rebuild and runner restart described above.

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

Standard-library logging emits WARNING and above to stderr; [logging.ini](logging.ini)
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

Docker/CLI tests use real local dependencies and scripted Pi/GitHub boundaries;
they make no live Copilot request or GitHub write. ARM64 CI cannot prove desktop
sharing/networking. The [current slice](docs/slices/current-slice.md) records local
provider/browser evidence, exact commands, coverage, and outstanding gaps.

No live authenticated probe is enabled by these commands. Historical live
harnesses are removed; any new Copilot/GitHub-writing demonstration requires
separate explicit approval. US-06 recovery and US-07 manual-requeue acceptance
remain future work; historical acceptance is not evidence for them.

## Architecture and repository structure

[Architecture](docs/architecture/service-architecture.md),
[workflow](docs/workflows/issue-to-draft-pr.md), [spec](SPEC.md), and
[contracts](docs/contracts.md) describe the shared-image boundaries.

- `agent/`: pinned shared-image build definition/instructions.
- `src/software_factory/`: CLI/config/startup, serial orchestration, Docker lifecycle,
  Pi bridge, GitHub, trusted Git, process/deadline boundaries.
- `tests/`: unit, real Git/process, native Docker/service and scripted CLI E2E checks.
- `scripts/`, `Makefile`, `.github/workflows/verify.yml`: development and ARM64 CI.
- `SPEC.md`, `DECISIONS.md`, `CONTEXT.md`, `docs/contracts.md`: accepted behavior,
  decisions, vocabulary, and interfaces.
- `docs/slices/current-slice.md`: single active delivery brief and evidence.
