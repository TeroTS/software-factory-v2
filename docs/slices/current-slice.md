# Current Slice

Status: done

## Slice Goal
- Let the operator start the runner under the fixed factory account and observe validated polling.

## Slice Boundary
- Actor: Operator.
- Trigger: A provisioned host has manual authentication, existing operator configuration, and an explicitly built updated shared agent image.
- Action: Start the runner under the factory account through the existing CLI/preflight path.
- Visible outcome: The runner validates the fixed host/image identity and enters polling.
- Authoritative state transition: Stopped configured runner → validated fixed-identity runner polling the repository.
- Include startup validation, failure diagnostics, cleanup, and interruption; do not process an issue or redesign configuration.

## Stories In Scope
- `US-09 Start the runner with the fixed factory identity`

## Stories Completed In This Slice
- `US-09 Start the runner with the fixed factory identity`

## Stories Remaining In This Slice
- None.

## Contract Inputs
- `docs/contracts.md`, Contract 1: unchanged CLI/four-field TOML, supported host/effective identity, artifact/authentication checks, immutable local image, fail-closed startup, cleanup, and exit semantics.
- `docs/contracts.md`, Contract 3: Debian-based native image, build-time factory identity/home/caches/npm prefix/account-scoped sudo, no runtime account mutation in the startup probe, and explicit rebuild/restart guidance.
- `docs/contracts.md`, Contract 9: already-provisioned Ubuntu 24.04 ARM64 Lima host; provisioning, authentication, and image builds remain explicit operator actions.
- No factory-owned HTTP API or `openapi.yaml` applies.

## Decision Inputs
- `DECISIONS.md`, Operations / Deployment and Operational / Deployment Constraints: fixed factory 2000:2000 deployment, baked image identity, local-Lima-only acceptance, ARM64 CI under the fixed identity, and explicit authorization for environment preparation.

## Shared State Required Now
- Existing provisioned local Lima Ubuntu 24.04 ARM64 host with factory UID/GID 2000:2000 and Docker access; no new account/configuration/artifact migration.
- Fixed image account/group factory 2000:2000, writable container-local `/tmp/factory-home`, XDG caches, npm user-local prefix/bin PATH, and factory-only passwordless sudo with root HOME selection.
- Existing four-field operator configuration, session-resolved immutable image ID, selected local Unix socket endpoint, and unique startup-probe cleanup identity.
- Existing retained diagnostics and workspace permissions remain unchanged.
- No issue-run state, socket-group mechanism, new configuration fields, or recovery state is added in this slice.

## Operations / Endpoints / Surfaces In This Slice
- `src/software_factory/runner.py`: reject unsupported OS/architecture and effective UID/GID before artifact/probe/issue activity; validate image identity/home/tools/sudo without calling runtime user initialization; preserve existing preflight cleanup and polling behavior.
- `agent/Dockerfile`: bake the fixed account/group/home/caches/npm prefix and account-scoped sudo; select the factory execution identity while preserving Debian and existing base/tool pins.
- `.github/workflows/verify.yml`: execute verification under factory 2000:2000 with Docker access, not the hosted runner's default identity.
- `tests/test_startup.py`, `tests/test_startup_docker.py`, affected CLI/toolchain tests and fixtures: identity rejection, image incompatibility, actual image execution, real CLI polling, and preserved failure/cleanup/interruption behavior.
- `sandbox_user_setup.py` now tolerates the already-baked home (`exist_ok=True`) and preserves its contents, keeping existing issue execution runnable until US-10 removes this initializer. No socket-group mechanism, alternate backend, or workspace repair was introduced.
- Retired the three-case real-Docker arbitrary-ID/sudo test because arbitrary identities and general image sudo are no longer supported. Added actual factory-only sudo/identity checks instead; retained other existing execution/failure regressions and initializer unit tests until US-10.
- Updated README, agent instructions, and standing guidance for the supported host, image identity, and explicit rebuild/restart. CLI/TOML, tool/base pins, and provisioning are unchanged.
- Working tree was clean at planning start. The operator authorized fresh test checkouts, declared development dependency installation, and an explicit updated image build in the existing Lima VM; no live authentication/service access was used.

## Tests Required
- Test-first host rejection: macOS/unsupported Linux release/architecture, root, wrong effective UID, and wrong effective GID; reject before commands, artifact changes, or issue claims. Valid identity continues through existing preflight checks.
- Image checks: actual factory account/group 2000:2000, selected ordinary identity, writable home/caches/npm prefix, required native tools, explicit sudo with root HOME, and rejection of old/wrong-identity/unwritable-home/broken-sudo images with rebuild/restart guidance.
- Preserve regressions for engine/image architecture and immutable ID, configuration/authentication, artifact preservation/access, partial probe startup, runtime failure, cleanup failure, and SIGTERM/interruption.
- Explicit story E2E: in the local Lima VM, run the real CLI as factory against the updated real local image with scripted authentication/GitHub boundaries; observe idle polling, no issue claims, probe cleanup, preserved prior diagnostics, and exit 130 on SIGTERM.
- Run Ruff format check → Ruff lint → tests/coverage, retaining the Python overall line/branch 80% gate. Investigate/report any coverage decrease from the previous recorded 99.34% baseline.
- Run existing real Docker/image regressions under the fixed account after an explicitly authorized image build; distinguish unchanged execution regression evidence from US-10 acceptance.
- Check affected documentation links/formatting and CI fixed-identity command behavior. No standalone type checker or Markdown linter is configured.

### Verification Evidence
- Test-first failures proved missing host/effective-identity rejection, startup's old root initialization/UID override, missing rebuild/restart guidance, absent baked image identity, and failure on an existing image home before implementation. The initial focused set then passed all 75 tests.
- Built `software-factory-agent:1.0.0` explicitly in the authorized local Lima guest; final immutable image ID is `sha256:9d2153ce3e03956cf00703c5a53afa64b9f27b7c96c0a67e89fe60e5e5f24049`. Base/tool versions and Debian snapshot pins are unchanged.
- Initial image build failed PyPI certificate verification with Zscaler enabled. After the operator disabled Zscaler and requested a retry, the build passed with TLS verification enabled. No CA, trust-root, credential, source, or verification-bypass change was made.
- The first built image's real tests caught root ownership of npm's intermediate `.local` directory. Explicitly creating that directory as factory fixed it; a rebuild passed. Real negative-image tests also caught a missing npm-bin writability check and shell `set -e` suppression in chained directory tests. After reproducing both failures, separate fail-closed checks reject missing/nonwritable cache/prefix/bin directories.
- The 23 real startup/image checks pass, including actual factory UID/GID/name, baked directories and native tools, root HOME under sudo, denied sudo for another account, wrong/root image identity, missing account, broken tools/sudo, and incompatible home/cache/prefix/bin with cleanup. The real CLI observes idle polling using scripted authentication/GitHub boundaries, preserves previous diagnostics, claims no issues, and exits 130 on SIGTERM. Final engine inspection found no `factory-startup-*` leftovers.
- `FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 ./scripts/verify` inside the Lima guest as factory 2000:2000 passed format → lint → tests/coverage: **361 passed, 3 skipped**, Python overall line/branch **99.35%**, above the prior **99.34%** baseline and unchanged **80%** gate. Skips are macOS/Lima-on-host-only checks and the separately authorized provisioning test; no provisioning was rerun.
- Existing real Docker execution and four issue-CLI outcomes passed under the new image: ordinary builds/Compose services, target-installed tool, socket/sibling mounts, host file access, scoped cleanup/sentinels, setup/verification/deadline failures, inaccessible output, interruption, and create-only local-Git/scripted-PR publication. These still use the old per-run initializer and do not establish US-10 supplementary-group acceptance.
- macOS `./scripts/verify` passed format → lint → tests/coverage: **320 passed, 44 skipped**, **99.35%** coverage. Skips are opt-in Docker/image/provisioning tests; the real Docker/image tests ran in Lima instead. CLI `--help` passed without polling.
- `git diff --check`, Markdown whitespace/fences, **24 local links/anchors**, and `bash -n` on both CI shell blocks passed. CI now stages a fresh factory-owned checkout, grants Docker membership but no host sudo, and runs setup/build/verification through explicit factory identity with both Docker opt-ins passed across sudo's environment boundary. Hosted GitHub Actions itself was not run; no commit/push was authorized.
- Test staging initially carried macOS AppleDouble metadata, causing Ruff to reject synthetic `._*.py` files in the guest. A fresh stage transferred with xattrs disabled fixed the harness; repository code/check configuration was not changed to ignore those files. Final native checkout: `/home/factory/us09.lJzOOBOJ`. Earlier stage `/home/factory/us09.ttM6PdUv` and private logs in host `artifacts/us09.ZSUoU7/` remain for operator inspection; no previous artifacts or shared image/cache resources were deleted.

### Review Follow-up Verification
- Reproduced both review findings against the real shared image before fixing them: all ten broken-tool cases failed an added invocation-marker assertion because the PATH guard short-circuited execution; unsearchable cache/bin directories incorrectly passed startup. Unsearchable home/prefix were already rejected indirectly.
- Broken-tool fixtures now install their executable into the existing npm bin directory without changing PATH, and assert its invocation marker in private command output. Startup explicitly requires search permission on home/cache/npm prefix/bin, with four real-image negative cases. The focused startup/image suite passes all **27** tests.
- `./scripts/verify` on macOS passes format → lint → tests/coverage: **320 passed, 48 skipped**. `FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 ./scripts/verify` in the existing Lima guest as factory 2000:2000 passes **365 tests, 3 skipped**. Both retain **99.35%** coverage and the unchanged 80% gate. Guest skips remain the two host-only checks and explicitly authorized provisioning test.
- Used the existing immutable shared image without rebuilding or provisioning; no live service authentication, hosted CI, commit, or push was performed. Fresh test checkout `/home/factory/us09-review.R4U56VtU` remains for inspection; earlier diagnostics/checkouts are unchanged.

## Not Now
- US-10 issue-run initialization removal, socket GID discovery/`--group-add`, actual exec supplementary-group feasibility, issue-to-draft-PR migration acceptance, and macOS browser-to-VM fixture-service evidence.
- Verification repairs, full manual-requeue acceptance, new coordination/publication behavior, or changes to the original deadline.
- Arbitrary host identities, direct macOS runner support, parallel backends, automatic migration, workspace permission repair, automatic image builds/pulls, or general host passwordless sudo.
- Reprovisioning/allocating the VM, changing trust roots, new network exposure, cloud resources, or live authenticated Copilot/GitHub access.
- Changes to VM allocation, host provisioning, credentials, trust roots, or network settings remain unauthorized; use only the existing guest and the explicitly authorized test checkout/dependencies/image build.

## Done When
- The supported fixed-identity host and compatible baked image reach polling through the unchanged CLI/TOML path, demonstrated by the real local-Lima CLI E2E with scripted external-service boundaries.
- Unsupported hosts/root/wrong IDs and incompatible images fail before claims with safe actionable diagnostics, without account switching, runtime startup account mutation, permission repair, or fallback.
- Startup retains artifact/authentication checks, immutable native local image selection, bounded probe cleanup, polling, and interruption behavior; cleanup failure blocks startup.
- ARM64 CI runs verification as factory 2000:2000, affected existing regressions pass, coverage meets the unchanged gate, and durable instructions match the supported startup behavior.
- US-10's distinct issue-execution outcome remains deferred; no live-service acceptance is claimed.

## Completion Summary
- The operator can start the unchanged CLI/TOML on the provisioned host as factory 2000:2000 and reach polling after validating the baked image's actual identity, writable directories, native tools, and explicit sudo. Startup no longer configures accounts or overrides the image user; unsupported hosts/identities and incompatible images fail before claims with rebuild/restart guidance.
- Required startup cleanup, artifact preservation, interruption, existing issue-execution regressions, and the unchanged coverage gate pass in the local Lima acceptance environment. No live provider/GitHub access, CA changes, provisioning, commit, or push was performed.

## Next Slice Recommendation
- `US-10 Execute issue runs without runtime account initialization`: remove the remaining per-run initializer/callers/obsolete fixtures and prove socket GID discovery plus `--group-add` through actual exec before relying on it. Preserve existing first-pass issue-to-draft-PR behavior, and add the distinct migration E2E and macOS-browser-to-VM-service evidence. Return to the operator if the accepted supplementary-group mechanism fails; do not add a root/account-mutation fallback. No other explicit migration story follows US-10.
