# Simplify Image Selection

## Goal

Remove the separate post-pull image-selection procedure. The operator pulls version-tagged
images beforehand and explicitly starts the factory using those local images.

## Proposed Changes

1. Keep `deployment.env` as the systemd image configuration; the operator supplies the
   runner and agent image references directly, without running selection smoke tests.
2. Update `infra/ec2/scripts/factory/start-runner.sh` to accept tagged image references
   while retaining local-image, ARM64, identity and stopped-state checks. Preserve the
   existing agent-image match with `factory.toml` and startup image-ID pinning.
3. Keep pulls separate from startup, `--pull=never`, explicit service start and existing
   runner preflight checks. Do not introduce automatic pulls, restarts or migrations.
4. Remove `tests/test_image_selection.py`, which tests the separate selection procedure.
   Update service tests to cover tagged images, missing local images and startup failures.
5. Run `./scripts/verify`, compare runtime and retain the 80% coverage gate. Run native
   ARM64 Docker checks on the prepared host when available.

## Constraint to Resolve Before Implementation

Do not edit other documentation as part of this change. `AGENTS.md` currently requires
pull/selection while stopped and accepted spec/contract updates before policy changes;
`docs/operations.md` still describes the selection procedure. Resolve that conflict before
implementation. The plan does not approve further documentation changes.
