# Autonomous Coding Factory

A local Python runner turns `agent:implement` GitHub issues into sandbox-validated
draft PRs. **US-01 passed real end-to-end acceptance:**
[issue 7](https://github.com/TeroTS/factory-smoke-test/issues/7) produced
[draft PR 8](https://github.com/TeroTS/factory-smoke-test/pull/8), with independent CI green.
**US-02 also passed live acceptance:** [issue 9](https://github.com/TeroTS/factory-smoke-test/issues/9)
recovered through one repair and produced [draft PR 10](https://github.com/TeroTS/factory-smoke-test/pull/10),
with both independent target CI runs green.
**US-03 passed live manual-requeue acceptance:** [issue 13](https://github.com/TeroTS/factory-smoke-test/issues/13)
was interrupted, stayed idle across restart, then produced [draft PR 14](https://github.com/TeroTS/factory-smoke-test/pull/14)
after explicit label reapplication, with both independent target CI runs green.
All explicit stories in `SPEC.md` are complete.
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

A completed verification failure supplies its stdout/stderr to a fresh Pi call
in the same workspace, with the same issue snapshot. The runner permits at most
three repair-and-verify cycles and stops at the first passing verification.
Exhaustion fails the run without publication. Missing scripts, setup/provider or
sandbox errors, and publication failures are not retried as verification repairs.
All run commands, including every repair and verification, share the original
900-second deadline; it never resets between attempts. Ctrl-C/SIGTERM triggers cleanup and
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

To manually requeue a failed or interrupted issue:

1. Inspect the issue status and local diagnostics. After a hard crash, inspect and
   stop/remove any leftover run-owned containers before starting the single runner.
2. Check `factory/issue-<number>`. A matching open PR is preserved and linked instead
   of executed. Without an open PR, inspect and delete any remaining remote factory
   branch yourself; the runner never deletes or overwrites it. A closed PR does not
   bypass this branch check.
3. Edit the issue title/body if needed, then explicitly reapply `agent:implement`.
   If a skip consumed the label, cleanup alone is insufficient: reapply it again.
4. The next poll captures the current title/body and creates a new workspace from
   the current default branch, with a new 900-second deadline and up to three
   repairs. It does not resume the old workspace or Pi session, and leaves previous
   failed workspaces/logs intact until you delete them.

## Verification beyond unit tests

Real Docker checks include setup/verification, a local dependency service, isolation,
missing entrypoints, failure exits, repair feedback/re-verification, bounded runner
recovery with a scripted agent, deadline termination, and cleanup. Manual-requeue
checks combine real local Git with scripted agent/external GitHub boundaries, plus
real Compose setup/verification for failure and interruption followed by requeue.
They check restart inactivity, edited inputs, an updated default branch, fresh run
budgets/repair allowances, orphan-branch blocking, and retained diagnostics. These
checks do not substitute for live Pi/Copilot recovery/requeue-to-PR acceptance.

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

To require US-02 evidence, use a fresh dedicated issue and add
`FACTORY_E2E_REQUIRE_REPAIR=1` to the command above. The test observes actual
sandbox verification results and requires an initial failure followed by success
within the three-repair allowance, in addition to all issue-to-PR gates. It does
not force a failure: select a dedicated recovery scenario with the operator.
A first-pass PR does not prove US-02 and fails this acceptance mode. The PR may
already exist when that assertion fails; inspect it rather than blindly rerunning.
The approved US-02 live test passed for issue 9 in 115.63 seconds, producing draft
PR 10 at `f4971d2` from baseline `44a3e90`. Initial canonical verification failed
its Ruff format check (pytest had not run); Pi received that output, repaired
formatting and the temporary staged off-by-one defect, and the same verification
passed with 18 tests and 100% line/branch coverage. Exactly one repair was used.
Both independent [push CI](https://github.com/TeroTS/factory-smoke-test/actions/runs/40081442415)
and [PR CI](https://github.com/TeroTS/factory-smoke-test/actions/runs/40081445595) passed.
The issue has its success link, the trigger label is absent, and run-owned containers
and the successful run directory were removed. PR 10 was draft at acceptance;
it was already non-draft at US-03 preflight and was left unchanged. No merge was performed. Private evidence is ignored under
`artifacts/operator/us02-issue-9/`; the completed slice note in git history
records the detailed inspected evidence. Do not rerun against issue 9's existing PR.

For US-03 acceptance, first arrange an operator-approved failed/interrupted run
on a dedicated issue, with its trigger absent, no open factory PR, and no remaining
remote factory branch. Inspect/clean up remote branches yourself if necessary.
Then use the same live test with both additional inputs:

```sh
FACTORY_E2E_APPROVED=1 FACTORY_E2E_CONFIG=/absolute/path/to/factory.toml \
  FACTORY_E2E_ISSUE=123 FACTORY_E2E_REQUIRE_REQUEUE=1 \
  FACTORY_E2E_REQUEUE_FROM=/absolute/path/to/artifacts/issue-123-failed \
  uv run --frozen pytest tests/test_e2e.py -s
```

This mode requires a prior `Failed:` issue comment and retained workspace/log,
then performs one explicit label reapplication. It observes real Pi implementation
receiving the current title/body and default-branch commit in a different run
directory, requires a linked validated draft PR, and checks that the previous log
is unchanged and workspace remains. It does not manufacture an initial failure,
clean up branches, or automatically retry a claimed failure. Independent target CI
and human inspection still follow.

The approved US-03 acceptance passed for issue 13 in 87.59 seconds, producing
[draft PR 14](https://github.com/TeroTS/factory-smoke-test/pull/14) at `d985c29`
from baseline `44a3e90`. The first real CLI run was stopped with SIGTERM during
Pi execution (exit 130, recorded as operator interruption). Its source had not yet
changed. A real 35-second restart produced no new run or status comment. After the
issue was edited from `--uppercase` to `--lowercase`, explicit label reapplication
started a different workspace and delivered the updated request without session
resumption. Canonical verification and both independent
[push CI](https://github.com/TeroTS/factory-smoke-test/actions/runs/40087578087) and
[PR CI](https://github.com/TeroTS/factory-smoke-test/actions/runs/40087580186)
passed with 8 tests and 100% line/branch coverage; no repair was needed.
The trigger is absent, successful run directory and run-owned containers are gone,
and the original failed workspace/log remain unchanged until operator deletion.
Private evidence is ignored under `artifacts/operator/us03-issue-13/`; the
[current slice](docs/slices/current-slice.md) records the inspected evidence.
PR 14 remains draft; no merge was performed. Do not rerun against issue 13's PR.

One earlier interruption monitor missed its process, so issue 11 completed normally
and produced [draft PR 12](https://github.com/TeroTS/factory-smoke-test/pull/12),
with both target CI runs green. This is not US-03 evidence. That runner was stopped,
the monitor was corrected and self-checked before using issue 13, and PR 12 was
preserved for human review rather than closed, overwritten, or requeued.

The approved US-01 issue-to-PR acceptance test passed for issue 7 in 72.83 seconds,
producing draft PR 8 from baseline `44a3e90`. Both target CI checks passed with
13 tests and 100% line/branch coverage. The issue has its success link, the trigger
label is removed, and run-owned containers are gone. Nothing was merged.

GitHub discovery can lag immediately after label application. The harness permits
up to three polls at 30-second intervals while the trigger remains present; it
never reapplies the trigger after claim or retries a failed issue run. Do not
rerun against issue 7's existing PR; select a fresh dedicated issue for another
approved live test. See [current implementation and acceptance status](docs/slices/current-slice.md).

## Source layout

- `src/software_factory/`: configuration, command budgets, GitHub coordination,
  trusted Git publication, Compose sandbox, and local runner.
- `tests/`: unit, real Git/process, Docker integration, and opt-in live tests.
- `scripts/`: setup, verification, and coverage entrypoints.
- `.github/workflows/verify.yml`: setup/verify with real Docker tests and coverage.
- `logging.ini`: optional WARNING-to-stderr configuration; startup uses equivalent
  standard-library logging defaults, without a shared log file.
