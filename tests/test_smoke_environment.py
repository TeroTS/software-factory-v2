import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from tests_support import prepared_compose

from software_factory.config import load_config
from software_factory.process import Commands
from software_factory.repository import Repository
from software_factory.runner import preflight
from software_factory.sandbox import PI_FLAGS, Sandbox, copilot_endpoint

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "artifacts" / "operator" / "factory-smoke-test.toml"


@pytest.mark.skipif(not CONFIG.is_file(), reason="operator-owned configuration is local, not versioned")
def test_smoke_environment_configuration_exists() -> None:
    config = load_config(CONFIG)
    assert config.repository == "TeroTS/factory-smoke-test"
    assert config.compose_service == "agent"
    assert config.model == "gpt-6.1-sol"
    assert (config.compose_file.parent / "Dockerfile").is_file()


def test_docker_test_fixture_matches_host_workspace_owner(tmp_path: Path) -> None:
    assert prepared_compose(tmp_path)["services"]["agent"]["user"] == f"{os.getuid()}:{os.getgid()}"


@pytest.mark.skipif(
    os.environ.get("FACTORY_SMOKE_SANDBOX_TESTS") != "1",
    reason="explicit opt-in required: real Docker, target checkout, and Copilot; no GitHub writes",
)
def test_prepared_smoke_environment_runs_setup_pi_and_verification() -> None:
    config = load_config(CONFIG)
    prepared = preflight(config)
    artifacts = ROOT / "artifacts" / "smoke-sandbox-validation"
    artifacts.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="probe-", dir=artifacts))
    commands = Commands(time.monotonic() + 900, directory / "run.log")
    repository = Repository(directory, commands)
    base = repository.checkout("https://github.com/TeroTS/factory-smoke-test.git", "main")
    for service in prepared["services"].values():
        for volume in service.get("volumes", []):
            if volume.get("type") == "bind":
                volume["source"] = str(repository.workspace)
    sandbox = Sandbox(prepared, config.compose_service, directory, commands)
    try:
        sandbox.start()
        versions = {}
        for tool, expected in [("node", "v22.19.0"), ("python", "Python 3.14.3"), ("uv", "uv 0.5.13"), ("pi", "1.3.0")]:
            result = commands.run(
                sandbox.base + ["exec", "-T", "agent", tool, "--version"],
                "runtime version",
                cwd=directory,
                env=sandbox.env,
            ).strip()
            assert result.startswith(expected), (tool, result)
            versions[tool] = result
        identity = commands.run(
            sandbox.base + ["exec", "-T", "agent", "id", "-u"], "sandbox identity", env=sandbox.env
        ).strip()
        assert identity == str(os.getuid()), "rebuild the image with this host's RUN_UID/RUN_GID"
        sandbox.setup()
        sandbox.verify()
        bearer = commands.run(
            [
                "pi",
                "auth",
                "print-bearer-token",
                "--provider",
                "github-copilot",
                "--min-expiry",
                "20m",
                *PI_FLAGS,
                "--no-context-files",
                "--offline",
            ],
            "Copilot authentication",
            cwd=directory,
            private=True,
        ).strip()
        commands.secrets.append(bearer)
        sandbox.implement(
            {
                "number": 1,
                "title": "Create smoke-sandbox-probe.txt containing exactly ready followed by a newline",
                "body": (
                    "This is a local sandbox preparation probe, not a GitHub issue run. "
                    "Do not modify existing files, create other files, commit, publish, "
                    "or retrieve remote task context."
                ),
                "base_commit": base,
            },
            bearer,
            copilot_endpoint(bearer),
            config.model,
        )
        assert (repository.workspace / "smoke-sandbox-probe.txt").read_text() == "ready\n"
        sandbox.verify()
        assert repository.git("status", "--porcelain", "--untracked-files=all").strip() == "?? smoke-sandbox-probe.txt"
        assert bearer not in (directory / "run.log").read_text()
        image = prepared["services"]["agent"]["image"]
        image_id = subprocess.check_output(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"], text=True
        ).strip()
        (directory / "result.json").write_text(
            json.dumps(
                {
                    "base_commit": base,
                    "image_id": image_id,
                    "versions": versions,
                    "setup": "passed",
                    "pi": "passed",
                    "verify": "passed",
                },
                indent=2,
            )
            + "\n"
        )
        print(f"Validated target main {base}; sanitized evidence: {directory / 'result.json'}")
    finally:
        sandbox.stop()
        leftovers = subprocess.check_output(
            ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={sandbox.project}"],
            text=True,
        )
        assert not leftovers.strip()
