# Autonomous Coding Factory

A local Python runner turns GitHub issues labeled `agent:implement` into
sandbox-validated draft PRs using Pi and an existing GitHub Copilot subscription.
It processes one issue at a time for one trusted target repository. GitHub holds
coordination state; there is no database, HTTP server, or hosted deployment.
Independent CI and human review follow publication; the factory never merges.

## Quick Start

Run commands from this repository's root. Development prerequisites:

- Python **3.14.3**, selected by [`.python-version`](.python-version).
- **uv 0.5.13** (the version pinned in CI), Make, a POSIX shell, and Git.
- **Node.js 22.19+** for the Pi bridge tests and coverage; CI uses **22.19.0**.
- A running Docker engine with Compose for the optional local integration checks
  that CI enables. Ordinary local verification does not require Docker or credentials.

Install these tools separately, then:

```sh
./scripts/setup
uv run --frozen python -m software_factory --help
./scripts/verify
```

Success means the CLI displays its `--config` option and verification exits zero
with clean Ruff checks and passing Python/Node coverage gates. Setup runs
`uv sync --locked`, installing the package editable and its locked development
dependencies in `.venv`; it does not install global tools or configure credentials.

This quick start does **not** start issue processing. To run the factory against
GitHub, complete [Operator setup](#operator-setup) first.

## Development and testing

[Makefile](Makefile) owns the commands; the setup/verify scripts delegate to it
and work even when invoked from another directory.

| Command | Purpose |
| --- | --- |
| `./scripts/setup` | Synchronize dependencies against `uv.lock`; fail if the lockfile is stale. |
| `./scripts/verify` | Format check → lint → Python tests/coverage → Node bridge tests/coverage. |
| `make format` | Apply Ruff formatting. |
| `make format-check` | Check formatting without modifying files. |
| `make lint` | Run Ruff lint rules from `pyproject.toml`. |
| `make test` | Run pytest without coverage enforcement. |
| `make coverage` | Run Python and Node bridge coverage checks. |
| `uv run --frozen pytest tests/test_toolchain.py -q` | Focused setup/verification tooling tests. |
| `uv run --frozen pytest tests/test_runner.py -k repair -q` | Focused runner repair tests. |

Python line/branch coverage must reach **80% overall**; Node bridge line, branch,
and function coverage must each reach **80%**. Reports are ignored local files:
`coverage.xml` and `coverage.lcov`. There is no configured standalone type checker
or Markdown linter. Packaging uses the pinned Hatchling backend in
[pyproject.toml](pyproject.toml); there is no release/publishing workflow.

For CI-equivalent verification with real Docker tests and live checks disabled:

```sh
FACTORY_DOCKER_TESTS=1 FACTORY_E2E_APPROVED=0 FACTORY_COPILOT_TESTS=0 \
  FACTORY_SMOKE_SANDBOX_TESTS=0 ./scripts/verify
```

[CI](.github/workflows/verify.yml) uses Ubuntu, Python 3.14.3, Node 22.19.0,
uv 0.5.13, and `FACTORY_DOCKER_TESTS=1` with the same setup/verify commands.
Docker tests use disposable Compose projects and `alpine:3.21.3` (pulled if absent),
not shared services. They cover setup/verification, a real local dependency,
isolation, failure exits, repair feedback, deadline cleanup, and manual requeue.
The remaining suite includes real local Git/process tests and scripted external
boundaries; those are not substitutes for live Copilot/GitHub acceptance.

Read [AGENTS.md](AGENTS.md) for coding policies and [CONTEXT.md](CONTEXT.md) for
canonical domain names. Update documentation when setup, configuration,
interfaces, or architecture changes.

## Operator setup

The host additionally needs authenticated GitHub CLI (`gh auth status --hostname
github.com`), Pi with authenticated Copilot access (tested version **1.3.0**), and
running Docker with Compose. GitHub authentication needs access to the target's
issues, branches, and PRs. Authentication and access approvals are manual;
setup never provisions them. Only **one runner** may operate on the configured
repository; labels are not a distributed lock.

1. Prepare the trusted target's default branch with executable, noninteractive
   `./scripts/setup` and `./scripts/verify`; verification must match its CI.
2. Prepare a **trusted, prebuilt agent image** with Node.js 22.19+, Pi, bash, and
   the target's runtime/toolchain. A verification-only image without Pi is insufficient.
3. Prepare a trusted Compose file outside the agent-accessible workspace:

   ```yaml
   services:
     agent:
       image: your-prepared-target-agent:pinned-version
       working_dir: /workspace
       volumes:
         - type: bind
           source: ${FACTORY_WORKSPACE:?runner supplies this path}
           target: /workspace
   ```

   `FACTORY_WORKSPACE` is supplied by the runner; do not set a fixed host path.
   Configure the container user for the host workspace owner where needed.
4. Write operator-owned `factory.toml` outside the target checkout and run workspace:

   ```toml
   repository = "TeroTS/factory-smoke-test"
   compose_file = "compose.yaml"
   compose_service = "agent"
   model = "gpt-6.1-sol"
   ```

   These are the **only four fields**, all required nonempty strings with no
   defaults. `repository` is GitHub `owner/name`, not a URL. `compose_file` is
   absolute or relative to the TOML file; `compose_service` must exist in the
   resolved Compose configuration. `model` is an exact, account-accessible
   `github-copilot` model ID, without provider prefix or patterns. Configuration
   contains no credentials; the application does not load a `.env` file.
5. Start the runner:

   ```sh
   uv run --frozen python -m software_factory --config /absolute/path/to/factory.toml
   ```

   Startup validates configuration, tools, Docker/GitHub readiness, and supported
   Compose isolation before claiming issues. Successful startup waits/polls and
   may print nothing; failures report to stderr and exit nonzero. This command
   can immediately process already-labeled issues and publish branches/PRs.
6. Apply `agent:implement` only to an issue you intend the factory to attempt.
   Ctrl-C or SIGTERM stops the runner, attempts active sandbox cleanup, and exits 130.

### Existing smoke target

The locally prepared target owns its agent Dockerfile and Compose profile at
`../factory-smoke-test/sandbox/agent/`, not in this repository. Its image pins
Node 22.19.0, Python 3.14.3, uv 0.5.13, and Pi 1.3.0. Operator configuration is
ignored `artifacts/operator/factory-smoke-test.toml`; `compose_file` points to the
absolute target Compose path. These local files are not provided by a fresh clone.

With that target checkout and operator configuration prepared, build for the
host workspace owner and validate without GitHub writes:

```sh
docker build --build-arg RUN_UID="$(id -u)" --build-arg RUN_GID="$(id -g)" \
  -t software-factory-smoke-agent:pi1.3.0-python3.14.3 ../factory-smoke-test/sandbox/agent
FACTORY_SMOKE_SANDBOX_TESTS=1 uv run --frozen pytest tests/test_smoke_environment.py -s
```

This opt-in probe checks runtime versions, setup, verification, a real Pi/Copilot
local-file change, re-verification, and cleanup against target `main`. It uses
Copilot but does not label issues, push branches, or create PRs. Private diagnostics
stay under ignored `artifacts/smoke-sandbox-validation/`. Rebuild if host UID/GID changes.

## Architecture and interfaces

The [architecture guide](docs/architecture/service-architecture.md) contains the
component diagram and boundary evidence. [Non-HTTP contracts](docs/contracts.md)
define the CLI, configuration, scripts, GitHub coordination, and publication.
There is no factory-owned HTTP API or generated API client.

The Python standard-library host runner coordinates GitHub CLI, Git, Pi auth,
and Docker Compose; a small Node bridge invokes Pi inside the sandbox:

1. Poll every 30 seconds between completed batches. Check exact open factory PR
   and branch identity, remove the trigger, and snapshot issue title/body only.
2. Create a fresh default-branch workspace and run setup → Pi → verification in
   Compose. Completed verification failures allow up to **three repairs**, each
   with the original snapshot and failed stdout/stderr in the same workspace.
3. All run phases share one **900-second deadline**; repairs never reset it.
   Missing scripts, setup/provider/sandbox errors, and publication failures do
   not authorize verification repairs.
4. Stop the sandbox before host publication. Only passing, nonempty changes can
   create `factory/issue-<number>` and a draft PR containing `Closes #<number>`.

See the [step-by-step workflow and manual requeue guide](docs/workflows/issue-to-draft-pr.md).

## Sandbox and publication boundaries

- Compose is resolved with a restricted host environment and frozen before claims.
  Each run has a unique project; the host controls lifecycle and publication.
- Only the run workspace may be bind-mounted, at `/workspace`. Dependency services
  can use run-local bridge networks and anonymous volumes. Builds, host ports,
  external/shared resources, named volumes, devices, privileged access, host
  namespaces, Docker socket, and host credential/configuration mounts are rejected.
- Every service runs with all capabilities dropped, `no-new-privileges`, and restart
  disabled. Dependency images/entrypoints must work under these constraints.
- Pi receives only a host-resolved Copilot bearer with at least 20 minutes remaining
  via stdin, with its endpoint derived from validated token metadata. Temporary
  Pi configuration is removed after invocation; discovered resources and persistent
  sessions are disabled. There is no fallback billing provider.
- Trusted Git metadata stays outside the mounted workspace. Host publication ignores
  sandbox Git configuration, hooks, global filters, and helpers; nested Git metadata
  is rejected. Existing remote factory branches are never overwritten.
- Internet access retains an exfiltration risk. Passing verification does not prove
  requirement fulfillment or preserve test quality; independent CI and human review
  remain mandatory. Do not rely on automatic credential renewal.

## Diagnostics and retry handling

Standard-library logging reports WARNING and above to stderr; [logging.ini](logging.ini)
provides equivalent optional development defaults, not an automatically loaded setting.
Concise issue comments report running, skipped, failed, or succeeded outcomes.
Full command output stays in `artifacts/issue-<number>-*/run.log` **beside the configured
Compose file**, not necessarily this repository. New run directories are mode 0700;
logs are 0600. Successful run directories are removed; failures remain until operator
deletion. Known Copilot bearers are redacted, but other sensitive source/output may remain.
Never commit or publish credentials, workspaces, or transcripts; `artifacts/` is ignored.

| Symptom | Action |
| --- | --- |
| Setup reports a stale lockfile | For an intentional dependency change, update `uv.lock` with uv and review it with `pyproject.toml`; do not bypass locked setup. |
| Node rejects coverage options | Use Node 22.19+; CI's reference is 22.19.0. |
| Docker integration fails at readiness | Start Docker, confirm `docker info` and `docker compose version`; allow the test image pull. |
| Startup rejects config/Compose | Check the four-field TOML and supported isolation subset; do not weaken sandbox validation. |
| Copilot unavailable/expired | Fix host Pi authentication and exact model access; never substitute another provider or copy broader credentials. |
| Reapplied label produces a skip | A matching open PR is preserved; an orphan factory branch requires operator inspection/deletion before reapplying the label. |
| Hard crash leaves a running status/resources | Inspect private diagnostics and leftover run-owned containers before restarting the single runner. |

Restart never resumes retained work or restores trigger labels. To retry, inspect
remote PR/branch state and diagnostics, resolve any orphan branch yourself, edit
the issue if needed, then explicitly reapply `agent:implement`. A skip also consumes
the trigger, so cleanup after a skip requires another label application. A clear
requeue starts a new snapshot/workspace, deadline, and repair allowance; previous
failed diagnostics remain untouched. Never blindly retry uncertain publication writes.

## Verification beyond unit tests

These checks are opt-in; they are not enabled by the ordinary setup/verify path.

A real Pi/Copilot coding probe in an isolated empty workspace (not issue-to-PR):

```sh
FACTORY_DOCKER_TESTS=1 FACTORY_COPILOT_TESTS=1 \
  FACTORY_COPILOT_IMAGE=your-prepared-pi-image:pinned-version \
  uv run --frozen pytest tests/test_docker_integration.py -k real_pi_copilot
```

The live end-to-end harness **writes labels, comments, a branch, and a draft PR**
in `TeroTS/factory-smoke-test`. It requires explicit operator approval, prepared
target configuration, a fresh dedicated open issue, and no other trigger-labeled
issues. It leaves the PR for review; it never merges. Do not rerun against an
existing factory PR.

```sh
FACTORY_E2E_APPROVED=1 FACTORY_E2E_CONFIG=/absolute/path/to/factory.toml \
  FACTORY_E2E_ISSUE=123 uv run --frozen pytest tests/test_e2e.py -s
```

- Add `FACTORY_E2E_REQUIRE_REPAIR=1` to test verification repair. Arrange a dedicated recovery
  scenario with the operator: the harness observes, but does not manufacture, a
  failing verification followed by success within the repair allowance. A first-pass
  PR fails this assertion even though publication may already have occurred; inspect
  it rather than blindly rerunning.
- To test manual requeue, first arrange an approved failed/interrupted run with a `Failed:` comment,
  absent trigger, no open factory PR or remote factory branch, and retained diagnostics.
  Add `FACTORY_E2E_REQUIRE_REQUEUE=1` and
  `FACTORY_E2E_REQUEUE_FROM=/absolute/path/to/artifacts/issue-123-failed` to the command.
  The harness reapplies the label once, verifies fresh inputs/workspace and success,
  and checks that the old workspace/log remain unchanged. It neither manufactures
  the prior failure nor cleans up remote branches.
- Discovery can lag after labeling. The harness permits up to three polls at
  30-second intervals while the trigger remains; it never relabels a claimed failure.

## Repository structure

- `src/software_factory/`: CLI/configuration, command deadlines, GitHub coordination,
  trusted Git publication, Compose sandbox, runner, and Node/Pi bridge.
- `tests/`: unit, real local Git/process, Docker integration, and opt-in live tests.
- `scripts/`, `Makefile`: setup, verification, formatting/lint, tests, and coverage.
- `.github/workflows/verify.yml`: CI using the same development entrypoints.
- `SPEC.md`, `DECISIONS.md`, `CONTEXT.md`: behavior, decision history, domain vocabulary.
- `docs/contracts.md`: authoritative non-HTTP interfaces.
- `docs/architecture/`, `docs/workflows/`: component diagram and operator workflow.
