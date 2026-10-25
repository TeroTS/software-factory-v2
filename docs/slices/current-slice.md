# Current Slice

Status: done

## Slice Goal
- Let the operator obtain a verified draft PR using the baked factory account and supplementary Docker socket access, without runtime account initialization.

## Slice Boundary
- Actor: Operator.
- Trigger: The fixed-identity runner is polling and an issue is labeled for implementation.
- Action: Submit the issue through the existing first-pass workflow.
- Visible outcome: The issue links to a verified draft PR produced using the fixed agent account and Docker socket access, without runtime account mutation.
- Authoritative state transition: Labeled issue on a validated fixed-identity runner → successful issue run linked to a draft PR after required cleanup.
- One migration regression E2E with real local Git/Docker services and scripted Pi/GitHub boundaries; no new coordination, repair, or publication behavior.

## Stories In Scope
- `US-10 Execute issue runs without runtime account initialization`

## Stories Completed In This Slice
- `US-10 Execute issue runs without runtime account initialization`

## Stories Remaining In This Slice
- None.

## Contract Inputs
- `docs/contracts.md`, Contract 3: baked factory identity/home/caches, selected socket numeric GID, `--group-add`, actual exec identity/socket validation before setup, stdin-only ephemeral credentials, and no runtime account mutation or root fallback.
- `docs/contracts.md`, Contracts 1–2 and 4–7: unchanged CLI/TOML, claims/snapshot, first-pass ordering/original deadline, trusted create-only publication, private diagnostics, and scoped cleanup/access gates.
- `docs/contracts.md`, Contracts 8–9: native Linux storage/services, explicit macOS-to-VM fixture access, existing provisioned Lima environment, and operator authorization for environment changes.
- No factory-owned HTTP API or `openapi.yaml` applies.

## Decision Inputs
- `DECISIONS.md`, Operations / Deployment and Operational / Deployment Constraints: fixed identity, selected socket GID via `--group-add`, feasibility through actual exec, local-Lima acceptance, removal audit, and explicit environment authorization.
- SPEC/contracts govern first-pass execution; historical repair provisions in DECISIONS.md are not work in this slice.

## Shared State Required Now
- Existing provisioned Ubuntu 24.04 ARM64 Lima guest and factory UID/GID 2000:2000; existing explicitly built compatible shared image resolved to its immutable ID.
- Selected local Unix socket path and its actual numeric GID; no new configuration fields or account/group mutations.
- Existing fresh workspace, run identity/ownership labels, original 900-second deadline, private logs, and trusted publication metadata.
- Previous artifacts, unrelated resources, images, and build cache remain unchanged.

## Operations / Endpoints / Surfaces In This Slice
- `src/software_factory/sandbox.py`: removed `configure_user`, host-identity exec overrides, and obsolete macOS socket translation. It discovers the selected Unix socket's actual GID, passes `--group-add` at creation, and validates actual exec UID/GID, socket membership, and engine access before setup. Missing/inaccessible/non-socket paths fail safely before container creation.
- Deleted `src/software_factory/sandbox_user_setup.py` and `tests/test_sandbox_user_setup.py` after replacement behavior was proven. No initializer caller, root setup exec, runtime account mutation, arbitrary-ID path, or macOS socket translation remains in production.
- `tests/test_sandbox.py`: replace initializer/host-user expectations with fixed identity, socket discovery, supplementary-group creation, and fail-closed exec access tests.
- `tests/test_docker_integration.py`: prove actual exec supplementary groups, writable baked home/caches, explicit sudo, socket access, and unchanged lifecycle/failure/cleanup behavior; retire initializer-only fixtures.
- `tests/test_issue_docker.py` and `tests/tests_support.py`: demonstrate labeled issue → verified draft PR through the new identity/group path using real Git/Docker and scripted service boundaries, including required service/tool/ownership evidence.
- Existing runner failure tests additionally assert that failed startup blocks setup, Pi, and commit. README and agent instructions document the fixed exec/group path. CLI/TOML, runner ordering, image/tool pins, CI, credential delivery, cleanup/publication logic, and coverage configuration are unchanged.
- Working tree was clean at planning start. US-09 completion/evidence remains in git history; its note reported 99.35% Python overall line/branch coverage and a compatible existing shared image.

## Tests Required
- First prove feasibility in the existing Lima guest: start the existing native shared image as its default factory identity with the selected socket GID via `--group-add`; use the intended actual exec form to assert UID/GID 2000:2000, supplementary membership with socket GID different from 2000, and successful `docker info`. No account edits, socket chmod, root retry, or fallback. If it fails, stop and return evidence to the operator.
- Test-first unit failures for missing/unusable socket discovery, wrong exec identity, lost supplementary membership, and denied engine access; setup/Pi must not run after failed validation. Preserve bounded cleanup after partial creation.
- Real Docker regressions: same-path sibling mounts, native defaults/unmodified Docker CLI, target-installed npm tool, explicit sudo/root HOME, service-backed verification, disposable service volumes, compatible workspace ownership, and unchanged inaccessible required files blocking publication.
- Explicit story E2E: operator labels the scripted issue and observes a verified draft PR through the real CLI, local Git remote, and real Docker services using the new fixed-identity/group path. Assert cleanup precedes publication, trigger consumption, draft payload/content, and previous diagnostic preservation.
- Preserve setup/verification/provider/credential/deadline/SIGTERM/partial-start/cleanup/access/uncertain-publication regressions and unrelated sentinel resources.
- Demonstrate a macOS browser reaching a fixture service through the already-configured Lima loopback port 8080 path, with explicit operator authorization to occupy that port; do not change forwarding or broaden exposure.
- Run Ruff format check → Ruff lint → tests/coverage on the development host and the real Docker/image suite as factory in Lima. Retain the 80% coverage gate; investigate/report changes from the recorded 99.35% baseline.
- Audit obsolete initializer callers/fixtures and parallel paths; check affected documentation links/formatting and `git diff --check`. No standalone type checker or Markdown linter is configured.

### Verification Evidence
- The operator approved the planned environment use with “proceed”. A scoped feasibility container in the existing Lima guest used immutable image `sha256:9d2153ce3e03956cf00703c5a53afa64b9f27b7c96c0a67e89fe60e5e5f24049`, discovered socket GID **988**, and `--group-add 988` without any user override or initialization. Actual `docker exec -i <name>` reported UID/GID **2000:2000**, supplementary group **988**, and successful native `linux/aarch64` engine access. The probe container was removed. The accepted mechanism is feasible; no fallback is needed.
- Test-first unit checks failed on the old user overrides and absent socket validation; real Docker checks failed on changed account files, missing supplementary membership, old image-user overrides, and absent fail-closed exec validation. The replacement's focused unit suite passes all **30** tests. The initial real execution/issue suite passed all **24** tests after implementation.
- Real negative checks remove `--group-add`, override exec UID/GID, or point the in-container client at an unavailable engine. Each fails the access check without setup, implementation, or a second start/validation attempt, and scoped cleanup removes the partial agent. A checksum comparison with a pristine container confirms `/etc/passwd`, `/etc/group`, `/etc/shadow`, and `/etc/gshadow` remain unchanged.
- Expanded the ordinary target fixture to assert fixed identity during setup/Pi/verification, explicit sudo with root HOME, target-installed npm tooling, private root-owned mode-0600 service data in a disposable volume, and service-written workspace output owned by 2000:2000. The real CLI publishes that service-written file alongside the verified implementation to a local Git remote and scripted draft PR; no real GitHub write or Copilot call occurs.
- The expanded fixture initially failed only the fresh-checkout CLI cases: its empty output directory was not tracked by Git, so Docker created a root-owned bind directory. Creating the directory as factory in target setup fixes the fixture without permission repair; all **four** real CLI success/interruption/inaccessible-file/inaccessible-directory outcomes then passed.
- macOS `agent-browser --session us10 open http://127.0.0.1:8080/` and `get text body` observed **implemented** from a fixture that completed setup → scripted Pi → real service verification through the new agent path. It used only the existing Lima loopback forwarding; no network configuration changed. Screenshot: `artifacts/us10/browser.png`. Browser session and owned containers/network/volume were removed; a subsequent connection to port 8080 failed as expected. The fixture image/cache and diagnostic directory remain, not active services.
- macOS `./scripts/verify` passes format → lint → tests/coverage: **310 passed, 52 skipped**, Python overall line/branch **99.33%**. Opt-in Docker/image/provisioning checks are skipped on macOS; the Docker/image checks ran in Lima instead.
- `FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 ./scripts/verify` in the existing Lima guest as factory 2000:2000 passes format → lint → tests/coverage: **359 passed, 3 skipped**, **99.33%** coverage. Guest skips are Lima-on-macOS configuration validation, direct macOS rejection, and separately authorized provisioning. Existing startup/image and execution/failure/cleanup/sentinel regressions pass. No image rebuild or reprovisioning was needed.
- Investigated the coverage decrease from **99.35%** to **99.33%**: deleting the fully covered initializer shrinks the measured code denominator. All new socket validation lines/branches are covered; the remaining two missed statements and five partial branches are in unchanged CLI/runner/cleanup paths. Coverage policy/exclusions and the **80%** gate are unchanged.
- The ad-hoc browser script initially appeared in guest Ruff discovery because the tar-staged checkout lacked Git metadata. Initializing that fresh checkout as a Git repository restored normal `.gitignore` handling of `artifacts/`; no lint exclusions or production code were changed. Final verification then passed in the ordinary checkout shape.
- Final `git diff --check`, Markdown whitespace/fences, **16 local links/anchors**, slice lifecycle/removal audit, and CLI `--help` pass. Final engine inspection found no remaining containers or factory-named networks/volumes. No standalone type checker or Markdown linter is configured.
- Fresh factory-owned test checkout: `/home/factory/us10.dJtYEpnF`. Local private evidence is under `artifacts/us10/`; guest browser logs/workspace are under that checkout's ignored `artifacts/`. Previous checkouts and diagnostics remain unchanged. No live authenticated access, hosted CI run, trust-root changes, VM provisioning, commit, or push was performed.

### Operator-authorized live smoke-test follow-up
- After migration completion, the operator explicitly authorized using `TeroTS/factory-smoke-test`, creating a test issue, and proceeding with a live Copilot/GitHub issue-to-draft-PR run. This narrowly authorizes the live call and normal runner publication for that issue; it does not authorize rebuilding/reprovisioning, credential copying, unrelated issues, merging, or automatic retries.
- Read-only checks found the existing Lima `factory` guest running, no active factory runner, the existing `software-factory-agent:1.0.0` image, and no open target issues/PRs before issue creation. Target setup/verify entrypoints are executable.
- Created [issue #15](https://github.com/TeroTS/factory-smoke-test/issues/15): trim surrounding whitespace from greeting names, preserve existing behavior, add regression tests, and document trimming. It has no trigger label yet.
- Initial live execution was blocked by absent guest gh/Pi authentication. The operator then manually authenticated both as factory; no credentials were copied or printed. GitHub confirmed account `TeroTS`, and Pi 1.3.0 listed `github-copilot/gpt-6.1-sol`.
- Staged the current tracked factory files into a fresh private factory-owned checkout at `/home/factory/live-smoke-15.AnzP5krO/checkout`, installed only locked dependencies with `uv sync --frozen`, and wrote the four-field operator TOML outside that checkout at `operator/factory.toml` (mode 0600). `preflight` passed against the existing immutable image `sha256:9d2153ce3e03956cf00703c5a53afa64b9f27b7c96c0a67e89fe60e5e5f24049`; no rebuild/provisioning was needed.
- Rechecked labels, absent `factory/issue-15` remote branch, and process state before triggering only issue #15. The real CLI ran with model `gpt-6.1-sol`, consumed the trigger, and posted Running then Succeeded with [draft PR #16](https://github.com/TeroTS/factory-smoke-test/pull/16). This was a live Copilot/GitHub run, not scripted boundaries. PR identity is `factory/issue-15` → `main`, with body `Closes #15`; its three changed files implement trimming, README guidance, and padded/internal-whitespace unit and CLI regression tests without dependency or verification changes. Runner success establishes passing in-agent canonical verification and required cleanup/publication gates; its successful issue workspace/log was removed by normal runner behavior, so no exact test-count/coverage claim is retained.
- Stopped the runner with SIGTERM after this one completed attempt; confirmed no runner remained. Before/after Docker container/network/volume snapshots match exactly. Trigger remains absent; no retry, merge, extra issue execution, image rebuild, provisioning, or network change occurred. Private launcher logs/config/snapshots remain under `/home/factory/live-smoke-15.AnzP5krO` (root mode 0700, logs mode 0600); previous diagnostics are unchanged.
- Independent target GitHub CI is **failing**, not verified: both push and PR runs (`40204416455`, `40204419808`) failed at `actions/setup-python@v5` before setup/tests. Check-run annotations report Python **3.14.3 x64 unavailable for Ubuntu 26.04**, selected by the target's moving `ubuntu-latest` label. This is a target CI environment failure, not evidence of failing application tests; the PR does not change CI. Next: human review and a separately approved target CI fix (for example, explicitly pinning a supported runner), followed by green independent CI before merge.

- At the operator's request, prepared the target CI fix locally on branch `fix/ci-ubuntu-24.04` in `artifacts/smoke-pr16.5kttf9s9/`: `.github/workflows/verify.yml` changes only `runs-on: ubuntu-latest` to `runs-on: ubuntu-24.04`. The official `actions/python-versions` manifest confirms a Python 3.14.3 Linux x64 artifact for Ubuntu 24.04. No tool/dependency pins, verification steps, permissions, or factory-owned remote branch changed. Publishing initially awaited explicit commit/push approval, subsequently granted by the operator below.
- Reviewed PR #16 at `e4282700357ccc8bdd38692030a115afd90d23e1` against base `19f10a84ada1348a2358c35643f5796da39f1971`, issue #15, target AGENTS, complete application/tests/README, and setup/verify/config/callers. No code correctness, scope, safety, or test findings. Formal slice-spec review is unavailable because the target has neither SPEC.md nor a current-slice brief; this is an ordinary code/issue review, not that formal workflow.
- Local Python 3.14.3 / uv 0.5.13 verification: target `./scripts/setup` and `./scripts/verify` on main plus the CI pin pass format → lint → **13 tests, 100% line/branch coverage**; PR #16 plus the same pin passes `./scripts/verify` with **21 tests, 100% line/branch coverage**. A regression assertion confirms the workflow differs from target main only in runner selection; `git diff --check` passes. No new GitHub CI run, remote write, review submission, merge, or Docker/live Copilot run was performed for this follow-up. PR #16 still requires green independent CI before merge.

- The operator explicitly approved committing/pushing the separate CI fix and opening its PR. Committed only the one-line workflow change as `7342aa7` on `fix/ci-ubuntu-24.04`, created that previously absent remote branch with a create-only empty-ref lease, and opened [CI-fix PR #17](https://github.com/TeroTS/factory-smoke-test/pull/17). `gh pr checks 17 --watch --interval 10` observed both independent GitHub push/PR `verify` jobs passing (runs `40204881842`, `40204885798`). No merge, factory branch update, or new Copilot call occurred. PR #16's review remains free of code findings, but its original CI runs remain red until the workflow fix is incorporated and fresh checks pass. The recommended next action was to merge #17, update #16 from main, and wait for green checks before merging #16.
- Subsequent read-only checks confirm the operator merged #17, then #16. PR #16's recorded head checks still show the original setup failures; no passing pre-merge PR-head check was observed. However, independent post-merge `main` verification **passed** at final commit `c01d5fd24ae7c4dffbee70ec26b05592aff3ef2a` ([run `40205328930`](https://github.com/TeroTS/factory-smoke-test/actions/runs/40205328930)); the preceding CI-fix merge run also passed (`40205112632`). The combined change is therefore independently verified on main. No further implementation or live run is required for this smoke test.

## Not Now
- No additional explicit migration story follows US-10. Do not invent a story after it.
- Verification repairs, full manual-requeue acceptance, new coordination/publication behavior, or deadline changes.
- Arbitrary host identities, direct macOS runner support, account-mutation/root fallbacks, workspace permission repair, automatic image build/pull, or configuration migration.
- VM allocation/reprovisioning, tool/trust-root upgrades, changed forwarding/new network exposure, cloud resources, live authenticated Copilot/GitHub access, commit, or push.
- The operator authorized a fresh factory-owned test checkout, declared dependencies, scoped Docker fixtures/cleanup, and temporary use of the existing localhost:8080 forwarding. Reuse the existing shared image; no rebuild, provisioning, forwarding changes, or live authenticated service access is authorized.

## Done When
- The actual exec path preserves the baked factory UID/GID and discovered supplementary socket membership, including a differing socket GID, before target setup; missing access fails visibly without mutation/elevation/fallback.
- No runtime account/shadow/group initialization or obsolete caller/compatibility path remains.
- The real local-Lima CLI E2E produces the existing verified draft-PR outcome, and required local service/browser/ownership and failure regressions pass without weakening cleanup, publication, credential, deadline, or coverage safeguards.
- Durable instructions match the single execution path, and evidence distinguishes scripted boundaries from live authenticated services.

## Completion Summary
- An operator's labeled issue reaches the existing verified draft-PR outcome using the baked factory 2000:2000 account and creation-time supplementary socket membership, without runtime account initialization or exec user overrides. Access is checked before target setup; failure remains terminal with scoped cleanup and no root fallback.
- Local-Lima real Git/Docker CLI acceptance, explicit sudo/tool/service-volume/workspace-ownership evidence, macOS browser access through existing forwarding, and preserved failure/publication safeguards pass. Durable instructions describe the single path; coverage stays above the unchanged gate.

## Next Slice Recommendation
- No explicit next story remains in `SPEC.md`; US-08, US-09, and US-10 migration outcomes are complete. Stop implementation unless the operator requests additional work.
