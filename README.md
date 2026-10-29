# Autonomous Coding Factory

Turns GitHub issues labeled `agent:implement` into verified draft PRs using a Python
runner and Pi/Copilot in a shared Linux agent image. GitHub holds coordination state;
there is no database or HTTP API. Human review and target CI remain required; the factory never merges.

## Development

Requires Python **3.14.3**, **uv 0.5.13**, Node **22 LTS**/npm, Make, a POSIX shell and Git.
From the repository root:

```sh
./scripts/setup
uv run --frozen python -m software_factory --help
./scripts/verify
```

Setup installs locked dependencies. Verification needs no Docker or credentials and runs
Ruff format/lint, tests with an **80%** line/branch coverage gate, CDK synthesis and shell syntax checks.
Use `make format` to format, `make test` for tests alone, or `make coverage` for the coverage gate.
[Docker/CLI tests](docs/operations.md#docker-and-cli-tests) require the prepared ARM64 test host;
live GitHub/Copilot checks require explicit approval.

## Run the factory

Deployment is **container-only on AWS EC2**, Ubuntu 24.04 ARM64, factory **2000:2000**,
with local native Docker. Runner and agent images are independently versioned.
Follow the [operator guide](docs/operations.md) for host setup, image selection and manual authentication.

Keep `/home/factory/.config/software-factory/factory.toml` outside the target checkout:

```toml
repository = "TeroTS/factory-smoke-test"
model = "gpt-6.1-sol"
agent_image = "software-factory-agent:1.0.0"
```

Exactly these three fields are required; `agent_image` must match the selected agent reference.
Use an accessible Copilot model ID, never credentials. Artifacts are fixed at `/home/factory/artifacts`;
remove legacy `artifacts_dir`/Compose fields explicitly without moving prior diagnostics.
Targets must supply executable, noninteractive `./scripts/setup` and `./scripts/verify` matching target CI.

**Inspect eligible issues before [starting](docs/operations.md#explicit-start):** already-labeled issues
can execute immediately. Run one runner per repository; no automatic restart, requeue or recovery.
Inspect [health](docs/operations.md#operational-health) and retained diagnostics before intervening.
**Docker access grants effective engine/host control, not isolation.**

## Plan a target backlog

Use the repo-local `.agents/skills/` in order: `grill-me`, `decision-to-spec`, then
`spec-to-tickets`. The last skill creates a local plan for review, without GitHub writes.
Validate it with `uv run --frozen python -m software_factory.planning validate --plan PLAN`.
Publication and backlog activation require separate explicit operator requests.

## Reference

- [Operator guide](docs/operations.md): deployment, authentication, health and recovery.
- [Image reference](docs/agent-image.md): tool pins, build/test commands, instructions and skills.
- [Specification](SPEC.md) · [Vocabulary](CONTEXT.md) · [Agent rules](AGENTS.md) · [CI](.github/workflows/verify.yml).

Update guidance when setup, configuration or runtime requirements change.
