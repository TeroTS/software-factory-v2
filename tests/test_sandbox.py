import json
import os
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from software_factory.process import FactoryError
from software_factory.sandbox import PI_FLAGS, Sandbox, VerificationFailed, copilot_endpoint

IMAGE = "sha256:" + "a" * 64


@pytest.fixture
def sandbox(tmp_path: Path):
    commands = Mock()
    commands.secrets = ["private-bearer"]
    commands.log = tmp_path / "run.log"
    commands.run.return_value = ""
    instance = Sandbox(IMAGE, "unix:///local/docker.sock", tmp_path, commands)
    return instance, commands


def test_shared_image_start_has_same_path_socket_and_cooperative_identity(sandbox, monkeypatch) -> None:
    instance, commands = sandbox
    monkeypatch.setenv("GH_TOKEN", "host-secret")
    instance.start()
    start = next(call for call in commands.run.call_args_list if call.args[1] == "agent startup")
    args = start.args[0]
    assert IMAGE in args
    assert args[args.index("--platform") + 1] == "linux/arm64"
    assert args[args.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"
    workspace = str(instance.directory / "workspace")
    assert f"type=bind,src={workspace},dst={workspace}" in args
    assert f"type=bind,src={instance.socket_path},dst=/var/run/docker.sock" in args
    assert f"FACTORY_RUN_ID={instance.project}" in args
    assert f"COMPOSE_PROJECT_NAME={instance.project}" in args
    assert "DOCKER_DEFAULT_PLATFORM=linux/arm64" in args
    assert f"software-factory.run-id={instance.project}" in args
    assert "GH_TOKEN" not in start.kwargs["env"]
    assert "host-secret" not in " ".join(args)
    assert "--pull=never" in args
    assert len(commands.run.call_args_list) == 2
    initialize = commands.run.call_args_list[1]
    assert initialize.args[1] == "agent user configuration"
    assert initialize.args[0][:5] == ["docker", "exec", "--user", "0:0", instance.project]
    script = Path(__file__).resolve().parents[1] / "src/software_factory/sandbox_user_setup.py"
    assert script.is_file(), "user setup must be a standalone Python script"
    assert initialize.args[0][5:] == [
        "/usr/local/bin/python",
        "-I",
        "-c",
        script.read_text(),
        str(os.getuid()),
        str(os.getgid()),
    ]
    assert "HOME=/tmp/factory-home" in args
    assert "XDG_CACHE_HOME=/tmp/factory-home/.cache" in args
    assert instance.base == ["docker", "exec", "--user", str(os.getuid()), "-i", instance.project]


@pytest.mark.parametrize("platform,expected", [("darwin", "/var/run/docker.sock"), ("linux", "/local/docker.sock")])
def test_socket_mount_uses_daemon_path_not_desktop_host_proxy(tmp_path, monkeypatch, platform, expected) -> None:
    monkeypatch.setattr("software_factory.sandbox.sys.platform", platform)
    instance = Sandbox(IMAGE, "unix:///local/docker.sock", tmp_path, Mock())
    assert instance.socket_path == expected


def test_setup_implementation_and_verification_stay_inside_agent(sandbox) -> None:
    instance, commands = sandbox
    instance.setup()
    instance.implement({"number": 3, "title": "$(touch /host)", "body": None}, "private-bearer", "endpoint", "model")
    commands.run.return_value = "checks passed\nFACTORY_VERIFY_EXIT=0\n"
    instance.verify()
    calls = commands.run.call_args_list
    assert [call.args[1] for call in calls] == ["required entrypoints", "setup", "implementation", "verification"]
    for call in calls:
        assert call.args[0][:6] == ["docker", "exec", "--user", str(os.getuid()), "-i", instance.project]
    assert calls[1].args[0][-1] == "./scripts/setup"
    implementation = calls[2]
    script = Path(__file__).resolve().parents[1] / "src/software_factory/sandbox_agent.py"
    assert script.is_file(), "Pi wrapper must be a standalone Python script"
    assert implementation.args[0][6:] == ["/usr/local/bin/python", "-I", "-c", script.read_text()]
    assert "private-bearer" not in " ".join(implementation.args[0])
    payload = json.loads(implementation.kwargs["input"])
    assert payload["snapshot"]["title"] == "$(touch /host)"
    assert payload["flags"] == PI_FLAGS
    assert payload["bearer"] == "private-bearer"


def test_failed_verification_preserves_redacted_feedback(sandbox) -> None:
    instance, commands = sandbox
    commands.run.return_value = "failed assertion\nprivate-bearer on stderr\n\nFACTORY_VERIFY_EXIT=8\n"
    with pytest.raises(VerificationFailed) as failure:
        instance.verify()
    assert failure.value.output == "failed assertion\n[REDACTED] on stderr\n"
    assert str(failure.value) == "verification failed"
    instance.implement({}, "private-bearer", "endpoint", "model", verification_output=failure.value.output)
    assert json.loads(commands.run.call_args.kwargs["input"])["verification_output"] == failure.value.output


@pytest.mark.parametrize("result", ["", "partial output", "\nFACTORY_VERIFY_EXIT=bad\n", "\nFACTORY_VERIFY_EXIT=256\n"])
def test_incomplete_verification_is_not_completed_failure(sandbox, result) -> None:
    instance, commands = sandbox
    commands.run.return_value = result
    with pytest.raises(FactoryError) as failure:
        instance.verify()
    assert not isinstance(failure.value, VerificationFailed)


def test_cleanup_uses_exact_labels_not_agent_compose_and_separate_budget(sandbox, monkeypatch) -> None:
    instance, commands = sandbox
    cleanup = Mock()
    cleanup.run.side_effect = lambda args, phase, **kwargs: (
        {"container": "container-id\n", "network": "network-id\n", "volume": "volume-name\n"}.get(args[1], "")
        if "ls" in args
        else ""
    )
    factory = Mock(return_value=cleanup)
    monkeypatch.setattr("software_factory.sandbox.Commands", factory)
    instance.stop()
    assert factory.call_args.kwargs["deadline"] > time.monotonic()
    assert factory.call_args.kwargs.get("log") is None  # broken diagnostic storage must not prevent engine cleanup
    assert cleanup.secrets == commands.secrets
    calls = cleanup.run.call_args_list
    args = [call.args[0] for call in calls]
    assert args[0] == ["docker", "container", "rm", "--force", instance.project]
    lists = [a for a in args if "ls" in a]
    assert len(lists) == 6
    assert all(
        any(
            f"label={label}={instance.project}" in a
            for label in ("software-factory.run-id", "com.docker.compose.project")
        )
        for a in lists
    )
    removals = [a for a in args if "rm" in a and a[-1] in {"container-id", "network-id", "volume-name"}]
    assert [a[1] for a in removals] == ["container", "network", "volume"]
    assert not any("compose" in a or "prune" in a for a in args)
    assert not any(call.args[1] == "workspace ownership" or call.args[0][1] == "run" for call in calls)


@pytest.mark.parametrize("kind,identity", [("container", "a" * 64), ("network", "b" * 64), ("volume", "owned-data")])
def test_failed_resource_removal_requires_confirmed_absence(sandbox, kind, identity) -> None:
    instance, _ = sandbox
    cleanup = Mock()
    cleanup.run.side_effect = [FactoryError("engine error"), identity + "\n"]
    with pytest.raises(FactoryError, match="cleanup"):
        instance.remove(cleanup, kind, identity)
    assert "absence" in cleanup.run.call_args.args[1]
    if kind in {"container", "network"}:
        assert "id=" + identity in cleanup.run.call_args.args[0]


@pytest.mark.parametrize(
    "phase",
    [
        "agent removal",
        "container discovery",
        "network discovery",
        "volume discovery",
        "container removal",
        "network removal",
        "volume removal",
    ],
)
def test_cleanup_failure_does_not_claim_success_or_broaden_scope(sandbox, monkeypatch, phase) -> None:
    instance, _ = sandbox
    cleanup = Mock()
    cleanup.run.return_value = ""
    monkeypatch.setattr("software_factory.sandbox.Commands", Mock(return_value=cleanup))

    def remove(commands, kind, identity):
        current = "agent removal" if identity == instance.project else kind + " removal"
        if phase == current:
            raise FactoryError(current + " failed")

    monkeypatch.setattr(instance, "remove", remove)

    def discover(commands, kind):
        if phase == kind + " discovery":
            raise FactoryError(phase + " failed")
        return {kind + "-id"}

    owned = Mock(side_effect=discover)
    monkeypatch.setattr(instance, "owned", owned)
    with pytest.raises(FactoryError):
        instance.stop()
    assert owned.call_count == 3
    assert not hasattr(instance, "restore_ownership")


def test_user_configuration_failure_never_falls_back_to_root(sandbox) -> None:
    instance, commands = sandbox
    commands.run.side_effect = ["", FactoryError("agent user configuration failed")]
    with pytest.raises(FactoryError, match="user configuration"):
        instance.start()
    assert len(commands.run.call_args_list) == 2


@pytest.mark.parametrize(
    "token",
    [
        "",
        "gho_refresh",
        "proxy-ep=attacker.com;exp=9999999999",
        "proxy-ep=proxy.business.githubcopilot.com;exp=1",
        pytest.param("proxy-ep=proxy.business.githubcopilot.com;exp=" + "9" * 400, id="overflow-expiry"),
        pytest.param("proxy-ep=proxy.business.githubcopilot.com;exp=" + "9" * 5000, id="oversized-expiry"),
    ],
)
def test_copilot_metadata_fails_closed(token: str) -> None:
    with pytest.raises(FactoryError, match="Copilot"):
        copilot_endpoint(token)


def test_copilot_endpoint_is_derived_and_lifetime_checked() -> None:
    token = f"tid=test;proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1300};sig=test"
    assert copilot_endpoint(token) == "https://api.business.githubcopilot.com"
