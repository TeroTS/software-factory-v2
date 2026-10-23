# Autonomous Coding Factory

A local Python runner turns `agent:implement` GitHub issues into sandbox-validated
draft PRs. **US-01 passed real end-to-end acceptance:**
[issue 7](https://github.com/TeroTS/factory-smoke-test/issues/7) produced
[draft PR 8](https://github.com/TeroTS/factory-smoke-test/pull/8), with independent CI green.
Repairs (US-02) and successful manual-requeue delivery (US-03) remain deferred.
See [SPEC.md](SPEC.md), [contracts](docs/contracts.md),
[current slice](docs/slices/current-slice.md), [domain vocabulary](CONTEXT.md),
and the [step-by-step issue-to-draft-PR workflow](docs/workflows/issue-to-draft-pr.md).

## Development

Requirements: Python 3.14.3, uv 0.5.13, Make, a POSIX shell, and Node.js 22.19+
(CI pins 22.19.0) for Pi-bridge tests/coverage. Docker is needed for integration tests.

```sh
./scripts/setup
make format
make lint
make test
make coverage                 # Python + Pi bridge coverage; coverage.xml / coverage.lcov
./scripts/verify              # Format check, lint, tests with coverage
FACTORY_DOCKER_TESTS=1 ./scripts/verify  # Same real Docker checks enabled in CI
```

`uv.lock` locks application/development dependencies; `pyproject.toml` pins the
package build backend. Commands use the virtual environment, not global Python packages.

## Operator setup

The host needs Git, authenticated GitHub CLI, Pi with authenticated Copilot access
(the tested Pi version is 1.3.0), and running Docker with Compose.
Only one runner may operate on the configured repository; there is no distributed lock.

The first target owns its agent Dockerfile and Compose profile at
`../factory-smoke-test/sandbox/agent/` (sibling target checkout), not in this
factory repository. The image pins Node 22.19.0, Python 3.14.3, uv 0.5.13, and
Pi 1.3.0. Keep operator-owned configuration at ignored
`artifacts/operator/factory-smoke-test.toml`, outside the target checkout and run
workspace. Its `compose_file` points to the absolute path of the target checkout's
`sandbox/agent/compose.yaml`; it contains no credentials.
Build for the host workspace owner, then validate without GitHub writes:

```sh
docker build --build-arg RUN_UID="$(id -u)" --build-arg RUN_GID="$(id -g)" \
  -t software-factory-smoke-agent:pi1.3.0-python3.14.3 ../factory-smoke-test/sandbox/agent
FACTORY_SMOKE_SANDBOX_TESTS=1 uv run --frozen pytest tests/test_smoke_environment.py -s
```

The opt-in validation checks actual runtime versions, setup, verification, a real
Pi/Copilot local-file change, re-verification, and cleanup against target `main`.
It uses Copilot but never labels an issue, publishes a branch, or creates a PR.
Sanitized evidence and private diagnostics stay under ignored
`artifacts/smoke-sandbox-validation/`. Rebuild if the host UID/GID changes.

When ready to process labeled issues (not part of the preparation probe):

```sh
uv run --frozen python -m software_factory --config artifacts/operator/factory-smoke-test.toml
```

For other prepared environments, follow these requirements:

1. Prepare the trusted target repository's default branch with executable,
   noninteractive `./scripts/setup` and `./scripts/verify`. Verification must match CI.
2. Prepare a **trusted, prebuilt agent image** containing Node.js (Pi requires
   22.19+), Pi, bash, and the target's runtime/toolchain. The smoke target's
   verification-only image does not satisfy this requirement.
3. Prepare a trusted Compose file outside any agent-accessible workspace:

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

4. Write operator-owned `factory.toml`:

   ```toml
   repository = "TeroTS/factory-smoke-test"
   compose_file = "compose.yaml"
   compose_service = "agent"
   model = "gpt-6.1-sol"
   ```

   All four fields are required. Compose paths resolve relative to the TOML file;
   the model must be an exact accessible `github-copilot` model ID.

5. Start the runner and apply `agent:implement` to an issue:

   ```sh
   uv run --frozen python -m software_factory --config /absolute/path/to/factory.toml
   ```

The runner polls every 30 seconds. It confirms trigger removal, checks exact
factory PR/branch identity, snapshots the issue title/body, creates a fresh
default-branch workspace, runs setup → Pi → verification in Compose, then stops
the sandbox before host-side publication. Only passing, nonempty changes can
produce `factory/issue-<number>` and a draft PR with `Closes #<number>`.

Verification failure currently fails immediately: no repair loops yet. All run
commands share one 900-second deadline. Ctrl-C/SIGTERM triggers cleanup and
failure reporting; a hard crash can leave resources/status requiring operator inspection.
The factory never merges, revises from review feedback, or resumes retained work.

## Sandbox and publication boundaries

- Compose is resolved with a restricted host environment and validated before claims.
  A run uses a frozen, uniquely named Compose project controlled by the host.
- Only the run workspace may be bind-mounted, at `/workspace`. Dependency services
  are supported with run-local bridge networks and anonymous volumes.
- Unsupported or isolation-defeating settings fail closed: no builds, host ports,
  external/shared resources, named volumes, devices, privileged access, host
  namespaces, Docker socket, or host credentials/configuration.
- All services run with `cap_drop: [ALL]`, `no-new-privileges`, and restart disabled.
  Prepare dependency images/entrypoints that can operate within those constraints.
- Pi receives only a host-resolved Copilot bearer with at least 20 minutes remaining,
  via stdin. Its endpoint is derived from validated Copilot token metadata. Temporary
  Pi configuration is created inside the container; discovered resources and sessions
  are disabled. No fallback billing provider is used.
- Trusted Git metadata remains outside the mounted workspace. Host commits ignore
  sandbox Git configuration, hooks, global filters, and helpers. Nested Git metadata
  is rejected rather than allowing host staging to inspect untrusted subrepositories.
- Internet access remains an exfiltration risk. Container isolation and passing
  verification do not prove requirement fulfillment or preserve test quality;
  independent CI and human review remain required.

## Diagnostics and retry handling

Failures are reported concisely in issue comments and stderr; full command output
stays local under `artifacts/issue-<number>-*/run.log`, beside the operator's Compose
file. New run directories use mode 0700 and logs 0600. Failed workspaces remain until
operator deletion; successful run directories are removed. Known Copilot bearers
are redacted, but diagnostics can still contain other sensitive repository output.
Never publish them or commit credentials, workspaces, or transcripts.

An existing exact factory PR is preserved and linked instead of executed. An existing
remote factory branch without an open PR blocks execution; the operator must inspect
and delete that branch before reapplying the label. Publication failures are never
blindly retried or force-pushed. Restarting does not restore trigger labels or resume runs.

## Verification beyond unit tests

Real Docker checks include setup/verification, a local dependency service, isolation,
missing entrypoints, failure exits, deadline termination, and cleanup.

A separate opt-in integration check exercises real Pi/Copilot coding in an empty
isolated workspace; it is **not** the issue-to-PR end-to-end acceptance test:

```sh
FACTORY_DOCKER_TESTS=1 FACTORY_COPILOT_TESTS=1 \
  FACTORY_COPILOT_IMAGE=your-prepared-pi-image:pinned-version \
  uv run --frozen pytest tests/test_docker_integration.py -k real_pi_copilot
```

The live end-to-end test writes a label, comments, branch, and draft PR in
`TeroTS/factory-smoke-test`. It requires a dedicated open issue, no other labeled
issues, completed target preparation, and explicit approval. It leaves the PR for
human review and never merges the preparation branch itself.

```sh
FACTORY_E2E_APPROVED=1 FACTORY_E2E_CONFIG=/absolute/path/to/factory.toml \
  FACTORY_E2E_ISSUE=123 uv run --frozen pytest tests/test_e2e.py -s
```

The approved issue-to-PR acceptance test passed for issue 7 in 72.83 seconds,
producing draft PR 8 from baseline `44a3e90`. Both target CI checks passed with
13 tests and 100% line/branch coverage. The issue has its success link, the trigger
label is removed, and run-owned containers are gone. Nothing was merged.

GitHub discovery can lag immediately after label application. The harness permits
up to three polls at 30-second intervals while the trigger remains present; it
never reapplies the trigger after claim or retries a failed issue run. Do not
rerun against issue 7's existing PR; select a fresh dedicated issue for another
approved live test. See the [completion evidence](docs/slices/current-slice.md).

## Source layout

- `src/software_factory/`: configuration, command budgets, GitHub coordination,
  trusted Git publication, Compose sandbox, and local runner.
- `tests/`: unit, real Git/process, Docker integration, and opt-in live tests.
- `scripts/`: setup, verification, and coverage entrypoints.
- `.github/workflows/verify.yml`: setup/verify with real Docker tests and coverage.
- `logging.ini`: optional WARNING-to-stderr configuration; startup uses equivalent
  standard-library logging defaults, without a shared log file.
