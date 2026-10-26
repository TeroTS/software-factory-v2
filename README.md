# Autonomous Coding Factory

Turns GitHub issues labeled `agent:implement` into verified draft PRs using a local
Python runner, a shared Linux agent image, and Pi/Copilot. Human review and target
CI remain required; the factory never merges.

## Development

Requires Python **3.14.3**, **uv 0.5.13**, Make, a POSIX shell, and Git.
From the repository root:

```sh
./scripts/setup
uv run --frozen python -m software_factory --help
./scripts/verify
```

Ordinary verification needs no Docker or credentials. It checks Ruff formatting,
lint, and tests with an **80%** line/branch coverage gate, including the Pi bridge.

| Command | Purpose |
| --- | --- |
| `make format` | Apply formatting. |
| `make format-check` | Check formatting without changes. |
| `make lint` | Check lint rules. |
| `make test` | Run tests without the coverage gate. |
| `make coverage` | Run tests with coverage. |

## Run the factory

Run on provisioned **Ubuntu 24.04 LTS ARM64** as **factory 2000:2000**, with local
native Docker/Compose, Git, authenticated `gh`, and authenticated Pi/Copilot
(tested Pi **1.3.0**). Direct macOS execution and remote Docker engines are unsupported.
Follow [host provisioning](docs/operations.md#operator-setup) first.

As `factory`, from a factory-owned checkout on the Linux disk:

```sh
./scripts/setup
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
```

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

```sh
uv run --frozen python -m software_factory --config /absolute/path/to/factory.toml
```

- Ctrl-C/SIGTERM stops the runner and attempts bounded cleanup.
- Failed runs retain private diagnostics; no automatic repair, requeue, or resume.
- Rebuild the image and restart the runner after image, instruction, or skill changes.
- **Docker access is not isolation:** the agent can effectively control the engine/host.

## Docker verification

Inside the provisioned ARM64 guest as `factory`, after building the image:

```sh
FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 ./scripts/verify
```

GitHub/Pi boundaries are scripted. Live authenticated checks and privileged
provisioning tests require explicit approval; see [extended verification](docs/operations.md#verification-beyond-unit-tests).

## Reference

- [Operator guide](docs/operations.md): provisioning, target setup, cleanup, diagnostics, extended tests.
- [Shared image](agent/README.md): build and test commands.
- [Image reference](docs/agent-image.md): pinned tools, instructions, skills, provenance, migration.
- [Agent rules](AGENTS.md) · [Domain vocabulary](CONTEXT.md) · [CI](.github/workflows/verify.yml)

Keep these instructions current when setup, configuration, or runtime requirements change.
