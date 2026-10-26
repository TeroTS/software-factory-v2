# Simplify validation

## Scope

Remove checks that enforce incidental file/layout details rather than useful
runtime behavior. Cover all four findings from the review. Do not add a replacement
validation framework, configuration options, dependencies, or checksum mechanism.

This is a plan only. Do not update existing documentation or slice notes. Preserve
all unrelated working-tree changes, including `todo.txt`. Skill checksum manifests
and checks are already removed from the source; do not reintroduce them.

## 1. Never check LICENSE files

- Keep existing license files bundled. Do not validate their existence, contents,
  readability, size, or checksums in runtime code, build checks, or tests.
- Remove license paths from the required-file lists in
  `src/software_factory/runner.py` and `sandbox_agent.py`.
- Remove license fixtures and failure cases from `tests/test_agent_wrapper.py`,
  `tests/test_startup.py`, and `tests/test_startup_docker.py`.
- In `tests/test_toolchain.py`, remove license-file reads and the exact directory
  inventory assertion. Check only files actually needed by Pi.
- In the native image-content test, read and compare only the two `SKILL.md` files
  and the TDD supporting reference. Do not recursively read the whole bundle,
  because that currently reads and compares LICENSE files indirectly.
- Keep required instruction/reference readability and nonempty checks. License
  files must not affect startup or implementation success.

Proof: wrapper and startup fixtures contain no license files and still succeed;
missing/empty actual instruction or reference files still fail. No test should
remove or corrupt a license file to test its handling: stop checking them entirely.

## 2. Reduce startup checks to capabilities

Affected code: `RUNTIME_CHECK` in `src/software_factory/runner.py`; inspect
`Sandbox.start()` in `sandbox.py` so startup and issue execution remain consistent.

- Keep numeric UID/GID checks, usable home/cache/npm directories, executable
  tools, working noninteractive sudo, actual issue-run Docker access, and native
  engine/image checks.
- Remove redundant account-name/account-database assertions, exact cache/prefix
  path comparisons, and the requirement that the npm directory be first on PATH.
  Review the home ownership assertion as image-layout validation rather than a
  substitute for actual usability.
- Keep necessary read/write/search capability checks. Do not replace a few shell
  checks with a new probing subsystem or automatic directory/permission repair.
- Put factory-image layout assertions in existing native image tests, where image
  construction is tested once. Do not move LICENSE checks there.
- Update startup unit tests and native failure cases to test retained capabilities,
  not incidental layout. Keep rejection of root/wrong numeric identity, broken
  tools, inaccessible required directories, failed sudo, and cleanup failures.
- Preserve the existing factory-built image layout and execution environment; this
  does not add support for arbitrary images or configurable directory layouts.

Proof: a harmless extra PATH directory does not fail startup; missing capabilities
still fail before polling. Existing issue execution continues to use the same
factory identity and working tool environment.

## 3. Remove brittle source/prose/format tests

Affected tests: `tests/test_toolchain.py` and overlapping startup/image tests.

- Remove exact-phrase assertions against natural-language instructions.
- Remove the regex requiring skill frontmatter fields in one particular order.
  Use the existing actual pinned-Pi loader test to prove both skills parse/load
  without diagnostics; do not introduce a YAML parser or custom schema validator.
- Remove exact skill-directory inventory requirements. Extra harmless documentation
  must not fail tests or become an additional automatically loaded skill.
- Remove redundant Dockerfile text assertions where existing native image tests
  already prove the resulting identity, environment, and capabilities.
- Keep tests that prove full factory instructions reach Pi, task data stays
  separate, only the two approved skills load, and credentials are removed.
- Keep image-to-repository content comparisons for required instruction/reference
  files: those test correct packaging, not prescribed prose or YAML formatting.

Proof: reordered valid frontmatter loads through pinned Pi; an extra README does
not affect loading; missing or invalid required skills are still caught. Preserve
restricted discovery, target context/overrides, and untrusted-config behavior.

## 4. Separate APT installation pins from readiness

Affected code: `check_readiness()` in `src/software_factory/provision.py` and
`tests/test_provision.py`.

- Remove the readiness loop requiring every APT package to match its exact recorded
  patch version. Use the existing functional tool, Python-module, identity, sudo,
  socket, and Docker checks; do not add another package/version checker.
- Keep exact package pins for explicit installation, signed repositories, downloaded
  release verification, and existing intentional Python/Node/uv/Pi version checks.
- Keep `package_matches()` where installation actually needs it. Do not remove it
  just because readiness stops calling it.
- Add a regression showing working tools with a newer APT security patch pass
  readiness, while missing/broken tools or native Docker access still fail.

Policy boundary: this relaxes operational readiness, not fresh-install pins or
upgrade behavior. Re-running installation after package upgrades can still follow
the current exact-pin installation path; changing that is a separate decision.
The proposed layout/readiness relaxations differ from existing strict requirements;
confirm that policy change before implementing those parts. The instruction to
never check LICENSE files is already explicit.

## Execution order and verification

1. Implement LICENSE-check removal first, then startup simplification, brittle-test
   removal, and APT readiness relaxation. Do not expand into unrelated cleanup.
2. For production behavior changes, write/update a focused test and observe the
   expected failure before editing production code. Retain meaningful failures;
   do not trade away safety checks or lower coverage to simplify tests.
3. Run relevant focused suites, then `./scripts/verify` (format, lint, tests/coverage)
   with the unchanged 80% gate. Investigate any coverage decrease.
4. Audit remaining source/tests for direct or indirect LICENSE-file validation.
   Leave ordinary bundled files and license metadata alone.
5. Rebuild a separate test image and rerun native image/startup/issue suites only
   with explicit authorization. Previously built images retain earlier checks;
   do not replace operator tags/configuration or claim they adopted source edits.
6. Report results directly. No slice-note or other documentation updates, commit,
   push, provisioning, live provider calls, or GitHub writes.

Keep credential validation/redaction, external-download signatures/checksums,
create-only branch publication, cleanup ownership and publication gates, trusted
host Git handling, and the original issue-run deadline unchanged.
