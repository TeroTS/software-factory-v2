# Autonomous Coding Factory

Turns GitHub issues labeled `agent:implement` into verified draft PRs using a local
Python runner, a shared Linux agent image, and Pi/Copilot. Human review and target
CI remain required; the factory never merges.

## Development

Requires Python **3.14.3**, **uv 0.5.13**, Node **22 LTS**/npm, Make, a POSIX shell, and Git.
Node/CDK are operator/development tools only; setup locks the local CDK CLI with `npm ci`.
From the repository root:

```sh
./scripts/setup
uv run --frozen python -m software_factory --help
./scripts/verify
```

Ordinary verification needs no Docker or credentials. It checks Ruff formatting,
lint, tests with an **80%** line/branch coverage gate (including the Pi bridge and Python CDK),
CDK synthesis, and host-script syntax.

| Command | Purpose |
| --- | --- |
| `make format` | Apply formatting. |
| `make format-check` | Check formatting without changes. |
| `make lint` | Check lint rules. |
| `make test` | Run tests without the coverage gate. |
| `make coverage` | Run tests with coverage. |

## Run the factory

Deploy the runner **only as a container on AWS EC2**, using **Ubuntu 24.04 LTS ARM64**,
**factory 2000:2000**, and local native Docker. CloudFormation UserData prepares retained
storage, Docker, AWS CLI for EC2-role ECR authentication, and factory identity;
it never authenticates or starts factory execution.
Runner Git/`gh`/Python/Node/Pi and Compose belong in images. Private GitHub App and
Pi/Copilot state persists outside containers. Remote Docker engines are unsupported.
Follow [EC2 host setup](docs/operations.md#ec2-host-setup), then
[manual authentication](docs/operations.md#authentication). No host checkout or separate
provisioner is needed. Build/publish images on the operator computer; see
[image publication](docs/operations.md#ec2-image-publication).

Keep operator TOML outside the target checkout/workspace, for example
`artifacts/operator/factory.toml`:

```toml
repository = "TeroTS/factory-smoke-test"
model = "gpt-6.1-sol"
agent_image = "software-factory-agent:1.0.0"
artifacts_dir = "../runs"
```

Exactly these four fields are required. Use an accessible Copilot model ID;
relative artifact paths resolve against the TOML directory. Never put credentials
in this file.

The target repository must already provide executable, noninteractive
`./scripts/setup` and `./scripts/verify`; verification must match target CI.
See [target preparation](docs/operations.md#shared-image-and-target-preparation)
for permissions and Docker resource conventions.

**Inspect existing trigger labels before starting:** already-labeled issues are eligible.
Run only one runner per repository.

Run the selected runner image through its explicit systemd start, with configuration,
private state, same-path artifacts, and the local Docker socket mounted as described in
the [operator guide](docs/operations.md#ec2-image-publication). Do not invoke host Python
to deploy the runner.

Application logs are JSON Lines on **stderr**, with **INFO** progress enabled by
default; logging leaves stdout unused. Each record has UTC `timestamp`, `level`,
`event`, and `message`, plus `repository`, `issue`, `phase`, `run_id`, and `pr_url`
when available. Command output remains in private run logs. See
[diagnostics](docs/operations.md#diagnostics-and-safety) for collection and limits.

- Ctrl-C/SIGTERM stops the runner and attempts bounded cleanup.
- Failed runs retain private diagnostics; no automatic repair, requeue, or resume.
- Rebuild the image and restart the runner after image, instruction, or skill changes.
- GitHub uses the configured App installation, not personal `gh` login. Host credentials
  survive runner stop/start; short-lived tokens renew automatically. Workflow-file
  changes are blocked in this version.
- **Docker access is not isolation:** the agent can effectively control the engine/host.

## Docker verification

On an Ubuntu ARM64 test host as `factory`, with the development dependencies installed
separately and the shared image already built:

```sh
docker build --platform linux/arm64 -f runner/Dockerfile -t software-factory-runner:test .
FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 FACTORY_RUNNER_IMAGE_TESTS=1 ./scripts/verify
```

GitHub/Pi boundaries are scripted. Live authenticated checks require explicit approval;
see [extended verification](docs/operations.md#verification-beyond-unit-tests).

## Reference

- [Operator guide](docs/operations.md): provisioning, target setup, cleanup, diagnostics, extended tests.
- [Shared image](agent/README.md): build and test commands.
- [Image reference](docs/agent-image.md): pinned tools, instructions, skills, provenance, migration.
- [Agent rules](AGENTS.md) · [Domain vocabulary](CONTEXT.md) · [CI](.github/workflows/verify.yml)

Keep these instructions current when setup, configuration, or runtime requirements change.
