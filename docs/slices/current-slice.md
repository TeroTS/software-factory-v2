# Current Slice

Status: done

## Slice Goal
- Let the operator start a validated runner with one locally built shared agent image, without a target-specific factory sandbox.

## Slice Boundary
- Actor: Operator.
- Trigger: The operator starts the factory for one trusted target repository with operator-owned configuration and a locally built shared agent image.
- Action: Validate configuration, artifact-root usability, host prerequisites, local Docker execution, and shared-image availability/compatibility, then begin polling.
- Visible outcome: The runner reaches polling without requiring target-specific factory Compose configuration.
- Authoritative state transition: Stopped runner with supplied configuration → validated runner polling the configured repository.
- Prove startup without claiming or processing a real GitHub issue. Issue-to-PR execution and its acceptance belong to US-05.
- Operator approval in this conversation: use a temporary pre-claim guard until US-05. Polling and direct issue dispatch must leave labels, comments, branches, PRs, and previous diagnostics unchanged; report the unavailable execution capability locally. This is an interim delivery constraint, not the final issue-processing policy.

## Stories In Scope
- `US-04 Start the runner with a shared agent image`

## Stories Completed In This Slice
- `US-04 Start the runner with a shared agent image`

## Stories Remaining In This Slice
- None.

## Contract Inputs
- `docs/contracts.md`, Contract 1: unchanged CLI invocation; exactly repository/model/agent_image/artifacts_dir; legacy-field rejection; artifact-path resolution; safe startup failures; no automatic migration/build/pull.
- `docs/contracts.md`, Contract 3 startup portions: factory-maintained pinned shared-image baseline, native local linux/arm64 execution, immutable session image ID, and no baked-in credentials.
- `docs/contracts.md`, Contract 6 startup portions: private diagnostic root, preservation of existing artifacts, and no restart-triggered recovery.

## Decision Inputs
- `DECISIONS.md`, Interfaces / Contracts and Operations / Deployment: replace the old backend rather than add a selector; pin the image baseline; reject remote engines/emulation; operator builds the image before startup.
- `DECISIONS.md`, Interface / Contract Expectations: standing instructions must reflect the approved Docker trust model before production execution changes.

## Shared State Required Now
- Validated immutable operator configuration: repository, exact Copilot model, local agent-image reference, and resolved artifact root.
- One compatible immutable local image ID for the runner session; adopting a rebuilt tag requires restart.
- Validated local engine/execution prerequisites. Engine access is not a host-security boundary.
- No new job state, database, recovery checkpoint, backend selector, or automatic configuration migration.

## Operations / Endpoints / Surfaces In This Slice
- `src/software_factory/config.py`: replace Compose fields and validation with the four contracted fields, migration diagnostics, and artifact-path resolution.
- `src/software_factory/runner.py`: replace prepared-Compose startup resolution with artifact-root and local engine/image readiness checks; carry the immutable session image identity into the runner.
- `src/software_factory/__main__.py`: preserve invocation, safe failure exits, interruption handling, and startup-to-polling ordering.
- Add the factory-owned shared-image build definition and operator build instructions with exact baseline pins and no credentials.
- Startup coverage is in `tests/test_config.py`, `tests/test_startup.py`, `tests/test_startup_docker.py`, and `tests/test_cli.py`. Historical runner/requeue/recovery scenarios are explicitly skipped pending ports, not silently adapted to a fake legacy backend. Scripted historical live-harness observation unit tests remain active.
- Update `README.md`, `AGENTS.md`, vocabulary status, architecture/workflow docs, SPEC, and contracts for the delivered startup interface and approved guard/trust boundary. `agent/Dockerfile` and `agent/README.md` supply the pinned baseline. CI explicitly builds/tests startup on `ubuntu-24.04-arm`; this is not acceptance of US-05 execution.
- Replace Runner.process_issue's obsolete prepared-Compose orchestration with the approved temporary pre-claim guard. Keep independently tested GitHub, trusted Git, command, credential, and verification-feedback boundaries for reuse in US-05. Historical orchestration tests cannot establish acceptance of the new execution model; retain deferred regression scenarios explicitly until they can be ported.

## Tests Required
- Config tests accept exactly four nonempty strings; preserve repository/model semantics; resolve relative and absolute artifact paths independently of the working directory; reject missing, wrong-type, unknown, malformed, and legacy fields with safe migration guidance.
- Startup tests reject missing tools, failed authentication/engine checks, unsupported/remote engines, unavailable or incompatible local images, and unusable artifact roots before any claim.
- Check image resolution is local-only, immutable for the session, and never builds/pulls/falls back; check existing diagnostic contents survive startup.
- Explicit startup E2E: load real TOML through the CLI/startup path, validate the operator-built shared image against real local ARM64 Docker, and observe entry to polling with scripted GitHub/authentication boundaries and no issue processing. Clearly distinguish scripted service boundaries from live authentication acceptance.
- Build and inspect the shared image locally; exercise its pinned baseline tools and native architecture without Copilot requests or GitHub writes.
- Run Ruff format check, Ruff lint, Python tests/coverage, and Node bridge coverage using `./scripts/verify`; preserve all existing 80% gates and report unavailable checks honestly.

## Not Now
- US-05 issue-to-draft-PR execution: per-run Docker access and same-path mounts, setup/Pi/verification with application services, resource identity and scoped cleanup, host file ownership, publication gates, desktop networking/browser evidence, execution-path removal audit, and Docker-enabled issue-execution acceptance in ARM64 CI.
- US-06 service-backed verification recovery and US-07 fresh manual requeue in the new environment. Independent GitHub/Git/process/credential/verification-feedback/Pi-bridge logic remains tested; port historical orchestration scenarios from the retained tests and git history instead of retaining the obsolete runner as a selectable backend.
- No live Copilot request, real GitHub issue processing, label/comment/branch/PR writes, automatic image build/pull by the runner, dependency upgrades outside the required image baseline, automatic migration, or parallel legacy backend.

## Done When
- New TOML and the locally built pinned shared image take the real startup path to polling without target-specific factory sandbox configuration or real issue processing.
- Legacy/invalid configuration, unusable artifacts, engine failures, and missing/incompatible images fail nonzero with safe actionable diagnostics before claims.
- The session retains a resolved immutable native linux/arm64 image ID, and startup neither builds/pulls images nor modifies earlier artifacts.
- Startup-to-execution wiring has no obsolete configuration access or hidden compatibility backend; any necessary scope decision has been resolved explicitly.
- Focused startup E2E, image/tool checks, and relevant verification pass with unchanged coverage gates; documentation accurately states which execution stories remain unimplemented.

## Completion Summary
- New four-field TOML and an operator-built shared image reach real CLI polling without target-specific factory Compose input. Legacy input receives migration guidance; invalid prerequisites fail safely before claims. Artifact roots resolve against TOML and previous diagnostics remain untouched.
- The runner resolves an immutable native linux/arm64 image ID and local engine endpoint once, checks host GitHub/Copilot authentication privately, runs a credential/mount/network-free root/tool probe, and removes that uniquely named probe with bounded cleanup even after failure/interruption. Cleanup failure blocks successful startup; an interruption remains exit 130 even if cleanup also fails.
- The approved temporary guard replaces old runner orchestration: discovery and direct issue dispatch cannot consume labels, write status/branches/PRs, create issue workspaces, or select the old backend. The runner logs read-only polling every 30 seconds and unavailable execution locally. No US-05/06/07 acceptance is claimed.
- Added `agent/Dockerfile` and `agent/README.md`: digest-pinned Python/Node/Docker stages, a fixed signed Debian snapshot, exact Pi/uv versions, root execution, and baseline development tools without credentials. CI now uses `ubuntu-24.04-arm`, explicitly builds the shared image, and enables native startup checks. No remote CI run is claimed.
- Real local build passed: `docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent`. Built image: `sha256:3a52473d5bb206f9a5b46420c548016280222741602936f30e6b040d29c674f7`, inspected as linux/arm64. Native tool checks passed for Node 22.19.0/npm 10.9.3, Python 3.14.3/uv 0.5.13, Pi 1.3.0, Docker 28.4.0/Compose 2.39.4, and the documented Debian tools.
- Real startup E2E passed on the local Apple Silicon Rancher Desktop engine (linux/aarch64, local Unix socket). Both idle and labeled-issue variants ran the actual CLI/TOML/image/probe/cleanup/polling path, preserved previous diagnostics, made only scripted GitHub reads, and exited 130 on SIGTERM. Authentication and GitHub were scripted; no live Copilot/GitHub request or GitHub write was performed. Final inspection found no `factory-startup-*` containers.
- Test-first evidence: configuration/startup tests failed against the old runtime (37 failures), then passed after implementation. Shared-image checks failed before the new image existed, then passed after its explicit build. Additional authentication and interruption-plus-cleanup regressions were observed failing before their fixes.
- Full local CI-equivalent command passed: `FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 FACTORY_E2E_APPROVED=0 FACTORY_COPILOT_TESTS=0 FACTORY_SMOKE_SANDBOX_TESTS=0 ./scripts/verify`. Ruff format/lint clean; 241 Python tests passed, 52 skipped; Python overall line/branch coverage 97.79% (previous recorded 97.28%, with different source scope after removing obsolete runner orchestration). Node bridge tests passed with 100% line/branch/function coverage. All 80% gates remain unchanged; no business logic coverage exclusions were added.
- Skip accounting: 37 historical runner cases, 7 historical requeue cases, and 4 historical recovery-orchestration cases await ports in US-05–US-07; 3 historical live issue/smoke cases are disabled; 1 separate live Copilot probe was deliberately not enabled. Independent real Git/process, GitHub, credential, Pi-bridge, verification-feedback, and historical Compose-helper checks remain active. The latter prove only those helpers, not a new execution backend.
- CLI help passed without polling. `git diff --check` and local documentation path/anchor/format checks passed. No new type checker/Markdown linter is configured. No service-backed issue execution, socket/sibling-mount/file-ownership/network/browser/issue-cleanup acceptance, live provider/model request, or remote CI was run; those checks are outside this startup slice.

## Next Slice Recommendation
- `US-05 Turn a labeled issue into a Docker-verified draft PR`: replace the temporary guard with one real Docker-enabled execution/publication path and complete its ownership/cleanup/trust-boundary/removal audit and desktop-provider evidence. Keep US-06 verification recovery and US-07 fresh manual requeue in view, but do not expand the next slice to include their outcomes.
