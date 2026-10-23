import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from tests_support import prepared_compose

from software_factory.process import Commands, FactoryError
from software_factory.sandbox import PI_FLAGS, Sandbox, copilot_endpoint, docker_environment, prepare_compose

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("FACTORY_DOCKER_TESTS") != "1", reason="set FACTORY_DOCKER_TESTS=1 for real Docker tests"
    ),
]
IMAGE = "alpine:3.21.3"


@pytest.fixture(scope="module", autouse=True)
def docker_image() -> None:
    subprocess.run(["docker", "info"], check=True, capture_output=True)
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode:
        subprocess.run(["docker", "pull", IMAGE], check=True, capture_output=True)


@pytest.fixture
def sandbox(tmp_path: Path, request: pytest.FixtureRequest):
    workspace = tmp_path / "workspace"
    scripts = workspace / "scripts"
    scripts.mkdir(parents=True)
    for name, body in [("setup", "echo ready > prepared"), ("verify", "test -f prepared && test -f implemented")]:
        path = scripts / name
        path.write_text("#!/bin/sh\nset -eu\n" + body + "\n")
        path.chmod(0o755)
    data = prepared_compose(workspace, IMAGE)
    if getattr(request, "param", None) == "dependency":
        data["services"]["dependency"] = {
            "image": IMAGE,
            "command": [
                "sh",
                "-c",
                "while true; do printf 'HTTP/1.1 200 OK\\r\\nContent-Length: 13\\r\\n"
                "Connection: close\\r\\n\\r\\nservice-ready'"
                " | nc -l -p 8080; done",
            ],
            "healthcheck": {
                "test": ["CMD", "wget", "-q", "-O", "/dev/null", "http://localhost:8080"],
                "interval": "1s",
                "timeout": "1s",
                "retries": 5,
            },
        }
        data["services"]["agent"]["depends_on"] = {"dependency": {"condition": "service_healthy"}}
        (scripts / "verify").write_text(
            "#!/bin/sh\nset -eu\nwget -qO dependency-response http://dependency:8080\n"
            "grep -qx service-ready dependency-response\n"
        )
    config = tmp_path / "operator-compose.json"
    config.write_text(json.dumps(data))
    resolved = json.loads(
        Commands().run(
            ["docker", "compose", "--env-file", "/dev/null", "-f", str(config), "config", "--format", "json"],
            "test config",
            env=docker_environment(workspace),
        )
    )
    commands = Commands(log=tmp_path / "run.log")
    instance = Sandbox(prepare_compose(resolved, "agent", workspace), "agent", tmp_path, commands)
    try:
        instance.start()
        yield instance, workspace
    finally:
        instance.stop()
        ids = subprocess.check_output(
            ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={instance.project}"], text=True
        )
        assert ids.strip() == ""


def test_real_compose_setup_implementation_verify_and_isolation(sandbox) -> None:
    instance, workspace = sandbox
    instance.setup()
    instance.commands.run(instance.base + ["exec", "-T", "agent", "touch", "implemented"], "test implementation")
    instance.verify()
    assert (workspace / "prepared").read_text().strip() == "ready"
    ids = instance.commands.run(instance.base + ["ps", "-q"], "test inspect").strip().splitlines()
    for container in ids:
        inspected = json.loads(subprocess.check_output(["docker", "inspect", container], text=True))[0]
        assert not inspected["HostConfig"]["Privileged"]
        assert inspected["HostConfig"]["RestartPolicy"]["Name"] == "no"
        binds = [mount["Source"] for mount in inspected["Mounts"] if mount["Type"] == "bind"]
        assert binds == [str(workspace)]
        assert not any("GH_TOKEN=" in value or "GITHUB_TOKEN=" in value for value in inspected["Config"]["Env"])


@pytest.mark.parametrize("sandbox", ["dependency"], indirect=True)
def test_verification_uses_real_local_dependency_service(sandbox) -> None:
    instance, workspace = sandbox
    instance.setup()
    instance.verify()
    assert (workspace / "dependency-response").read_text() == "service-ready"


def test_real_nonzero_verification_is_not_success(sandbox) -> None:
    instance, _ = sandbox
    instance.setup()
    with pytest.raises(FactoryError, match="verification failed"):
        instance.verify()


def test_missing_scripts_prevent_setup(sandbox) -> None:
    instance, workspace = sandbox
    (workspace / "scripts" / "verify").unlink()
    with pytest.raises(FactoryError, match="required entrypoints"):
        instance.setup()
    assert not (workspace / "prepared").exists()


def test_real_setup_failure_is_visible(sandbox) -> None:
    instance, workspace = sandbox
    (workspace / "scripts" / "setup").write_text("#!/bin/sh\nexit 8\n")
    with pytest.raises(FactoryError, match="setup failed"):
        instance.setup()


@pytest.mark.skipif(
    os.environ.get("FACTORY_COPILOT_TESTS") != "1", reason="requires explicit opt-in to real Copilot use"
)
def test_real_pi_copilot_can_implement_in_isolated_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    commands = Commands(time.monotonic() + 900, tmp_path / "run.log")
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
        cwd=tmp_path,
        private=True,
    ).strip()
    commands.secrets.append(bearer)
    image = os.environ.get("FACTORY_COPILOT_IMAGE", "software-factory-pi-feasibility:local")
    data = prepare_compose(prepared_compose(workspace, image), "agent", workspace)
    instance = Sandbox(data, "agent", tmp_path, commands)
    try:
        instance.start()
        instance.implement(
            {
                "number": 1,
                "title": "Create probe.txt containing exactly ready followed by a newline",
                "body": (
                    "This is an empty probe workspace. Create only that one file; "
                    "no setup, tests, Git, or network context is needed."
                ),
            },
            bearer,
            copilot_endpoint(bearer),
            "gpt-6.1-sol",
        )
        assert (workspace / "probe.txt").read_text() == "ready\n"
        assert bearer not in (tmp_path / "run.log").read_text()
    finally:
        instance.stop()


def test_deadline_stops_execution_and_cleanup_still_runs(sandbox) -> None:
    instance, workspace = sandbox
    (workspace / "scripts" / "setup").write_text("#!/bin/sh\nsleep 2\ntouch too-late\n")
    instance.commands.deadline = time.monotonic() + 0.3
    with pytest.raises(FactoryError, match="deadline"):
        instance.setup()
    instance.stop()
    time.sleep(2)
    assert not (workspace / "too-late").exists()
