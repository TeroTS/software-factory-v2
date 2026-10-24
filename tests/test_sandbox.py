import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest


def compose(workspace: Path) -> dict:
    return {
        "name": "operator-name",
        "services": {
            "agent": {
                "image": "node:24-bookworm-slim",
                "working_dir": "/workspace",
                "volumes": [{"type": "bind", "source": str(workspace), "target": "/workspace"}],
            },
            "db": {"image": "postgres:17", "environment": {"POSTGRES_PASSWORD": "local-test"}},
        },
    }


def test_compose_preserves_dependencies_but_controls_lifecycle(tmp_path: Path) -> None:
    from software_factory.sandbox import prepare_compose

    original = compose(tmp_path)
    original["services"]["agent"]["depends_on"] = {"db": {"condition": "service_started", "required": True}}
    result = prepare_compose(original, "agent", tmp_path)
    assert "name" not in result
    assert result["services"]["db"]["image"] == "postgres:17"
    assert result["services"]["agent"]["entrypoint"] == ["sleep", "infinity"]
    assert result["services"]["agent"]["command"] == []
    for service in result["services"].values():
        assert service["restart"] == "no"
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]
    assert original["services"]["agent"].get("entrypoint") is None


@pytest.mark.parametrize(
    "patch",
    [
        {"privileged": True},
        {"pid": "host"},
        {"ipc": "host"},
        {"network_mode": "host"},
        {"devices": ["/dev/kvm"]},
        {"cap_add": ["SYS_ADMIN"]},
        {"volumes_from": ["other"]},
        {"build": {"context": "."}},
        {"container_name": "shared"},
        {"ports": ["5432:5432"]},
        {"environment": {"GH_TOKEN": "secret"}},
        {"environment": {"OPENAI_API_KEY": "secret"}},
        {"environment": {"PI_CODING_AGENT_DIR": "/workspace/.pi"}},
        {"volumes": [{"type": "bind", "source": "/var/run/docker.sock", "target": "/sock"}]},
        {"volumes": [{"type": "bind", "source": "/etc", "target": "/host"}]},
        {"volumes": [{"type": "volume", "source": "shared", "target": "/data"}]},
        {"security_opt": ["seccomp:unconfined"]},
        {"cgroup": "host"},
        {"restart": "always"},
        {"use_api_socket": True},
    ],
)
@pytest.mark.parametrize("service", ["agent", "db"])
def test_rejects_isolation_bypasses_in_every_service(tmp_path: Path, patch: dict, service: str) -> None:
    from software_factory.process import FactoryError
    from software_factory.sandbox import prepare_compose

    data = compose(tmp_path)
    data["services"][service].update(patch)
    with pytest.raises(FactoryError, match="Compose"):
        prepare_compose(data, "agent", tmp_path)


@pytest.mark.parametrize(
    "top",
    [
        {"secrets": {"auth": {"file": "/secret"}}},
        {"volumes": {"data": {"external": True}}},
        {"networks": {"default": {"external": True}}},
        {"networks": {"default": {"driver": "host"}}},
    ],
)
def test_rejects_external_resources(tmp_path: Path, top: dict) -> None:
    from software_factory.process import FactoryError
    from software_factory.sandbox import prepare_compose

    data = compose(tmp_path)
    data.update(top)
    with pytest.raises(FactoryError, match="Compose"):
        prepare_compose(data, "agent", tmp_path)


def test_requires_agent_and_workspace(tmp_path: Path) -> None:
    from software_factory.process import FactoryError
    from software_factory.sandbox import prepare_compose

    for service in ["missing", "db"]:
        with pytest.raises(FactoryError):
            prepare_compose(compose(tmp_path), service, tmp_path)


def test_ephemeral_anonymous_volumes_and_bridge_networks(tmp_path: Path) -> None:
    from software_factory.sandbox import prepare_compose

    data = compose(tmp_path)
    data["services"]["db"]["volumes"] = [{"type": "volume", "target": "/var/lib/postgresql/data"}]
    data["networks"] = {"default": {"name": "old_default", "ipam": {"driver": "default", "config": []}}}
    result = prepare_compose(data, "agent", tmp_path)
    assert "name" not in result["networks"]["default"]


def test_sandbox_runs_commands_with_snapshot_and_secret_only_on_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from software_factory.sandbox import PI_FLAGS, Sandbox

    commands = Mock()
    commands.run.return_value = "\nFACTORY_VERIFY_EXIT=0\n"
    sandbox = Sandbox(prepared_compose=compose(tmp_path), service="agent", directory=tmp_path, commands=commands)
    sandbox.start()
    sandbox.setup()
    sandbox.implement(
        {"number": 3, "title": "$(touch /host)", "body": "request"},
        "private-token-value",
        "https://api.business.githubcopilot.com",
        "model",
    )
    sandbox.verify()
    cleanup = Mock()
    monkeypatch.setattr("software_factory.sandbox.Commands", Mock(return_value=cleanup))
    sandbox.stop()
    assert "down" in cleanup.run.call_args.args[0]
    calls = commands.run.call_args_list
    phases = [call.args[1] for call in calls]
    assert phases == ["sandbox startup", "required entrypoints", "setup", "implementation", "verification"]
    implementation = calls[3]
    assert "private-token-value" not in " ".join(implementation.args[0])
    payload = json.loads(implementation.kwargs["input"])
    assert payload["snapshot"]["title"] == "$(touch /host)"
    assert payload["flags"] == PI_FLAGS
    assert calls[2].args[0][-1] == "./scripts/setup"
    assert "./scripts/verify" in calls[4].args[0][-1]
    assert (tmp_path / "compose.json").exists()


def test_failed_verification_supplies_redacted_stdout_and_stderr_for_repair(tmp_path: Path) -> None:
    from software_factory.sandbox import Sandbox, VerificationFailed

    commands = Mock()
    commands.secrets = ["private-bearer"]
    commands.run.return_value = "failed assertion\nprivate-bearer on stderr\n\nFACTORY_VERIFY_EXIT=8\n"
    sandbox = Sandbox(compose(tmp_path), "agent", tmp_path, commands)
    with pytest.raises(VerificationFailed) as failure:
        sandbox.verify()
    assert failure.value.output == "failed assertion\n[REDACTED] on stderr\n"
    assert "failed assertion" not in str(failure.value)
    assert "private-bearer" not in str(failure.value)
    sandbox.implement({"number": 1}, "private-bearer", "endpoint", "model", verification_output=failure.value.output)
    payload = json.loads(commands.run.call_args.kwargs["input"])
    assert payload["verification_output"] == failure.value.output
    assert commands.run.call_args.args[1] == "repair"
    assert failure.value.output not in " ".join(commands.run.call_args.args[0])


@pytest.mark.parametrize(
    "result",
    [
        "",
        "partial output",
        "\nFACTORY_VERIFY_EXIT=not-a-number\n",
        "\nFACTORY_VERIFY_EXIT=256\n",
    ],
)
def test_incomplete_verification_result_is_not_a_repairable_failure(tmp_path: Path, result: str) -> None:
    from software_factory.process import FactoryError
    from software_factory.sandbox import Sandbox, VerificationFailed

    commands = Mock()
    commands.run.return_value = result
    commands.secrets = []
    sandbox = Sandbox(compose(tmp_path), "agent", tmp_path, commands)
    with pytest.raises(FactoryError) as failure:
        sandbox.verify()
    assert not isinstance(failure.value, VerificationFailed)


@pytest.mark.parametrize(
    "token",
    ["", "gho_oauth-token", "proxy-ep=attacker.com;exp=9999999999", "proxy-ep=proxy.business.githubcopilot.com;exp=1"],
)
def test_copilot_metadata_fails_closed(token: str) -> None:
    from software_factory.process import FactoryError
    from software_factory.sandbox import copilot_endpoint

    with pytest.raises(FactoryError, match="Copilot"):
        copilot_endpoint(token)


def test_copilot_endpoint_is_derived_and_lifetime_checked() -> None:
    from software_factory.sandbox import copilot_endpoint

    token = f"tid=test;proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1300};sig=test"
    assert copilot_endpoint(token) == "https://api.business.githubcopilot.com"
