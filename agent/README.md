# Shared agent image

Credential-free Linux ARM64 image for factory issue runs. Includes Python, Node,
Pi, uv, Docker CLI/Compose/buildx, build tools, and the factory's TDD/Ponytail skills.
Exact versions and digests live in the [Dockerfile](Dockerfile).

## Build and test

From the repository root on provisioned Ubuntu 24.04 ARM64, as `factory`
(UID/GID **2000:2000**) in a factory-owned checkout on the Linux disk:

```sh
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
docker build --platform linux/arm64 -f runner/Dockerfile -t software-factory-runner:test .
FACTORY_AGENT_IMAGE_TESTS=1 uv run --frozen pytest tests/test_startup_docker.py -q
FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 FACTORY_RUNNER_IMAGE_TESTS=1 ./scripts/verify
```

Tests require both images already built. Set `FACTORY_AGENT_IMAGE` and
`FACTORY_RUNNER_IMAGE` to test different local references. GitHub/Pi authentication boundaries are scripted; no live provider
request or GitHub write is made.

## Requirements

- The runner never builds or pulls the image. Rebuild explicitly and restart the
  runner after changing the image, [instructions](pi/AGENTS.md), or [skills](pi/skills/).
- Setup, Pi, and verification run as `factory` 2000:2000. Use explicit `sudo -n`
  for system installs, not whole setup scripts or builds. Permissions are not repaired.
- Targets install nonbaseline dependencies during setup and use native ARM64 tools/images.
- Keep credentials out of the image. Docker engine access gives effective engine/host
  control; this image is **not a security boundary**.

[Operator guide](../docs/operations.md) ·
[Tool pins, skill provenance, startup and migration details](../docs/agent-image.md)
