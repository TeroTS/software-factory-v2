# Autonomous Coding Factory

A local Python runner is being refactored to turn GitHub issues labeled
`agent:implement` into verified draft PRs using one factory-maintained Linux agent
image and Pi/Copilot. GitHub holds durable coordination; there is no database,
HTTP server, or hosted deployment. Human review and independent target CI remain
required; the factory never merges.

**Current delivery: US-04 startup only.** The operator-approved temporary guard
allows validated startup and read-only polling, but does not claim or execute
issues until US-05 lands. It leaves labels, comments, branches/PRs, and previous
artifacts unchanged and reports unavailable execution locally. The previous
prepared-Compose backend is not selectable. Historical US-01–US-03 acceptance
applies to that previous runtime, not the new execution model.

Docker engine access grants effective engine control and potentially host
control. The planned agent environment is **not a security boundary** protecting
host files, credentials, or other containers. Ordinary credential/mount separation
cannot prevent deliberate Docker-mediated access.

## Quick start

Development prerequisites:

- Python **3.14.3**, selected by [`.python-version`](.python-version).
- **uv 0.5.13**, Make, a POSIX shell, and Git.
- **Node.js 22.19+**; CI uses **22.19.0**.
- Local native ARM64 Docker with Compose for integration checks. Ordinary local
  verification does not need Docker or service credentials.

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

[Makefile](Makefile) owns the development commands. The scripts work from any
working directory.

| Command | Purpose |
| --- | --- |
| `./scripts/setup` | Synchronize dependencies; reject a stale lockfile. |
| `./scripts/verify` | Ruff format check → Ruff lint → Python coverage/tests → Node bridge coverage/tests. |
| `make format` | Apply Ruff formatting. |
| `make format-check` | Check formatting without modifying files. |
| `make lint` | Check Ruff lint rules. |
| `make test` | Run pytest without coverage enforcement. |
| `make coverage` | Run Python and Node coverage checks. |
| `uv run --frozen pytest tests/test_config.py tests/test_startup.py -q` | Focused US-04 configuration/startup/guard checks. |

Python overall line/branch coverage and Node line/branch/function coverage must
meet their **80%** gates. Do not lower them or exclude business logic. Reports,
workspaces, and caches are ignored. No standalone type checker or Markdown linter
is configured. Packaging uses the pinned Hatchling backend; there is no release
workflow.

The new startup tests use scripted authentication/GitHub responses, not live
Copilot requests or GitHub writes. For real local ARM64 image and CLI-to-polling
checks, build the image explicitly first:

```sh
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 \
  FACTORY_E2E_APPROVED=0 FACTORY_COPILOT_TESTS=0 \
  FACTORY_SMOKE_SANDBOX_TESTS=0 ./scripts/verify
```

`FACTORY_AGENT_IMAGE_TESTS=1` requires that already-built image; override its name
with `FACTORY_AGENT_IMAGE` if needed. The tests run the real CLI, TOML loader,
Docker/image checks, native tool execution, startup cleanup, polling, and SIGTERM
exit. Host authentication and GitHub discovery are scripted; one variant discovers
a labeled issue and proves the guard prevents writes. No target issue is processed.

[CI](.github/workflows/verify.yml) uses `ubuntu-24.04-arm`, Python 3.14.3,
Node 22.19.0, and uv 0.5.13, explicitly builds the shared image, then runs these
checks. A CI build is a development action; the runner never builds/pulls images.

Historical prepared-Compose helper tests still run independently with
`FACTORY_DOCKER_TESTS=1` and disposable `alpine:3.21.3` fixtures (pulled if absent).
They are not acceptance of the new execution model. Old runner orchestration,
requeue, and live smoke tests are explicitly skipped until ported in US-05–US-07.
The old live-harness observation unit tests remain active with scripted boundaries.
The US-05 removal audit must replace/remove obsolete helpers, callers, and fixtures;
there is no runtime backend selector. See [current slice](docs/slices/current-slice.md).

## Operator setup

Startup requires Git, authenticated GitHub CLI, authenticated host Pi/Copilot
(tested Pi **1.3.0**), and a running **local native Linux ARM64** Docker engine.
Apple Silicon with Rancher Desktop/Docker Desktop is supported; remote engines
and AMD64 emulation are not. Docker must use an absolute local Unix socket endpoint.
Explicit `DOCKER_CONTEXT` takes precedence over `DOCKER_HOST`; otherwise the host
override or active context selects the engine. Authentication/access approvals
remain manual. Only one runner may operate on a configured repository; labels
are not a distributed lock.

1. Build the credential-free [shared image](agent/README.md) before startup:

   ```sh
   docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
   ```

2. Write operator-owned TOML outside the target checkout and any future run
   workspace, for example `artifacts/operator/factory.toml`:

   ```toml
   repository = "TeroTS/factory-smoke-test"
   model = "gpt-6.1-sol"
   agent_image = "software-factory-agent:1.0.0"
   artifacts_dir = "../runs"
   ```

   Exactly these four nonempty strings are required, with no defaults or
   credentials. `repository` is GitHub.com `owner/name`, not a URL. `model` is an
   exact account-accessible `github-copilot` model ID, without provider prefix or
   patterns; there is no fallback provider. Relative `artifacts_dir` paths resolve
   against the TOML directory, not the working directory. No `.env` file is loaded.
   Old `compose_file`/`compose_service` input is rejected with migration guidance;
   remove those fields and build/select the shared image. No automatic migration
   or target-specific factory Compose configuration is supported.

3. Start the runner:

   ```sh
   uv run --frozen python -m software_factory --config /absolute/path/to/factory.toml
   ```

   Before polling, startup checks artifact-root usability, host tools, local
   engine architecture, GitHub authentication, Copilot bearer endpoint/lifetime,
   local image architecture, and actual native root/tool execution. The short
   startup probe has no network access, workspace/socket mounts, or credentials
   and is removed with a separate bounded cleanup attempt, including after failure
   or interruption. Cleanup errors block successful startup; inspect any named
   `factory-startup-*` container reported locally, not unrelated resources.

   The image tag is resolved once to an immutable local image ID for the session.
   Rebuilding/retagging it does not update a running session: restart to adopt it.
   Missing/incompatible images fail startup without automatic build, pull, or
   fallback. Startup does not move/delete previous artifacts. A fresh artifact
   root is mode 0700; existing directory permissions are not silently changed.

   Successful startup prints a warning that polling is active and **issue execution
   is disabled until US-05**. Polling occurs serially every 30 seconds. A labeled
   issue produces a local `not claimed` warning only; the trigger remains applied.
   Once US-05 enables execution, existing labeled issues will become eligible for
   processing, so inspect labels before running that later version.

4. Ctrl-C/SIGTERM attempts startup-probe cleanup if active and exits **130**.
   Invalid configuration or startup failures exit nonzero with safe stderr
   diagnostics. Do not treat successful startup as issue-to-PR acceptance.

## Shared image and target preparation

[agent/README.md](agent/README.md) documents pinned tools, Debian snapshot,
build instructions, and checked baseline versions. The image includes Pi,
Node.js/npm, Docker CLI/Compose/buildx, Python/uv, Bash, Git, Make, a C/C++ toolchain,
curl, CA certificates, tar, unzip, and standard Linux utilities. It runs as root
so future target setup can install additional runtimes/tools. No credentials are
baked into image layers.

For US-05, the target will need executable, deterministic, noninteractive
`./scripts/setup` and `./scripts/verify`; verification must align with target CI.
Additional tools/browser binaries belong in target setup, not on the host.
Ordinary target application/dependency Compose definitions replace target-specific
factory agent profiles. Native ARM64, explicit service addresses, same-path bind
mounts, host-usable workspace files, and cooperative resource ownership must be
proved in that slice. Sibling-service localhost is not the agent's localhost.

## Architecture and delivery status

- **US-04:** shared-image startup, new four-field TOML, safe prerequisite failures,
  immutable image resolution, read-only polling, and the temporary pre-claim guard.
- **US-05, deferred:** fresh per-issue environment with engine access, real target
  build/Compose/service-backed verification, scoped cleanup, and host publication.
- **US-06, deferred:** up to three verification repairs in that same environment
  under the original 900-second deadline.
- **US-07, deferred:** fresh explicit manual requeue without session recovery or
  removal of prior failed diagnostics.

[Architecture](docs/architecture/service-architecture.md),
[workflow](docs/workflows/issue-to-draft-pr.md), [spec](SPEC.md), and
[non-HTTP contracts](docs/contracts.md) distinguish active startup from target
execution. No factory-owned HTTP API or generated client exists.

## Diagnostics and safety

Standard-library logging emits WARNING and above to stderr; [logging.ini](logging.ini)
provides optional equivalent development defaults. Startup command output is not
posted or logged as full transcripts. Copilot credentials are read privately and
validated without printing them. Startup does not validate requirement fulfillment
or demonstrate live model invocation; actual provider/model access is enforced by
future exact-model execution, with no billing-provider fallback.

Existing failed workspaces/logs remain private retained diagnostics until operator
deletion, never resumable state. The approved guard creates no issue-run directory
and does not read, mutate, or execute retained diagnostics. Deleting diagnostics
does not stop leftover Docker resources. Preserve operator TOML when inspecting
artifacts and never commit credentials, source workspaces, or transcripts.

A future Docker-authorized agent can access more than its normal mounts; neither
credential separation nor host-owned Git metadata protects against deliberate
engine-mediated access. Scoped cleanup conventions are cooperation, not security
controls. Unknown resources and hard-crash leftovers require operator inspection;
never use daemon-wide pruning. Independent target CI and human review remain
mandatory when publication is implemented.

## Verification beyond unit tests

The real local startup path is explicitly covered by `tests/test_startup_docker.py`
with scripted host authentication and GitHub boundaries. It makes no live Copilot
request and writes nothing to GitHub. It does not prove same-path sibling mounts,
engine socket access from a run, service networking, desktop browser access,
workspace ownership, issue-run cleanup, repair, requeue, or publication; those
are US-05–US-07 acceptance work.

Historical live Copilot/GitHub-writing harnesses are disabled during the startup-only
transition. Do not run them to bypass the guard. Any new live authenticated probe
or issue-to-PR demonstration requires separate explicit approval; none is required
to complete the new stories. Historical acceptance evidence is in git history,
not the active slice's new-runtime completion record.

## Repository structure

- `agent/`: shared-image build definition and pinned baseline/build instructions.
- `src/software_factory/`: CLI/configuration/startup/guard plus GitHub, trusted Git,
  process, credential, and verification boundaries to reuse for US-05.
- `tests/`: focused startup/guard, real local image/CLI tests, independent boundary
  checks, and explicitly identified historical/deferred execution scenarios.
- `scripts/`, `Makefile`, `.github/workflows/verify.yml`: deterministic development
  and ARM64 CI entrypoints with unchanged coverage gates.
- `SPEC.md`, `DECISIONS.md`, `CONTEXT.md`, `docs/contracts.md`: target behavior,
  accepted decisions, domain vocabulary, and interfaces.
- `docs/slices/current-slice.md`: the single active delivery brief and evidence.
