# Shared agent image reference

## Build and update

From a factory-owned checkout on an Ubuntu 24.04 ARM64 test host,
logged in as **factory 2000:2000**:

```sh
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
docker build --platform linux/arm64 -f runner/Dockerfile -t software-factory-runner:test .
FACTORY_AGENT_IMAGE_TESTS=1 uv run --frozen pytest tests/test_startup_docker.py -q
```

EC2 operators may [publish through ECR](operations.md#ec2-image-publication) and explicitly pull on the host
instead. Runner and agent tags/commits are independent: the runner supplies the bridge;
the agent supplies its tools, instructions, and skills. No new compatibility negotiation
or rollback/retention guarantee is provided.

The operator builds; the runner never builds/pulls or selects an emulation fallback.
Startup pins the local tag to an immutable image ID. **Rebuild and restart** after
changing tools, instructions, or skills; existing containers do not adopt updates.
`FACTORY_AGENT_IMAGE` and `FACTORY_RUNNER_IMAGE` select other already-built test images.

## Pinned baseline

[Dockerfile](../agent/Dockerfile) is the source of truth for image digests and tool
installation. Python/Node use pinned official images; Docker CLI/plugins come from
the pinned Docker CLI image. Debian packages use the signed **2026-03-01 UTC**
Bookworm/security snapshot, with expiry checks disabled only for that historical
snapshot—not signature verification.

| Tool | Baseline |
| --- | --- |
| Python / uv | 3.14.3 / 0.5.13 |
| Node.js / npm | 22.19.0 / 10.9.3 |
| Pi | `@earendil-works/pi-coding-agent@1.3.0` |
| Docker CLI / Compose | 28.4.0 / 2.39.4; buildx included |
| Build tools | GCC/G++ 12.2.0, Make 4.3 |
| Shell / Git | Bash 5.2.15, Git 2.39.5 |
| Utilities | curl 7.88.1, tar 1.34, unzip 6.00, CA certificates |
| sudo | 1.9.13p3, Debian snapshot revision |

Pins provide a repeatable baseline, not a security-update promise or a complete
transitive npm lockfile. Review updated pins and rerun native checks when upgrading.
Targets install nonbaseline dependencies through their setup script; uv may obtain
other Python versions, and `UV_LINK_MODE=copy` handles cross-filesystem installs.

## Runtime requirements

- The image bakes in factory **2000:2000**, writable `/tmp/factory-home`, caches,
  and a user-local npm prefix on PATH. Only factory has passwordless `sudo -n`,
  with root HOME. Use it for system installs, not entire builds/setup scripts.
- Startup checks the image's default identity and capabilities without account
  initialization or permission repair. Old incompatible images require a rebuild.
  Each issue-run container receives the socket's supplementary GID; identity and
  actual Docker access are checked before setup.
- Factory containers request `--platform linux/arm64 --pull=never`; targets inherit
  `DOCKER_DEFAULT_PLATFORM=linux/arm64` and the unmodified Docker executable.
  Explicit target platform overrides are not blocked and may invoke emulation.
- Images contain no credentials, host configuration, Docker daemon, or target code.
  Normal binds are the workspace and engine socket—not host authentication state.
  **Docker access grants effective engine/host control; this is not isolation.**

See [target preparation](operations.md#shared-image-and-target-preparation) for
setup permissions, resource labels, networking, and cleanup rules.

## Factory instructions and skills

[`agent/pi/AGENTS.md`](../agent/pi/AGENTS.md) and the checked-in
[`pi/skills/`](../agent/pi/skills/) are baked into `/opt/software-factory/pi/`.
The wrapper loads the complete factory instructions, TDD, and Ponytail full skills
in a temporary private Pi directory alongside ephemeral credential/model settings.
The issue snapshot is sent separately over stdin; temporary state is removed on
normal exit.

Factory context loads alongside target `AGENTS.md`; it does not replace Pi's system
prompt. Only the two baked skills are explicitly enabled. Discovered/configured
skills and trust-gated project configuration remain disabled. Host authentication
and model-catalog checks do not load implementation skills.

Missing/unreadable/empty required instruction or skill files fail startup/invocation
with rebuild guidance; there are no runtime downloads, updates, or fallback copies.
Git and the immutable image ID identify the bundle; no runtime checksum manifest
is used. Loading instructions does not prove model adherence to TDD or replace
verification, target CI, or human review.

### Skill provenance

Both skill directories include MIT notices. Preserve notices and review adaptations
when updating the bundle:

- **TDD:** operator-selected `TeroTS/.agents` revision
  `512ea122a8b7017f054b71479b77ea3830ea96eb`; supporting reference/license recovered
  from [obra/superpowers](https://github.com/obra/superpowers/tree/9ea7e2b6cb27161545e8d906aebd831d5311f5dd/skills/test-driven-development)
  at `9ea7e2b6cb27161545e8d906aebd831d5311f5dd` (Jesse Vincent).
  Factory adaptations add unattended safety, preserve unrelated work, replace
  clarification with blocker reporting, and use relative reference links.
- **Ponytail:** [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail/tree/09c434ab73ca43761c5d8b0c5d341926c2fba710/skills/ponytail)
  at `09c434ab73ca43761c5d8b0c5d341926c2fba710` (DietrichGebert).
  Factory adaptations fix full mode, remove interactive switching, and preserve
  target conventions, existing work/tests, TDD, and run/publication limits.

## Verification boundary

[Image tests](../tests/test_startup_docker.py) check native tools, baked file contents,
Pi context/skill loading, and real CLI startup. The startup probe has no network,
mounts, or credentials. GitHub/Pi authentication boundaries are scripted.

The [Docker suite](../tests/test_docker_integration.py) and
[issue CLI tests](../tests/test_issue_docker.py) cover real builds, services, Git,
permissions, and scoped cleanup. They make no live provider calls or GitHub writes.
For full test commands and separately approved live/provisioning checks, see
[operator verification](operations.md#docker-and-cli-tests).
