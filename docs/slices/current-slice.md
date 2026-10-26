# Current Slice

Status: done

## Slice Goal
- Load standing implementation instructions from factory-owned image context, keeping issue-specific input separate and existing execution behavior unchanged.

## Slice Boundary
- Actor: Operator.
- Trigger: Build the updated shared agent image and start the runner.
- Action: Submit an issue through the existing first-pass workflow.
- Visible outcome: Pi receives factory instructions alongside target context and a separate immutable task snapshot.
- Authoritative state transition: Compatible shared image and captured issue → implementation with factory context and separate issue data.

## Stories In Scope
- `US-11 Load standing implementation instructions from the shared image`.

## Stories Completed In This Slice
- `US-11 Load standing implementation instructions from the shared image`.

## Stories Remaining In This Slice
- None.

## Contract Inputs
- `SPEC.md`, US-11.
- `docs/contracts.md`, Contract 3: baked instructions, temporary Pi context, separate task data, fail-closed loading, existing credential/resource restrictions.
- Contracts 1–2 and 4–8: unchanged startup/claims, first-pass deadline, cleanup, publication, private diagnostics, and native target execution.

## Decision Inputs
- Operator approved the point-1 plan and implementation: extract existing instructions, load alongside target context, reject old images, preserve execution behavior; no skills.
- `DECISIONS.md`, shared image ownership, immutable session image, fixed identity, private credentials, and explicit image builds.
- SPEC/contracts govern first-pass behavior; historical repair policy is not activated.

## Shared State Required Now
- Existing shared image build definition and Pi 1.3.0; no new dependencies or TOML fields.
- `agent/pi/AGENTS.md` → `/opt/software-factory/pi/AGENTS.md` → temporary Pi agent-directory context.
- Existing immutable issue snapshot, ephemeral credentials, model selection, run identity, deadline, and cleanup/publication gates.

## Operations / Endpoints / Surfaces In This Slice
- `agent/pi/AGENTS.md`, `agent/Dockerfile`, `agent/README.md`: factory instruction source, baked location, upgrade guidance.
- `src/software_factory/sandbox_agent.py`: context loading and reduced per-issue prompt.
- `src/software_factory/runner.py`: fail-closed startup instruction validation.
- Wrapper, startup, image, toolchain, and scripted execution fixtures/tests cover the new context file. The scripted execution Pi boundary checks that temporary context equals the baked source and standing rules no longer appear in the task prompt.
- Working tree at start contained only untracked operator-owned `todo.txt`; preserve it unchanged.

## Tests Required
- Test-first wrapper assertions for factory context, separate task data, no duplicated standing prompt, existing feedback interface, credential cleanup, and missing/unreadable/empty instructions.
- Test-first startup rejection for incompatible instruction files, preserving probe cleanup and rebuild/restart guidance.
- Image content must match repository instructions; actual Pi 1.3.0 resource loading must observe factory plus target context while trust-gated project configuration stays disabled, without provider access.
- Existing scripted Docker issue fixtures must assert context loading inputs, not merely task contents.
- Ruff format check → Ruff lint → tests/coverage via `./scripts/verify`, unchanged 80% gate. Audit affected links and run `git diff --check`.
- Native Docker/image/execution verification requires an explicitly rebuilt image. The operator separately approved staging a fresh factory-owned checkout in the existing Lima guest, building `software-factory-agent:us11` without replacing the operator image tag, and running native scripted-boundary suites. No live authenticated check or reprovisioning is authorized.

## Verification Evidence
- Planning inspected the standalone wrapper, callers, Dockerfile, startup probe, tests, Pi 1.3.0 documentation and context loader. Agent-directory context loads alongside repository context without granting project trust.
- Test-first `uv run --frozen pytest tests/test_agent_wrapper.py tests/test_startup.py tests/test_toolchain.py -q` produced **23 failed, 75 passed**: missing temporary instruction context prevented the scripted Pi catalog check, missing/unreadable/empty instructions were not safely rejected, startup lacked the instruction checks, and the image lacked the COPY. After the extraction/loading implementation, the same focused suite passed **98 tests**.
- `agent/pi/AGENTS.md` preserves the existing standing rules, correcting stale host-matched-user wording to the fixed factory identity. Docker copies it outside the workspace/home. The wrapper reads/validates it before creating credentials, writes it into the private temporary Pi agent directory, and keeps only the implementation/repair request and existing task/feedback data in stdin. Repair invocation is not activated; existing flags/model/provider/tools and lifecycle gates remain unchanged.
- Startup checks for a regular file containing non-whitespace instructions and rejects incompatible images with rebuild/restart guidance. Wrapper failures for missing files, read errors, empty/whitespace-only contents, missing Pi/model, catalog/execution failures, and termination leave no temporary context/credentials behind. Both actual child-process and in-process coverage paths are exercised; deployment file access is redirected only in host tests.
- `./scripts/verify` passes Ruff format check → Ruff lint → **323 passed, 57 skipped**, Python overall line/branch coverage **99.33%**, unchanged from the recorded US-10 baseline and above the unchanged **80%** gate. The standalone wrapper has **100%** measured line/branch coverage. Skips are the opt-in Docker/image/provisioning checks; no exclusions or thresholds changed. Ruff formatting was applied only to the changed image test file.
- Executed the new image-test resource-loader JavaScript against the already-installed host **Pi 1.3.0**, adapting only the package/source paths, with `PI_OFFLINE=1` and `PI_TELEMETRY=0`: all assertions passed. Factory and target context load together; a target `AGENTS.override.md` replaces only target context; untrusted project model settings and system/append prompts stay disabled. No session/model request, credential access, or provider call was made. This is host evidence, not proof of the rebuilt image.
- Final `git diff --check` passes. A standard-library Markdown check validated **15 local links/anchors** plus whitespace and balanced fences across the five affected Markdown files. No standalone type checker or Markdown linter is configured.
- Added native tests for exact baked source content, actual Pi context loading under `--network none`, and missing/unreadable/empty/whitespace instruction startup rejection with probe cleanup. Updated real Docker execution fixtures to inspect temporary context. These initially awaited separate image-build/guest-execution authorization, granted by the operator's subsequent “proceed”.
- Before native work, read-only checks confirmed the existing Lima `factory` guest was running natively on ARM64, factory identity was **2000:2000** with Docker group **988**, no factory runner/test/build was active, and about **31 GiB** disk space was available. There were no containers or volumes and only the three default Docker networks. The `us11` image tag did not exist. No operator authentication was read or copied.
- Staged **53** current repository files, including the new `agent/pi/AGENTS.md` but excluding operator-owned untracked `todo.txt`, into a fresh private factory-owned Linux checkout at `/home/factory/us11.1iIHesIp`. Initialized fresh Git metadata so ordinary ignore handling applies. As factory, `./scripts/setup` installed only locked dependencies, then `docker build --platform linux/arm64 -t software-factory-agent:us11 agent` succeeded. Existing pinned baseline layers were cached; the new instruction COPY was built explicitly.
- The separate native test image resolves to **`sha256:b082e55e3bc093abab7cad14787600417e4e80df598626e751611a412109b20e`**, `linux/arm64`. Operator image `software-factory-agent:1.0.0` remains unchanged at **`sha256:9d2153ce3e03956cf00703c5a53afa64b9f27b7c96c0a67e89fe60e5e5f24049`**; no operator configuration, running container, or immutable runner session was updated.
- In that checkout as factory **2000:2000**, `FACTORY_AGENT_IMAGE=software-factory-agent:us11 FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 ./scripts/verify` passed Ruff format check → Ruff lint → **377 passed, 3 skipped**, with **99.33%** overall Python line/branch coverage and **100%** wrapper coverage. Coverage matches the host/US-10 baseline and the unchanged 80% gate. Guest skips are Lima configuration validation requiring macOS-installed `limactl`, the macOS-only rejection check (covered by host verification), and separately authorized provisioning. No relevant native image/execution check was skipped.
- Native evidence includes exact baked instruction contents, actual pinned Pi context loading with network disabled, factory context surviving a target `AGENTS.override.md`, untrusted project configuration staying disabled, and all four instruction-file startup failures removing their probes. Real Docker/CLI suites also passed context-copy/task-separation assertions, setup/verification/credential/identity/access/interruption/cleanup/publication regressions, and unrelated sentinel preservation. Pi/authentication/GitHub issue/publication boundaries were scripted; no live provider call or GitHub write occurred.
- Final local/guest SHA-256 comparison confirms all **39 source/test/toolchain/instruction files** match the native tested checkout. Markdown checks again passed **15 local links/anchors** and whitespace/fences in five files, and `git diff --check` passed.
- Post-verification inspection confirms no containers, volumes, active factory runners, or non-default networks remain; the same three original default network IDs remain. Test fixtures cleaned their owned resources only. The separate test image, build cache, fresh checkout, and private diagnostics remain for inspection. Local evidence is under ignored `artifacts/us11/` (`setup-build.log`, `verify-native.log`, `post-verification.txt`, `guest-path`); guest coverage reports are inside the fresh checkout. No provisioning, network changes, live authenticated checks, commit, or push occurred. Operator-owned untracked `todo.txt` remains unchanged.

## Not Now
- TDD/Ponytail skill bundling (todo point 2), planning/publishing tickets, routing, parallelism, reviews, cloud deployment, notifications, or other backlog items.
- Repair activation, new settings/dependencies, credential or image-versioning frameworks, replacing target AGENTS.md, or changing the default system prompt.
- Image rebuild, provisioning, network changes, live authenticated service checks, commit, or push without separate authorization.

## Done When
- Existing reusable instructions live in the image-owned version-controlled context, not the Python prompt; issue data remains separate.
- Startup and wrapper fail visibly rather than running without factory instructions; target context and existing safety/credential/lifecycle behavior remain intact.
- Tests and documentation cover the changed boundary, with native verification gaps stated explicitly.

## Completion Summary
- Standing implementation rules now live in factory-owned version-controlled image context, not in the Python task prompt. Pi receives factory plus target context and separate immutable task data; unavailable/empty factory instructions fail closed at startup and invocation.
- Host and real native Linux image/execution verification pass without changing skills, credentials, settings, execution ordering, deadlines, or cleanup/publication gates. No live authenticated smoke test is needed for this extraction.

## Next Steps
- No further US-11 implementation or verification remains. No later todo item is automatically in scope.
- Operator deployment is not performed: explicitly select the updated image and restart the updated runner when ready, after inspecting trigger labels. The retained `us11` test image is available in the existing guest; the operator's `1.0.0` tag/configuration remains unchanged. No running container or immutable session image adopts these changes automatically.
